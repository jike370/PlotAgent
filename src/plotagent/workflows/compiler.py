"""Pure TaskDraft validation and compilation against one immutable context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.workflows import (
    CompiledTaskItem,
    DraftVisualAction,
    ResolvedFieldBinding,
    ResolvedWorkflowField,
    TaskDraft,
    TaskPlan,
    WorkflowContext,
)
from plotagent.engine import EngineCatalog, EngineProfile


class WorkflowCompileError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class DraftValidation:
    valid: bool
    error_code: str | None = None
    message: str | None = None


class DraftCompiler:
    """Resolve aliases and enforce profile capability without mutating a project."""

    def __init__(self, catalog: EngineCatalog) -> None:
        self._catalog = catalog

    def validate(self, draft: TaskDraft, context: WorkflowContext) -> DraftValidation:
        try:
            self.compile(draft, context)
        except WorkflowCompileError as error:
            return DraftValidation(False, error.code, error.message)
        return DraftValidation(True)

    def compile(self, draft: TaskDraft, context: WorkflowContext) -> TaskPlan:
        if draft.workflow_run_id != context.workflow_run_id:
            raise WorkflowCompileError("WORKFLOW_CONTEXT_MISMATCH", "草稿不属于当前任务。")
        sources = {item.source_alias: item for item in context.sources}
        fields = {item.field_alias: item for item in context.fields}
        plots = {item.plot_alias: item for item in context.plots}
        token = draft.draft_id.removeprefix("draft:")
        compiled: list[CompiledTaskItem] = []
        for position, item in enumerate(draft.items, start=1):
            if item.profile_id not in context.allowed_profile_ids:
                raise WorkflowCompileError("PROFILE_NOT_ALLOWED", "草稿使用了不可用的图形类型。")
            profile = self._catalog.get(item.profile_id)
            if item.task_kind == "edit":
                target = plots.get(item.target_plot_alias or "")
                if target is None:
                    raise WorkflowCompileError("PLOT_ALIAS_INVALID", "草稿引用了不可用的图形。")
                if target.profile_id != item.profile_id:
                    raise WorkflowCompileError(
                        "PROFILE_TARGET_MISMATCH", "草稿图类与待编辑图形不一致。"
                    )
                self._validate_visual_actions(profile, item.visual_actions)
                compiled.append(
                    CompiledTaskItem(
                        task_kind="edit",
                        item_id=item.item_id,
                        plot_alias=item.plot_alias,
                        plot_id=target.plot_id,
                        profile_id=item.profile_id,
                        target_plot_id=target.plot_id,
                        target_plot_version=target.plot_version,
                        data_operations=(),
                        visual_actions=item.visual_actions,
                        idempotency_key=f"workflow.{token}.{position}",
                    )
                )
                continue
            item_sources = []
            for alias in item.source_aliases:
                source = sources.get(alias)
                if source is None:
                    raise WorkflowCompileError("SOURCE_ALIAS_INVALID", "草稿引用了不可用的数据表。")
                item_sources.append(source)
            synthetic_fields: dict[str, ResolvedWorkflowField] = {}
            for operation in item.data_operations:
                if operation.operation == "concatenate_sources":
                    alias = operation.source_label_field
                    synthetic_fields[alias] = ResolvedWorkflowField(
                        field_alias=alias,
                        source_alias=item.source_aliases[0],
                        field_id=f"field:workflow_{token}_{position}_{alias}",
                        name="Source",
                        logical_type="categorical",
                    )
                elif operation.operation == "reshape_wide_to_long":
                    synthetic_fields[operation.output_name] = ResolvedWorkflowField(
                        field_alias=operation.output_name,
                        source_alias=operation.source_alias,
                        field_id=(f"field:workflow_{token}_{position}_{operation.output_name}"),
                        name=operation.output_name,
                        logical_type="categorical",
                    )
                    synthetic_fields[operation.output_value] = ResolvedWorkflowField(
                        field_alias=operation.output_value,
                        source_alias=operation.source_alias,
                        field_id=(f"field:workflow_{token}_{position}_{operation.output_value}"),
                        name=operation.output_value,
                        logical_type="numeric",
                    )
            bound: list[ResolvedFieldBinding] = []
            resolved_fields: dict[str, ResolvedWorkflowField] = {}
            for binding in item.bindings:
                field = fields.get(binding.field_alias)
                synthetic = synthetic_fields.get(binding.field_alias)
                if synthetic is not None:
                    if synthetic.source_alias != binding.source_alias:
                        raise WorkflowCompileError(
                            "FIELD_ALIAS_INVALID", "派生字段不属于绑定的数据来源。"
                        )
                    bound.append(
                        ResolvedFieldBinding(
                            role=binding.role,
                            source_alias=binding.source_alias,
                            field_id=synthetic.field_id,
                        )
                    )
                    resolved_fields[synthetic.field_alias] = synthetic
                    continue
                if field is None or field.source_alias != binding.source_alias:
                    raise WorkflowCompileError("FIELD_ALIAS_INVALID", "草稿字段不属于所选数据表。")
                if binding.source_alias not in item.source_aliases:
                    raise WorkflowCompileError("FIELD_SOURCE_INVALID", "字段来源不属于当前任务项。")
                bound.append(
                    ResolvedFieldBinding(
                        role=binding.role,
                        source_alias=binding.source_alias,
                        field_id=field.field_id,
                    )
                )
                resolved_fields[field.field_alias] = ResolvedWorkflowField(
                    field_alias=field.field_alias,
                    source_alias=field.source_alias,
                    field_id=field.field_id,
                    name=field.name,
                    logical_type=field.logical_type,
                    unit_label=field.unit_label,
                )
            operation_aliases: set[str] = set()
            for operation in item.data_operations:
                dumped = operation.model_dump(mode="python")
                for key, value in dumped.items():
                    if "field_alias" not in key:
                        continue
                    if isinstance(value, str):
                        operation_aliases.add(value)
                    elif isinstance(value, (list, tuple)):
                        operation_aliases.update(cast(str, item) for item in value)
                if operation.operation == "filter_rows":
                    operation_aliases.update(
                        predicate.field_alias for predicate in operation.predicates
                    )
                if operation.operation == "sort_rows":
                    operation_aliases.update(key.field_alias for key in operation.keys)
            for alias in operation_aliases:
                if alias in synthetic_fields:
                    continue
                field = fields.get(alias)
                if field is None or field.source_alias not in item.source_aliases:
                    raise WorkflowCompileError(
                        "FIELD_ALIAS_INVALID", "数据操作引用了不可用的字段。"
                    )
                resolved_fields.setdefault(
                    alias,
                    ResolvedWorkflowField(
                        field_alias=field.field_alias,
                        source_alias=field.source_alias,
                        field_id=field.field_id,
                        name=field.name,
                        logical_type=field.logical_type,
                        unit_label=field.unit_label,
                    ),
                )
            for operation in item.data_operations:
                if operation.operation != "concatenate_sources":
                    continue
                for source_alias in operation.source_aliases:
                    for field in context.fields:
                        if field.source_alias != source_alias:
                            continue
                        resolved_fields.setdefault(
                            field.field_alias,
                            ResolvedWorkflowField(
                                field_alias=field.field_alias,
                                source_alias=field.source_alias,
                                field_id=field.field_id,
                                name=field.name,
                                logical_type=field.logical_type,
                                unit_label=field.unit_label,
                            ),
                        )
            roles = tuple(binding.role for binding in bound)
            if not set(profile.required_roles) <= set(roles):
                raise WorkflowCompileError("REQUIRED_ROLE_MISSING", "草稿缺少图形必填字段角色。")
            fixed_roles = set(profile.required_roles + profile.optional_roles)
            for role in roles:
                if role in fixed_roles:
                    continue
                if not any(
                    role.startswith(prefix + "_") and role.removeprefix(prefix + "_").isdigit()
                    for prefix in profile.repeatable_role_prefixes
                ):
                    raise WorkflowCompileError("ROLE_NOT_ALLOWED", "草稿包含图形不支持的字段角色。")
            self._validate_visual_actions(profile, item.visual_actions)
            plot_id = f"plot:workflow.{token}.{position}"
            compiled.append(
                CompiledTaskItem(
                    task_kind="create",
                    item_id=item.item_id,
                    plot_alias=item.plot_alias,
                    plot_id=plot_id,
                    profile_id=item.profile_id,
                    sources=tuple(item_sources),
                    resolved_fields=tuple(resolved_fields.values()),
                    data_operations=item.data_operations,
                    bindings=tuple(bound),
                    visual_actions=item.visual_actions,
                    idempotency_key=f"workflow.{token}.{position}",
                )
            )
        return TaskPlan(
            plan_id=f"plan:{token}",
            workflow_run_id=draft.workflow_run_id,
            draft_hash=canonical_hash(draft.model_dump(mode="json")),
            expected_project_revision=context.project_revision,
            items=tuple(compiled),
        )

    @staticmethod
    def _validate_visual_actions(
        profile: EngineProfile, actions: tuple[DraftVisualAction, ...]
    ) -> None:
        for action in actions:
            capability = next(
                (
                    candidate
                    for candidate in profile.capabilities
                    if candidate.operation == action.operation
                ),
                None,
            )
            if capability is None:
                raise WorkflowCompileError(
                    "ACTION_NOT_ALLOWED",
                    f"{profile.display_name} 不支持动作 {action.operation}。",
                )
            used = DraftCompiler._visual_parameters(action)
            unsupported = used - set(capability.parameters)
            if unsupported:
                raise WorkflowCompileError(
                    "ACTION_PARAMETER_NOT_ALLOWED",
                    f"{profile.display_name} 不支持 {action.operation} 参数："
                    f"{', '.join(sorted(unsupported))}。",
                )
            if action.target_alias == "plot":
                continue
            fixed_aliases = {candidate.object_alias for candidate in profile.objects}
            repeatable = tuple(
                candidate.object_alias_prefix for candidate in profile.repeatable_objects
            )
            if action.target_alias not in fixed_aliases and not any(
                action.target_alias.startswith(prefix + "_")
                and action.target_alias.removeprefix(prefix + "_").isdigit()
                for prefix in repeatable
            ):
                raise WorkflowCompileError(
                    "TARGET_ALIAS_INVALID",
                    f"{profile.display_name} 没有目标 {action.target_alias}。",
                )

    @staticmethod
    def _visual_parameters(action: DraftVisualAction) -> set[str]:
        dumped = action.model_dump(exclude_none=True)
        operation = dumped.pop("operation")
        dumped.pop("target_alias", None)
        if operation == "set_axis":
            minimum = dumped.pop("minimum", None)
            maximum = dumped.pop("maximum", None)
            if minimum is not None or maximum is not None:
                dumped["bounds"] = True
        if operation == "set_chart_parameter":
            return {str(dumped["parameter"])}
        return set(dumped)
