"""All-or-nothing target, version, capability, permission, and scope validation."""

from __future__ import annotations

from dataclasses import dataclass

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
        allowed_targets = authority.allowed_target_aliases | {envelope.target_snapshot.object_alias}
        visible_fields = {
            item.field_alias for item in envelope.selected_context.fields
        } & authority.allowed_field_aliases

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
            if isinstance(action, PatchPlotAction) and any(
                patch.operation not in envelope_patches
                or patch.operation not in authority.allowed_patch_operations
                or patch.target_alias not in allowed_targets
                for patch in action.patches
            ):
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
