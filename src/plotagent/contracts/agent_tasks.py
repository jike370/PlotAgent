"""Durable task protocol for the PlotAgent v2 Agent foundation.

These contracts deliberately contain no runtime implementation.  Core will
own their state transitions in a later construction phase; Pi and the desktop
may only exchange the versioned projections defined here.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, TypeAdapter, model_validator

from plotagent.contracts.base import (
    NonEmptyText,
    NonNegativeInt,
    ResourceRef,
    Sha256,
    SourceDatasetRef,
    StrictModel,
    Token,
    VersionId,
)
from plotagent.contracts.workflows import InputQuestion, TaskDraftItem

TaskId = Annotated[
    str,
    StringConstraints(pattern=r"^task:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
TaskItemIdV2 = Annotated[
    str,
    StringConstraints(pattern=r"^item:[A-Za-z0-9][A-Za-z0-9._-]{0,191}$", strict=True),
]
TaskIntentId = Annotated[
    str,
    StringConstraints(pattern=r"^intent:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
AgentActivationId = Annotated[
    str,
    StringConstraints(pattern=r"^activation:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
ExecutionGrantId = Annotated[
    str,
    StringConstraints(pattern=r"^grant:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
ToolReceiptId = Annotated[
    str,
    StringConstraints(pattern=r"^receipt:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
VerificationReportId = Annotated[
    str,
    StringConstraints(pattern=r"^verification:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
TaskEventId = Annotated[
    str,
    StringConstraints(pattern=r"^event:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
TaskCheckpointId = Annotated[
    str,
    StringConstraints(pattern=r"^checkpoint:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
IsoTimestamp = Annotated[
    str,
    StringConstraints(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$",
        strict=True,
    ),
]

TaskState = Literal[
    "created",
    "investigating",
    "awaiting_input",
    "intent_staged",
    "awaiting_confirmation",
    "executing",
    "verifying",
    "repairing",
    "awaiting_reconfirmation",
    "delivering",
    "partial",
    "blocked",
    "unsupported",
    "cancelling",
    "cancelled",
    "rejected",
    "failed",
    "completed_verified",
]
TaskItemState = Literal[
    "pending",
    "staged",
    "running",
    "succeeded",
    "repairable_failed",
    "failed",
    "blocked",
    "cancelled",
]
AgentActivationReason = Literal[
    "new_task",
    "user_answered",
    "user_corrected",
    "verification_failed",
    "external_blocker_cleared",
    "resume_after_restart",
]
PermissionPhase = Literal["p0_read", "p1_staged", "p2_confirmed", "p3_expanded"]


class TaskBudgetLimits(StrictModel):
    """Task-wide ceilings chosen by Core before Agent execution."""

    max_model_calls: Annotated[int, Field(ge=1, le=256)] = 24
    max_model_turns: Annotated[int, Field(ge=1, le=512)] = 64
    max_input_tokens: Annotated[int, Field(ge=1, le=100_000_000)] = 1_000_000
    max_output_tokens: Annotated[int, Field(ge=1, le=10_000_000)] = 200_000
    max_tool_calls: Annotated[int, Field(ge=1, le=10_000)] = 256
    max_disclosed_scalars: Annotated[int, Field(ge=1, le=10_000_000)] = 200_000
    max_origin_sessions: Annotated[int, Field(ge=0, le=512)] = 16
    max_repair_attempts: Annotated[int, Field(ge=0, le=128)] = 8
    max_wall_time_ms: Annotated[int, Field(ge=1_000, le=604_800_000)] | None = None
    max_estimated_cost: Annotated[float, Field(ge=0, le=1_000_000, allow_inf_nan=False)] = 0


class TaskBudgetUsage(StrictModel):
    model_calls: NonNegativeInt = 0
    model_turns: NonNegativeInt = 0
    input_tokens: NonNegativeInt = 0
    output_tokens: NonNegativeInt = 0
    tool_calls: NonNegativeInt = 0
    disclosed_scalars: NonNegativeInt = 0
    origin_sessions: NonNegativeInt = 0
    repair_attempts: NonNegativeInt = 0
    wall_time_ms: NonNegativeInt = 0
    estimated_cost: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0


class TaskBudgetSnapshot(StrictModel):
    limits: TaskBudgetLimits
    usage: TaskBudgetUsage = TaskBudgetUsage()

    @model_validator(mode="after")
    def usage_within_limits(self) -> TaskBudgetSnapshot:
        pairs = (
            (self.usage.model_calls, self.limits.max_model_calls),
            (self.usage.model_turns, self.limits.max_model_turns),
            (self.usage.input_tokens, self.limits.max_input_tokens),
            (self.usage.output_tokens, self.limits.max_output_tokens),
            (self.usage.tool_calls, self.limits.max_tool_calls),
            (self.usage.disclosed_scalars, self.limits.max_disclosed_scalars),
            (self.usage.origin_sessions, self.limits.max_origin_sessions),
            (self.usage.repair_attempts, self.limits.max_repair_attempts),
            (self.usage.estimated_cost, self.limits.max_estimated_cost),
        )
        if any(used > limit for used, limit in pairs) or (
            self.limits.max_wall_time_ms is not None
            and self.usage.wall_time_ms > self.limits.max_wall_time_ms
        ):
            raise ValueError("task budget usage cannot exceed its limits")
        return self


class ActivationBudget(StrictModel):
    max_model_turns: Annotated[int, Field(ge=1, le=32)] = 10
    max_tool_calls: Annotated[int, Field(ge=0, le=128)] = 24
    max_disclosed_scalars: Annotated[int, Field(ge=0, le=200_000)] = 20_000
    timeout_ms: Annotated[int, Field(ge=1_000, le=3_600_000)] | None = None


class SelectedPlotRef(StrictModel):
    plot_id: Token
    plot_version: VersionId
    profile_id: Token


class TaskEnvelope(StrictModel):
    schema_version: Literal["task-envelope.v2"] = "task-envelope.v2"
    task_id: TaskId
    task_version: VersionId
    project_id: Token
    project_revision: NonNegativeInt
    original_instruction: NonEmptyText
    parent_task_id: TaskId | None = None
    relationship: Literal["follow_up"] | None = None
    locale: Literal["zh-CN", "en-US"] = "zh-CN"
    selected_sources: Annotated[tuple[SourceDatasetRef, ...], Field(max_length=64)] = ()
    selected_plots: Annotated[tuple[SelectedPlotRef, ...], Field(max_length=64)] = ()
    selected_profile_ids: Annotated[tuple[Token, ...], Field(max_length=64)] = ()
    authorized_resources: Annotated[tuple[ResourceRef, ...], Field(max_length=128)] = ()
    budget: TaskBudgetLimits
    created_at: IsoTimestamp

    @model_validator(mode="after")
    def selections_are_unique(self) -> TaskEnvelope:
        if (self.parent_task_id is None) != (self.relationship is None):
            raise ValueError("follow-up task linkage must include both parent and relationship")
        if self.parent_task_id == self.task_id:
            raise ValueError("a task cannot follow up itself")
        groups = (
            tuple(item.source_dataset_id for item in self.selected_sources),
            tuple(item.plot_id for item in self.selected_plots),
            self.selected_profile_ids,
            tuple(item.resource_id for item in self.authorized_resources),
        )
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("task envelope selections must be unique")
        if not self.selected_sources and not self.selected_plots:
            raise ValueError("task envelope needs at least one selected source or plot")
        return self


class SemanticDecision(StrictModel):
    decision_id: Token
    kind: Literal[
        "profile",
        "field_binding",
        "unit",
        "ordering",
        "filter",
        "aggregation",
        "calculation",
        "visual",
        "output",
    ]
    summary: NonEmptyText
    evidence_refs: Annotated[tuple[Token, ...], Field(max_length=64)] = ()


class TaskIntent(StrictModel):
    schema_version: Literal["task-intent.v2"] = "task-intent.v2"
    intent_id: TaskIntentId
    intent_version: VersionId
    task_id: TaskId
    task_version: VersionId
    created_by_activation_id: AgentActivationId
    summary: NonEmptyText
    items: Annotated[tuple[TaskDraftItem, ...], Field(min_length=1, max_length=64)]
    semantic_decisions: Annotated[tuple[SemanticDecision, ...], Field(max_length=256)] = ()
    context_hash: Sha256
    content_hash: Sha256

    @model_validator(mode="after")
    def item_identity_is_unique(self) -> TaskIntent:
        item_ids = tuple(item.item_id for item in self.items)
        plot_aliases = tuple(item.plot_alias for item in self.items)
        decision_ids = tuple(item.decision_id for item in self.semantic_decisions)
        if len(item_ids) != len(set(item_ids)) or len(plot_aliases) != len(set(plot_aliases)):
            raise ValueError("task intent item identities must be unique")
        if len(decision_ids) != len(set(decision_ids)):
            raise ValueError("task intent semantic decisions must be unique")
        return self


class IntentRef(StrictModel):
    intent_id: TaskIntentId
    intent_version: VersionId
    content_hash: Sha256


class ExecutionScope(StrictModel):
    item_id: TaskItemIdV2
    operations: Annotated[tuple[Token, ...], Field(min_length=1, max_length=128)]
    target_object_ids: Annotated[tuple[Token, ...], Field(max_length=128)] = ()
    output_resources: Annotated[tuple[ResourceRef, ...], Field(max_length=64)] = ()

    @model_validator(mode="after")
    def scope_values_are_unique(self) -> ExecutionScope:
        groups = (
            self.operations,
            self.target_object_ids,
            tuple(item.resource_id for item in self.output_resources),
        )
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("execution scope values must be unique")
        return self


class ExecutionGrant(StrictModel):
    schema_version: Literal["execution-grant.v2"] = "execution-grant.v2"
    grant_id: ExecutionGrantId
    task_id: TaskId
    task_version: VersionId
    intent: IntentRef
    expected_project_revision: NonNegativeInt
    permission_phase: Literal["p2_confirmed", "p3_expanded"]
    scopes: Annotated[tuple[ExecutionScope, ...], Field(min_length=1, max_length=64)]
    issued_at: IsoTimestamp
    expires_at: IsoTimestamp | None = None
    content_hash: Sha256

    @model_validator(mode="after")
    def item_scopes_are_unique(self) -> ExecutionGrant:
        item_ids = tuple(scope.item_id for scope in self.scopes)
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("execution grant item scopes must be unique")
        if self.expires_at is not None and self.expires_at <= self.issued_at:
            raise ValueError("execution grant expiry must follow issuance")
        return self


class SideEffectReceipt(StrictModel):
    effect_kind: Literal[
        "none",
        "project_revision",
        "plot_version",
        "staged_data_view",
        "staged_plot",
        "staged_file",
        "published_file",
        "origin_session",
    ]
    object_id: Token | None = None
    object_version: VersionId | None = None
    resource: ResourceRef | None = None
    artifact_hash: Sha256 | None = None
    reversible: bool = True

    @model_validator(mode="after")
    def required_identity_matches_kind(self) -> SideEffectReceipt:
        if self.effect_kind == "none":
            if any(
                value is not None
                for value in (
                    self.object_id,
                    self.object_version,
                    self.resource,
                    self.artifact_hash,
                )
            ):
                raise ValueError("a no-effect receipt cannot retain object or artifact identity")
            return self
        if self.effect_kind in {
            "project_revision",
            "plot_version",
            "staged_data_view",
            "staged_plot",
            "origin_session",
        } and self.object_id is None:
            raise ValueError("object side effects require object_id")
        if self.effect_kind == "plot_version" and self.object_version is None:
            raise ValueError("plot side effects require object_version")
        if self.effect_kind in {"staged_data_view", "staged_plot"} and (
            self.object_version is None or self.artifact_hash is None
        ):
            raise ValueError("staged object side effects require version and artifact hash")
        if self.effect_kind in {"staged_file", "published_file"} and (
            self.resource is None or self.artifact_hash is None
        ):
            raise ValueError("file side effects require resource and artifact_hash")
        return self


class TaskError(StrictModel):
    code: Token
    category: Literal[
        "transient_external",
        "deterministic_technical",
        "semantic_conflict",
        "stale_or_concurrent",
        "unsupported",
        "safety_or_permission",
        "budget",
        "runtime",
    ]
    message: NonEmptyText
    retryable: bool
    requires_user: bool
    side_effect_state: Literal["known_none", "known_applied", "unknown"]
    diagnostic_id: Token | None = None

    @model_validator(mode="after")
    def category_matches_recovery_flags(self) -> TaskError:
        if (
            self.category in {"semantic_conflict", "safety_or_permission"}
            and not self.requires_user
        ):
            raise ValueError("semantic and permission errors require user involvement")
        if self.category in {"unsupported", "safety_or_permission"} and self.retryable:
            raise ValueError("unsupported and permission errors cannot be blindly retried")
        return self


class ToolReceipt(StrictModel):
    schema_version: Literal["tool-receipt.v2"] = "tool-receipt.v2"
    receipt_id: ToolReceiptId
    task_id: TaskId
    task_version: VersionId
    activation_id: AgentActivationId | None = None
    item_id: TaskItemIdV2 | None = None
    tool_call_id: Token
    tool_name: Token
    permission_phase: PermissionPhase
    outcome: Literal["succeeded", "failed", "cancelled", "unknown"]
    idempotency_key: Token | None = None
    input_hash: Sha256
    output_hash: Sha256 | None = None
    project_revision_before: NonNegativeInt
    project_revision_after: NonNegativeInt
    side_effects: Annotated[tuple[SideEffectReceipt, ...], Field(max_length=128)] = ()
    budget_delta: TaskBudgetUsage = TaskBudgetUsage(tool_calls=1)
    error: TaskError | None = None
    started_at: IsoTimestamp
    finished_at: IsoTimestamp

    @model_validator(mode="after")
    def outcome_metadata_is_consistent(self) -> ToolReceipt:
        if self.finished_at < self.started_at:
            raise ValueError("tool receipt cannot finish before it starts")
        if self.outcome == "succeeded":
            if self.error is not None or self.output_hash is None:
                raise ValueError("successful tool receipts require output_hash and no error")
        elif self.outcome == "failed":
            if self.error is None:
                raise ValueError("failed tool receipts require an error")
        elif self.error is not None and self.outcome == "cancelled":
            raise ValueError("cancelled tool receipts do not retain a failure error")
        if self.project_revision_after < self.project_revision_before:
            raise ValueError("tool receipts cannot move a project revision backwards")
        if self.permission_phase in {"p0_read", "p1_staged"} and (
            self.project_revision_after != self.project_revision_before
        ):
            raise ValueError("read and staged tools cannot change the project revision")
        non_empty_effects = tuple(
            effect for effect in self.side_effects if effect.effect_kind != "none"
        )
        if self.outcome == "succeeded" and self.permission_phase != "p0_read" and not (
            non_empty_effects
        ):
            raise ValueError("successful side-effecting receipts require concrete effects")
        if self.outcome == "succeeded" and self.permission_phase in {
            "p2_confirmed",
            "p3_expanded",
        } and self.project_revision_after <= self.project_revision_before:
            raise ValueError("successful committed receipts must advance project revision")
        if (
            non_empty_effects and self.idempotency_key is None
        ):
            raise ValueError("side-effecting tool receipts require an idempotency key")
        if self.budget_delta.tool_calls != 1:
            raise ValueError("one tool receipt must account for exactly one tool call")
        if any(
            (
                self.budget_delta.model_calls,
                self.budget_delta.model_turns,
                self.budget_delta.input_tokens,
                self.budget_delta.output_tokens,
                self.budget_delta.repair_attempts,
            )
        ) or self.budget_delta.estimated_cost != 0:
            raise ValueError("tool receipts may account only for tool resource usage")
        if self.budget_delta.origin_sessions > 1:
            raise ValueError("one tool call may open at most one Origin session")
        return self


class VerificationEvidenceRef(StrictModel):
    evidence_id: Token
    evidence_kind: Literal[
        "task_state",
        "data_snapshot",
        "plot_document",
        "backend_readback",
        "artifact",
        "fresh_reopen",
        "visual_review",
        "tool_receipt",
    ]
    content_hash: Sha256


class VerificationClaim(StrictModel):
    claim_id: Token
    requirement: Literal["required", "advisory"] = "required"
    status: Literal["passed", "failed", "blocked", "unknown"]
    expected: NonEmptyText
    observed: NonEmptyText
    evidence: Annotated[tuple[VerificationEvidenceRef, ...], Field(max_length=128)] = ()
    repair_scope: Annotated[tuple[Token, ...], Field(max_length=128)] = ()
    error: TaskError | None = None

    @model_validator(mode="after")
    def claim_metadata_matches_status(self) -> VerificationClaim:
        if self.status == "passed" and self.error is not None:
            raise ValueError("passed verification claims cannot retain errors")
        if self.status == "failed" and self.error is None:
            raise ValueError("failed verification claims require an error")
        if self.status != "failed" and self.repair_scope:
            raise ValueError("only failed verification claims may declare repair scope")
        return self


class VerificationReport(StrictModel):
    schema_version: Literal["verification-report.v2"] = "verification-report.v2"
    report_id: VerificationReportId
    task_id: TaskId
    task_version: VersionId
    intent: IntentRef
    item_id: TaskItemIdV2 | None = None
    status: Literal["passed", "failed", "blocked", "unknown"]
    claims: Annotated[tuple[VerificationClaim, ...], Field(min_length=1, max_length=512)]
    content_hash: Sha256
    verified_at: IsoTimestamp

    @model_validator(mode="after")
    def aggregate_status_matches_required_claims(self) -> VerificationReport:
        required = tuple(claim.status for claim in self.claims if claim.requirement == "required")
        if not required:
            raise ValueError("verification reports need at least one required claim")
        expected = (
            "failed"
            if "failed" in required
            else "blocked"
            if "blocked" in required
            else "unknown"
            if "unknown" in required
            else "passed"
        )
        if self.status != expected:
            raise ValueError("verification report status must match its required claims")
        claim_ids = tuple(claim.claim_id for claim in self.claims)
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("verification report claim ids must be unique")
        return self


class AgentActivation(StrictModel):
    schema_version: Literal["agent-activation.v2"] = "agent-activation.v2"
    activation_id: AgentActivationId
    task_id: TaskId
    task_version: VersionId
    reason: AgentActivationReason
    task_state: TaskState
    original_instruction: NonEmptyText
    current_user_message: NonEmptyText | None = None
    confirmed_intent: IntentRef | None = None
    item_states: Annotated[
        tuple[tuple[TaskItemIdV2, TaskItemState], ...], Field(max_length=64)
    ] = ()
    context_refs: Annotated[tuple[Token, ...], Field(max_length=256)] = ()
    domain_knowledge_refs: Annotated[tuple[Token, ...], Field(max_length=128)] = ()
    verification_report_ids: Annotated[
        tuple[VerificationReportId, ...], Field(max_length=128)
    ] = ()
    prior_receipt_ids: Annotated[tuple[ToolReceiptId, ...], Field(max_length=512)] = ()
    # A fully specified activation may need no ordinary tools. The Pi runtime
    # exposes the Core-validated terminal yield tool separately.
    allowed_tools: Annotated[tuple[Token, ...], Field(max_length=256)]
    permission_phase: PermissionPhase
    activation_budget: ActivationBudget
    task_budget: TaskBudgetSnapshot
    deadline: IsoTimestamp | None = None
    created_at: IsoTimestamp

    @model_validator(mode="after")
    def activation_matches_reason_and_state(self) -> AgentActivation:
        item_ids = tuple(item_id for item_id, _state in self.item_states)
        groups = (
            item_ids,
            self.context_refs,
            self.domain_knowledge_refs,
            self.verification_report_ids,
            self.prior_receipt_ids,
            self.allowed_tools,
        )
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("agent activation references and tools must be unique")
        if self.deadline is not None and self.deadline <= self.created_at:
            raise ValueError("agent activation deadline must follow creation")
        if self.reason == "verification_failed" and not self.verification_report_ids:
            raise ValueError("verification repair activations need a verification report")
        if self.reason in {"user_answered", "user_corrected"} and (
            self.current_user_message is None
        ):
            raise ValueError("answer and correction activations need the user's message")
        if self.reason == "new_task" and self.task_state != "created":
            raise ValueError("new task activations must start from created")
        return self


class AgentIntentReady(StrictModel):
    outcome: Literal["intent_ready"] = "intent_ready"
    activation_id: AgentActivationId
    task_id: TaskId
    task_version: VersionId
    intent: TaskIntent

    @model_validator(mode="after")
    def intent_matches_activation(self) -> AgentIntentReady:
        if (
            self.intent.task_id != self.task_id
            or self.intent.task_version != self.task_version
            or self.intent.created_by_activation_id != self.activation_id
        ):
            raise ValueError("intent yield must match its task and activation")
        return self


class AgentNeedsInput(StrictModel):
    outcome: Literal["needs_input"] = "needs_input"
    activation_id: AgentActivationId
    task_id: TaskId
    task_version: VersionId
    questions: Annotated[tuple[InputQuestion, ...], Field(min_length=1, max_length=4)]


class RepairProposal(StrictModel):
    failed_report_ids: Annotated[
        tuple[VerificationReportId, ...], Field(min_length=1, max_length=64)
    ]
    affected_item_ids: Annotated[tuple[TaskItemIdV2, ...], Field(min_length=1, max_length=64)]
    repair_operations: Annotated[tuple[Token, ...], Field(min_length=1, max_length=128)]
    preserves_confirmed_semantics: Literal[True] = True
    proposal_hash: Sha256

    @model_validator(mode="after")
    def repair_values_are_unique(self) -> RepairProposal:
        groups = (self.failed_report_ids, self.affected_item_ids, self.repair_operations)
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("repair proposal values must be unique")
        return self


class AgentTechnicalRepairReady(StrictModel):
    outcome: Literal["technical_repair_ready"] = "technical_repair_ready"
    activation_id: AgentActivationId
    task_id: TaskId
    task_version: VersionId
    proposal: RepairProposal


class AgentUnsupported(StrictModel):
    outcome: Literal["unsupported"] = "unsupported"
    activation_id: AgentActivationId
    task_id: TaskId
    task_version: VersionId
    reason_code: Token
    message: NonEmptyText
    alternatives: Annotated[tuple[NonEmptyText, ...], Field(max_length=8)] = ()


class AgentBlocked(StrictModel):
    outcome: Literal["blocked"] = "blocked"
    activation_id: AgentActivationId
    task_id: TaskId
    task_version: VersionId
    blocker_code: Token
    message: NonEmptyText
    resume_condition: NonEmptyText
    retryable: bool


class AgentBudgetExhausted(StrictModel):
    outcome: Literal["budget_exhausted"] = "budget_exhausted"
    activation_id: AgentActivationId
    task_id: TaskId
    task_version: VersionId
    exhausted_budget: Literal[
        "model_calls",
        "model_turns",
        "input_tokens",
        "output_tokens",
        "tool_calls",
        "disclosed_scalars",
        "origin_sessions",
        "repair_attempts",
        "wall_time",
        "estimated_cost",
    ]
    message: NonEmptyText


class AgentCancelled(StrictModel):
    outcome: Literal["cancelled"] = "cancelled"
    activation_id: AgentActivationId
    task_id: TaskId
    task_version: VersionId
    message: NonEmptyText


class AgentRuntimeFailed(StrictModel):
    outcome: Literal["runtime_failed"] = "runtime_failed"
    activation_id: AgentActivationId
    task_id: TaskId
    task_version: VersionId
    error: TaskError

    @model_validator(mode="after")
    def error_is_a_runtime_failure(self) -> AgentRuntimeFailed:
        if self.error.category != "runtime":
            raise ValueError("runtime failure yields require a runtime error")
        return self


AgentYield = Annotated[
    AgentIntentReady
    | AgentNeedsInput
    | AgentTechnicalRepairReady
    | AgentUnsupported
    | AgentBlocked
    | AgentBudgetExhausted
    | AgentCancelled
    | AgentRuntimeFailed,
    Field(discriminator="outcome"),
]


class TaskItemSnapshot(StrictModel):
    item_id: TaskItemIdV2
    state: TaskItemState
    attempt_count: Annotated[int, Field(ge=0, le=128)] = 0
    last_error: TaskError | None = None
    output_plot_id: Token | None = None
    output_plot_version: VersionId | None = None
    receipt_ids: Annotated[tuple[ToolReceiptId, ...], Field(max_length=512)] = ()
    verification_report_ids: Annotated[
        tuple[VerificationReportId, ...], Field(max_length=256)
    ] = ()

    @model_validator(mode="after")
    def item_metadata_matches_state(self) -> TaskItemSnapshot:
        if self.state in {"repairable_failed", "failed", "blocked"} and self.last_error is None:
            raise ValueError("failed and blocked task items require an error")
        if self.state not in {"repairable_failed", "failed", "blocked"} and self.last_error:
            raise ValueError("non-failed task items cannot retain an error")
        if (self.output_plot_id is None) != (self.output_plot_version is None):
            raise ValueError("task item plot identity and version must appear together")
        if len(self.receipt_ids) != len(set(self.receipt_ids)) or len(
            self.verification_report_ids
        ) != len(set(self.verification_report_ids)):
            raise ValueError("task item receipt and verification ids must be unique")
        return self


class TaskCompletion(StrictModel):
    completed_at: IsoTimestamp
    final_project_revision: NonNegativeInt
    required_report_ids: Annotated[
        tuple[VerificationReportId, ...], Field(min_length=1, max_length=512)
    ]
    artifact_receipt_ids: Annotated[tuple[ToolReceiptId, ...], Field(max_length=512)] = ()

    @model_validator(mode="after")
    def evidence_ids_are_unique(self) -> TaskCompletion:
        if len(self.required_report_ids) != len(set(self.required_report_ids)) or len(
            self.artifact_receipt_ids
        ) != len(set(self.artifact_receipt_ids)):
            raise ValueError("task completion evidence ids must be unique")
        return self


class TaskCheckpoint(StrictModel):
    schema_version: Literal["task-checkpoint.v2"] = "task-checkpoint.v2"
    checkpoint_id: TaskCheckpointId
    task_id: TaskId
    task_version: VersionId
    state: TaskState
    project_revision: NonNegativeInt
    last_event_sequence: NonNegativeInt
    intent: IntentRef | None = None
    active_activation_id: AgentActivationId | None = None
    items: Annotated[tuple[TaskItemSnapshot, ...], Field(max_length=64)] = ()
    budget: TaskBudgetSnapshot
    completion: TaskCompletion | None = None
    updated_at: IsoTimestamp
    content_hash: Sha256

    @model_validator(mode="after")
    def completion_matches_state(self) -> TaskCheckpoint:
        item_ids = tuple(item.item_id for item in self.items)
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("task checkpoint item ids must be unique")
        if self.state == "completed_verified":
            if self.completion is None or not self.items:
                raise ValueError("completed tasks require completion evidence and task items")
            if any(item.state != "succeeded" for item in self.items):
                raise ValueError("completed tasks require every task item to succeed")
        elif self.completion is not None:
            raise ValueError("only completed tasks may retain completion evidence")
        if self.active_activation_id is not None and self.state not in {
            "created",
            "investigating",
            "repairing",
        }:
            raise ValueError("only agent-active task states may retain an activation")
        return self


TERMINAL_TASK_STATES: frozenset[TaskState] = frozenset(
    {"unsupported", "cancelled", "rejected", "failed", "completed_verified"}
)
ALLOWED_TASK_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    "created": frozenset({"investigating", "cancelling", "cancelled", "failed"}),
    "investigating": frozenset(
        {"awaiting_input", "intent_staged", "blocked", "unsupported", "cancelling", "failed"}
    ),
    "awaiting_input": frozenset({"investigating", "cancelling", "cancelled", "failed"}),
    "intent_staged": frozenset(
        {"awaiting_confirmation", "awaiting_reconfirmation", "investigating", "failed"}
    ),
    "awaiting_confirmation": frozenset(
        {"executing", "rejected", "investigating", "cancelling", "failed"}
    ),
    "executing": frozenset({"verifying", "partial", "blocked", "cancelling", "failed"}),
    "verifying": frozenset(
        {
            "delivering",
            "repairing",
            "awaiting_reconfirmation",
            "partial",
            "blocked",
            "cancelling",
            "failed",
        }
    ),
    "repairing": frozenset(
        {
            "executing",
            "verifying",
            "awaiting_reconfirmation",
            "partial",
            "blocked",
            "cancelling",
            "failed",
        }
    ),
    "awaiting_reconfirmation": frozenset(
        {"executing", "repairing", "rejected", "cancelling", "failed"}
    ),
    "delivering": frozenset(
        {"completed_verified", "repairing", "blocked", "partial", "cancelling", "failed"}
    ),
    "partial": frozenset(
        {
            "investigating",
            "executing",
            "verifying",
            "repairing",
            "delivering",
            "cancelling",
            "cancelled",
        }
    ),
    "blocked": frozenset(
        {
            "investigating",
            "executing",
            "verifying",
            "repairing",
            "delivering",
            "cancelling",
            "cancelled",
            "failed",
        }
    ),
    "unsupported": frozenset(),
    "cancelling": frozenset({"cancelled", "partial"}),
    "cancelled": frozenset(),
    "rejected": frozenset(),
    "failed": frozenset(),
    "completed_verified": frozenset(),
}

ALLOWED_TASK_ITEM_TRANSITIONS: dict[TaskItemState, frozenset[TaskItemState]] = {
    "pending": frozenset({"staged", "running", "blocked", "failed", "cancelled"}),
    "staged": frozenset({"running", "blocked", "failed", "cancelled"}),
    "running": frozenset(
        {"succeeded", "repairable_failed", "failed", "blocked", "cancelled"}
    ),
    "succeeded": frozenset(),
    "repairable_failed": frozenset({"running", "failed", "blocked", "cancelled"}),
    "failed": frozenset(),
    "blocked": frozenset({"pending", "running", "failed", "cancelled"}),
    "cancelled": frozenset(),
}


def is_legal_task_transition(previous: TaskState, next_state: TaskState) -> bool:
    return previous == next_state or next_state in ALLOWED_TASK_TRANSITIONS[previous]


def is_legal_task_item_transition(previous: TaskItemState, next_state: TaskItemState) -> bool:
    return previous == next_state or next_state in ALLOWED_TASK_ITEM_TRANSITIONS[previous]


class TaskEventBase(StrictModel):
    event_id: TaskEventId
    task_id: TaskId
    task_version: VersionId
    sequence: Annotated[int, Field(ge=1)]
    occurred_at: IsoTimestamp


class TaskStateTransitionEvent(TaskEventBase):
    event_type: Literal["task_state_transition"] = "task_state_transition"
    previous_state: TaskState
    next_state: TaskState
    reason_code: Token

    @model_validator(mode="after")
    def transition_is_legal(self) -> TaskStateTransitionEvent:
        if not is_legal_task_transition(self.previous_state, self.next_state):
            raise ValueError("illegal task state transition")
        return self


class TaskItemTransitionEvent(TaskEventBase):
    event_type: Literal["task_item_transition"] = "task_item_transition"
    item_id: TaskItemIdV2
    previous_state: TaskItemState
    next_state: TaskItemState
    reason_code: Token

    @model_validator(mode="after")
    def transition_is_legal(self) -> TaskItemTransitionEvent:
        if not is_legal_task_item_transition(self.previous_state, self.next_state):
            raise ValueError("illegal task item state transition")
        return self


class AgentActivationEvent(TaskEventBase):
    event_type: Literal["agent_activation"] = "agent_activation"
    activation_id: AgentActivationId
    phase: Literal["requested", "started", "yielded", "aborted", "runtime_failed"]
    yield_outcome: Literal[
        "intent_ready",
        "needs_input",
        "technical_repair_ready",
        "unsupported",
        "blocked",
        "budget_exhausted",
        "cancelled",
        "runtime_failed",
    ] | None = None

    @model_validator(mode="after")
    def yield_outcome_matches_phase(self) -> AgentActivationEvent:
        if (self.phase == "yielded") != (self.yield_outcome is not None):
            raise ValueError("only yielded activation events carry a yield outcome")
        return self


class UserTaskEvent(TaskEventBase):
    event_type: Literal["user_task_event"] = "user_task_event"
    action: Literal[
        "answered",
        "confirmed",
        "rejected",
        "corrected",
        "cancel_requested",
        "budget_extended",
        "partial_accepted",
        "resumed",
    ]
    user_event_id: Token
    payload_hash: Sha256
    message: NonEmptyText | None = None

    @model_validator(mode="after")
    def message_matches_action(self) -> UserTaskEvent:
        needs_message = self.action in {"answered", "corrected"}
        if needs_message != (self.message is not None):
            raise ValueError("answers and corrections alone carry user message text")
        return self


class ToolReceiptEvent(TaskEventBase):
    event_type: Literal["tool_receipt"] = "tool_receipt"
    receipt: ToolReceipt

    @model_validator(mode="after")
    def receipt_matches_task(self) -> ToolReceiptEvent:
        if (self.receipt.task_id, self.receipt.task_version) != (
            self.task_id,
            self.task_version,
        ):
            raise ValueError("tool receipt event must match its task version")
        return self


class VerificationReportEvent(TaskEventBase):
    event_type: Literal["verification_report"] = "verification_report"
    report: VerificationReport

    @model_validator(mode="after")
    def report_matches_task(self) -> VerificationReportEvent:
        if (self.report.task_id, self.report.task_version) != (
            self.task_id,
            self.task_version,
        ):
            raise ValueError("verification event must match its task version")
        return self


class TaskBudgetEvent(TaskEventBase):
    event_type: Literal["task_budget"] = "task_budget"
    budget: TaskBudgetSnapshot
    change_reason: Literal["usage", "user_extended", "policy_reduced", "reconciled"]


TaskEvent = Annotated[
    TaskStateTransitionEvent
    | TaskItemTransitionEvent
    | AgentActivationEvent
    | UserTaskEvent
    | ToolReceiptEvent
    | VerificationReportEvent
    | TaskBudgetEvent,
    Field(discriminator="event_type"),
]

AGENT_YIELD_ADAPTER: TypeAdapter[AgentYield] = TypeAdapter(AgentYield)
TASK_EVENT_ADAPTER: TypeAdapter[TaskEvent] = TypeAdapter(TaskEvent)
