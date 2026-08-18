from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, TypeAdapter

from plotagent.contracts.agent_tasks import (
    ActivationBudget,
    AgentActivation,
    ExecutionGrant,
    ExecutionScope,
    IntentRef,
    SideEffectReceipt,
    TaskBudgetLimits,
    TaskBudgetSnapshot,
    TaskBudgetUsage,
    TaskCheckpoint,
)
from plotagent.contracts.agent_tools import ToolInvocation
from plotagent.contracts.base import StrictModel
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.tooling import ToolExecutionOutput, ToolGateway, register_domain_tools
from plotagent.tooling.domain_tools import GetChartKnowledgeInput, ListChartCatalogInput

NOW = datetime(2026, 8, 18, 10, 0, 0, tzinfo=UTC)
NOW_TEXT = "2026-08-18T10:00:00Z"
CALL_DEADLINE = "2026-08-18T10:00:04Z"
ACTIVATION_DEADLINE = "2026-08-18T10:00:05Z"
HASH_A = "a" * 64


def budget(
    *,
    tool_calls: int = 0,
    disclosed: int = 0,
    origin_sessions: int = 0,
    max_tool_calls: int = 20,
    max_disclosed: int = 100,
    max_origin_sessions: int = 2,
) -> TaskBudgetSnapshot:
    return TaskBudgetSnapshot(
        limits=TaskBudgetLimits(
            max_tool_calls=max_tool_calls,
            max_disclosed_scalars=max_disclosed,
            max_origin_sessions=max_origin_sessions,
            max_estimated_cost=10,
        ),
        usage=TaskBudgetUsage(
            tool_calls=tool_calls,
            disclosed_scalars=disclosed,
            origin_sessions=origin_sessions,
        ),
    )


def activation(
    *tools: str,
    task_budget: TaskBudgetSnapshot | None = None,
    activation_tool_calls: int = 20,
    disclosed: int = 100,
) -> AgentActivation:
    return AgentActivation(
        activation_id="activation:test",
        task_id="task:test",
        task_version=1,
        reason="new_task",
        task_state="created",
        original_instruction="Create an appropriate chart from the selected source.",
        allowed_tools=tools or ("list_chart_catalog",),
        permission_phase="p0_read",
        activation_budget=ActivationBudget(
            max_tool_calls=activation_tool_calls,
            max_disclosed_scalars=disclosed,
        ),
        task_budget=task_budget or budget(),
        deadline=ACTIVATION_DEADLINE,
        created_at=NOW_TEXT,
    )


def checkpoint(*, task_budget: TaskBudgetSnapshot | None = None) -> TaskCheckpoint:
    return TaskCheckpoint(
        checkpoint_id="checkpoint:test",
        task_id="task:test",
        task_version=1,
        state="created",
        project_revision=0,
        last_event_sequence=1,
        active_activation_id="activation:test",
        budget=task_budget or budget(),
        updated_at=NOW_TEXT,
        content_hash=HASH_A,
    )


def invocation(
    tool_name: str,
    arguments: JsonValue,
    *,
    deadline: str = CALL_DEADLINE,
    calls_before: int = 0,
    disclosed_before: int = 0,
) -> ToolInvocation:
    return ToolInvocation(
        tool_call_id=f"toolcall:{tool_name}",
        task_id="task:test",
        task_version=1,
        activation_id="activation:test",
        tool_name=tool_name,
        permission_phase="p0_read",
        arguments_hash=canonical_hash(arguments),
        activation_tool_calls_before=calls_before,
        activation_disclosed_scalars_before=disclosed_before,
        deadline=deadline,
    )


def gateway() -> ToolGateway:
    result = ToolGateway(clock=lambda: NOW)
    register_domain_tools(result)
    return result


def invoke_domain(
    tool_name: str,
    arguments: JsonValue,
    *,
    current_activation: AgentActivation | None = None,
    current_checkpoint: TaskCheckpoint | None = None,
    call: ToolInvocation | None = None,
):
    current_activation = current_activation or activation(
        "list_chart_catalog",
        "get_chart_knowledge",
        "compare_chart_profiles",
        "get_calculation_contract",
        "get_domain_example",
    )
    return gateway().invoke(
        invocation=call or invocation(tool_name, arguments),
        arguments=arguments,
        activation=current_activation,
        checkpoint=current_checkpoint or checkpoint(task_budget=current_activation.task_budget),
    )


def test_registration_publishes_stable_schema_hashed_contracts() -> None:
    current = gateway()
    assert tuple(contract.tool_name for contract in current.contracts) == (
        "list_chart_catalog",
        "get_chart_knowledge",
        "compare_chart_profiles",
        "get_calculation_contract",
        "get_domain_example",
    )
    catalog_contract = current.contracts[0]
    chart_contract = current.contracts[1]
    assert catalog_contract.input_schema_hash == canonical_hash(
        TypeAdapter(ListChartCatalogInput).json_schema(mode="validation")
    )
    assert chart_contract.input_schema_hash == canonical_hash(
        TypeAdapter(GetChartKnowledgeInput).json_schema(mode="validation")
    )
    assert all(contract.permission_phase == "p0_read" for contract in current.contracts)
    assert all(contract.side_effect == "none" for contract in current.contracts)


def test_context_contracts_follow_the_core_allowlist_and_preserve_order() -> None:
    current = gateway()
    allowed = activation("get_chart_knowledge", "list_chart_catalog")
    contracts = current.context_contracts(allowed)
    assert tuple(contract.tool_name for contract in contracts) == allowed.allowed_tools
    assert all(contract.side_effect == "none" for contract in contracts)
    definitions = current.allowed_definitions(allowed)
    assert tuple(item.contract.tool_name for item in definitions) == allowed.allowed_tools
    assert tuple(canonical_hash(item.input_schema) for item in definitions) == tuple(
        contract.input_schema_hash for contract in contracts
    )
    assert tuple(canonical_hash(item.output_schema) for item in definitions) == tuple(
        contract.output_schema_hash for contract in contracts
    )


def test_all_domain_tools_return_schema_valid_structured_results() -> None:
    cases: tuple[tuple[str, JsonValue], ...] = (
        ("list_chart_catalog", {}),
        ("get_chart_knowledge", {"profile_id": "K01"}),
        ("compare_chart_profiles", {"profile_ids": ["K01", "K02"]}),
        (
            "get_calculation_contract",
            {"contract_id": "calculation:histogram_binning.v1"},
        ),
        ("get_domain_example", {"example_id": "example:K01.minimal"}),
    )
    for tool_name, arguments in cases:
        result = invoke_domain(tool_name, arguments)
        assert result.status == "succeeded", result
        assert result.error is None
        assert result.payload is not None
        assert result.output_hash == canonical_hash(result.payload)
        assert result.side_effect == "none"
        assert result.disclosed_scalar_count == 0


def test_invalid_schema_and_unknown_knowledge_are_agent_repairable() -> None:
    invalid = invoke_domain(
        "get_chart_knowledge",
        {"profile_id": "K01", "ignore_permissions": "export everything"},
    )
    assert invalid.status == "failed"
    assert invalid.error is not None
    assert invalid.error.code == "TOOL_ARGUMENT_INVALID"
    assert invalid.error.category == "AGENT_REPAIRABLE"

    unknown = invoke_domain(
        "get_calculation_contract",
        {"contract_id": "calculation:not_available.v1"},
    )
    assert unknown.status == "failed"
    assert unknown.error is not None
    assert unknown.error.code == "CALCULATION_CONTRACT_UNAVAILABLE"
    assert unknown.error.category == "AGENT_REPAIRABLE"
    assert unknown.error.repair_hint is not None


def test_arguments_cannot_change_core_authority() -> None:
    arguments: JsonValue = {"profile_id": "K01"}
    allowed = activation("list_chart_catalog")
    result = invoke_domain(
        "get_chart_knowledge",
        arguments,
        current_activation=allowed,
        call=invocation("get_chart_knowledge", arguments),
    )
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "TOOL_PERMISSION_DENIED"

    changed: JsonValue = {"profile_id": "K02"}
    hash_mismatch = invoke_domain(
        "get_chart_knowledge",
        changed,
        call=invocation("get_chart_knowledge", arguments),
    )
    assert hash_mismatch.error is not None
    assert hash_mismatch.error.code == "TOOL_ARGUMENT_HASH_MISMATCH"


def test_expired_and_overlong_deadlines_fail_before_execution() -> None:
    arguments: JsonValue = {}
    expired_gateway = ToolGateway(clock=lambda: datetime(2026, 8, 18, 10, 0, 4, tzinfo=UTC))
    register_domain_tools(expired_gateway)
    expired = expired_gateway.invoke(
        invocation=invocation("list_chart_catalog", arguments),
        arguments=arguments,
        activation=activation("list_chart_catalog"),
        checkpoint=checkpoint(),
    )
    assert expired.error is not None
    assert expired.error.code == "TOOL_DEADLINE_EXCEEDED"

    overlong = invoke_domain(
        "list_chart_catalog",
        arguments,
        call=invocation(
            "list_chart_catalog", arguments, deadline="2026-08-18T10:00:05.001Z"
        ),
    )
    assert overlong.error is not None
    assert overlong.error.code == "TOOL_DEADLINE_INVALID"


class _EmptyInput(StrictModel):
    pass


class _ValueOutput(StrictModel):
    value: int


def _register_test_tool(
    current: ToolGateway,
    *,
    tool_name: str,
    disclosed: int = 0,
    result_side_effect: str = "none",
    uses_origin: bool = False,
) -> None:
    def handler(_input: BaseModel) -> ToolExecutionOutput:
        return ToolExecutionOutput(
            payload=_ValueOutput(value=1),
            summary="Returned one test value.",
            side_effect=result_side_effect,  # type: ignore[arg-type]
            disclosed_scalar_count=disclosed,
        )

    current.register(
        contract_id=f"tool:{tool_name}",
        contract_version=1,
        tool_name=tool_name,
        description="Test one gateway invariant.",
        permission_phase="p0_read",
        side_effect="none",
        allowed_task_states=("created",),
        input_model=_EmptyInput,
        output_model=_ValueOutput,
        cost_class="moderate" if uses_origin else "cheap",
        timeout_ms=5_000,
        max_disclosed_scalars=1,
        uses_origin=uses_origin,
        handler=handler,
    )


def test_budget_disclosure_origin_and_side_effect_fail_closed() -> None:
    arguments: JsonValue = {}

    exhausted_calls = budget(tool_calls=1, max_tool_calls=1)
    call_budget_result = gateway().invoke(
        invocation=invocation("list_chart_catalog", arguments),
        arguments=arguments,
        activation=activation("list_chart_catalog", task_budget=exhausted_calls),
        checkpoint=checkpoint(task_budget=exhausted_calls),
    )
    assert call_budget_result.error is not None
    assert call_budget_result.error.code == "TOOL_BUDGET_EXHAUSTED"

    disclosure_gateway = ToolGateway(clock=lambda: NOW)
    _register_test_tool(disclosure_gateway, tool_name="disclose", disclosed=2)
    disclosure = disclosure_gateway.invoke(
        invocation=invocation("disclose", arguments),
        arguments=arguments,
        activation=activation("disclose"),
        checkpoint=checkpoint(),
    )
    assert disclosure.error is not None
    assert disclosure.error.code == "TOOL_DISCLOSURE_BUDGET_EXCEEDED"

    exhausted_budget = budget(origin_sessions=0, max_origin_sessions=0)
    origin_gateway = ToolGateway(clock=lambda: NOW)
    _register_test_tool(origin_gateway, tool_name="origin_probe", uses_origin=True)
    origin_result = origin_gateway.invoke(
        invocation=invocation("origin_probe", arguments),
        arguments=arguments,
        activation=activation("origin_probe", task_budget=exhausted_budget),
        checkpoint=checkpoint(task_budget=exhausted_budget),
    )
    assert origin_result.error is not None
    assert origin_result.error.code == "TOOL_ORIGIN_BUDGET_EXHAUSTED"

    side_effect_gateway = ToolGateway(clock=lambda: NOW)
    _register_test_tool(
        side_effect_gateway,
        tool_name="misreported_effect",
        result_side_effect="staged",
    )
    side_effect = side_effect_gateway.invoke(
        invocation=invocation("misreported_effect", arguments),
        arguments=arguments,
        activation=activation("misreported_effect"),
        checkpoint=checkpoint(),
    )
    assert side_effect.error is not None
    assert side_effect.error.code == "TOOL_SIDE_EFFECT_MISMATCH"
    assert side_effect.side_effect == "unknown"


def test_result_builds_a_deterministic_budgeted_receipt() -> None:
    arguments: JsonValue = {"profile_id": "K01"}
    current_gateway = gateway()
    current_budget = budget()
    current_checkpoint = checkpoint(task_budget=current_budget)
    call = invocation("get_chart_knowledge", arguments)
    result = current_gateway.invoke(
        invocation=call,
        arguments=arguments,
        activation=activation("get_chart_knowledge", task_budget=current_budget),
        checkpoint=current_checkpoint,
    )
    receipt = current_gateway.build_receipt(
        invocation=call,
        result=result,
        checkpoint=current_checkpoint,
    )
    duplicate = current_gateway.build_receipt(
        invocation=call,
        result=result,
        checkpoint=current_checkpoint,
    )
    assert receipt == duplicate
    assert receipt.receipt_id.startswith("receipt:")
    assert receipt.outcome == "succeeded"
    assert receipt.input_hash == call.arguments_hash
    assert receipt.output_hash == result.output_hash
    assert receipt.budget_delta.tool_calls == 1
    assert receipt.budget_delta.disclosed_scalars == 0
    assert receipt.project_revision_before == receipt.project_revision_after == 0


def test_committed_tool_requires_item_scoped_execution_grant() -> None:
    current_gateway = ToolGateway(clock=lambda: NOW)

    def handler(_input: BaseModel) -> ToolExecutionOutput:
        return ToolExecutionOutput(
            payload=_ValueOutput(value=1),
            summary="Committed one authorized test revision.",
            side_effect="committed",
            side_effects=(
                SideEffectReceipt(effect_kind="project_revision", object_id="project:test"),
            ),
        )

    current_gateway.register(
        contract_id="tool:commit_test",
        contract_version=1,
        tool_name="commit_test",
        description="Commit one test revision.",
        permission_phase="p2_confirmed",
        side_effect="committed",
        allowed_task_states=("repairing",),
        input_model=_EmptyInput,
        output_model=_ValueOutput,
        cost_class="moderate",
        timeout_ms=5_000,
        max_disclosed_scalars=0,
        uses_origin=False,
        handler=handler,
    )
    current_budget = budget()
    current_activation = AgentActivation(
        activation_id="activation:test",
        task_id="task:test",
        task_version=1,
        reason="external_blocker_cleared",
        task_state="repairing",
        original_instruction="Repair the confirmed task without changing its intent.",
        allowed_tools=("commit_test",),
        permission_phase="p2_confirmed",
        activation_budget=ActivationBudget(max_disclosed_scalars=10),
        task_budget=current_budget,
        deadline=ACTIVATION_DEADLINE,
        created_at=NOW_TEXT,
    )
    current_checkpoint = checkpoint(task_budget=current_budget).model_copy(
        update={"state": "repairing"}
    )
    arguments: JsonValue = {}
    call = ToolInvocation(
        tool_call_id="toolcall:commit_test",
        task_id="task:test",
        task_version=1,
        activation_id="activation:test",
        item_id="item:test.1",
        execution_grant_id="grant:test",
        idempotency_key="idem:commit_test",
        tool_name="commit_test",
        permission_phase="p2_confirmed",
        arguments_hash=canonical_hash(arguments),
        activation_tool_calls_before=0,
        activation_disclosed_scalars_before=0,
        expected_project_revision=0,
        deadline=CALL_DEADLINE,
    )
    denied = current_gateway.invoke(
        invocation=call,
        arguments=arguments,
        activation=current_activation,
        checkpoint=current_checkpoint,
    )
    assert denied.error is not None
    assert denied.error.code == "TOOL_GRANT_REQUIRED"

    grant = ExecutionGrant(
        grant_id="grant:test",
        task_id="task:test",
        task_version=1,
        intent=IntentRef(intent_id="intent:test", intent_version=1, content_hash=HASH_A),
        expected_project_revision=0,
        permission_phase="p2_confirmed",
        scopes=(ExecutionScope(item_id="item:test.1", operations=("commit_test",)),),
        issued_at=NOW_TEXT,
        expires_at=ACTIVATION_DEADLINE,
        content_hash=HASH_A,
    )
    expired = grant.model_copy(
        update={
            "issued_at": "2026-08-18T09:59:00Z",
            "expires_at": NOW_TEXT,
        }
    )
    expired_result = current_gateway.invoke(
        invocation=call,
        arguments=arguments,
        activation=current_activation,
        checkpoint=current_checkpoint,
        execution_grant=expired,
    )
    assert expired_result.error is not None
    assert expired_result.error.code == "TOOL_GRANT_EXPIRED"

    out_of_scope = grant.model_copy(
        update={
            "scopes": (
                ExecutionScope(
                    item_id="item:test.1",
                    operations=("another_operation",),
                ),
            )
        }
    )
    scope_result = current_gateway.invoke(
        invocation=call,
        arguments=arguments,
        activation=current_activation,
        checkpoint=current_checkpoint,
        execution_grant=out_of_scope,
    )
    assert scope_result.error is not None
    assert scope_result.error.code == "TOOL_GRANT_SCOPE_DENIED"

    result = current_gateway.invoke(
        invocation=call,
        arguments=arguments,
        activation=current_activation,
        checkpoint=current_checkpoint,
        execution_grant=grant,
    )
    assert result.status == "succeeded"
    receipt = current_gateway.build_receipt(
        invocation=call,
        result=result,
        checkpoint=current_checkpoint,
        project_revision_after=1,
    )
    assert receipt.permission_phase == "p2_confirmed"
    assert receipt.idempotency_key == "idem:commit_test"
    assert receipt.project_revision_after == 1
    assert receipt.side_effects[0].effect_kind == "project_revision"


def test_expanded_risk_tool_requires_an_explicit_p3_grant() -> None:
    current_gateway = ToolGateway(clock=lambda: NOW)

    def handler(_input: BaseModel) -> ToolExecutionOutput:
        return ToolExecutionOutput(
            payload=_ValueOutput(value=1),
            summary="Applied one explicitly expanded-risk operation.",
            side_effect="committed",
            side_effects=(
                SideEffectReceipt(effect_kind="project_revision", object_id="project:test"),
            ),
        )

    current_gateway.register(
        contract_id="tool:expanded_test",
        contract_version=1,
        tool_name="expanded_test",
        description="Exercise the P3 permission boundary.",
        permission_phase="p3_expanded",
        side_effect="expanded_risk",
        allowed_task_states=("repairing",),
        input_model=_EmptyInput,
        output_model=_ValueOutput,
        cost_class="expensive",
        timeout_ms=5_000,
        max_disclosed_scalars=0,
        uses_origin=False,
        handler=handler,
    )
    current_budget = budget()
    current_checkpoint = checkpoint(task_budget=current_budget).model_copy(
        update={"state": "repairing"}
    )
    arguments: JsonValue = {}
    call = ToolInvocation(
        tool_call_id="toolcall:expanded_test",
        task_id="task:test",
        task_version=1,
        activation_id="activation:test",
        item_id="item:test.1",
        execution_grant_id="grant:expanded",
        idempotency_key="idem:expanded_test",
        tool_name="expanded_test",
        permission_phase="p3_expanded",
        arguments_hash=canonical_hash(arguments),
        activation_tool_calls_before=0,
        activation_disclosed_scalars_before=0,
        expected_project_revision=0,
        deadline=CALL_DEADLINE,
    )
    p2_activation = AgentActivation(
        activation_id="activation:test",
        task_id="task:test",
        task_version=1,
        reason="external_blocker_cleared",
        task_state="repairing",
        original_instruction="Apply only the separately confirmed expanded-risk operation.",
        allowed_tools=("expanded_test",),
        permission_phase="p2_confirmed",
        activation_budget=ActivationBudget(max_disclosed_scalars=10),
        task_budget=current_budget,
        deadline=ACTIVATION_DEADLINE,
        created_at=NOW_TEXT,
    )
    p2_grant = ExecutionGrant(
        grant_id="grant:expanded",
        task_id="task:test",
        task_version=1,
        intent=IntentRef(intent_id="intent:test", intent_version=1, content_hash=HASH_A),
        expected_project_revision=0,
        permission_phase="p2_confirmed",
        scopes=(ExecutionScope(item_id="item:test.1", operations=("expanded_test",)),),
        issued_at=NOW_TEXT,
        expires_at=ACTIVATION_DEADLINE,
        content_hash=HASH_A,
    )
    denied = current_gateway.invoke(
        invocation=call,
        arguments=arguments,
        activation=p2_activation,
        checkpoint=current_checkpoint,
        execution_grant=p2_grant,
    )
    assert denied.error is not None
    assert denied.error.code == "TOOL_GRANT_STALE"

    p3_activation = p2_activation.model_copy(update={"permission_phase": "p3_expanded"})
    p3_grant = p2_grant.model_copy(update={"permission_phase": "p3_expanded"})
    allowed = current_gateway.invoke(
        invocation=call,
        arguments=arguments,
        activation=p3_activation,
        checkpoint=current_checkpoint,
        execution_grant=p3_grant,
    )
    assert allowed.status == "succeeded", allowed.error
    receipt = current_gateway.build_receipt(
        invocation=call,
        result=allowed,
        checkpoint=current_checkpoint,
        project_revision_after=1,
    )
    assert receipt.permission_phase == "p3_expanded"
