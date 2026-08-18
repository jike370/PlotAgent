"""Schema-validating, permissioned gateway for PlotAgent Agent tools."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, TypedDict, cast

from pydantic import BaseModel, TypeAdapter, ValidationError

from plotagent.contracts.agent_tasks import (
    AgentActivation,
    ExecutionGrant,
    PermissionPhase,
    SideEffectReceipt,
    TaskBudgetUsage,
    TaskCheckpoint,
    TaskError,
    TaskState,
    ToolReceipt,
    VerificationReportId,
)
from plotagent.contracts.agent_tools import (
    AgentToolError,
    AgentToolResult,
    ToolContract,
    ToolContractSideEffect,
    ToolCostClass,
    ToolErrorCategory,
    ToolInvocation,
    ToolProvenance,
    ToolSideEffect,
    ToolWarning,
)
from plotagent.contracts.canonical import JsonValue, canonical_hash, canonical_json
from plotagent.contracts.domain_knowledge import ContextToolContract

_PHASE_ORDER = {
    "p0_read": 0,
    "p1_staged": 1,
    "p2_confirmed": 2,
    "p3_expanded": 3,
}
type _ContextSideEffect = Literal["none", "staged", "confirmed_write", "expanded_risk"]


class ToolGatewayError(ValueError):
    pass


class _FailureSpec(TypedDict):
    code: str
    category: ToolErrorCategory
    message: str
    retryable: bool
    requires_user: bool


class ToolExecutionProblem(ValueError):
    def __init__(
        self,
        *,
        code: str,
        category: ToolErrorCategory,
        message: str,
        retryable: bool,
        requires_user: bool,
        repair_hint: str | None = None,
        side_effect_state: ToolSideEffect = "none",
        diagnostic_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error = AgentToolError(
            code=code,
            category=category,
            message=message,
            retryable=retryable,
            requires_user=requires_user,
            repair_hint=repair_hint,
            side_effect_state=side_effect_state,
            diagnostic_id=diagnostic_id,
        )


@dataclass(frozen=True, slots=True)
class ToolExecutionOutput:
    payload: BaseModel
    summary: str
    output_handle: str | None = None
    provenance: tuple[ToolProvenance, ...] = ()
    verification_report_ids: tuple[VerificationReportId, ...] = ()
    warnings: tuple[ToolWarning, ...] = ()
    side_effect: ToolSideEffect = "none"
    side_effects: tuple[SideEffectReceipt, ...] = ()
    disclosed_field_count: int = 0
    disclosed_row_count: int = 0
    disclosed_scalar_count: int = 0


ToolHandler = Callable[[BaseModel], ToolExecutionOutput]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """One runtime tool definition suitable for a model adapter."""

    contract: ToolContract
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _RegisteredTool:
    contract: ToolContract
    input_adapter: TypeAdapter[Any]
    output_adapter: TypeAdapter[Any]
    handler: ToolHandler


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _budget_usage_values(usage: TaskBudgetUsage) -> tuple[int | float, ...]:
    return (
        usage.model_calls,
        usage.model_turns,
        usage.input_tokens,
        usage.output_tokens,
        usage.tool_calls,
        usage.disclosed_scalars,
        usage.origin_sessions,
        usage.repair_attempts,
        usage.wall_time_ms,
        usage.estimated_cost,
    )


class ToolGateway:
    """Validate tool schema, task authority, budget and structured results."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._tools: dict[str, _RegisteredTool] = {}

    @property
    def contracts(self) -> tuple[ToolContract, ...]:
        return tuple(item.contract for item in self._tools.values())

    def definition(self, tool_name: str) -> ToolDefinition:
        registered = self._tools.get(tool_name)
        if registered is None:
            raise ToolGatewayError(f"tool is not registered: {tool_name}")
        return ToolDefinition(
            contract=registered.contract,
            input_schema=registered.input_adapter.json_schema(mode="validation"),
            output_schema=registered.output_adapter.json_schema(mode="validation"),
        )

    def allowed_definitions(self, activation: AgentActivation) -> tuple[ToolDefinition, ...]:
        self.context_contracts(activation)
        return tuple(self.definition(tool_name) for tool_name in activation.allowed_tools)

    def register(
        self,
        *,
        contract_id: str,
        contract_version: int,
        tool_name: str,
        description: str,
        permission_phase: PermissionPhase,
        side_effect: ToolContractSideEffect,
        allowed_task_states: tuple[TaskState, ...],
        input_model: type[BaseModel],
        output_model: type[BaseModel],
        cost_class: ToolCostClass,
        timeout_ms: int,
        max_disclosed_scalars: int,
        uses_origin: bool,
        handler: ToolHandler,
    ) -> ToolContract:
        if tool_name in self._tools:
            raise ToolGatewayError(f"duplicate tool registration: {tool_name}")
        input_adapter = TypeAdapter(input_model)
        output_adapter = TypeAdapter(output_model)
        contract = ToolContract(
            contract_id=contract_id,
            contract_version=contract_version,
            tool_name=tool_name,
            description=description,
            permission_phase=permission_phase,
            side_effect=side_effect,
            allowed_task_states=allowed_task_states,
            input_schema_hash=canonical_hash(input_adapter.json_schema(mode="validation")),
            output_schema_hash=canonical_hash(output_adapter.json_schema(mode="validation")),
            cost_class=cost_class,
            timeout_ms=timeout_ms,
            max_disclosed_scalars=max_disclosed_scalars,
            uses_origin=uses_origin,
        )
        self._tools[tool_name] = _RegisteredTool(
            contract=contract,
            input_adapter=input_adapter,
            output_adapter=output_adapter,
            handler=handler,
        )
        return contract

    def context_contracts(self, activation: AgentActivation) -> tuple[ContextToolContract, ...]:
        result = []
        for name in activation.allowed_tools:
            registered = self._tools.get(name)
            if registered is None:
                raise ToolGatewayError(f"activation references unregistered tool: {name}")
            contract = registered.contract
            if activation.task_state not in contract.allowed_task_states:
                raise ToolGatewayError(f"tool {name} is unavailable in {activation.task_state}")
            if _PHASE_ORDER[contract.permission_phase] > _PHASE_ORDER[activation.permission_phase]:
                raise ToolGatewayError(f"tool {name} exceeds activation permission")
            side_effect = cast(
                _ContextSideEffect,
                {
                    "none": "none",
                    "staged": "staged",
                    "committed": "confirmed_write",
                    "expanded_risk": "expanded_risk",
                }[contract.side_effect],
            )
            result.append(
                ContextToolContract(
                    tool_name=name,
                    permission_phase=contract.permission_phase,
                    input_schema_hash=contract.input_schema_hash,
                    output_schema_hash=contract.output_schema_hash,
                    description=contract.description,
                    side_effect=side_effect,
                )
            )
        return tuple(result)

    def invoke(
        self,
        *,
        invocation: ToolInvocation,
        arguments: JsonValue,
        activation: AgentActivation,
        checkpoint: TaskCheckpoint,
        execution_grant: ExecutionGrant | None = None,
    ) -> AgentToolResult:
        started = self._clock()
        registered = self._tools.get(invocation.tool_name)
        if registered is None:
            return self._failure(
                invocation,
                started,
                code="TOOL_UNAVAILABLE",
                category="UNSUPPORTED",
                message="The requested tool is not registered.",
                retryable=False,
                requires_user=False,
            )
        protocol_error = self._protocol_error(
            invocation,
            activation,
            checkpoint,
            registered,
            now=started,
            execution_grant=execution_grant,
        )
        if protocol_error is not None:
            return self._failure(invocation, started, **protocol_error)
        if invocation.arguments_hash != canonical_hash(arguments):
            return self._failure(
                invocation,
                started,
                code="TOOL_ARGUMENT_HASH_MISMATCH",
                category="FATAL",
                message="Tool arguments differ from the authorized invocation.",
                retryable=False,
                requires_user=False,
            )
        try:
            typed_input = registered.input_adapter.validate_json(canonical_json(arguments))
        except ValidationError:
            return self._failure(
                invocation,
                started,
                code="TOOL_ARGUMENT_INVALID",
                category="AGENT_REPAIRABLE",
                message="Tool arguments do not match the published schema.",
                retryable=True,
                requires_user=False,
                repair_hint="Read the current tool schema and correct only the invalid arguments.",
            )
        try:
            output = registered.handler(cast(BaseModel, typed_input))
            typed_output = registered.output_adapter.validate_python(output.payload)
        except ToolExecutionProblem as problem:
            return self._failure(
                invocation,
                started,
                code=problem.error.code,
                category=problem.error.category,
                message=problem.error.message,
                retryable=problem.error.retryable,
                requires_user=problem.error.requires_user,
                repair_hint=problem.error.repair_hint,
                side_effect=problem.error.side_effect_state,
                diagnostic_id=problem.error.diagnostic_id,
            )
        except Exception:
            return self._failure(
                invocation,
                started,
                code="TOOL_RESULT_INVALID",
                category="FATAL",
                message="The tool returned a result outside its published contract.",
                retryable=False,
                requires_user=False,
            )
        if any(
            value < 0
            for value in (
                output.disclosed_field_count,
                output.disclosed_row_count,
                output.disclosed_scalar_count,
            )
        ):
            return self._failure(
                invocation,
                started,
                code="TOOL_RESULT_INVALID",
                category="FATAL",
                message="The tool returned invalid disclosure metadata.",
                retryable=False,
                requires_user=False,
            )
        if not self._side_effect_matches(registered.contract.side_effect, output.side_effect):
            return self._failure(
                invocation,
                started,
                code="TOOL_SIDE_EFFECT_MISMATCH",
                category="FATAL",
                message="The tool result side effect differs from its registered contract.",
                retryable=False,
                requires_user=False,
                side_effect="unknown",
            )
        completed = self._clock()
        if completed > _datetime(invocation.deadline):
            return self._failure(
                invocation,
                started,
                code="TOOL_DEADLINE_EXCEEDED",
                category="TRANSIENT",
                message="The tool did not complete before its authorized deadline.",
                retryable=output.side_effect == "none",
                requires_user=False,
                side_effect=output.side_effect if output.side_effect != "none" else "none",
            )
        disclosure_error = self._disclosure_error(
            invocation,
            activation,
            checkpoint,
            registered.contract,
            output.disclosed_scalar_count,
        )
        if disclosure_error is not None:
            return self._failure(invocation, started, **disclosure_error)
        payload = cast(BaseModel, typed_output).model_dump(mode="json")
        try:
            return AgentToolResult(
                tool_call_id=invocation.tool_call_id,
                task_id=invocation.task_id,
                task_version=invocation.task_version,
                activation_id=invocation.activation_id,
                tool_name=invocation.tool_name,
                status="succeeded",
                summary=output.summary,
                payload=cast(JsonValue, payload),
                output_hash=canonical_hash(cast(JsonValue, payload)),
                output_handle=output.output_handle,
                provenance=output.provenance,
                verification_report_ids=output.verification_report_ids,
                warnings=output.warnings,
                side_effect=output.side_effect,
                side_effects=output.side_effects,
                disclosed_field_count=output.disclosed_field_count,
                disclosed_row_count=output.disclosed_row_count,
                disclosed_scalar_count=output.disclosed_scalar_count,
                started_at=_iso(started),
                completed_at=_iso(completed),
            )
        except ValidationError:
            return self._failure(
                invocation,
                started,
                code="TOOL_RESULT_INVALID",
                category="FATAL",
                message="The tool returned a result outside its published contract.",
                retryable=False,
                requires_user=False,
            )

    def build_receipt(
        self,
        *,
        invocation: ToolInvocation,
        result: AgentToolResult,
        checkpoint: TaskCheckpoint,
        project_revision_after: int | None = None,
    ) -> ToolReceipt:
        """Project one validated result into the durable task receipt contract."""

        if (
            result.tool_call_id != invocation.tool_call_id
            or result.task_id != invocation.task_id
            or result.task_version != invocation.task_version
            or result.activation_id != invocation.activation_id
            or result.tool_name != invocation.tool_name
        ):
            raise ToolGatewayError("tool result does not match its invocation")
        if (
            checkpoint.task_id != invocation.task_id
            or checkpoint.task_version != invocation.task_version
        ):
            raise ToolGatewayError("tool receipt checkpoint is stale")
        revision_after = (
            checkpoint.project_revision
            if project_revision_after is None
            else project_revision_after
        )
        if result.side_effect in {"none", "staged"} and (
            revision_after != checkpoint.project_revision
        ):
            raise ToolGatewayError("read and staged tools cannot change the project revision")
        if result.side_effect == "committed" and revision_after <= checkpoint.project_revision:
            raise ToolGatewayError("committed tools must advance the project revision")
        error = self._task_error(result.error) if result.error is not None else None
        registered = self._tools.get(invocation.tool_name)
        elapsed_ms = max(
            0,
            int(
                (
                    _datetime(result.completed_at) - _datetime(result.started_at)
                ).total_seconds()
                * 1_000
            ),
        )
        return ToolReceipt(
            receipt_id=f"receipt:{canonical_hash(invocation.tool_call_id)[:32]}",
            task_id=invocation.task_id,
            task_version=invocation.task_version,
            activation_id=invocation.activation_id,
            item_id=invocation.item_id,
            tool_call_id=invocation.tool_call_id,
            tool_name=invocation.tool_name,
            permission_phase=invocation.permission_phase,
            outcome="succeeded" if result.status == "succeeded" else "failed",
            idempotency_key=invocation.idempotency_key,
            input_hash=invocation.arguments_hash,
            output_hash=result.output_hash,
            project_revision_before=checkpoint.project_revision,
            project_revision_after=revision_after,
            side_effects=result.side_effects,
            budget_delta=TaskBudgetUsage(
                tool_calls=1,
                disclosed_scalars=result.disclosed_scalar_count,
                origin_sessions=(
                    1 if registered is not None and registered.contract.uses_origin else 0
                ),
                wall_time_ms=elapsed_ms,
            ),
            error=error,
            started_at=result.started_at,
            finished_at=result.completed_at,
        )

    @staticmethod
    def _task_error(error: AgentToolError) -> TaskError:
        if error.category == "TRANSIENT":
            category = "transient_external"
        elif error.category == "USER_INPUT_REQUIRED":
            category = "semantic_conflict"
        elif error.category == "UNSUPPORTED":
            category = "unsupported"
        elif "BUDGET" in error.code:
            category = "budget"
        elif "STALE" in error.code or "VERSION" in error.code:
            category = "stale_or_concurrent"
        elif "PERMISSION" in error.code or "GRANT" in error.code:
            category = "safety_or_permission"
        elif error.category == "AGENT_REPAIRABLE":
            category = "deterministic_technical"
        else:
            category = "runtime"
        requires_user = error.requires_user or category == "safety_or_permission"
        side_effect_state = {
            "none": "known_none",
            "staged": "known_applied",
            "committed": "known_applied",
            "unknown": "unknown",
        }[error.side_effect_state]
        return TaskError(
            code=error.code,
            category=category,  # type: ignore[arg-type]
            message=error.message,
            retryable=error.retryable,
            requires_user=requires_user,
            side_effect_state=side_effect_state,  # type: ignore[arg-type]
            diagnostic_id=error.diagnostic_id,
        )

    @staticmethod
    def _side_effect_matches(
        contract_side_effect: ToolContractSideEffect, result_side_effect: ToolSideEffect
    ) -> bool:
        expected = cast(
            ToolSideEffect,
            {
                "none": "none",
                "staged": "staged",
                "committed": "committed",
                "expanded_risk": "committed",
            }[contract_side_effect],
        )
        return result_side_effect == expected

    @staticmethod
    def _protocol_error(
        invocation: ToolInvocation,
        activation: AgentActivation,
        checkpoint: TaskCheckpoint,
        registered: _RegisteredTool,
        *,
        now: datetime,
        execution_grant: ExecutionGrant | None,
    ) -> _FailureSpec | None:
        if (
            invocation.task_id != activation.task_id
            or invocation.task_id != checkpoint.task_id
            or invocation.task_version != activation.task_version
            or invocation.task_version != checkpoint.task_version
            or invocation.activation_id != activation.activation_id
            or checkpoint.active_activation_id != activation.activation_id
        ):
            return {
                "code": "TOOL_ACTIVATION_STALE",
                "category": "FATAL",
                "message": "Tool invocation is stale or belongs to another task activation.",
                "retryable": False,
                "requires_user": False,
            }
        contract = registered.contract
        if invocation.tool_name != contract.tool_name:
            return {
                "code": "TOOL_CONTRACT_MISMATCH",
                "category": "FATAL",
                "message": "Tool invocation does not match the registered contract.",
                "retryable": False,
                "requires_user": False,
            }
        invocation_deadline = _datetime(invocation.deadline)
        activation_deadline = (
            None if activation.deadline is None else _datetime(activation.deadline)
        )
        if activation_deadline is not None and invocation_deadline > activation_deadline:
            return {
                "code": "TOOL_DEADLINE_INVALID",
                "category": "FATAL",
                "message": "Tool deadline exceeds the activation deadline.",
                "retryable": False,
                "requires_user": False,
            }
        if now >= invocation_deadline:
            return {
                "code": "TOOL_DEADLINE_EXCEEDED",
                "category": "TRANSIENT",
                "message": "Tool invocation deadline has expired.",
                "retryable": True,
                "requires_user": False,
            }
        if invocation_deadline - now > timedelta(milliseconds=contract.timeout_ms):
            return {
                "code": "TOOL_DEADLINE_INVALID",
                "category": "FATAL",
                "message": "Tool deadline exceeds its registered timeout.",
                "retryable": False,
                "requires_user": False,
            }
        if activation.task_state != checkpoint.state:
            return {
                "code": "TOOL_TASK_STATE_STALE",
                "category": "FATAL",
                "message": "Tool activation state differs from the durable checkpoint.",
                "retryable": False,
                "requires_user": False,
            }
        if invocation.expected_project_revision != checkpoint.project_revision:
            return {
                "code": "TOOL_PROJECT_REVISION_STALE",
                "category": "FATAL",
                "message": "Tool invocation targets a stale project revision.",
                "retryable": False,
                "requires_user": False,
            }
        if activation.task_budget.limits != checkpoint.budget.limits or any(
            initial > current
            for initial, current in zip(
                _budget_usage_values(activation.task_budget.usage),
                _budget_usage_values(checkpoint.budget.usage),
                strict=True,
            )
        ):
            return {
                "code": "TOOL_BUDGET_SNAPSHOT_STALE",
                "category": "FATAL",
                "message": "Tool activation budget differs from the durable checkpoint.",
                "retryable": False,
                "requires_user": False,
            }
        grant_error = ToolGateway._grant_error(
            invocation,
            activation,
            checkpoint,
            execution_grant,
            now=now,
        )
        if grant_error is not None:
            return grant_error
        if invocation.tool_name not in activation.allowed_tools:
            return {
                "code": "TOOL_PERMISSION_DENIED",
                "category": "FATAL",
                "message": "Tool is outside the activation allowlist.",
                "retryable": False,
                "requires_user": False,
            }
        if (
            invocation.permission_phase != contract.permission_phase
            or activation.task_state not in contract.allowed_task_states
            or _PHASE_ORDER[contract.permission_phase]
            > _PHASE_ORDER[activation.permission_phase]
        ):
            return {
                "code": "TOOL_PERMISSION_DENIED",
                "category": "FATAL",
                "message": "Tool is not allowed in the current task state or permission phase.",
                "retryable": False,
                "requires_user": False,
            }
        if (
            invocation.activation_tool_calls_before >= activation.activation_budget.max_tool_calls
            or checkpoint.budget.usage.tool_calls
            >= checkpoint.budget.limits.max_tool_calls
        ):
            return {
                "code": "TOOL_BUDGET_EXHAUSTED",
                "category": "FATAL",
                "message": "The activation or task tool-call budget is exhausted.",
                "retryable": False,
                "requires_user": False,
            }
        if (
            contract.uses_origin
            and checkpoint.budget.usage.origin_sessions
            >= checkpoint.budget.limits.max_origin_sessions
        ):
            return {
                "code": "TOOL_ORIGIN_BUDGET_EXHAUSTED",
                "category": "FATAL",
                "message": "The task Origin-session budget is exhausted.",
                "retryable": False,
                "requires_user": False,
            }
        return None

    @staticmethod
    def _grant_error(
        invocation: ToolInvocation,
        activation: AgentActivation,
        checkpoint: TaskCheckpoint,
        grant: ExecutionGrant | None,
        *,
        now: datetime,
    ) -> _FailureSpec | None:
        committed = invocation.permission_phase in {"p2_confirmed", "p3_expanded"}
        if not committed:
            if grant is not None:
                return {
                    "code": "TOOL_GRANT_UNEXPECTED",
                    "category": "FATAL",
                    "message": "Read and staged tools cannot consume an execution grant.",
                    "retryable": False,
                    "requires_user": False,
                }
            return None
        if grant is None or invocation.execution_grant_id != grant.grant_id:
            return {
                "code": "TOOL_GRANT_REQUIRED",
                "category": "FATAL",
                "message": "Committed tool invocation lacks its Core-issued execution grant.",
                "retryable": False,
                "requires_user": False,
            }
        if (
            grant.task_id != invocation.task_id
            or grant.task_version != invocation.task_version
            or grant.expected_project_revision != checkpoint.project_revision
            or invocation.expected_project_revision != checkpoint.project_revision
            or grant.permission_phase != activation.permission_phase
            or _PHASE_ORDER[grant.permission_phase]
            < _PHASE_ORDER[invocation.permission_phase]
        ):
            return {
                "code": "TOOL_GRANT_STALE",
                "category": "FATAL",
                "message": "Execution grant is stale or belongs to another task revision.",
                "retryable": False,
                "requires_user": False,
            }
        if grant.expires_at is not None and now >= _datetime(grant.expires_at):
            return {
                "code": "TOOL_GRANT_EXPIRED",
                "category": "FATAL",
                "message": "Execution grant has expired.",
                "retryable": False,
                "requires_user": False,
            }
        scope = next(
            (scope for scope in grant.scopes if scope.item_id == invocation.item_id),
            None,
        )
        if scope is None or invocation.tool_name not in scope.operations:
            return {
                "code": "TOOL_GRANT_SCOPE_DENIED",
                "category": "FATAL",
                "message": "Tool or task item is outside the execution grant scope.",
                "retryable": False,
                "requires_user": False,
            }
        return None

    @staticmethod
    def _disclosure_error(
        invocation: ToolInvocation,
        activation: AgentActivation,
        checkpoint: TaskCheckpoint,
        contract: ToolContract,
        disclosed: int,
    ) -> _FailureSpec | None:
        activation_remaining = (
            activation.activation_budget.max_disclosed_scalars
            - invocation.activation_disclosed_scalars_before
        )
        task_remaining = (
            checkpoint.budget.limits.max_disclosed_scalars
            - checkpoint.budget.usage.disclosed_scalars
        )
        if disclosed > min(contract.max_disclosed_scalars, activation_remaining, task_remaining):
            return {
                "code": "TOOL_DISCLOSURE_BUDGET_EXCEEDED",
                "category": "FATAL",
                "message": "The tool result exceeds the authorized data disclosure budget.",
                "retryable": False,
                "requires_user": False,
            }
        return None

    def _failure(
        self,
        invocation: ToolInvocation,
        started: datetime,
        *,
        code: str,
        category: ToolErrorCategory,
        message: str,
        retryable: bool,
        requires_user: bool,
        repair_hint: str | None = None,
        side_effect: ToolSideEffect = "none",
        diagnostic_id: str | None = None,
    ) -> AgentToolResult:
        error = AgentToolError(
            code=code,
            category=category,
            message=message,
            retryable=retryable,
            requires_user=requires_user,
            repair_hint=repair_hint,
            side_effect_state=side_effect,
            diagnostic_id=diagnostic_id,
        )
        return AgentToolResult(
            tool_call_id=invocation.tool_call_id,
            task_id=invocation.task_id,
            task_version=invocation.task_version,
            activation_id=invocation.activation_id,
            tool_name=invocation.tool_name,
            status="failed",
            summary=message,
            side_effect=side_effect,
            error=error,
            started_at=_iso(started),
            completed_at=_iso(self._clock()),
        )
