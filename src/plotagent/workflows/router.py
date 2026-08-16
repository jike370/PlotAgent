"""Program-first workflow routing and deterministic field binding."""

from __future__ import annotations

import re
from dataclasses import dataclass

from plotagent.contracts.workflows import (
    DraftFieldBinding,
    InputQuestion,
    TaskDraft,
    TaskDraftItem,
    WorkflowContext,
    WorkflowDecision,
    WorkflowDraftReady,
    WorkflowField,
    WorkflowNeedsInput,
    WorkflowRoute,
)
from plotagent.engine import EngineCatalog

from .profiles import explicit_profile_ids, unspecified_chart_request

_NON_NUMERIC_ROLES = frozenset(
    {
        "actual",
        "category",
        "column",
        "event",
        "facet",
        "feature",
        "group",
        "label",
        "panel",
        "predicted",
        "row",
        "series",
        "time",
    }
)

_AGENT_GOAL_DETAIL = re.compile(
    r"(?:"
    r"标题|颜色|色板|填充|边框|线宽|虚线|点线|点划线|实线|"
    r"符号|点大小|符号大小|透明|图例|字体|字号|加粗|旋转|"
    r"网格|刻度|坐标范围|轴范围|对数|log10|反向|数据标签|"
    r"端帽|注释|参考线|中点|筛选|过滤|排序|宽转长|长转宽|"
    r"拼接|合并|只保留|排除|剔除|#[0-9a-fA-F]{6}"
    r")"
)


def _needs_agent_interpretation(instruction: str) -> bool:
    """Keep the cheap route from silently discarding requested work.

    The deterministic resolver currently owns chart/field binding only.  Any
    visible style request or closed data operation must therefore be translated
    into a TaskDraft by Pi instead of being accepted as a bare create request.
    """

    return _AGENT_GOAL_DETAIL.search(instruction) is not None


@dataclass(frozen=True, slots=True)
class RouteDecision:
    route: WorkflowRoute
    reason: str
    deterministic: WorkflowDecision | None = None


def _normalized_tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in re.split(r"[^\w\u4e00-\u9fff]+", value.casefold()) if token)


def _role_tokens(role: str) -> tuple[str, ...]:
    aliases: dict[str, tuple[str, ...]] = {
        "x": ("x", "time", "时间", "横轴"),
        "y": ("y", "value", "值", "纵轴"),
        "time": ("time", "date", "timestamp", "时间", "日期"),
        "category": ("category", "class", "类别", "分类"),
        "group": ("group", "condition", "组", "分组"),
        "label": ("label", "name", "subject", "标签", "名称", "样本"),
        "row": ("row", "actual", "行"),
        "column": ("column", "predicted", "列"),
        "actual": ("actual", "真实", "实际"),
        "predicted": ("predicted", "预测"),
        "value": ("value", "response", "measurement", "值", "数值"),
        "count": ("count", "frequency", "计数", "频数"),
    }
    if role.startswith("series_"):
        return (role, role.removeprefix("series_"), "series", "value", "系列")
    return aliases.get(role, (role,))


def _field_score(role: str, name: str, logical_type: str, ordinal: int) -> int | None:
    if role == "time" and logical_type != "datetime":
        return None
    if (
        role not in _NON_NUMERIC_ROLES
        and not role.startswith("series_")
        and logical_type != "numeric"
    ):
        return None
    if role.startswith("series_") and logical_type != "numeric":
        return None
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", name.casefold())
    score = 0
    for token in _role_tokens(role):
        folded = re.sub(r"[^\w\u4e00-\u9fff]+", "", token.casefold())
        if normalized == folded:
            score = max(score, 100)
        elif folded and folded in normalized:
            score = max(score, 70)
    if role == "x" and ordinal == 0:
        score = max(score, 20)
    if role == "y" and ordinal == 1:
        score = max(score, 20)
    if role.startswith("series_"):
        wanted = int(role.removeprefix("series_"))
        if ordinal == wanted - 1:
            score = max(score, 15)
    if logical_type in {"categorical", "text"} and role in _NON_NUMERIC_ROLES:
        score += 5
    return score


class DeterministicResolver:
    """Resolve only high-confidence chart/source/field instructions without a model."""

    def __init__(self, catalog: EngineCatalog) -> None:
        self._catalog = catalog

    def resolve(self, context: WorkflowContext) -> WorkflowDecision | None:
        # Existing plot edits require interpreting the requested visual change;
        # they are never mistaken for a new-plot request.
        if context.selected_plot_aliases:
            return None
        profile_ids = explicit_profile_ids(context.instruction, context.allowed_profile_ids)
        if not profile_ids and len(context.selected_profile_ids) == 1:
            profile_ids = context.selected_profile_ids
        if not profile_ids:
            if unspecified_chart_request(context.instruction) or context.sources:
                return WorkflowNeedsInput(
                    workflow_run_id=context.workflow_run_id,
                    questions=(
                        InputQuestion(
                            question_key="chart_type",
                            prompt="请选择要创建的图形类型。",
                            answer_kind="profile",
                        ),
                    ),
                )
            return None
        if len(profile_ids) != 1:
            return None
        profile = self._catalog.get(profile_ids[0])
        if not context.selected_source_aliases:
            return WorkflowNeedsInput(
                workflow_run_id=context.workflow_run_id,
                questions=(
                    InputQuestion(
                        question_key="source_data",
                        prompt="请选择包含绘图数据的数据表。",
                        answer_kind="single_choice",
                    ),
                ),
            )
        batch = len(context.selected_source_aliases) > 1 and any(
            token in context.instruction.casefold()
            for token in ("批量", "分别", "每个", "each", "batch")
        )
        if len(context.selected_source_aliases) > 1 and not batch:
            return None
        token = context.workflow_run_id.removeprefix("workflow:")
        items: list[TaskDraftItem] = []
        for position, source_alias in enumerate(context.selected_source_aliases, start=1):
            fields = tuple(field for field in context.fields if field.source_alias == source_alias)
            bindings = self._bindings(profile.required_roles, fields, source_alias)
            if bindings is None:
                return None
            items.append(
                TaskDraftItem(
                    task_kind="create",
                    item_id=f"item:{token}.{position}",
                    plot_alias=f"plot_{position}",
                    profile_id=profile.profile_id,
                    source_aliases=(source_alias,),
                    bindings=bindings,
                )
            )
        draft = TaskDraft(
            draft_id=f"draft:{token}",
            workflow_run_id=context.workflow_run_id,
            route="deterministic",
            summary=f"使用 {profile.display_name} 创建 {len(items)} 张图",
            items=tuple(items),
            confidence=1.0,
            hard_constraints=("preserve_source_values", "require_confirmation"),
        )
        return WorkflowDraftReady(draft=draft)

    @staticmethod
    def _bindings(
        required_roles: tuple[str, ...],
        fields: tuple[WorkflowField, ...],
        source_alias: str,
    ) -> tuple[DraftFieldBinding, ...] | None:
        used: set[str] = set()
        bindings: list[DraftFieldBinding] = []
        for role in required_roles:
            candidates = sorted(
                (
                    (score, index, field)
                    for index, field in enumerate(fields)
                    if field.field_alias not in used
                    and (score := _field_score(role, field.name, field.logical_type, index))
                    is not None
                ),
                key=lambda item: (-item[0], item[1]),
            )
            if not candidates or candidates[0][0] < 15:
                return None
            if len(candidates) > 1 and candidates[0][0] == candidates[1][0] < 70:
                return None
            field = candidates[0][2]
            used.add(field.field_alias)
            bindings.append(
                DraftFieldBinding(
                    role=role,
                    source_alias=source_alias,
                    field_alias=field.field_alias,
                )
            )
        return tuple(bindings)


class WorkflowRouter:
    """Choose the cheapest level that can still satisfy the requested goal."""

    def __init__(self, catalog: EngineCatalog) -> None:
        self._deterministic = DeterministicResolver(catalog)

    def route(self, context: WorkflowContext) -> RouteDecision:
        deterministic = (
            None
            if _needs_agent_interpretation(context.instruction)
            else self._deterministic.resolve(context)
        )
        if deterministic is not None:
            route: WorkflowRoute = (
                "deterministic" if deterministic.outcome == "draft_ready" else "needs_input"
            )
            return RouteDecision(route, "local resolver completed the request", deterministic)
        explicit_profiles = explicit_profile_ids(context.instruction, context.allowed_profile_ids)
        mentions_multiple_sources = len(context.selected_source_aliases) > 1
        mentions_batch = any(
            token in context.instruction.casefold()
            for token in ("批量", "分别", "每个", "each", "batch")
        )
        if context.budget.max_agent_turns == 0:
            return RouteDecision("needs_input", "the workflow budget forbids model use")
        if mentions_multiple_sources or mentions_batch or len(explicit_profiles) > 1:
            return RouteDecision("agent_exploration", "the goal requires source/task decomposition")
        return RouteDecision("agent_single_turn", "one bounded model turn can resolve aliases")
