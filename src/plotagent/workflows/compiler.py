"""Pure TaskDraft validation and compilation against one immutable context."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any, cast

from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.workflows import (
    CompiledTaskItem,
    DataOperation,
    DraftVisualAction,
    ResolvedFieldBinding,
    ResolvedWorkflowField,
    SourceFieldBindingEvidence,
    TaskDraft,
    TaskDraftItem,
    TaskPlan,
    WorkflowContext,
    WorkflowField,
    data_operation_field_aliases,
)
from plotagent.engine import EngineCatalog, EngineProfile
from plotagent.units import resolve_unit


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

    def validate(
        self,
        draft: TaskDraft,
        context: WorkflowContext,
        *,
        unit_decision_ids: Collection[str] = (),
    ) -> DraftValidation:
        try:
            self.compile(draft, context, unit_decision_ids=unit_decision_ids)
        except WorkflowCompileError as error:
            return DraftValidation(False, error.code, error.message)
        return DraftValidation(True)

    def compile(
        self,
        draft: TaskDraft,
        context: WorkflowContext,
        *,
        unit_decision_ids: Collection[str] = (),
    ) -> TaskPlan:
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
            target = None
            if item.task_kind in {"edit", "update_data"}:
                target = plots.get(item.target_plot_alias or "")
                if target is None:
                    raise WorkflowCompileError("PLOT_ALIAS_INVALID", "草稿引用了不可用的图形。")
                if target.profile_id != item.profile_id:
                    raise WorkflowCompileError(
                        "PROFILE_TARGET_MISMATCH", "草稿图类与待编辑图形不一致。"
                    )
            if item.task_kind == "edit":
                assert target is not None
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
                if (
                    operation.operation == "concatenate_sources"
                    or operation.operation == "align_sources_on_x"
                ):
                    operation_sources = operation.source_aliases
                else:
                    operation_sources = (operation.source_alias,)
                if not set(operation_sources) <= set(item.source_aliases):
                    raise WorkflowCompileError(
                        "SOURCE_ALIAS_INVALID",
                        "数据操作只能使用当前任务项声明的数据来源。",
                    )
                if operation.operation == "concatenate_sources":
                    alias = operation.source_label_field
                    if alias in fields or alias in synthetic_fields:
                        raise WorkflowCompileError(
                            "FIELD_ALIAS_DUPLICATED", "派生字段别名必须互不重复。"
                        )
                    synthetic_fields[alias] = ResolvedWorkflowField(
                        field_alias=alias,
                        source_alias=item.source_aliases[0],
                        field_id=f"field:workflow_{token}_{position}_{alias}",
                        name="Source",
                        logical_type="categorical",
                    )
                elif operation.operation == "align_sources_on_x":
                    first_x = synthetic_fields.get(operation.x_field_aliases[0]) or fields.get(
                        operation.x_field_aliases[0]
                    )
                    if first_x is None or first_x.source_alias != operation.source_aliases[0]:
                        raise WorkflowCompileError(
                            "FIELD_ALIAS_INVALID", "多源对齐的首个 X 字段不可用。"
                        )
                    aligned_outputs = (
                        (operation.output_x_field_alias, operation.output_x_name, first_x),
                        *tuple(
                            (
                                output.field_alias,
                                output.name,
                                synthetic_fields.get(value_alias) or fields.get(value_alias),
                            )
                            for output, value_alias in zip(
                                operation.output_series_fields,
                                operation.value_field_aliases,
                                strict=True,
                            )
                        ),
                    )
                    for alias, name, original in aligned_outputs:
                        if alias in fields or alias in synthetic_fields:
                            raise WorkflowCompileError(
                                "FIELD_ALIAS_DUPLICATED", "多源对齐输出字段别名必须互不重复。"
                            )
                        if original is None:
                            raise WorkflowCompileError(
                                "FIELD_ALIAS_INVALID", "多源对齐的系列字段不可用。"
                            )
                        synthetic_fields[alias] = ResolvedWorkflowField(
                            field_alias=alias,
                            source_alias=operation.source_aliases[0],
                            field_id=f"field:workflow_{token}_{position}_{alias}",
                            name=name,
                            logical_type=original.logical_type,
                            unit_label=original.unit_label,
                        )
                elif operation.operation == "reshape_wide_to_long":
                    if (
                        operation.output_name in fields
                        or operation.output_name in synthetic_fields
                        or operation.output_value in fields
                        or operation.output_value in synthetic_fields
                        or operation.output_name == operation.output_value
                    ):
                        raise WorkflowCompileError(
                            "FIELD_ALIAS_DUPLICATED", "派生字段别名必须互不重复。"
                        )
                    value_fields = tuple(
                        synthetic_fields.get(alias) or fields.get(alias)
                        for alias in operation.value_field_aliases
                    )
                    if any(field is None for field in value_fields):
                        raise WorkflowCompileError("FIELD_ALIAS_INVALID", "宽转长数值字段不可用。")
                    value_signatures = {
                        (field.logical_type, field.unit_label or "")
                        for field in value_fields
                        if field is not None
                    }
                    if len(value_signatures) != 1:
                        raise WorkflowCompileError(
                            "WORKFLOW_RESHAPE_VALUE_MISMATCH",
                            "宽转长数值字段必须具有相同类型和单位。",
                        )
                    value_type, value_unit = next(iter(value_signatures))
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
                        logical_type=cast(Any, value_type),
                        unit_label=value_unit or None,
                    )
                elif operation.operation == "reshape_long_to_wide":
                    value_field = fields.get(operation.value_field_alias)
                    if value_field is None:
                        raise WorkflowCompileError("FIELD_ALIAS_INVALID", "长转宽数值字段不可用。")
                    for output in operation.output_fields:
                        if output.field_alias in fields or output.field_alias in synthetic_fields:
                            raise WorkflowCompileError(
                                "FIELD_ALIAS_DUPLICATED", "派生字段别名必须互不重复。"
                            )
                        synthetic_fields[output.field_alias] = ResolvedWorkflowField(
                            field_alias=output.field_alias,
                            source_alias=operation.source_alias,
                            field_id=(f"field:workflow_{token}_{position}_{output.field_alias}"),
                            name=output.name,
                            logical_type=value_field.logical_type,
                            unit_label=value_field.unit_label,
                        )
                elif operation.operation in {
                    "rename_field",
                    "derive_column",
                    "convert_type",
                    "convert_unit",
                    "declare_unit",
                    "bucketize_numeric",
                }:
                    derived_operation = cast(Any, operation)
                    alias = derived_operation.output_field_alias
                    if alias in fields or alias in synthetic_fields:
                        raise WorkflowCompileError(
                            "FIELD_ALIAS_DUPLICATED", "派生字段别名必须互不重复。"
                        )
                    logical_type = "numeric"
                    unit_label = getattr(derived_operation, "target_unit", None)
                    if operation.operation == "rename_field":
                        original = synthetic_fields.get(
                            derived_operation.field_alias
                        ) or fields.get(derived_operation.field_alias)
                        if (
                            original is None
                            or original.source_alias != derived_operation.source_alias
                        ):
                            raise WorkflowCompileError(
                                "FIELD_ALIAS_INVALID", "重命名字段不属于所选数据表。"
                            )
                        logical_type = original.logical_type
                        unit_label = original.unit_label
                    elif operation.operation == "derive_column":
                        original = synthetic_fields.get(
                            derived_operation.input_field_aliases[0]
                        ) or fields.get(derived_operation.input_field_aliases[0])
                        unit_label = original.unit_label if original is not None else None
                    elif operation.operation == "bucketize_numeric":
                        logical_type = "categorical"
                        unit_label = None
                    elif operation.operation == "convert_type":
                        logical_type = derived_operation.target_type
                        original = synthetic_fields.get(
                            derived_operation.field_alias
                        ) or fields.get(derived_operation.field_alias)
                        unit_label = (
                            original.unit_label
                            if original is not None and logical_type == "numeric"
                            else None
                        )
                    elif operation.operation == "declare_unit":
                        original = synthetic_fields.get(
                            derived_operation.field_alias
                        ) or fields.get(derived_operation.field_alias)
                        if (
                            original is None
                            or original.source_alias != derived_operation.source_alias
                        ):
                            raise WorkflowCompileError(
                                "FIELD_ALIAS_INVALID", "单位声明字段不属于所选数据表。"
                            )
                        if original.logical_type != "numeric":
                            raise WorkflowCompileError(
                                "WORKFLOW_UNIT_TYPE_INVALID", "单位声明只接受数值字段。"
                            )
                        if original.unit_label is not None and original.unit_label.strip():
                            raise WorkflowCompileError(
                                "WORKFLOW_UNIT_ALREADY_DECLARED",
                                "已有单位的字段必须使用单位换算，不能覆盖原单位。",
                            )
                        if derived_operation.evidence_ref not in unit_decision_ids:
                            raise WorkflowCompileError(
                                "WORKFLOW_UNIT_EVIDENCE_INVALID",
                                "缺失单位只能依据当前任务中明确记录的单位决定进行声明。",
                            )
                        target_definition = resolve_unit(derived_operation.target_unit)
                        if target_definition is None:
                            raise WorkflowCompileError(
                                "WORKFLOW_UNIT_UNKNOWN", "声明单位不在注册表中。"
                            )
                        logical_type = "numeric"
                        unit_label = target_definition.symbol
                    synthetic_fields[alias] = ResolvedWorkflowField(
                        field_alias=alias,
                        source_alias=derived_operation.source_alias,
                        field_id=f"field:workflow_{token}_{position}_{alias}",
                        name=derived_operation.output_name,
                        logical_type=cast(Any, logical_type),
                        unit_label=unit_label,
                    )
            self._validate_operation_flow(item.source_aliases, item.data_operations, fields)
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
            for alias, synthetic in synthetic_fields.items():
                resolved_fields.setdefault(alias, synthetic)
            operation_aliases: set[str] = set()
            for operation in item.data_operations:
                inputs, _outputs = self._operation_fields(operation)
                operation_aliases.update(inputs)
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
            for binding in item.bindings:
                candidate_field = synthetic_fields.get(binding.field_alias) or fields.get(
                    binding.field_alias
                )
                if candidate_field is None:
                    continue
                accepted = profile.role_field_types.get(binding.role)
                if accepted is None:
                    accepted = next(
                        (
                            profile.role_field_types[prefix]
                            for prefix in profile.repeatable_role_prefixes
                            if binding.role.startswith(prefix + "_")
                            and binding.role.removeprefix(prefix + "_").isdigit()
                            and prefix in profile.role_field_types
                        ),
                        None,
                    )
                if accepted is not None and candidate_field.logical_type not in accepted:
                    expected = "、".join(accepted)
                    raise WorkflowCompileError(
                        "FIELD_TYPE_INCOMPATIBLE",
                        f"{profile.display_name} 的 {binding.role} 字段需要 {expected} 类型，"
                        f"但 {candidate_field.name} 是 {candidate_field.logical_type}。",
                    )
            self._validate_visual_actions(profile, item.visual_actions)
            plot_id = (
                target.plot_id
                if item.task_kind == "update_data" and target is not None
                else f"plot:workflow.{token}.{position}"
            )
            compiled.append(
                CompiledTaskItem(
                    task_kind=item.task_kind,
                    item_id=item.item_id,
                    plot_alias=item.plot_alias,
                    plot_id=plot_id,
                    profile_id=item.profile_id,
                    target_plot_id=(target.plot_id if target is not None else None),
                    target_plot_version=(target.plot_version if target is not None else None),
                    sources=tuple(item_sources),
                    resolved_fields=tuple(resolved_fields.values()),
                    data_operations=item.data_operations,
                    bindings=tuple(bound),
                    binding_evidence=self._binding_evidence(item, fields),
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
    def _binding_evidence(
        item: TaskDraftItem,
        fields: dict[str, WorkflowField],
    ) -> tuple[SourceFieldBindingEvidence, ...]:
        """Resolve final roles back to the raw fields that produced them."""

        lineage: dict[str, tuple[tuple[str, str], ...]] = {
            alias: ((field.source_alias, field.field_id),) for alias, field in fields.items()
        }

        def merged(*aliases: str) -> tuple[tuple[str, str], ...]:
            return tuple(
                dict.fromkeys(origin for alias in aliases for origin in lineage.get(alias, ()))
            )

        for operation in item.data_operations:
            if operation.operation == "align_sources_on_x":
                lineage[operation.output_x_field_alias] = merged(*operation.x_field_aliases)
                for output, value_alias in zip(
                    operation.output_series_fields,
                    operation.value_field_aliases,
                    strict=True,
                ):
                    lineage[output.field_alias] = merged(value_alias)
            elif operation.operation == "reshape_wide_to_long":
                combined = merged(*operation.value_field_aliases)
                lineage[operation.output_name] = combined
                lineage[operation.output_value] = combined
            elif operation.operation == "reshape_long_to_wide":
                combined = merged(operation.name_field_alias, operation.value_field_alias)
                for output in operation.output_fields:
                    lineage[output.field_alias] = combined
            elif operation.operation == "concatenate_sources":
                lineage[operation.source_label_field] = ()
                head = operation.source_aliases[0]
                head_fields = tuple(
                    field for field in fields.values() if field.source_alias == head
                )
                for head_field in head_fields:
                    signature = (
                        head_field.name,
                        head_field.logical_type,
                        head_field.unit_label or "",
                    )
                    equivalents = tuple(
                        field.field_alias
                        for field in fields.values()
                        if field.source_alias in operation.source_aliases
                        and (
                            field.name,
                            field.logical_type,
                            field.unit_label or "",
                        )
                        == signature
                    )
                    if equivalents:
                        lineage[head_field.field_alias] = merged(*equivalents)
            elif operation.operation in {
                "rename_field",
                "convert_type",
                "convert_unit",
                "declare_unit",
                "bucketize_numeric",
            }:
                derived_operation = cast(Any, operation)
                lineage[derived_operation.output_field_alias] = merged(
                    derived_operation.field_alias
                )
            elif operation.operation == "derive_column":
                lineage[operation.output_field_alias] = merged(*operation.input_field_aliases)

        evidence = tuple(
            SourceFieldBindingEvidence(
                role=binding.role,
                source_alias=source_alias,
                field_id=field_id,
            )
            for binding in item.bindings
            for source_alias, field_id in lineage.get(binding.field_alias, ())
        )
        return tuple(dict.fromkeys(evidence))

    @staticmethod
    def _validate_operation_flow(
        item_source_aliases: tuple[str, ...],
        operations: tuple[DataOperation, ...],
        fields: dict[str, WorkflowField],
    ) -> None:
        available: dict[str, set[str]] = {
            source_alias: {
                field.field_alias for field in fields.values() if field.source_alias == source_alias
            }
            for source_alias in item_source_aliases
        }
        for operation in operations:
            if operation.operation == "concatenate_sources":
                if any(alias not in available for alias in operation.source_aliases):
                    raise WorkflowCompileError(
                        "SOURCE_ALIAS_INVALID", "数据拼接引用了已不可用的数据表。"
                    )
                if set(operation.source_aliases) != set(available):
                    raise WorkflowCompileError(
                        "WORKFLOW_SOURCES_NOT_COMBINED",
                        "同一任务项的全部数据来源必须在一次明确的数据合并操作中处理。",
                    )
                head = operation.source_aliases[0]
                available = {
                    head: available[head] | {operation.source_label_field},
                }
                continue
            if operation.operation == "align_sources_on_x":
                if set(operation.source_aliases) != set(available):
                    raise WorkflowCompileError(
                        "WORKFLOW_SOURCES_NOT_COMBINED",
                        "同一任务项的全部数据来源必须在一次明确的数据合并操作中处理。",
                    )
                for source_alias, x_alias, value_alias in zip(
                    operation.source_aliases,
                    operation.x_field_aliases,
                    operation.value_field_aliases,
                    strict=True,
                ):
                    current = available.get(source_alias)
                    if current is None:
                        raise WorkflowCompileError(
                            "SOURCE_ALIAS_INVALID", "多源对齐引用了已不可用的数据表。"
                        )
                    if x_alias not in current or value_alias not in current:
                        raise WorkflowCompileError(
                            "FIELD_ALIAS_INVALID", "多源对齐字段不属于对应数据表。"
                        )
                head = operation.source_aliases[0]
                available = {
                    head: {
                        operation.output_x_field_alias,
                        *(field.field_alias for field in operation.output_series_fields),
                    }
                }
                continue
            source_alias = operation.source_alias
            current = available.get(source_alias)
            if current is None:
                raise WorkflowCompileError(
                    "SOURCE_ALIAS_INVALID", "数据操作引用了已不可用的数据表。"
                )
            inputs, outputs = DraftCompiler._operation_fields(operation)
            if not set(inputs) <= current:
                raise WorkflowCompileError(
                    "FIELD_ALIAS_INVALID", "数据操作引用了尚未生成或已移除的字段。"
                )
            if operation.operation == "select_fields":
                available[source_alias] = set(operation.field_aliases)
            elif operation.operation == "drop_empty_fields":
                available[source_alias].difference_update(operation.field_aliases)
            elif operation.operation == "reshape_wide_to_long":
                available[source_alias] = set(operation.id_field_aliases) | set(outputs)
            elif operation.operation == "reshape_long_to_wide":
                available[source_alias] = set(operation.index_field_aliases) | set(outputs)
            else:
                available[source_alias].update(outputs)
        if len(available) != 1:
            raise WorkflowCompileError(
                "WORKFLOW_SOURCES_NOT_COMBINED",
                "同一任务项的多个数据来源必须通过 concatenate_sources 或 "
                "align_sources_on_x 明确合并。",
            )

    @staticmethod
    def _operation_fields(operation: DataOperation) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return data_operation_field_aliases(operation)

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
            bounds_mode = dumped.pop("bounds_mode", None)
            minimum = dumped.pop("minimum", None)
            maximum = dumped.pop("maximum", None)
            if bounds_mode is not None or minimum is not None or maximum is not None:
                dumped["bounds"] = True
        if operation == "set_chart_parameter":
            return {str(dumped["parameter"])}
        return set(dumped)
