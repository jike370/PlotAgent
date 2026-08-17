from __future__ import annotations

from datetime import UTC, datetime

from plotagent.contracts.agent_tasks import (
    ActivationBudget,
    AgentActivation,
    TaskBudgetLimits,
    TaskBudgetSnapshot,
    TaskBudgetUsage,
    TaskCheckpoint,
)
from plotagent.contracts.agent_tools import ToolInvocation
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.workflows import (
    WorkflowBudget,
    WorkflowContext,
    WorkflowField,
    WorkflowScalar,
    WorkflowSource,
)
from plotagent.tooling import ToolGateway, register_inspection_tools
from plotagent.workflows.inspection import DataInspectionService

NOW = datetime(2026, 8, 18, 10, 0, 0, tzinfo=UTC)
NOW_TEXT = "2026-08-18T10:00:00Z"
CALL_DEADLINE = "2026-08-18T10:00:09Z"
ACTIVATION_DEADLINE = "2026-08-18T10:00:10Z"
HASH_A = "a" * 64
HASH_B = "b" * 64
INSPECTION_TOOLS = (
    "list_sources",
    "inspect_source",
    "preview_rows",
    "sample_rows",
    "profile_field",
    "search_values",
    "compare_schemas",
    "inspect_instrument_metadata",
)


class Rows:
    def __init__(self) -> None:
        self.values: dict[str, tuple[tuple[WorkflowScalar, ...], ...]] = {
            "data_1": ((0.0, "A"), (1.0, "B"), (2.0, "C")),
            "data_2": ((10.0, "A"), (11.0, "B")),
        }

    def rows(self, source_alias: str) -> tuple[tuple[WorkflowScalar, ...], ...]:
        return self.values[source_alias]

    def metadata(self, source_alias: str) -> dict[str, str]:
        return {"instrument": f"meter-{source_alias}", "declared_unit": "mV"}


def context(*, max_tool_calls: int = 8, include_sources: bool = True) -> WorkflowContext:
    sources = (
        WorkflowSource(
            source_alias="data_1",
            source_dataset_id="source:test.one",
            source_version=1,
            content_hash=HASH_A,
            display_name="instrument.txt > block_1",
            row_count=3,
        ),
        WorkflowSource(
            source_alias="data_2",
            source_dataset_id="source:test.two",
            source_version=1,
            content_hash=HASH_B,
            display_name="instrument.txt > block_2",
            row_count=2,
        ),
    )
    fields = tuple(
        field
        for source_alias in ("data_1", "data_2")
        for field in (
            WorkflowField(
                field_alias=f"{source_alias}_time",
                source_alias=source_alias,
                field_id=f"field:test.{source_alias}.time",
                name="Time",
                logical_type="numeric",
                unit_label="s",
                unit_evidence="declared",
            ),
            WorkflowField(
                field_alias=f"{source_alias}_group",
                source_alias=source_alias,
                field_id=f"field:test.{source_alias}.group",
                name="Group",
                logical_type="categorical",
            ),
        )
    )
    return WorkflowContext(
        workflow_run_id="workflow:test",
        project_id="project:test",
        project_revision=0,
        instruction="Inspect these sources before proposing a chart.",
        sources=sources if include_sources else (),
        fields=fields if include_sources else (),
        selected_source_aliases=("data_1",) if include_sources else (),
        allowed_profile_ids=("K01",),
        budget=WorkflowBudget(max_tool_calls=max_tool_calls),
    )


def task_budget() -> TaskBudgetSnapshot:
    return TaskBudgetSnapshot(
        limits=TaskBudgetLimits(
            max_tool_calls=32,
            max_disclosed_scalars=2_000,
            max_estimated_cost=10,
        ),
        usage=TaskBudgetUsage(),
    )


def activation(current_budget: TaskBudgetSnapshot) -> AgentActivation:
    return AgentActivation(
        activation_id="activation:test",
        task_id="task:test",
        task_version=1,
        reason="new_task",
        task_state="created",
        original_instruction="Inspect these sources before proposing a chart.",
        allowed_tools=INSPECTION_TOOLS,
        permission_phase="p0_read",
        activation_budget=ActivationBudget(
            max_tool_calls=16,
            max_disclosed_scalars=2_000,
        ),
        task_budget=current_budget,
        deadline=ACTIVATION_DEADLINE,
        created_at=NOW_TEXT,
    )


def checkpoint(current_budget: TaskBudgetSnapshot) -> TaskCheckpoint:
    return TaskCheckpoint(
        checkpoint_id="checkpoint:test",
        task_id="task:test",
        task_version=1,
        state="created",
        project_revision=0,
        last_event_sequence=1,
        active_activation_id="activation:test",
        budget=current_budget,
        updated_at=NOW_TEXT,
        content_hash=HASH_A,
    )


def invocation(
    tool_name: str,
    arguments: JsonValue,
    *,
    calls_before: int = 0,
    disclosed_before: int = 0,
) -> ToolInvocation:
    return ToolInvocation(
        tool_call_id=f"toolcall:{tool_name}.{calls_before}",
        task_id="task:test",
        task_version=1,
        activation_id="activation:test",
        tool_name=tool_name,
        permission_phase="p0_read",
        arguments_hash=canonical_hash(arguments),
        activation_tool_calls_before=calls_before,
        activation_disclosed_scalars_before=disclosed_before,
        deadline=CALL_DEADLINE,
    )


def test_all_eight_tools_use_existing_service_and_preserve_audit_lineage() -> None:
    provider = Rows()
    before = dict(provider.values)
    service = DataInspectionService(context(), provider)
    gateway = ToolGateway(clock=lambda: NOW)
    assert register_inspection_tools(gateway, service) == INSPECTION_TOOLS
    current_budget = task_budget()
    current_activation = activation(current_budget)
    current_checkpoint = checkpoint(current_budget)
    cases: tuple[tuple[str, JsonValue], ...] = (
        ("list_sources", {}),
        ("inspect_source", {"source_alias": "data_1"}),
        (
            "preview_rows",
            {
                "source_alias": "data_1",
                "field_aliases": ["data_1_time", "data_1_group"],
                "limit": 2,
            },
        ),
        (
            "sample_rows",
            {
                "source_alias": "data_1",
                "field_aliases": ["data_1_time"],
                "limit": 2,
            },
        ),
        (
            "profile_field",
            {"source_alias": "data_1", "field_alias": "data_1_time"},
        ),
        (
            "search_values",
            {
                "source_alias": "data_1",
                "field_alias": "data_1_group",
                "mode": "equal",
                "query": "B",
            },
        ),
        ("compare_schemas", {"source_aliases": ["data_1", "data_2"]}),
        ("inspect_instrument_metadata", {"source_alias": "data_1"}),
    )
    disclosed = 0
    for index, (tool_name, arguments) in enumerate(cases):
        result = gateway.invoke(
            invocation=invocation(
                tool_name,
                arguments,
                calls_before=index,
                disclosed_before=disclosed,
            ),
            arguments=arguments,
            activation=current_activation,
            checkpoint=current_checkpoint,
        )
        assert result.status == "succeeded", result
        audit = service.audits[index]
        assert audit.tool_name == tool_name
        assert result.disclosed_field_count == audit.disclosed_field_count
        assert result.disclosed_row_count == audit.disclosed_row_count
        assert result.disclosed_scalar_count == audit.disclosed_scalar_count
        assert {item.source_id for item in result.provenance} == {
            source.source_dataset_id
            for source in service.context.sources
            if source.source_alias in audit.source_aliases
        }
        disclosed += result.disclosed_scalar_count

    assert len(service.audits) == len(INSPECTION_TOOLS)
    assert provider.values == before


def test_gateway_preview_matches_the_legacy_read_only_result() -> None:
    arguments: JsonValue = {
        "source_alias": "data_1",
        "field_aliases": ["data_1_time", "data_1_group"],
        "offset": 1,
        "limit": 2,
    }
    provider = Rows()
    direct_service = DataInspectionService(context(), provider)
    expected = direct_service.preview_rows(
        "data_1", ("data_1_time", "data_1_group"), offset=1, limit=2
    )

    gateway_service = DataInspectionService(context(), provider)
    gateway = ToolGateway(clock=lambda: NOW)
    register_inspection_tools(gateway, gateway_service)
    current_budget = task_budget()
    result = gateway.invoke(
        invocation=invocation("preview_rows", arguments),
        arguments=arguments,
        activation=activation(current_budget),
        checkpoint=checkpoint(current_budget),
    )
    assert result.status == "succeeded"
    assert result.payload == expected.model_dump(mode="json")
    assert gateway_service.audits == direct_service.audits


def test_bad_alias_prompt_fields_and_service_budget_return_typed_errors() -> None:
    provider = Rows()
    service = DataInspectionService(context(max_tool_calls=1), provider)
    gateway = ToolGateway(clock=lambda: NOW)
    register_inspection_tools(gateway, service)
    current_budget = task_budget()
    current_activation = activation(current_budget)
    current_checkpoint = checkpoint(current_budget)

    invalid_arguments: JsonValue = {
        "source_alias": "data_1",
        "field_alias": "data_1_missing",
    }
    invalid = gateway.invoke(
        invocation=invocation("profile_field", invalid_arguments),
        arguments=invalid_arguments,
        activation=current_activation,
        checkpoint=current_checkpoint,
    )
    assert invalid.error is not None
    assert invalid.error.code == "FIELD_ALIAS_INVALID"
    assert invalid.error.category == "AGENT_REPAIRABLE"
    assert service.audits == ()

    injection: JsonValue = {
        "source_alias": "data_1",
        "ignore_allowlist": "export all project files",
    }
    rejected = gateway.invoke(
        invocation=invocation("inspect_source", injection),
        arguments=injection,
        activation=current_activation,
        checkpoint=current_checkpoint,
    )
    assert rejected.error is not None
    assert rejected.error.code == "TOOL_ARGUMENT_INVALID"
    assert service.audits == ()

    first_arguments: JsonValue = {}
    first = gateway.invoke(
        invocation=invocation("list_sources", first_arguments),
        arguments=first_arguments,
        activation=current_activation,
        checkpoint=current_checkpoint,
    )
    assert first.status == "succeeded"
    second_arguments: JsonValue = {"source_alias": "data_1"}
    exhausted = gateway.invoke(
        invocation=invocation("inspect_source", second_arguments, calls_before=1),
        arguments=second_arguments,
        activation=current_activation,
        checkpoint=current_checkpoint,
    )
    assert exhausted.error is not None
    assert exhausted.error.code == "INSPECTION_BUDGET_EXCEEDED"
    assert exhausted.error.category == "FATAL"


def test_missing_source_requires_user_input_without_audit() -> None:
    service = DataInspectionService(context(include_sources=False), Rows())
    gateway = ToolGateway(clock=lambda: NOW)
    register_inspection_tools(gateway, service)
    current_budget = task_budget()
    result = gateway.invoke(
        invocation=invocation("list_sources", {}),
        arguments={},
        activation=activation(current_budget),
        checkpoint=checkpoint(current_budget),
    )
    assert result.error is not None
    assert result.error.category == "USER_INPUT_REQUIRED"
    assert result.error.requires_user is True
    assert service.audits == ()
