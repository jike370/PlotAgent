"""Typed tool contracts for the PlotAgent-controlled Agent gateway."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, JsonValue, StringConstraints, model_validator

from plotagent.contracts.agent_tasks import (
    AgentActivationId,
    ExecutionGrantId,
    IsoTimestamp,
    PermissionPhase,
    SideEffectReceipt,
    TaskId,
    TaskItemIdV2,
    TaskState,
    VerificationReportId,
)
from plotagent.contracts.base import (
    NonEmptyText,
    NonNegativeInt,
    Sha256,
    StrictModel,
    Token,
    VersionId,
)

ToolCallId = Annotated[
    str,
    StringConstraints(pattern=r"^toolcall:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
ToolContractId = Annotated[
    str,
    StringConstraints(pattern=r"^tool:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]

ToolSideEffect = Literal["none", "staged", "committed", "unknown"]
ToolContractSideEffect = Literal["none", "staged", "committed", "expanded_risk"]
ToolCostClass = Literal["cheap", "moderate", "expensive"]
ToolErrorCategory = Literal[
    "AGENT_REPAIRABLE",
    "USER_INPUT_REQUIRED",
    "TRANSIENT",
    "UNSUPPORTED",
    "FATAL",
]


class ToolContract(StrictModel):
    schema_version: Literal["tool-contract.v2"] = "tool-contract.v2"
    contract_id: ToolContractId
    contract_version: VersionId
    tool_name: Token
    description: NonEmptyText
    permission_phase: PermissionPhase
    side_effect: ToolContractSideEffect
    allowed_task_states: Annotated[tuple[TaskState, ...], Field(min_length=1, max_length=16)]
    input_schema_hash: Sha256
    output_schema_hash: Sha256
    cost_class: ToolCostClass
    timeout_ms: Annotated[int, Field(ge=100, le=3_600_000)]
    max_disclosed_scalars: NonNegativeInt = 0
    uses_origin: bool = False

    @model_validator(mode="after")
    def coherent_contract(self) -> ToolContract:
        expected_phase = {
            "none": "p0_read",
            "staged": "p1_staged",
            "committed": "p2_confirmed",
            "expanded_risk": "p3_expanded",
        }[self.side_effect]
        if self.permission_phase != expected_phase:
            raise ValueError("tool side effect must match its minimum permission phase")
        if len(self.allowed_task_states) != len(set(self.allowed_task_states)):
            raise ValueError("tool task states must be unique")
        if self.uses_origin and self.cost_class == "cheap":
            raise ValueError("Origin tools cannot be classified as cheap")
        return self


class ToolInvocation(StrictModel):
    schema_version: Literal["tool-invocation.v2"] = "tool-invocation.v2"
    tool_call_id: ToolCallId
    task_id: TaskId
    task_version: VersionId
    activation_id: AgentActivationId
    item_id: TaskItemIdV2 | None = None
    execution_grant_id: ExecutionGrantId | None = None
    idempotency_key: Token | None = None
    tool_name: Token
    permission_phase: PermissionPhase
    arguments_hash: Sha256
    activation_tool_calls_before: NonNegativeInt
    activation_disclosed_scalars_before: NonNegativeInt
    expected_project_revision: NonNegativeInt = 0
    deadline: IsoTimestamp

    @model_validator(mode="after")
    def authority_fields_match_phase(self) -> ToolInvocation:
        if self.permission_phase == "p0_read":
            if self.execution_grant_id is not None:
                raise ValueError("read-only tools cannot carry an execution grant")
        elif self.idempotency_key is None:
            raise ValueError("staged and committed tools require an idempotency key")
        if self.permission_phase in {"p2_confirmed", "p3_expanded"} and (
            self.execution_grant_id is None or self.item_id is None
        ):
            raise ValueError("committed tools require an item-scoped execution grant")
        if self.permission_phase == "p1_staged" and self.execution_grant_id is not None:
            raise ValueError("staged tools cannot carry a formal execution grant")
        return self


class ToolProvenance(StrictModel):
    source_id: Token
    source_version: VersionId | None = None
    content_hash: Sha256 | None = None
    coordinate: Annotated[str, StringConstraints(max_length=256, strict=True)] | None = None


class ToolWarning(StrictModel):
    code: Token
    message: NonEmptyText


class AgentToolError(StrictModel):
    code: Token
    category: ToolErrorCategory
    message: NonEmptyText
    retryable: bool
    requires_user: bool
    repair_hint: NonEmptyText | None = None
    side_effect_state: ToolSideEffect
    diagnostic_id: Token | None = None

    @model_validator(mode="after")
    def category_matches_flags(self) -> AgentToolError:
        if self.category == "USER_INPUT_REQUIRED" and not self.requires_user:
            raise ValueError("user-input tool errors must require the user")
        if self.category == "UNSUPPORTED" and self.retryable:
            raise ValueError("unsupported tool errors cannot be retryable")
        if self.category == "FATAL" and self.retryable:
            raise ValueError("fatal tool errors cannot be retryable")
        return self


class AgentToolResult(StrictModel):
    schema_version: Literal["agent-tool-result.v2"] = "agent-tool-result.v2"
    tool_call_id: ToolCallId
    task_id: TaskId
    task_version: VersionId
    activation_id: AgentActivationId
    tool_name: Token
    status: Literal["succeeded", "failed"]
    summary: NonEmptyText
    payload: JsonValue | None = None
    output_hash: Sha256 | None = None
    output_handle: Token | None = None
    provenance: Annotated[tuple[ToolProvenance, ...], Field(max_length=128)] = ()
    verification_report_ids: Annotated[
        tuple[VerificationReportId, ...], Field(max_length=64)
    ] = ()
    warnings: Annotated[tuple[ToolWarning, ...], Field(max_length=64)] = ()
    side_effect: ToolSideEffect
    side_effects: Annotated[tuple[SideEffectReceipt, ...], Field(max_length=128)] = ()
    disclosed_field_count: NonNegativeInt = 0
    disclosed_row_count: NonNegativeInt = 0
    disclosed_scalar_count: NonNegativeInt = 0
    error: AgentToolError | None = None
    started_at: IsoTimestamp
    completed_at: IsoTimestamp

    @model_validator(mode="after")
    def status_matches_payload_and_error(self) -> AgentToolResult:
        if self.completed_at < self.started_at:
            raise ValueError("tool completion cannot precede its start")
        groups = (
            tuple((item.source_id, item.coordinate) for item in self.provenance),
            self.verification_report_ids,
            tuple(item.code for item in self.warnings),
        )
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("tool result references must be unique")
        if self.status == "succeeded":
            if self.error is not None or self.payload is None or self.output_hash is None:
                raise ValueError("successful tool results require payload/hash and no error")
            if self.side_effect == "unknown":
                raise ValueError("successful tool results cannot have unknown side effects")
        elif self.error is None or self.payload is not None or self.output_hash is not None:
            raise ValueError("failed tool results require only a structured error")
        if self.status == "failed" and any(
            (
                self.disclosed_field_count,
                self.disclosed_row_count,
                self.disclosed_scalar_count,
            )
        ):
            raise ValueError("failed tool results cannot claim disclosed data")
        if self.error is not None and self.error.side_effect_state != self.side_effect:
            raise ValueError("tool error and result side-effect states must match")
        non_empty_effects = tuple(
            effect for effect in self.side_effects if effect.effect_kind != "none"
        )
        if self.side_effect == "none" and non_empty_effects:
            raise ValueError("read-only tool results cannot retain side-effect receipts")
        if self.status == "succeeded" and self.side_effect != "none" and not non_empty_effects:
            raise ValueError("successful side-effecting tools require concrete receipts")
        return self
