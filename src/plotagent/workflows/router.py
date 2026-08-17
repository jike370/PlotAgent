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
    WorkflowUnsupported,
)
from plotagent.engine import EngineCatalog, EngineProfile

from .natural_language import ExplicitGoal, parse_explicit_goal
from .profiles import explicit_profile_ids, profile_mentions, unspecified_chart_request

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

_OPTIONAL_ROLE_LABELS: dict[str, tuple[str, ...]] = {
    "group": ("group", "分组"),
    "label": ("label", "标签", "subject", "样本"),
    "size": ("size", "大小"),
    "color": ("color", "颜色"),
    "count": ("count", "计数", "频数"),
}

_BINDING_OPERATOR = r"(?:映射(?:为|到)?|绑定(?:为|到)?|→|->|=|作为|设为|为)"
_FIELD_DESCRIPTOR = r"(?:\s*(?:字段|列))?"


def _binding_expression(field_name: str, role_label: str) -> str:
    """Return the shared explicit-binding grammar.

    Users commonly say ``Y 字段映射为 value`` rather than ``Y 映射为
    value``.  Every binding gate must recognize the same optional descriptor;
    otherwise the ambiguity gate and the actual binder disagree and a closed
    request is needlessly sent to the model.
    """

    return (
        rf"(?:(?<!\w){field_name}{_FIELD_DESCRIPTOR}\s*{_BINDING_OPERATOR}\s*"
        rf"(?<!\w){role_label}(?!\w)"
        rf"|(?<!\w){role_label}{_FIELD_DESCRIPTOR}\s*{_BINDING_OPERATOR}\s*"
        rf"(?<!\w){field_name}(?!\w))"
    )


def _unsupported_t1_boundary(instruction: str) -> tuple[str, str] | None:
    """Reject capabilities outside the T1 product before any model call."""

    if re.search(
        r"(?:四宫格|九宫格|多面板|组合图|拼图|合并(?:成|为)?(?:一张)?组合)"
        r"|(?:显微镜|医学|遥感)?(?:图片|图像)(?:生成|处理|分割|识别)?"
        r"|生成(?:一张|一个)?(?:图片|图像)",
        instruction,
        flags=re.IGNORECASE,
    ):
        return (
            "T1_SCOPE_COMPOSITION_OR_IMAGE",
            "当前版本只执行单张 T1 数据图，不提供组合图、拼图或图像生成。",
        )
    if re.search(
        r"(?:回归|拟合|聚类|统计检验|显著性检验|预测模型|机器学习)"
        r"|(?:编写|运行|执行|生成)(?:\s*Python|\s*SQL|\s*R\s|代码|脚本)",
        instruction,
        flags=re.IGNORECASE,
    ):
        return (
            "T1_SCOPE_ANALYSIS_OR_CODE",
            "当前版本只执行 T1 绘图和视觉编辑，不运行分析、拟合或代码。",
        )
    return None


def _vague_visual_request(instruction: str) -> bool:
    normalized = re.sub(r"[\s，,。.!！?？]", "", instruction.casefold())
    return normalized in {
        "美化",
        "美化一下",
        "优化",
        "优化一下",
        "好看一点",
        "改好看一点",
        "调整样式",
        "优化样式",
    }

@dataclass(frozen=True, slots=True)
class RouteDecision:
    route: WorkflowRoute
    reason: str
    deterministic: WorkflowDecision | None = None


@dataclass(frozen=True, slots=True)
class _SourceMention:
    source_alias: str
    start: int
    end: int


def _source_mentions(context: WorkflowContext) -> tuple[_SourceMention, ...]:
    """Resolve stable UI source references without asking the model to guess."""

    text = context.instruction
    candidates: list[_SourceMention] = []
    for ordinal, source in enumerate(context.sources, start=1):
        letter = chr(ord("A") + ordinal - 1)
        labels = {
            source.source_alias,
            f"数据{letter}",
            f"数据 {letter}",
            f"data {letter}",
            f"data{letter}",
            source.display_name,
        }
        # A sheet or block name on its own is not a safe source identifier:
        # names such as "K19" are also chart IDs.  Keep the complete
        # "file > sheet" identity and the file portion, but never register the
        # trailing sheet/block as an independent alias.
        source_head = re.split(r"\s*>\s*|:", source.display_name, maxsplit=1)[0].strip()
        if source_head:
            labels.add(source_head)
            basename = re.split(r"[\\/]", source_head)[-1].strip()
            if basename:
                labels.add(basename)
        for label in labels:
            for matched in re.finditer(re.escape(label), text, flags=re.IGNORECASE):
                candidates.append(
                    _SourceMention(source.source_alias, matched.start(), matched.end())
                )
    mentions: list[_SourceMention] = []
    used_sources: set[str] = set()
    occupied: list[tuple[int, int]] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (item.start, -(item.end - item.start), item.source_alias),
    ):
        if candidate.source_alias in used_sources:
            continue
        same_span = {
            item.source_alias
            for item in candidates
            if item.start == candidate.start and item.end == candidate.end
        }
        if len(same_span) > 1:
            continue
        if any(
            candidate.start < used_end and candidate.end > used_start
            for used_start, used_end in occupied
        ):
            continue
        mentions.append(candidate)
        used_sources.add(candidate.source_alias)
        occupied.append((candidate.start, candidate.end))
    return tuple(mentions)


def _selected_sources_in_goal(context: WorkflowContext) -> tuple[str, ...]:
    named = tuple(item.source_alias for item in _source_mentions(context))
    return named or context.selected_source_aliases


def named_source_aliases(context: WorkflowContext) -> tuple[str, ...]:
    """Return only sources explicitly named in the user's instruction."""

    return tuple(item.source_alias for item in _source_mentions(context))


def _requested_source_labels(
    context: WorkflowContext,
    source_aliases: tuple[str, ...],
) -> tuple[str, ...]:
    """Resolve explicit series labels without exposing internal source aliases."""

    patterns = (
        r"(?:保留|使用|采用)\s*(?P<labels>.+?)\s*(?:数据)?来源身份作为系列名称",
        r"系列名称(?:分别)?(?:使用|为|设为|命名为)\s*(?P<labels>[^。；;]+)",
    )
    for pattern in patterns:
        matched = re.search(pattern, context.instruction, flags=re.IGNORECASE)
        if matched is None:
            continue
        labels = tuple(
            label.strip().strip('"\'“”‘’')
            for label in re.split(r"\s*(?:[、,，/；;]|\b(?:and|和)\b)\s*", matched.group("labels"))
            if label.strip().strip('"\'“”‘’')
        )
        unique_labels = {label.casefold() for label in labels}
        if len(labels) == len(source_aliases) and len(unique_labels) == len(labels):
            return labels
    return ()


def _has_create_intent(text: str) -> bool:
    return re.search(
        r"画|绘制|绘图|作图|创建|生成|重试|retry|映射|作为|→|->|横轴|纵轴|x\s*=|y\s*=",
        text,
        flags=re.IGNORECASE,
    ) is not None


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
        boundary = _unsupported_t1_boundary(context.instruction)
        if boundary is not None:
            reason_code, message = boundary
            return WorkflowUnsupported(
                workflow_run_id=context.workflow_run_id,
                reason_code=reason_code,
                message=message,
            )
        mentions = profile_mentions(context.instruction, context.allowed_profile_ids)
        if context.selected_plot_aliases and not (
            mentions and _has_create_intent(context.instruction)
        ):
            return self._resolve_edit(context)
        profile_ids = tuple(dict.fromkeys(item[0] for item in mentions))
        if len({item[0] for item in mentions}) > 1:
            heterogeneous = self._resolve_heterogeneous(context, mentions)
            if heterogeneous is not None:
                return heterogeneous
        if (
            not profile_ids
            and len(context.selected_profile_ids) == 1
            and _has_create_intent(context.instruction)
        ):
            profile_ids = context.selected_profile_ids
        if not profile_ids:
            if unspecified_chart_request(context.instruction) or context.sources:
                if not _has_create_intent(context.instruction):
                    return WorkflowUnsupported(
                        workflow_run_id=context.workflow_run_id,
                        reason_code="CAPABILITY_UNAVAILABLE",
                        message="当前请求不能编译为 T1 绘图或视觉编辑动作。",
                    )
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
        source_aliases = _selected_sources_in_goal(context)
        if not source_aliases:
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
        if len(source_aliases) > 1 and self._concat_requested(context):
            return self._resolve_concat(context, profile.profile_id, source_aliases)
        batch = len(source_aliases) > 1 and any(
            token in context.instruction.casefold()
            for token in ("批量", "分别", "每个", "each", "batch")
        )
        if len(source_aliases) > 1 and not batch:
            return None
        token = context.workflow_run_id.removeprefix("workflow:")
        items: list[TaskDraftItem] = []
        goal_constraints: set[str] = set()
        batch_titles = self._batch_titles(context.instruction, len(source_aliases))
        for position, source_alias in enumerate(source_aliases, start=1):
            fields = tuple(field for field in context.fields if field.source_alias == source_alias)
            ambiguity = self._binding_ambiguity(
                profile.required_roles,
                fields,
                context.instruction,
            )
            if ambiguity is not None:
                return WorkflowNeedsInput(
                    workflow_run_id=context.workflow_run_id,
                    questions=(ambiguity,),
                )
            unsupported_role = self._unsupported_explicit_role(profile, fields, context.instruction)
            if unsupported_role is not None:
                return WorkflowUnsupported(
                    workflow_run_id=context.workflow_run_id,
                    reason_code="ROLE_UNAVAILABLE",
                    message=(
                        f"{profile.display_name} 不支持字段角色 {unsupported_role}；"
                        "请更换图类或移除该绑定。"
                    ),
                )
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
        same_plot = any(
            token in text
            for token in (
                "同一张",
                "同一幅",
                "一张图中",
                "一幅图中",
                "画在一起",
                "绘制在一起",
                "各作为一条",
                "每个数据一条",
                "same plot",
                "same chart",
            )
        )
        # Naming a single target chart is already an explicit multi-source
        # intent.  Requiring a second word such as "拼接" or "一起" sent the
        # common instruction "把三个数据表画在同一张图中" to the model even
        # though the selected sources and chart make the operation closed and
        # deterministic.
        return same_plot

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

    def _resolve_heterogeneous(
        self,
        context: WorkflowContext,
        mentions: tuple[tuple[str, int, int], ...],
    ) -> WorkflowDecision | None:
        source_mentions = _source_mentions(context)
        assignments: list[tuple[str, str, str]] = []
        used_sources: set[str] = set()
        separators = re.compile(r"[，,；;。\n、]")
        for profile_id, start, end in mentions:
            previous = tuple(separators.finditer(context.instruction[:start]))
            following = separators.search(context.instruction, end)
            clause_start = previous[-1].end() if previous else 0
            clause_end = following.start() if following is not None else len(context.instruction)
            clause = context.instruction[clause_start:clause_end].strip()
            in_clause = tuple(
                item
                for item in source_mentions
                if clause_start <= item.start and item.end <= clause_end
                and item.source_alias not in used_sources
            )
            if len(in_clause) == 1:
                source_alias = in_clause[0].source_alias
            else:
                candidates = tuple(
                    item for item in source_mentions if item.source_alias not in used_sources
                )
                if not candidates:
                    return None
                source_alias = min(
                    candidates,
                    key=lambda item: min(abs(item.end - start), abs(item.start - end)),
                ).source_alias
            used_sources.add(source_alias)
            assignments.append((source_alias, profile_id, clause))
        if len(assignments) != len(mentions) or len(used_sources) != len(assignments):
            return None

        token = context.workflow_run_id.removeprefix("workflow:")
        items: list[TaskDraftItem] = []
        constraints: set[str] = set()
        for position, (source_alias, profile_id, clause) in enumerate(assignments, start=1):
            profile = self._catalog.get(profile_id)
            fields = tuple(field for field in context.fields if field.source_alias == source_alias)
            ambiguity = self._binding_ambiguity(profile.required_roles, fields, clause)
            if ambiguity is not None:
                return WorkflowNeedsInput(
                    workflow_run_id=context.workflow_run_id,
                    questions=(ambiguity,),
                )
            unsupported_role = self._unsupported_explicit_role(profile, fields, clause)
            if unsupported_role is not None:
                return WorkflowUnsupported(
                    workflow_run_id=context.workflow_run_id,
                    reason_code="ROLE_UNAVAILABLE",
                    message=f"{profile.display_name} 不支持字段角色 {unsupported_role}。",
                )
            bindings = self._bindings(
                profile.required_roles,
                profile.optional_roles,
                fields,
                source_alias,
                clause,
            )
            if bindings is None:
                return None
            clause_context = context.model_copy(update={"instruction": clause})
            goal = parse_explicit_goal(clause_context, source_alias=source_alias)
            if goal is None:
                return None
            constraints.update(goal.hard_constraints)
            items.append(
                TaskDraftItem(
                    task_kind="create",
                    item_id=f"item:{token}.{position}",
                    plot_alias=f"plot_{position}",
                    profile_id=profile_id,
                    source_aliases=(source_alias,),
                    data_operations=goal.data_operations,
                    bindings=bindings,
                    visual_actions=goal.visual_actions,
                )
            )
        return WorkflowDraftReady(
            draft=TaskDraft(
                draft_id=f"draft:{token}",
                workflow_run_id=context.workflow_run_id,
                route="deterministic",
                summary=f"创建 {len(items)} 个数据—图类独立任务",
                items=tuple(items),
                confidence=1,
                hard_constraints=(
                    "preserve_source_values",
                    "preserve_source_identity",
                    "require_confirmation",
                    *sorted(constraints),
                ),
            )
        )

    @staticmethod
    def _field_is_explicit_for_role(
        role: str,
        field: WorkflowField,
        instruction: str,
    ) -> bool:
        labels = tuple(
            dict.fromkeys((role, *_EXPLICIT_ROLE_LABELS.get(role, ()), *_role_tokens(role)))
        )
        field_name = re.escape(field.name)
        return any(
            re.search(
                _binding_expression(field_name, re.escape(label)),
                instruction,
                flags=re.IGNORECASE,
            )
            is not None
            for label in labels
        )

    @classmethod
    def _binding_ambiguity(
        cls,
        required_roles: tuple[str, ...],
        fields: tuple[WorkflowField, ...],
        instruction: str,
    ) -> InputQuestion | None:
        for role in required_roles:
            if any(cls._field_is_explicit_for_role(role, field, instruction) for field in fields):
                continue
            candidates = tuple(
                field
                for index, field in enumerate(fields)
                if (score := _field_score(role, field.name, field.logical_type, index)) is not None
                and score >= 70
            )
            if len(candidates) > 1:
                return InputQuestion(
                    question_key=f"field_{role}",
                    prompt=f"字段角色 {role} 有多个候选，请明确选择。",
                    answer_kind="field",
                    choices=tuple(field.name for field in candidates[:24]),
                )
        return None

    @classmethod
    def _unsupported_explicit_role(
        cls,
        profile: EngineProfile,
        fields: tuple[WorkflowField, ...],
        instruction: str,
    ) -> str | None:
        allowed = set(profile.required_roles + profile.optional_roles)
        for role, labels in _OPTIONAL_ROLE_LABELS.items():
            if role in allowed:
                continue
            for field in fields:
                field_name = re.escape(field.name)
                if any(
                    re.search(
                        _binding_expression(field_name, re.escape(label)),
                        instruction,
                        flags=re.IGNORECASE,
                    )
                    is not None
                    for label in labels
                ):
                    return role
        return None

    def _resolve_concat(
        self,
        context: WorkflowContext,
        profile_id: str,
        aliases: tuple[str, ...],
    ) -> WorkflowDecision | None:
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
            return WorkflowUnsupported(
                workflow_run_id=context.workflow_run_id,
                reason_code="MULTI_SOURCE_SCHEMA_MISMATCH",
                message="同一张图中的多个数据表必须具有相同字段名称和类型。",
            )
        profile = self._catalog.get(profile_id)
        if "group" not in profile.optional_roles:
            return WorkflowUnsupported(
                workflow_run_id=context.workflow_run_id,
                reason_code="MULTI_SOURCE_PROFILE_UNSUPPORTED",
                message=(
                    f"{profile.display_name} 当前不支持把多个数据表"
                    "作为独立系列绘制在同一张图中。"
                ),
            )
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
        bindings = (
            *bindings,
            DraftFieldBinding(
                role="group",
                source_alias=first,
                field_alias="source_group",
            ),
        )
        source_labels = _requested_source_labels(context, aliases)
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
                            source_labels=source_labels,
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
        if _vague_visual_request(context.instruction):
            return WorkflowNeedsInput(
                workflow_run_id=context.workflow_run_id,
                questions=(
                    InputQuestion(
                        question_key="visual_change",
                        prompt=(
                            "请明确要调整的视觉元素，例如标题、颜色、线型、符号、"
                            "坐标轴或图例。"
                        ),
                        answer_kind="text",
                    ),
                ),
            )
        goal = parse_explicit_goal(context, source_alias=None)
        if goal is None or not goal.visual_actions or goal.data_operations:
            return WorkflowUnsupported(
                workflow_run_id=context.workflow_run_id,
                reason_code="CAPABILITY_UNAVAILABLE",
                message="当前请求不能编译为这张图支持的视觉编辑动作。",
            )
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
                role_labels = tuple(
                    dict.fromkeys((role, *_EXPLICIT_ROLE_LABELS.get(role, ()), *_role_tokens(role)))
                )
                for role_label in role_labels:
                    role_name = re.escape(role_label)
                    if re.search(
                        _binding_expression(field_name, role_name),
                        instruction,
                        flags=re.IGNORECASE,
                    ):
                        explicit[role] = field
                        break
                if role in explicit:
                    break
            if role in explicit:
                continue
            role_labels = tuple(
                dict.fromkeys((role, *_EXPLICIT_ROLE_LABELS.get(role, ()), *_role_tokens(role)))
            )
            role_pattern = "|".join(re.escape(label) for label in role_labels)
            semantic_binding = re.search(
                rf"(?<!\w)(?:{role_pattern})\s*{_BINDING_OPERATOR}\s*"
                rf"(?<!\w)(?:{role_pattern})(?!\w)",
                instruction,
                flags=re.IGNORECASE,
            )
            if semantic_binding is None:
                continue
            candidates = sorted(
                (
                    (score, index, field)
                    for index, field in enumerate(fields)
                    if (score := _field_score(role, field.name, field.logical_type, index))
                    is not None
                    and score >= 70
                ),
                key=lambda item: (-item[0], item[1]),
            )
            if candidates and (
                len(candidates) == 1 or candidates[0][0] > candidates[1][0]
            ):
                explicit[role] = candidates[0][2]
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
            if deterministic.outcome == "draft_ready":
                route: WorkflowRoute = "deterministic"
            elif deterministic.outcome == "needs_input":
                route = "needs_input"
            else:
                route = "unsupported"
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
