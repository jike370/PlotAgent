"""Versioned domain knowledge and bounded Agent context contracts.

The models in this module are the public, renderer-neutral knowledge surface.
They deliberately exclude backend commands, template identities, filesystem
paths and native object identifiers.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.agent_tasks import (
    ActivationBudget,
    AgentActivationId,
    AgentActivationReason,
    IntentRef,
    PermissionPhase,
    SelectedPlotRef,
    TaskBudgetSnapshot,
    TaskCheckpointId,
    TaskId,
    TaskItemIdV2,
    TaskItemState,
    TaskState,
    ToolReceiptId,
    VerificationReport,
    VerificationReportId,
)
from plotagent.contracts.base import (
    CalculationKind,
    ChartTypeId,
    FieldId,
    NonEmptyText,
    NonNegativeInt,
    Sha256,
    SourceDatasetRef,
    StrictModel,
    Token,
    VersionId,
)
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.workflows import RowPage, WorkflowAlias, WorkflowField, WorkflowSource
from plotagent.engine.contracts import EngineProfile

KnowledgeId = Annotated[
    str,
    StringConstraints(pattern=r"^knowledge:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
CalculationContractId = Annotated[
    str,
    StringConstraints(pattern=r"^calculation:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
ContextSnapshotId = Annotated[
    str,
    StringConstraints(pattern=r"^context:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
DomainExampleId = Annotated[
    str,
    StringConstraints(pattern=r"^example:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
_OfficialUrl = Annotated[
    str,
    StringConstraints(
        pattern=r"^https://(?:docs|cloud)\.originlab\.com/", max_length=512, strict=True
    ),
]

SourceShape = Literal[
    "worksheet_xy",
    "worksheet_wide",
    "worksheet_long_indexed",
    "matrix",
    "analysis_table",
]


class ChartEvidenceRef(StrictModel):
    """Reviewed evidence projection safe for ordinary Agent context."""

    evidence_id: Token
    title: NonEmptyText
    official_url: _OfficialUrl
    reviewed_product_version: Token
    evidence_digest: Sha256
    claim_ids: Annotated[tuple[Token, ...], Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def unique_claims(self) -> ChartEvidenceRef:
        if len(self.claim_ids) != len(set(self.claim_ids)):
            raise ValueError("chart evidence claim ids must be unique")
        return self


class DomainExample(StrictModel):
    example_id: DomainExampleId
    kind: Literal["minimal", "representative", "near_miss", "invalid"]
    summary: NonEmptyText
    role_assignments: Annotated[tuple[tuple[Token, NonEmptyText], ...], Field(max_length=32)]
    expected_outcome: Literal["supported", "needs_input", "rejected"]

    @model_validator(mode="after")
    def unique_roles(self) -> DomainExample:
        roles = tuple(role for role, _description in self.role_assignments)
        if len(roles) != len(set(roles)):
            raise ValueError("domain example role assignments must be unique")
        return self


class ChartKnowledgeCard(StrictModel):
    """One reviewed chart card bound to the executable EngineProfile truth."""

    schema_version: Literal["chart-knowledge.v1"] = "chart-knowledge.v1"
    knowledge_id: KnowledgeId
    knowledge_version: VersionId
    profile_id: ChartTypeId
    engine_profile: EngineProfile
    engine_profile_hash: Sha256
    display_name_zh: NonEmptyText
    official_name: NonEmptyText
    user_facing_description: NonEmptyText
    intended_questions: Annotated[tuple[NonEmptyText, ...], Field(min_length=1, max_length=8)]
    unsuitable_questions: Annotated[tuple[NonEmptyText, ...], Field(min_length=1, max_length=8)]
    source_shapes: Annotated[tuple[SourceShape, ...], Field(min_length=1, max_length=4)]
    data_requirements: Annotated[tuple[NonEmptyText, ...], Field(min_length=1, max_length=32)]
    row_relations: Annotated[tuple[NonEmptyText, ...], Field(min_length=1, max_length=16)]
    ordering_semantics: Annotated[tuple[NonEmptyText, ...], Field(min_length=1, max_length=8)]
    fixed_scientific_semantics: Annotated[
        tuple[NonEmptyText, ...], Field(min_length=1, max_length=16)
    ]
    allowed_preparations: Annotated[tuple[NonEmptyText, ...], Field(max_length=16)] = ()
    forbidden_preparations: Annotated[
        tuple[NonEmptyText, ...], Field(min_length=1, max_length=16)
    ]
    unsupported_actions: Annotated[tuple[NonEmptyText, ...], Field(max_length=16)] = ()
    calculation_contract_ids: Annotated[
        tuple[CalculationContractId, ...], Field(max_length=8)
    ] = ()
    examples: Annotated[tuple[DomainExample, ...], Field(min_length=2, max_length=8)]
    validation_claims: Annotated[tuple[Token, ...], Field(min_length=1, max_length=32)]
    evidence_refs: Annotated[tuple[ChartEvidenceRef, ...], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def bound_to_engine_contract(self) -> ChartKnowledgeCard:
        if self.profile_id != self.engine_profile.profile_id:
            raise ValueError("chart knowledge profile must match its EngineProfile")
        if self.engine_profile_hash != canonical_hash(self.engine_profile):
            raise ValueError("chart knowledge EngineProfile hash is stale")
        if not any(example.kind == "minimal" for example in self.examples):
            raise ValueError("chart knowledge requires a minimal example")
        if not any(example.kind in {"near_miss", "invalid"} for example in self.examples):
            raise ValueError("chart knowledge requires a counterexample")
        groups = (
            self.calculation_contract_ids,
            tuple(example.example_id for example in self.examples),
            self.validation_claims,
            tuple(item.evidence_id for item in self.evidence_refs),
        )
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("chart knowledge references must be unique")
        evidence_claims = {
            claim_id for evidence in self.evidence_refs for claim_id in evidence.claim_ids
        }
        if not set(self.validation_claims) <= evidence_claims:
            raise ValueError("every validation claim needs reviewed evidence")
        return self


class ChartCatalogEntry(StrictModel):
    profile_id: ChartTypeId
    knowledge_id: KnowledgeId
    knowledge_version: VersionId
    knowledge_hash: Sha256
    display_name_zh: NonEmptyText
    official_name: NonEmptyText
    summary: NonEmptyText
    required_roles: tuple[Token, ...]
    optional_roles: tuple[Token, ...] = ()
    repeatable_role_prefixes: tuple[Token, ...] = ()


class ChartProfileComparison(StrictModel):
    profile_ids: Annotated[tuple[ChartTypeId, ...], Field(min_length=2, max_length=8)]
    entries: Annotated[tuple[ChartCatalogEntry, ...], Field(min_length=2, max_length=8)]
    source_shapes: dict[ChartTypeId, tuple[SourceShape, ...]]
    fixed_semantics: dict[ChartTypeId, tuple[NonEmptyText, ...]]
    forbidden_preparations: dict[ChartTypeId, tuple[NonEmptyText, ...]]

    @model_validator(mode="after")
    def aligned_profiles(self) -> ChartProfileComparison:
        if len(self.profile_ids) != len(set(self.profile_ids)):
            raise ValueError("comparison profile ids must be unique")
        entry_ids = tuple(entry.profile_id for entry in self.entries)
        if entry_ids != self.profile_ids:
            raise ValueError("comparison entries must preserve requested profile order")
        if set(self.source_shapes) != set(self.profile_ids):
            raise ValueError("comparison source shapes must cover requested profiles")
        if set(self.fixed_semantics) != set(self.profile_ids):
            raise ValueError("comparison semantics must cover requested profiles")
        if set(self.forbidden_preparations) != set(self.profile_ids):
            raise ValueError("comparison preparation boundaries must cover requested profiles")
        return self


class CalculationInputRole(StrictModel):
    role: Token
    accepted_types: Annotated[
        tuple[Literal["numeric", "categorical", "datetime", "boolean", "text"], ...],
        Field(min_length=1, max_length=5),
    ]
    required: bool = True


class CalculationParameter(StrictModel):
    name: Token
    value_type: Literal["enum", "integer", "number", "boolean", "field", "field_list"]
    default: str | int | float | bool | None = None
    constraint: NonEmptyText


class CalculationContract(StrictModel):
    schema_version: Literal["calculation-contract.v1"] = "calculation-contract.v1"
    contract_id: CalculationContractId
    contract_version: VersionId
    calculation_kind: CalculationKind
    algorithm_id: Token
    algorithm_version: Token
    spec_schema_hash: Sha256
    input_roles: Annotated[tuple[CalculationInputRole, ...], Field(min_length=1, max_length=16)]
    definition: Annotated[tuple[NonEmptyText, ...], Field(min_length=1, max_length=16)]
    parameters: Annotated[tuple[CalculationParameter, ...], Field(max_length=24)] = ()
    missing_value_behavior: NonEmptyText
    boundary_behavior: Annotated[tuple[NonEmptyText, ...], Field(min_length=1, max_length=16)]
    output_fields: Annotated[tuple[FieldId, ...], Field(min_length=1, max_length=32)]
    linked_profile_ids: Annotated[tuple[ChartTypeId, ...], Field(max_length=16)] = ()
    oracle_ids: Annotated[tuple[Token, ...], Field(min_length=1, max_length=16)]

    @model_validator(mode="after")
    def unique_contract_values(self) -> CalculationContract:
        groups = (
            tuple(role.role for role in self.input_roles),
            tuple(parameter.name for parameter in self.parameters),
            self.output_fields,
            self.linked_profile_ids,
            self.oracle_ids,
        )
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("calculation contract values must be unique")
        return self


class UntrustedSourceContext(StrictModel):
    """Authorized, bounded data projection whose content can never grant authority."""

    content_is_untrusted: Literal[True] = True
    source: WorkflowSource
    fields: Annotated[tuple[WorkflowField, ...], Field(max_length=128)] = ()
    preview: RowPage | None = None

    @model_validator(mode="after")
    def aligned_source(self) -> UntrustedSourceContext:
        if any(field.source_alias != self.source.source_alias for field in self.fields):
            raise ValueError("context fields must belong to their source")
        field_aliases = tuple(field.field_alias for field in self.fields)
        if len(field_aliases) != len(set(field_aliases)):
            raise ValueError("context field aliases must be unique")
        if self.preview is not None:
            if self.preview.source_alias != self.source.source_alias:
                raise ValueError("context preview must belong to its source")
            if not set(self.preview.field_aliases) <= set(field_aliases):
                raise ValueError("context preview fields must be disclosed field summaries")
            if self.preview.offset + len(self.preview.rows) > self.source.row_count:
                raise ValueError("context preview cannot exceed source row count")
        return self


class ContextToolContract(StrictModel):
    tool_name: Token
    permission_phase: PermissionPhase
    input_schema_hash: Sha256
    output_schema_hash: Sha256
    description: NonEmptyText
    side_effect: Literal["none", "staged", "confirmed_write", "expanded_risk"]

    @model_validator(mode="after")
    def side_effect_matches_phase(self) -> ContextToolContract:
        expected = {
            "none": "p0_read",
            "staged": "p1_staged",
            "confirmed_write": "p2_confirmed",
            "expanded_risk": "p3_expanded",
        }[self.side_effect]
        if self.permission_phase != expected:
            raise ValueError("tool side effect must match its minimum permission phase")
        return self


class SelectedPlotBindingContext(StrictModel):
    """One existing plot binding expressed only with activation-local aliases."""

    role: Token
    source_alias: WorkflowAlias
    field_alias: WorkflowAlias


class SelectedPlotContext(StrictModel):
    """Pinned current plot state needed to plan edits and data updates safely."""

    plot_alias: WorkflowAlias
    plot_id: Token
    plot_version: VersionId
    profile_id: Token
    source_aliases: Annotated[tuple[WorkflowAlias, ...], Field(max_length=8)] = ()
    bindings: Annotated[tuple[SelectedPlotBindingContext, ...], Field(max_length=128)] = ()

    @model_validator(mode="after")
    def aligned_bindings(self) -> SelectedPlotContext:
        if len(self.source_aliases) != len(set(self.source_aliases)):
            raise ValueError("selected plot source aliases must be unique")
        roles = tuple(binding.role for binding in self.bindings)
        if len(roles) != len(set(roles)):
            raise ValueError("selected plot binding roles must be unique")
        if any(binding.source_alias not in self.source_aliases for binding in self.bindings):
            raise ValueError("selected plot bindings must use a selected plot source")
        return self


class AgentContextSnapshot(StrictModel):
    """Rebuildable, hash-addressed input to one Agent activation."""

    schema_version: Literal["agent-context.v2"] = "agent-context.v2"
    context_snapshot_id: ContextSnapshotId
    context_version: VersionId
    task_id: TaskId
    task_version: VersionId
    activation_id: AgentActivationId
    activation_reason: AgentActivationReason
    task_state: TaskState
    checkpoint_id: TaskCheckpointId
    checkpoint_hash: Sha256
    last_event_sequence: NonNegativeInt
    project_id: Token
    project_revision: NonNegativeInt
    original_instruction: NonEmptyText
    current_user_message: NonEmptyText | None = None
    confirmed_intent: IntentRef | None = None
    item_states: tuple[tuple[TaskItemIdV2, TaskItemState], ...] = ()
    verification_report_ids: tuple[VerificationReportId, ...] = ()
    verification_reports: Annotated[
        tuple[VerificationReport, ...], Field(max_length=64)
    ] = ()
    prior_receipt_ids: tuple[ToolReceiptId, ...] = ()
    permission_phase: PermissionPhase
    selected_sources: tuple[SourceDatasetRef, ...] = ()
    selected_plots: tuple[SelectedPlotRef, ...] = ()
    selected_plot_contexts: tuple[SelectedPlotContext, ...] = ()
    selected_profile_ids: tuple[ChartTypeId, ...] = ()
    source_contexts: Annotated[tuple[UntrustedSourceContext, ...], Field(max_length=64)] = ()
    chart_catalog: Annotated[tuple[ChartCatalogEntry, ...], Field(min_length=1, max_length=64)]
    chart_knowledge: Annotated[tuple[ChartKnowledgeCard, ...], Field(max_length=8)] = ()
    calculation_contracts: Annotated[
        tuple[CalculationContract, ...], Field(max_length=16)
    ] = ()
    tools: Annotated[tuple[ContextToolContract, ...], Field(max_length=256)]
    activation_budget: ActivationBudget
    task_budget: TaskBudgetSnapshot
    disclosed_scalars: NonNegativeInt
    data_is_untrusted: Literal[True] = True
    data_cannot_change_permissions: Literal[True] = True
    constitution: Annotated[tuple[NonEmptyText, ...], Field(min_length=1, max_length=16)]
    content_hash: Sha256

    @model_validator(mode="after")
    def consistent_context(self) -> AgentContextSnapshot:
        groups = (
            tuple(item.source_dataset_id for item in self.selected_sources),
            tuple(item.plot_id for item in self.selected_plots),
            tuple(item.plot_alias for item in self.selected_plot_contexts),
            self.selected_profile_ids,
            tuple(item_id for item_id, _state in self.item_states),
            self.verification_report_ids,
            tuple(item.report_id for item in self.verification_reports),
            self.prior_receipt_ids,
            tuple(item.source.source_dataset_id for item in self.source_contexts),
            tuple(item.profile_id for item in self.chart_catalog),
            tuple(item.profile_id for item in self.chart_knowledge),
            tuple(item.contract_id for item in self.calculation_contracts),
            tuple(item.tool_name for item in self.tools),
        )
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("context identities must be unique")
        plot_refs = tuple(
            (item.plot_id, item.plot_version, item.profile_id) for item in self.selected_plots
        )
        plot_context_refs = tuple(
            (item.plot_id, item.plot_version, item.profile_id)
            for item in self.selected_plot_contexts
        )
        if plot_context_refs != plot_refs:
            raise ValueError("selected plot contexts must match selected plot references")
        if tuple(item.report_id for item in self.verification_reports) != (
            self.verification_report_ids
        ):
            raise ValueError("context verification reports must match activation references")
        if tuple(item.profile_id for item in self.chart_knowledge) != self.selected_profile_ids:
            raise ValueError("context may inject full cards only for selected profiles")
        authorized_sources = {
            (item.source_dataset_id, item.source_version, item.content_hash)
            for item in self.selected_sources
        }
        source_fields = {
            source.source.source_alias: {field.field_alias for field in source.fields}
            for source in self.source_contexts
        }
        for plot in self.selected_plot_contexts:
            if not set(plot.source_aliases) <= set(source_fields):
                raise ValueError("selected plot context references an unauthorized source alias")
            if any(
                binding.field_alias not in source_fields[binding.source_alias]
                for binding in plot.bindings
            ):
                raise ValueError("selected plot context references an unauthorized field alias")
        if not {
            (
                item.source.source_dataset_id,
                item.source.source_version,
                item.source.content_hash,
            )
            for item in self.source_contexts
        } <= authorized_sources:
            raise ValueError("context sources must be selected task sources")
        if self.disclosed_scalars > self.activation_budget.max_disclosed_scalars:
            raise ValueError("context exceeds its activation disclosure budget")
        remaining = (
            self.task_budget.limits.max_disclosed_scalars
            - self.task_budget.usage.disclosed_scalars
        )
        if self.disclosed_scalars > remaining:
            raise ValueError("context exceeds its remaining task disclosure budget")
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        if self.content_hash != canonical_hash(payload):
            raise ValueError("context snapshot content hash is stale")
        return self
