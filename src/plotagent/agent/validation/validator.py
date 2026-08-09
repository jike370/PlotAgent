"""All-or-nothing target, version, capability, permission, and scope validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from plotagent.agent.errors import AgentRuntimeError
from plotagent.contracts.agent_context import ContextEnvelope, ContextObjectRef
from plotagent.contracts.decisions import (
    ActionPlan,
    AgentDecision,
    CreateBatchAction,
    CreateFigureAction,
    CreatePlotAction,
    ExportArtifactAction,
    NeedsInput,
    PatchPlotAction,
)
from plotagent.contracts.registry import CHARTS_BY_ID


@dataclass(frozen=True, slots=True)
class ValidationAuthority:
    current_target: ContextObjectRef
    allowed_target_aliases: frozenset[str]
    allowed_field_aliases: frozenset[str]
    allowed_action_types: frozenset[str]
    allowed_chart_type_ids: frozenset[str]
    allowed_patch_operations: frozenset[str]
    allowed_export_formats: frozenset[str] = frozenset()
    allowed_export_scopes: frozenset[str] = frozenset()
    selected_plot_aliases: frozenset[str] = frozenset()
    permission_grants: frozenset[str] = frozenset()
    target_chart_type_ids: dict[str, str] = field(default_factory=dict)


class DecisionValidator:
    def validate(
        self,
        decision: AgentDecision,
        envelope: ContextEnvelope,
        authority: ValidationAuthority,
    ) -> AgentDecision:
        if authority.current_target != envelope.target_snapshot:
            raise AgentRuntimeError("TARGET_STALE")
        if decision.schema_version != envelope.schema_version:
            raise AgentRuntimeError("SCHEMA_VERSION_UNSUPPORTED")
        if decision.target_alias != envelope.target_snapshot.object_alias:
            raise AgentRuntimeError("AGENT_TARGET_INVALID")
        if isinstance(decision, NeedsInput):
            self._validate_data_request(decision, envelope, authority)
        elif isinstance(decision, ActionPlan):
            self._validate_plan(decision, envelope, authority)
        return decision

    def _validate_data_request(
        self,
        decision: NeedsInput,
        envelope: ContextEnvelope,
        authority: ValidationAuthority,
    ) -> None:
        request = decision.data_request
        if request is None:
            return
        objects = {
            envelope.target_snapshot.object_alias: envelope.target_snapshot,
            **{item.object_alias: item for item in envelope.selected_context.selected_objects},
        }
        target = objects.get(request.dataset_alias)
        if target is None or target.object_version != request.expected_version:
            raise AgentRuntimeError("TARGET_STALE")
        visible_fields = {
            item.field_alias for item in envelope.selected_context.fields
        } | authority.allowed_field_aliases
        if not set(request.field_aliases).issubset(visible_fields):
            raise AgentRuntimeError("AGENT_ACTION_SCOPE_INVALID")

    def _validate_plan(
        self,
        plan: ActionPlan,
        envelope: ContextEnvelope,
        authority: ValidationAuthority,
    ) -> None:
        errors: list[str] = []
        envelope_actions = set(envelope.chart_capabilities.allowed_action_types)
        envelope_charts = set(envelope.chart_capabilities.allowed_chart_type_ids)
        envelope_patches = set(envelope.chart_capabilities.allowed_patch_operations)
        envelope_formats = set(envelope.chart_capabilities.export_formats)
        chart_patch_operations: dict[str, set[str]] = {
            item.chart_type_id: set(item.allowed_patch_operations)
            for item in envelope.chart_capabilities.chart_edit_capabilities
        }
        target_chart_types = dict(authority.target_chart_type_ids)
        allowed_targets = authority.allowed_target_aliases | {envelope.target_snapshot.object_alias}
        visible_fields = {
            item.field_alias for item in envelope.selected_context.fields
        } & authority.allowed_field_aliases
        context_fields = {item.field_alias: item for item in envelope.selected_context.fields}

        for action in plan.actions:
            if (
                action.action_type not in envelope_actions
                or action.action_type not in authority.allowed_action_types
                or action.action_type not in authority.permission_grants
            ):
                errors.append("AGENT_CAPABILITY_UNSUPPORTED")
            if action.target_alias not in allowed_targets:
                errors.append("AGENT_ACTION_SCOPE_INVALID")
            if isinstance(action, (CreatePlotAction, CreateBatchAction)):
                if len(envelope_charts) > 1 and _is_unspecified_chart_request(
                    envelope.user_instruction
                ):
                    errors.append("CHART_TYPE_REQUIRED")
                if (
                    action.chart_type_id not in envelope_charts
                    or action.chart_type_id not in authority.allowed_chart_type_ids
                ):
                    errors.append("AGENT_CAPABILITY_UNSUPPORTED")
                if any(
                    selection.context_field_alias not in visible_fields
                    for selection in action.field_selections
                ):
                    errors.append("AGENT_ACTION_SCOPE_INVALID")
                registration = CHARTS_BY_ID.get(action.chart_type_id)
                if registration is not None:
                    roles = tuple(selection.role for selection in action.field_selections)
                    role_set = set(roles)
                    allowed_roles = set(registration.required_roles) | set(
                        registration.optional_roles
                    )
                    if len(role_set) != len(roles):
                        errors.append("MAPPING_DUPLICATE_ROLE")
                    if not set(registration.required_roles).issubset(role_set):
                        errors.append("MAPPING_REQUIRED_ROLE_MISSING")
                    if any(
                        role not in allowed_roles and not role.startswith("series_")
                        for role in role_set
                    ):
                        errors.append("AGENT_ACTION_SCOPE_INVALID")
                    for selection in action.field_selections:
                        field = context_fields.get(selection.context_field_alias)
                        if (
                            field is not None
                            and field.semantic_role is not None
                            and field.semantic_role in allowed_roles
                            and field.semantic_role != selection.role
                        ):
                            errors.append("AGENT_FIELD_ROLE_INVALID")
                    explicit_roles = {
                        role
                        for role in allowed_roles
                        if _mentions_role(envelope.user_instruction, role)
                    }
                    if not explicit_roles.issubset(role_set):
                        errors.append("MAPPING_REQUIRED_ROLE_MISSING")
                    if action.chart_type_id == "K06" and not _valid_k06_roles(role_set):
                        errors.append("AGENT_FIELD_ROLE_INVALID")
                if isinstance(action, CreatePlotAction):
                    target_chart_types[action.target_alias] = action.chart_type_id
            if isinstance(action, PatchPlotAction) and any(
                patch.operation not in envelope_patches
                or patch.operation not in authority.allowed_patch_operations
                or patch.target_alias not in allowed_targets
                for patch in action.patches
            ):
                errors.append("AGENT_CAPABILITY_UNSUPPORTED")
            if isinstance(action, PatchPlotAction):
                if any(not _patch_target_matches_operation(patch) for patch in action.patches):
                    errors.append("AGENT_TARGET_INVALID")
                chart_type_id = target_chart_types.get(action.target_alias)
                if chart_type_id is not None:
                    per_chart = chart_patch_operations.get(chart_type_id, set())
                    if any(patch.operation not in per_chart for patch in action.patches):
                        errors.append("AGENT_CAPABILITY_UNSUPPORTED")
            if isinstance(action, CreateFigureAction) and not set(action.plot_aliases).issubset(
                authority.selected_plot_aliases
            ):
                errors.append("AGENT_ACTION_SCOPE_INVALID")
            if isinstance(action, ExportArtifactAction):
                if (
                    action.format not in envelope_formats
                    or action.format not in authority.allowed_export_formats
                ):
                    errors.append("AGENT_CAPABILITY_UNSUPPORTED")
                if action.target_scope not in authority.allowed_export_scopes:
                    errors.append("AGENT_ACTION_SCOPE_INVALID")
        if errors:
            unique = tuple(dict.fromkeys(errors))
            raise AgentRuntimeError(unique[0], categories=unique)


def _mentions_role(instruction: str, role: str) -> bool:
    """Return whether a provider-visible role token is explicitly requested."""

    normalized = re.sub(r"[\s.-]+", "_", instruction.casefold())
    return (
        re.search(rf"(?<![a-z0-9_]){re.escape(role.casefold())}(?![a-z0-9_])", normalized)
        is not None
    )


def _is_unspecified_chart_request(instruction: str) -> bool:
    normalized = re.sub(r"[^\w]+", "", instruction.casefold()).replace("_", "")
    return normalized in {
        "画图",
        "画一个图",
        "画一张图",
        "帮我画图",
        "绘图",
        "绘制一个图",
        "绘制一张图",
        "用这些数据画图",
        "用这个数据画图",
        "drawachart",
        "makeachart",
        "plotachart",
    }


def _valid_k06_roles(roles: set[str]) -> bool:
    horizontal = {"x_lower", "x_upper"} & roles
    vertical_bounds = {"lower", "upper"} & roles
    if horizontal and not {"x", "x_lower", "x_upper"}.issubset(roles):
        return False
    if vertical_bounds and not {"lower", "upper"}.issubset(roles):
        return False
    return not ({"error", "lower", "upper"}.isdisjoint(roles))


def _patch_target_matches_operation(patch: object) -> bool:
    operation = getattr(patch, "operation", "")
    target_alias = getattr(patch, "target_alias", "")
    if operation in {
        "set_axis_range",
        "set_axis_scale",
        "set_axis_label",
        "set_axis_reverse",
        "set_axis_ticks",
    }:
        return target_alias in {"x_axis", "y_axis", "right_y_axis"}
    if operation == "set_series_style":
        return isinstance(target_alias, str) and target_alias.startswith("series_")
    return True
