"""Program-first workflow routing and deterministic field binding."""

from __future__ import annotations

import re
from dataclasses import dataclass

from plotagent.contracts.workflows import (
    ConcatenateSources,
    DraftFieldBinding,
    DraftSetTitle,
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

from .natural_language import ExplicitGoal, parse_explicit_goal
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

_EXPLICIT_ROLE_LABELS: dict[str, tuple[str, ...]] = {
    "x_err_minus": ("x_err_minus", "x_lower"),
    "x_err_plus": ("x_err_plus", "x_upper"),
    "y_err_minus": ("y_err_minus", "lower", "y_lower"),
    "y_err_plus": ("y_err_plus", "upper", "y_upper"),
}

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
        if context.selected_plot_aliases:
            return self._resolve_edit(context)
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
        if len(context.selected_source_aliases) > 1 and self._concat_requested(context):
            return self._resolve_concat(context, profile.profile_id)
        batch = len(context.selected_source_aliases) > 1 and any(
            token in context.instruction.casefold()
            for token in ("批量", "分别", "每个", "each", "batch")
        )
        if len(context.selected_source_aliases) > 1 and not batch:
            return None
        token = context.workflow_run_id.removeprefix("workflow:")
        items: list[TaskDraftItem] = []
        goal_constraints: set[str] = set()
        batch_titles = self._batch_titles(context.instruction, len(context.selected_source_aliases))
        for position, source_alias in enumerate(context.selected_source_aliases, start=1):
            fields = tuple(field for field in context.fields if field.source_alias == source_alias)
            bindings = self._bindings(
                profile.required_roles,
                profile.optional_roles,
                fields,
                source_alias,
                context.instruction,
            )
            if bindings is None:
                return None
            goal = (
                ExplicitGoal(
                    visual_actions=(DraftSetTitle(text=batch_titles[position - 1]),),
                    hard_constraints=("preserve_explicit_visual_parameters",),
                )
                if batch_titles is not None
                else parse_explicit_goal(context, source_alias=source_alias)
            )
            if goal is None:
                return None
            goal_constraints.update(goal.hard_constraints)
            items.append(
                TaskDraftItem(
                    task_kind="create",
                    item_id=f"item:{token}.{position}",
                    plot_alias=f"plot_{position}",
                    profile_id=profile.profile_id,
                    source_aliases=(source_alias,),
                    data_operations=goal.data_operations,
                    bindings=bindings,
                    visual_actions=goal.visual_actions,
                )
            )
        draft = TaskDraft(
            draft_id=f"draft:{token}",
            workflow_run_id=context.workflow_run_id,
            route="deterministic",
            summary=f"使用 {profile.display_name} 创建 {len(items)} 张图",
            items=tuple(items),
            confidence=1.0,
            hard_constraints=(
                "preserve_source_values",
                "require_confirmation",
                *sorted(goal_constraints),
            ),
        )
        return WorkflowDraftReady(draft=draft)

    @staticmethod
    def _concat_requested(context: WorkflowContext) -> bool:
        text = context.instruction.casefold()
        return any(token in text for token in ("纵向拼接", "拼接", "concatenate")) and any(
            token in text for token in ("同一张", "一张", "same plot")
        )

    @staticmethod
    def _batch_titles(instruction: str, count: int) -> tuple[str, ...] | None:
        if count != 2:
            return None
        matched = re.search(
            r"标题分别(?:设)?为\s*([^，,；;。]+?)\s*(?:和|与)\s*([^，,；;。]+)",
            instruction,
        )
        if matched is None:
            return None
        return matched.group(1).strip(), matched.group(2).strip()

    def _resolve_concat(
        self,
        context: WorkflowContext,
        profile_id: str,
    ) -> WorkflowDecision | None:
        aliases = context.selected_source_aliases
        signatures = []
        for source_alias in aliases:
            signatures.append(
                tuple(
                    (field.name.casefold(), field.logical_type)
                    for field in context.fields
                    if field.source_alias == source_alias
                )
            )
        if not signatures or len(set(signatures)) != 1:
            return None
        profile = self._catalog.get(profile_id)
        first = aliases[0]
        fields = tuple(field for field in context.fields if field.source_alias == first)
        bindings = self._bindings(
            profile.required_roles,
            profile.optional_roles,
            fields,
            first,
            context.instruction,
        )
        if bindings is None:
            return None
        if "label" in profile.optional_roles:
            bindings = (
                *bindings,
                DraftFieldBinding(
                    role="label",
                    source_alias=first,
                    field_alias="source_group",
                ),
            )
        token = context.workflow_run_id.removeprefix("workflow:")
        draft = TaskDraft(
            draft_id=f"draft:{token}",
            workflow_run_id=context.workflow_run_id,
            route="deterministic",
            summary=f"拼接 {len(aliases)} 个同构数据表并创建 {profile.display_name}",
            items=(
                TaskDraftItem(
                    task_kind="create",
                    item_id=f"item:{token}.1",
                    plot_alias="plot_1",
                    profile_id=profile_id,
                    source_aliases=aliases,
                    data_operations=(
                        ConcatenateSources(
                            source_aliases=aliases,
                            source_label_field="source_group",
                        ),
                    ),
                    bindings=bindings,
                ),
            ),
            confidence=1,
            hard_constraints=(
                "preserve_source_values",
                "preserve_source_identity",
                "require_confirmation",
            ),
        )
        return WorkflowDraftReady(draft=draft)

    @staticmethod
    def _resolve_edit(context: WorkflowContext) -> WorkflowDecision | None:
        if len(context.selected_plot_aliases) != 1:
            return None
        target_alias = context.selected_plot_aliases[0]
        target = next((plot for plot in context.plots if plot.plot_alias == target_alias), None)
        if target is None:
            return None
        goal = parse_explicit_goal(context, source_alias=None)
        if goal is None or not goal.visual_actions or goal.data_operations:
            return None
        token = context.workflow_run_id.removeprefix("workflow:")
        draft = TaskDraft(
            draft_id=f"draft:{token}",
            workflow_run_id=context.workflow_run_id,
            route="deterministic",
            summary=f"修改 {target.profile_id} 图形",
            items=(
                TaskDraftItem(
                    task_kind="edit",
                    item_id=f"item:{token}.1",
                    plot_alias="plot_1",
                    profile_id=target.profile_id,
                    target_plot_alias=target_alias,
                    visual_actions=goal.visual_actions,
                ),
            ),
            confidence=1.0,
            hard_constraints=("require_confirmation", *goal.hard_constraints),
        )
        return WorkflowDraftReady(draft=draft)

    @staticmethod
    def _bindings(
        required_roles: tuple[str, ...],
        optional_roles: tuple[str, ...],
        fields: tuple[WorkflowField, ...],
        source_alias: str,
        instruction: str,
    ) -> tuple[DraftFieldBinding, ...] | None:
        explicit: dict[str, WorkflowField] = {}
        all_roles = (*required_roles, *optional_roles)
        for role in all_roles:
            for field in fields:
                field_name = re.escape(field.name)
                for role_label in _EXPLICIT_ROLE_LABELS.get(role, (role,)):
                    role_name = re.escape(role_label)
                    if re.search(
                    rf"(?:(?<!\w){field_name}(?!\w)\s*(?:映射|→|->|=|作为|为)\s*"
                        rf"(?<!\w){role_name}(?!\w)"
                        rf"|(?<!\w){role_name}(?!\w)\s*(?:映射|→|->|=|作为|为)\s*"
                        rf"(?<!\w){field_name}(?!\w))",
                        instruction,
                        flags=re.IGNORECASE,
                    ):
                        explicit[role] = field
                        break
                if role in explicit:
                    break
        used: set[str] = set()
        bindings: list[DraftFieldBinding] = []
        for role in required_roles:
            if role in explicit:
                field = explicit[role]
                if field.field_alias in used:
                    return None
                used.add(field.field_alias)
                bindings.append(
                    DraftFieldBinding(
                        role=role,
                        source_alias=source_alias,
                        field_alias=field.field_alias,
                    )
                )
                continue
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
        for role in optional_roles:
            optional_field = explicit.get(role)
            if optional_field is None:
                continue
            if optional_field.field_alias in used:
                return None
            used.add(optional_field.field_alias)
            bindings.append(
                DraftFieldBinding(
                    role=role,
                    source_alias=source_alias,
                    field_alias=optional_field.field_alias,
                )
            )
        return tuple(bindings)


class WorkflowRouter:
    """Choose the cheapest level that can still satisfy the requested goal."""

    def __init__(self, catalog: EngineCatalog) -> None:
        self._deterministic = DeterministicResolver(catalog)

    def route(self, context: WorkflowContext) -> RouteDecision:
        deterministic = self._deterministic.resolve(context)
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
