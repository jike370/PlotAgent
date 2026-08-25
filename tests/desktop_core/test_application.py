from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from plotagent.contracts.agent_tasks import (
    AgentIntentReady,
    ProfileSelectionDecision,
    TaskIntent,
)
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.workflows import DraftFieldBinding, TaskDraftItem
from plotagent.desktop_core.agent_execution import DurableTaskExecutionService
from plotagent.desktop_core.application import DesktopApplication
from plotagent.desktop_core.engine_session import DesktopEngineSession
from plotagent.desktop_core.protocol import JsonValue
from plotagent.desktop_core.services import RpcContext, RpcServiceError, ServiceRegistry
from plotagent.desktop_core.tasks import BoundedWorkerExecutor, TaskRegistry
from plotagent.desktop_core.workflow_service import (
    DesktopWorkflowService,
    WorkflowServiceError,
)
from plotagent.security.credentials import InMemoryCredentialStore
from plotagent.workflows.executor import TaskPlanExecutor

FIXTURES = Path(__file__).parents[1] / "fixtures" / "import" / "files"


class ApplicationHarness:
    def __init__(self, root: Path) -> None:
        self.application = DesktopApplication(
            root,
            credential_store=InMemoryCredentialStore(),
        )
        self.registry = ServiceRegistry()
        self.workers = BoundedWorkerExecutor(max_workers=2, maximum_pending=4)
        self.tasks = TaskRegistry(lambda _event: None)
        self.application.configure_services(self.registry, self.tasks, self.workers)

    def call(self, method: str, params: dict[str, JsonValue]) -> dict[str, Any]:
        context = RpcContext(
            request_id="req:" + uuid.uuid4().hex,
            tasks=self.tasks,
            workers=self.workers,
        )
        return cast(dict[str, Any], self.registry.dispatch(method, context, params))

    def close(self) -> None:
        self.workers.shutdown()
        self.application.close()


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[ApplicationHarness]:
    value = ApplicationHarness(tmp_path / "app")
    try:
        yield value
    finally:
        value.close()


@pytest.mark.parametrize(
    "method",
    (
        "workflow.prepare",
        "workflow.submit_draft",
        "workflow.inspect",
        "workflow.preview_operation",
        "workflow.ask_user",
        "workflow.report_unsupported",
        "workflow.plans.get",
        "workflow.plans.list",
        "workflow.plans.confirm",
        "workflow.plans.reject",
        "workflow.plans.run",
        "workflow.plans.resume",
        "workflow.recipes.save",
        "workflow.recipes.list",
    ),
)
def test_legacy_workflow_rpc_is_not_public(
    harness: ApplicationHarness,
    method: str,
) -> None:
    with pytest.raises(RpcServiceError) as captured:
        harness.call(method, {})
    assert captured.value.code == "METHOD_NOT_FOUND"


def _create_open(harness: ApplicationHarness) -> tuple[str, int]:
    created = harness.call(
        "projects.create",
        {"display_name": "Agent Native 测试", "idempotency_key": "project-key"},
    )
    project_id = cast(str, created["project_id"])
    opened = harness.call("projects.open", {"project_id": project_id})
    return project_id, cast(int, opened["project_version"])


def test_workflow_source_boundary_accepts_sixty_four_and_rejects_sixty_five() -> None:
    sixty_four_sources = [
        {"dataset_id": f"source:{position}", "source_version": 1}
        for position in range(1, 65)
    ]
    assert len(
        DesktopWorkflowService._source_requests({"selected_sources": sixty_four_sources})
    ) == 64

    with pytest.raises(WorkflowServiceError) as captured:
        DesktopWorkflowService._source_requests(
            {
                "selected_sources": [
                    {"dataset_id": f"source:{position}", "source_version": 1}
                    for position in range(1, 66)
                ]
            }
        )
    assert captured.value.code == "SOURCE_LIMIT_EXCEEDED"


def test_agent_task_v2_api_persists_checkpoint_and_events(
    harness: ApplicationHarness,
) -> None:
    project_id, _revision = _create_open(harness)
    envelope = {
        "schema_version": "task-envelope.v2",
        "task_id": "task:desktop-api",
        "task_version": 1,
        "project_id": project_id,
        "project_revision": 0,
        "original_instruction": "Create a line chart.",
        "locale": "zh-CN",
        "selected_sources": [
            {
                "source_dataset_id": "source:test",
                "source_version": 1,
                "content_hash": "a" * 64,
            }
        ],
        "selected_plots": [],
        "selected_profile_ids": ["K01"],
        "authorized_resources": [],
        "budget": {"max_estimated_cost": 10},
        "created_at": "2026-08-18T10:00:00Z",
    }
    created = harness.call(
        "agent.tasks.create",
        {"project_id": project_id, "envelope": envelope},
    )
    assert created["state"] == "created"
    advanced = harness.call(
        "agent.tasks.advance",
        {
            "project_id": project_id,
            "task_id": "task:desktop-api",
            "expected_task_version": 1,
            "next_state": "investigating",
            "reason_code": "API_TEST",
        },
    )
    assert advanced["task_version"] == 2
    assert harness.call(
        "agent.tasks.list", {"project_id": project_id, "state": "investigating"}
    )["tasks"] == [advanced]
    events = harness.call(
        "agent.tasks.events", {"project_id": project_id, "task_id": "task:desktop-api"}
    )["events"]
    assert [event["sequence"] for event in events] == [1, 2]

    harness.call("projects.close", {"project_id": project_id})
    harness.call("projects.open", {"project_id": project_id})
    restored = harness.call(
        "agent.tasks.get", {"project_id": project_id, "task_id": "task:desktop-api"}
    )
    assert restored == advanced


def test_agent_task_answer_accepts_json_selection_arrays_in_context_update(
    harness: ApplicationHarness,
) -> None:
    project_id, _revision = _create_open(harness)
    sources = [
        {
            "source_dataset_id": f"source:sheet-{position}",
            "source_version": 1,
            "content_hash": format(position, "064x"),
        }
        for position in range(1, 6)
    ]
    created = harness.call(
        "agent.tasks.create",
        {
            "project_id": project_id,
            "envelope": {
                "task_id": "task:multi-question-answer",
                "task_version": 1,
                "project_id": project_id,
                "project_revision": 0,
                "original_instruction": "Create one K01 plot for each selected sheet.",
                "selected_sources": sources,
                "selected_profile_ids": ["K01"],
                "budget": {"max_estimated_cost": 10},
                "created_at": "2026-08-21T10:00:00Z",
            },
        },
    )
    investigating = harness.call(
        "agent.tasks.advance",
        {
            "project_id": project_id,
            "task_id": "task:multi-question-answer",
            "expected_task_version": created["task_version"],
            "next_state": "investigating",
            "reason_code": "ASKING_MULTIPLE_BINDINGS",
        },
    )
    waiting = harness.call(
        "agent.tasks.advance",
        {
            "project_id": project_id,
            "task_id": "task:multi-question-answer",
            "expected_task_version": investigating["task_version"],
            "next_state": "awaiting_input",
            "reason_code": "MULTIPLE_BINDINGS_REQUIRED",
        },
    )

    answered = harness.call(
        "agent.tasks.user_event",
        {
            "project_id": project_id,
            "task_id": "task:multi-question-answer",
            "expected_task_version": waiting["task_version"],
            "action": "answered",
            "user_event_id": "user-event:multi-question-answer",
            "payload_hash": "b" * 64,
            "message": (
                "Events_A: X=Time_min, Y=Signal_mV; "
                "Events_B: X=Dose_uM, Y=Response_mV."
            ),
            "context_update": {
                "project_revision": 0,
                "selected_sources": sources,
                "selected_plots": [],
                "selected_profile_ids": ["K01"],
            },
        },
    )

    assert answered["state"] == "investigating"
    events = harness.call(
        "agent.tasks.events",
        {"project_id": project_id, "task_id": "task:multi-question-answer"},
    )["events"]
    user_event = next(event for event in events if event["event_type"] == "user_task_event")
    assert user_event["context_update"] == {
        "project_revision": 0,
        "selected_sources": sources,
        "selected_plots": [],
        "selected_profile_ids": ["K01"],
    }


def test_agent_task_v2_cancel_is_durable_and_terminal(harness: ApplicationHarness) -> None:
    project_id, _revision = _create_open(harness)
    task_id = "task:desktop-cancel"
    created = harness.call(
        "agent.tasks.create",
        {
            "project_id": project_id,
            "envelope": {
                "task_id": task_id,
                "task_version": 1,
                "project_id": project_id,
                "project_revision": 0,
                "original_instruction": "Create a line chart.",
                "selected_sources": [
                    {
                        "source_dataset_id": "source:test",
                        "source_version": 1,
                        "content_hash": "a" * 64,
                    }
                ],
                "selected_profile_ids": ["K01"],
                "budget": {"max_estimated_cost": 10},
                "created_at": "2026-08-18T10:00:00Z",
            },
        },
    )
    directive = harness.call(
        "agent.tasks.pump.next", {"project_id": project_id, "task_id": task_id}
    )
    activation_id = directive["activation"]["activation_id"]
    harness.call(
        "agent.tasks.activation.running",
        {"project_id": project_id, "activation_id": activation_id},
    )
    cancelled = harness.call(
        "agent.tasks.cancel",
        {
            "project_id": project_id,
            "task_id": task_id,
            "expected_task_version": created["task_version"],
            "user_event_id": "user-event:desktop-cancel",
            "payload_hash": "c" * 64,
        },
    )
    assert cancelled["state"] == "cancelled"
    events = harness.call(
        "agent.tasks.events", {"project_id": project_id, "task_id": task_id}
    )["events"]
    activation_events = [
        event for event in events if event["event_type"] == "agent_activation"
    ]
    assert [event["phase"] for event in activation_events] == [
        "requested",
        "started",
        "aborted",
    ]


def test_agent_v2_restart_finalizes_pre_execution_cancellation_without_a_plan(
    tmp_path: Path,
) -> None:
    root = tmp_path / "restart-pre-execution-cancel"
    first = ApplicationHarness(root)
    try:
        project_id, _revision = _create_open(first)
        created = first.call(
            "agent.tasks.create",
            {
                "project_id": project_id,
                "envelope": {
                    "task_id": "task:restart-pre-execution-cancel",
                    "task_version": 1,
                    "project_id": project_id,
                    "project_revision": 0,
                    "original_instruction": "Create a line chart.",
                    "selected_sources": [{
                        "source_dataset_id": "source:test",
                        "source_version": 1,
                        "content_hash": "a" * 64,
                    }],
                    "selected_profile_ids": ["K01"],
                    "budget": {"max_estimated_cost": 10},
                    "created_at": "2026-08-20T10:00:00Z",
                },
            },
        )
        session = first.application._sessions[project_id]  # noqa: SLF001
        cancelling = session.durable_tasks.cancel(
            "task:restart-pre-execution-cancel",
            expected_task_version=created["task_version"],
            user_event_id="user-event:restart-pre-execution-cancel",
            payload_hash="c" * 64,
        )
        assert cancelling.state == "cancelling"
        assert cancelling.items == ()
    finally:
        first.close()

    second = ApplicationHarness(root)
    try:
        second.call("projects.open", {"project_id": project_id})
        restored = second.call(
            "agent.tasks.get",
            {
                "project_id": project_id,
                "task_id": "task:restart-pre-execution-cancel",
            },
        )
        assert restored["state"] == "cancelled"
        assert restored["project_revision"] == 0
    finally:
        second.close()


def test_agent_follow_up_links_new_task_without_reopening_parent(
    harness: ApplicationHarness,
) -> None:
    project_id, _revision = _create_open(harness)

    def envelope(task_id: str, *, parent_task_id: str | None = None) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "task_version": 1,
            "project_id": project_id,
            "project_revision": 0,
            "original_instruction": "Continue with a related chart.",
            "selected_sources": [
                {
                    "source_dataset_id": "source:test",
                    "source_version": 1,
                    "content_hash": "a" * 64,
                }
            ],
            "selected_profile_ids": ["K01"],
            "budget": {"max_estimated_cost": 10},
            "created_at": "2026-08-18T10:00:00Z",
            **(
                {}
                if parent_task_id is None
                else {"parent_task_id": parent_task_id, "relationship": "follow_up"}
            ),
        }

    parent = harness.call(
        "agent.tasks.create",
        {"project_id": project_id, "envelope": envelope("task:parent")},
    )
    cancelled = harness.call(
        "agent.tasks.cancel",
        {
            "project_id": project_id,
            "task_id": "task:parent",
            "expected_task_version": parent["task_version"],
            "user_event_id": "user-event:parent-cancel",
            "payload_hash": "c" * 64,
        },
    )
    child = harness.call(
        "agent.tasks.create",
        {
            "project_id": project_id,
            "envelope": envelope("task:child", parent_task_id="task:parent"),
        },
    )
    assert cancelled["state"] == "cancelled"
    assert child["state"] == "created"
    assert harness.call(
        "agent.tasks.get", {"project_id": project_id, "task_id": "task:parent"}
    ) == cancelled

    harness.call(
        "agent.tasks.create",
        {"project_id": project_id, "envelope": envelope("task:active-parent")},
    )
    with pytest.raises(RpcServiceError) as caught:
        harness.call(
            "agent.tasks.create",
            {
                "project_id": project_id,
                "envelope": envelope(
                    "task:premature-child", parent_task_id="task:active-parent"
                ),
            },
        )
    assert caught.value.code == "FOLLOW_UP_PARENT_ACTIVE"


def test_agent_task_pump_next_creates_one_durable_activation(
    harness: ApplicationHarness,
) -> None:
    project_id, _revision = _create_open(harness)
    envelope = {
        "task_id": "task:pump-api",
        "task_version": 1,
        "project_id": project_id,
        "project_revision": 0,
        "original_instruction": "Create one K01 line chart.",
        "selected_sources": [
            {
                "source_dataset_id": "source:test",
                "source_version": 1,
                "content_hash": "a" * 64,
            }
        ],
        "selected_profile_ids": ["K01"],
        "budget": {},
        "created_at": "2026-08-18T10:00:00Z",
    }
    harness.call("agent.tasks.create", {"project_id": project_id, "envelope": envelope})

    first = harness.call(
        "agent.tasks.pump.next",
        {"project_id": project_id, "task_id": "task:pump-api"},
    )
    second = harness.call(
        "agent.tasks.pump.next",
        {"project_id": project_id, "task_id": "task:pump-api"},
    )
    assert first == second
    assert first["kind"] == "run_activation"
    activation = cast(dict[str, object], first["activation"])
    assert activation["task_id"] == "task:pump-api"
    assert activation["task_state"] == "created"
    assert "inspect_source" in cast(list[str], activation["allowed_tools"])


def _import_dataset(
    harness: ApplicationHarness,
    project_id: str,
    revision: int,
    *,
    key: str,
) -> dict[str, Any]:
    imported = harness.call(
        "datasets.import",
        {
            "project_id": project_id,
            "resource_id": "resource:" + key,
            "source_path": str(FIXTURES / "excel_two_sheets.xlsx"),
            "idempotency_key": key,
            "expected_version": revision,
            "options": {},
        },
    )
    return cast(dict[str, Any], imported)


def test_agent_activation_host_rpc_prepares_and_invokes_read_tool(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="agent-v2-host")
    dataset = cast(dict[str, Any], cast(list[object], imported["datasets"])[0])
    task_id = "task:activation-host-api"
    harness.call(
        "agent.tasks.create",
        {
            "project_id": project_id,
            "envelope": {
                "task_id": task_id,
                "task_version": 1,
                "project_id": project_id,
                "project_revision": imported["project_version"],
                "original_instruction": "Create one K01 line chart.",
                "selected_sources": [
                    {
                        "source_dataset_id": dataset["source_dataset_id"],
                        "source_version": dataset["source_version"],
                        "content_hash": dataset["content_hash"],
                    }
                ],
                "selected_profile_ids": ["K01"],
                "budget": {},
                "created_at": "2026-08-18T10:00:00Z",
            },
        },
    )
    directive = harness.call(
        "agent.tasks.pump.next", {"project_id": project_id, "task_id": task_id}
    )
    activation = cast(dict[str, Any], directive["activation"])
    activation_id = cast(str, activation["activation_id"])
    harness.call(
        "agent.tasks.activation.running",
        {"project_id": project_id, "activation_id": activation_id},
    )
    prepared = harness.call(
        "agent.activations.prepare",
        {"project_id": project_id, "activation_id": activation_id},
    )
    context = cast(dict[str, Any], prepared["context"])
    assert cast(list[dict[str, Any]], context["selected_sources"])[0] == {
        "source_dataset_id": dataset["source_dataset_id"],
        "source_version": dataset["source_version"],
        "content_hash": dataset["content_hash"],
    }
    assert len(cast(list[object], prepared["tools"])) == len(activation["allowed_tools"])

    arguments = {"source_alias": "data_1"}
    deadline = (datetime.now(UTC) + timedelta(seconds=3)).isoformat().replace("+00:00", "Z")
    result = harness.call(
        "agent.tools.invoke",
        {
            "project_id": project_id,
            "invocation": {
                "tool_call_id": "toolcall:activation-host-api",
                "task_id": task_id,
                "task_version": 1,
                "activation_id": activation_id,
                "tool_name": "inspect_source",
                "permission_phase": "p0_read",
                "arguments_hash": canonical_hash(arguments),
                "activation_tool_calls_before": 0,
                "activation_disclosed_scalars_before": 0,
                "expected_project_revision": imported["project_version"],
                "deadline": deadline,
            },
            "arguments": arguments,
        },
    )
    assert result["status"] == "succeeded"
    checkpoint = harness.call(
        "agent.tasks.get", {"project_id": project_id, "task_id": task_id}
    )
    assert cast(dict[str, Any], checkpoint["budget"])["usage"]["tool_calls"] == 1


def test_agent_v2_confirmed_plan_executes_and_verifies_one_plot(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="agent-v2-execute")
    dataset = cast(dict[str, Any], cast(list[object], imported["datasets"])[0])
    task_id = "task:confirmed-execution-api"
    harness.call(
        "agent.tasks.create",
        {
            "project_id": project_id,
            "envelope": {
                "task_id": task_id,
                "task_version": 1,
                "project_id": project_id,
                "project_revision": imported["project_version"],
                "original_instruction": "Create one K01 line chart.",
                "selected_sources": [
                    {
                        "source_dataset_id": dataset["source_dataset_id"],
                        "source_version": dataset["source_version"],
                        "content_hash": dataset["content_hash"],
                    }
                ],
                "selected_profile_ids": ["K01"],
                "budget": {},
                "created_at": "2026-08-18T10:00:00Z",
            },
        },
    )
    directive = harness.call(
        "agent.tasks.pump.next", {"project_id": project_id, "task_id": task_id}
    )
    activation = cast(dict[str, Any], directive["activation"])
    activation_id = cast(str, activation["activation_id"])
    harness.call(
        "agent.tasks.activation.running",
        {"project_id": project_id, "activation_id": activation_id},
    )
    prepared = harness.call(
        "agent.activations.prepare",
        {"project_id": project_id, "activation_id": activation_id},
    )
    context = cast(dict[str, Any], prepared["context"])
    source_context = cast(list[dict[str, Any]], context["source_contexts"])[0]
    numeric_aliases = [
        cast(str, field["field_alias"])
        for field in cast(list[dict[str, object]], source_context["fields"])
        if field["logical_type"] == "numeric"
    ]
    assert len(numeric_aliases) >= 2
    intent = TaskIntent(
        intent_id="intent:confirmed-execution-api",
        intent_version=1,
        task_id=task_id,
        task_version=1,
        created_by_activation_id=activation_id,
        summary="Create one K01 line chart.",
        items=(
            TaskDraftItem(
                task_kind="create",
                item_id="item:confirmed-execution-api.1",
                plot_alias="plot_1",
                profile_id="K01",
                source_aliases=("data_1",),
                bindings=(
                    DraftFieldBinding(
                        role="x",
                        source_alias="data_1",
                        field_alias=numeric_aliases[0],
                    ),
                    DraftFieldBinding(
                        role="y",
                        source_alias="data_1",
                        field_alias=numeric_aliases[1],
                    ),
                ),
            ),
        ),
        profile_selections=(
            ProfileSelectionDecision(
                decision_id="decision:profile-confirmed-execution-api-1",
                item_id="item:confirmed-execution-api.1",
                profile_id="K01",
                basis="ui_selected",
            ),
        ),
        context_hash=cast(str, context["content_hash"]),
        content_hash="0" * 64,
    )
    intent = intent.model_copy(
        update={
            "content_hash": canonical_hash(
                intent.model_dump(mode="json", exclude={"content_hash"})
            )
        }
    )
    yielded = AgentIntentReady(
        activation_id=activation_id,
        task_id=task_id,
        task_version=1,
        intent=intent,
    )
    validated = harness.call(
        "agent.yields.validate",
        {
            "project_id": project_id,
            "activation_id": activation_id,
            "yield": yielded.model_dump(mode="json"),
        },
    )
    staged = harness.call(
        "agent.tasks.yield.accept",
        {"project_id": project_id, "yield": validated},
    )
    assert staged["state"] == "intent_staged"
    waiting = harness.call(
        "agent.tasks.pump.next", {"project_id": project_id, "task_id": task_id}
    )
    assert waiting["reason"] == "awaiting_confirmation"
    view = harness.call(
        "agent.tasks.plan.get", {"project_id": project_id, "task_id": task_id}
    )
    assert view["confirmation_state"] == "pending"
    assert view["plan"]["items"][0]["profile_id"] == "K01"
    assert view["prepared_preview_errors"] == []
    assert len(view["prepared_previews"]) == 1
    prepared_preview = view["prepared_previews"][0]
    assert prepared_preview["item_id"] == "item:confirmed-execution-api.1"
    assert prepared_preview["input_row_count"] == prepared_preview["output_row_count"]
    assert prepared_preview["input_field_count"] == prepared_preview["output_field_count"]
    assert 1 <= len(prepared_preview["rows"]) <= 3
    assert all(
        len(row) == prepared_preview["output_field_count"]
        for row in prepared_preview["rows"]
    )
    assert harness.call("engine.plots.list", {"project_id": project_id})[
        "project_version"
    ] == imported["project_version"]
    confirmed = harness.call(
        "agent.tasks.plan.confirm",
        {
            "project_id": project_id,
            "task_id": task_id,
            "expected_task_version": view["task"]["task_version"],
            "user_event_id": "user-event:confirm-execution-api",
            "plan_hash": view["plan_hash"],
        },
    )
    assert confirmed["task"]["state"] == "executing"
    result = harness.call(
        "agent.tasks.execute", {"project_id": project_id, "task_id": task_id}
    )
    assert result["task"]["state"] == "completed_verified"
    assert result["plot"]["plot_version"] == 1
    plots = harness.call("engine.plots.list", {"project_id": project_id})["plots"]
    assert [plot["plot_id"] for plot in plots] == [result["plot"]["plot_id"]]


def _execute_agent_create_batch(
    harness: ApplicationHarness,
    project_id: str,
    imported: dict[str, Any],
    *,
    token: str,
    profiles: tuple[str, ...],
    confirm: bool = True,
    execute: bool = True,
) -> dict[str, Any]:
    dataset = cast(dict[str, Any], cast(list[object], imported["datasets"])[0])
    task_id = f"task:{token}"
    harness.call(
        "agent.tasks.create",
        {
            "project_id": project_id,
            "envelope": {
                "task_id": task_id,
                "task_version": 1,
                "project_id": project_id,
                "project_revision": imported["project_version"],
                "original_instruction": "Create the requested chart batch.",
                "selected_sources": [
                    {
                        "source_dataset_id": dataset["source_dataset_id"],
                        "source_version": dataset["source_version"],
                        "content_hash": dataset["content_hash"],
                    }
                ],
                "selected_profile_ids": list(profiles),
                "budget": {},
                "created_at": "2026-08-18T10:00:00Z",
            },
        },
    )
    directive = harness.call(
        "agent.tasks.pump.next", {"project_id": project_id, "task_id": task_id}
    )
    activation = cast(dict[str, Any], directive["activation"])
    activation_id = cast(str, activation["activation_id"])
    harness.call(
        "agent.tasks.activation.running",
        {"project_id": project_id, "activation_id": activation_id},
    )
    prepared = harness.call(
        "agent.activations.prepare",
        {"project_id": project_id, "activation_id": activation_id},
    )
    context = cast(dict[str, Any], prepared["context"])
    source_context = cast(list[dict[str, Any]], context["source_contexts"])[0]
    numeric_aliases = [
        cast(str, field["field_alias"])
        for field in cast(list[dict[str, object]], source_context["fields"])
        if field["logical_type"] == "numeric"
    ]
    assert len(numeric_aliases) >= 2
    intent = TaskIntent(
        intent_id=f"intent:{token}",
        intent_version=1,
        task_id=task_id,
        task_version=1,
        created_by_activation_id=activation_id,
        summary="Create the requested chart batch.",
        items=tuple(
            TaskDraftItem(
                task_kind="create",
                item_id=f"item:{token}.{position}",
                plot_alias=f"plot_{position}",
                profile_id=profile,
                source_aliases=("data_1",),
                bindings=(
                    DraftFieldBinding(
                        role="x",
                        source_alias="data_1",
                        field_alias=numeric_aliases[0],
                    ),
                    DraftFieldBinding(
                        role="y",
                        source_alias="data_1",
                        field_alias=numeric_aliases[1],
                    ),
                ),
            )
            for position, profile in enumerate(profiles, start=1)
        ),
        profile_selections=tuple(
            ProfileSelectionDecision(
                decision_id=f"decision:profile-{token}-{position}",
                item_id=f"item:{token}.{position}",
                profile_id=profile,
                basis="ui_selected",
            )
            for position, profile in enumerate(profiles, start=1)
        ),
        context_hash=cast(str, context["content_hash"]),
        content_hash="0" * 64,
    )
    intent = intent.model_copy(
        update={
            "content_hash": canonical_hash(
                intent.model_dump(mode="json", exclude={"content_hash"})
            )
        }
    )
    yielded = AgentIntentReady(
        activation_id=activation_id,
        task_id=task_id,
        task_version=1,
        intent=intent,
    )
    validated = harness.call(
        "agent.yields.validate",
        {
            "project_id": project_id,
            "activation_id": activation_id,
            "yield": yielded.model_dump(mode="json"),
        },
    )
    harness.call(
        "agent.tasks.yield.accept", {"project_id": project_id, "yield": validated}
    )
    waiting = harness.call(
        "agent.tasks.pump.next", {"project_id": project_id, "task_id": task_id}
    )
    assert waiting["reason"] == "awaiting_confirmation"
    view = harness.call(
        "agent.tasks.plan.get", {"project_id": project_id, "task_id": task_id}
    )
    if not confirm:
        return view
    confirmed = harness.call(
        "agent.tasks.plan.confirm",
        {
            "project_id": project_id,
            "task_id": task_id,
            "expected_task_version": view["task"]["task_version"],
            "user_event_id": f"user-event:{token}",
            "plan_hash": view["plan_hash"],
        },
    )
    if not execute:
        return confirmed
    return harness.call(
        "agent.tasks.execute", {"project_id": project_id, "task_id": task_id}
    )


def test_agent_v2_rejects_a_stale_confirmation_without_project_side_effects(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="stale-confirmation")
    view = _execute_agent_create_batch(
        harness,
        project_id,
        imported,
        token="stale-confirmation",
        profiles=("K01",),
        confirm=False,
        execute=False,
    )
    revision_before = harness.call(
        "engine.plots.list", {"project_id": project_id}
    )["project_version"]

    with pytest.raises(RpcServiceError) as caught:
        harness.call(
            "agent.tasks.plan.confirm",
            {
                "project_id": project_id,
                "task_id": "task:stale-confirmation",
                "expected_task_version": view["task"]["task_version"],
                "user_event_id": "user-event:stale-confirmation",
                "plan_hash": "f" * 64,
            },
        )
    assert caught.value.code == "PLAN_CONFIRMATION_STALE"
    restored = harness.call(
        "agent.tasks.get",
        {"project_id": project_id, "task_id": "task:stale-confirmation"},
    )
    assert restored["state"] == "awaiting_confirmation"
    assert all(item["attempt_count"] == 0 for item in restored["items"])
    assert harness.call(
        "engine.plots.list", {"project_id": project_id}
    )["project_version"] == revision_before


def _accept_scoped_retry(
    harness: ApplicationHarness,
    project_id: str,
    task_id: str,
    item_id: str,
) -> None:
    directive = harness.call(
        "agent.tasks.pump.next", {"project_id": project_id, "task_id": task_id}
    )
    activation = cast(dict[str, Any], directive["activation"])
    activation_id = cast(str, activation["activation_id"])
    harness.call(
        "agent.tasks.activation.running",
        {"project_id": project_id, "activation_id": activation_id},
    )
    repair_environment = harness.call(
        "agent.activations.prepare",
        {"project_id": project_id, "activation_id": activation_id},
    )
    repair_prompt = cast(str, repair_environment["system_prompt"])
    assert "return intent_ready with the same intent_id" in repair_prompt
    assert "WORKFLOW_SOURCES_NOT_COMBINED" in repair_prompt
    assert "WORKFLOW_NON_ISOMORPHIC" in repair_prompt
    assert "field names, logical/physical types, and units identical" in repair_prompt
    assert "return needs_input for that exact fact" in repair_prompt
    assert "shown to the user for reconfirmation" in repair_prompt
    validated = harness.call(
        "agent.yields.validate",
        {
            "project_id": project_id,
            "activation_id": activation_id,
            "yield": {
                "outcome": "technical_repair_ready",
                "activation_id": activation_id,
                "task_id": task_id,
                "task_version": activation["task_version"],
                "proposal": {
                    "failed_report_ids": activation["verification_report_ids"],
                    "affected_item_ids": [item_id],
                    "repair_operations": ["retry_execution"],
                    "preserves_confirmed_semantics": True,
                },
            },
        },
    )
    accepted = harness.call(
        "agent.tasks.yield.accept", {"project_id": project_id, "yield": validated}
    )
    assert accepted["state"] == "executing"


def test_agent_v2_executes_confirmed_batch_and_verifies_every_item(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="agent-v2-batch")

    result = _execute_agent_create_batch(
        harness,
        project_id,
        imported,
        token="confirmed-batch",
        profiles=("K01", "K02"),
    )

    assert result["task"]["state"] == "completed_verified"
    assert len(result["plots"]) == 2
    assert len(result["verifications"]) == 2
    assert {item["state"] for item in result["task"]["items"]} == {"succeeded"}
    assert len(harness.call("engine.plots.list", {"project_id": project_id})["plots"]) == 2


def test_agent_v2_step_execution_yields_between_atomic_items_for_cancellation(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="agent-v2-step-cancel")
    confirmed = _execute_agent_create_batch(
        harness,
        project_id,
        imported,
        token="step-cancel",
        profiles=("K01", "K02"),
        execute=False,
    )

    first_step = harness.call(
        "agent.tasks.execute",
        {"project_id": project_id, "task_id": "task:step-cancel", "step": True},
    )

    assert confirmed["task"]["state"] == "executing"
    assert first_step["execution_pending"] is True
    assert first_step["task"]["state"] == "executing"
    assert [item["state"] for item in first_step["task"]["items"]] == [
        "succeeded",
        "staged",
    ]
    assert len(first_step["plots"]) == 1

    cancelled = harness.call(
        "agent.tasks.cancel",
        {
            "project_id": project_id,
            "task_id": "task:step-cancel",
            "expected_task_version": first_step["task"]["task_version"],
            "user_event_id": "user-event:step-cancel-request",
            "payload_hash": "f" * 64,
        },
    )
    assert cancelled["state"] == "cancelled"
    assert [item["state"] for item in cancelled["items"]] == [
        "succeeded",
        "cancelled",
    ]
    assert len(harness.call("engine.plots.list", {"project_id": project_id})["plots"]) == 1


def test_agent_v2_step_execution_does_not_implicitly_retry_an_earlier_failure(
    harness: ApplicationHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="agent-v2-step-failure")
    execute = TaskPlanExecutor.execute_compiled_item
    first_attempts = 0

    def fail_first(
        self: TaskPlanExecutor,
        item: Any,
        current_revision: int,
    ) -> tuple[int, int]:
        nonlocal first_attempts
        if item.profile_id == "K01":
            first_attempts += 1
            raise RuntimeError("Stable first-item failure.")
        return execute(self, item, current_revision)

    monkeypatch.setattr(TaskPlanExecutor, "execute_compiled_item", fail_first)
    _execute_agent_create_batch(
        harness,
        project_id,
        imported,
        token="step-failure",
        profiles=("K01", "K02"),
        execute=False,
    )

    first_step = harness.call(
        "agent.tasks.execute",
        {"project_id": project_id, "task_id": "task:step-failure", "step": True},
    )
    assert [item["state"] for item in first_step["task"]["items"]] == [
        "repairable_failed",
        "staged",
    ]

    second_step = harness.call(
        "agent.tasks.execute",
        {"project_id": project_id, "task_id": "task:step-failure", "step": True},
    )
    assert second_step["task"]["state"] == "partial"
    assert [item["attempt_count"] for item in second_step["task"]["items"]] == [1, 1]
    assert [failure["item_id"] for failure in second_step["failures"]] == [
        "item:step-failure.1"
    ]
    assert first_attempts == 1


def test_agent_v2_cancel_waits_for_the_running_item_and_preserves_its_receipt(
    harness: ApplicationHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="agent-v2-cancel-boundary")
    execute = TaskPlanExecutor.execute_compiled_item
    task_id = "task:cancel-boundary"
    requested = False

    def cancel_during_first_atomic_item(
        self: TaskPlanExecutor,
        item: Any,
        current_revision: int,
    ) -> tuple[int, int]:
        nonlocal requested
        if not requested:
            requested = True
            task = harness.call(
                "agent.tasks.get", {"project_id": project_id, "task_id": task_id}
            )
            cancelling = harness.call(
                "agent.tasks.cancel",
                {
                    "project_id": project_id,
                    "task_id": task_id,
                    "expected_task_version": task["task_version"],
                    "user_event_id": "user-event:cancel-at-boundary",
                    "payload_hash": "f" * 64,
                },
            )
            assert cancelling["state"] == "cancelling"
            assert cancelling["items"][0]["state"] == "running"
        return execute(self, item, current_revision)

    monkeypatch.setattr(
        TaskPlanExecutor,
        "execute_compiled_item",
        cancel_during_first_atomic_item,
    )
    result = _execute_agent_create_batch(
        harness,
        project_id,
        imported,
        token="cancel-boundary",
        profiles=("K01", "K02"),
    )

    assert requested is True
    assert result["task"]["state"] == "cancelled"
    assert [item["state"] for item in result["task"]["items"]] == [
        "succeeded",
        "cancelled",
    ]
    assert len(result["plots"]) == 1
    assert len(result["verifications"]) == 1
    assert result["verifications"][0]["status"] == "passed"
    events = harness.call(
        "agent.tasks.events", {"project_id": project_id, "task_id": task_id}
    )["events"]
    assert any(event["event_type"] == "tool_receipt" for event in events)
    assert any(event["event_type"] == "verification_report" for event in events)
    assert len(harness.call("engine.plots.list", {"project_id": project_id})["plots"]) == 1


@pytest.mark.parametrize("commit_before_exit", (False, True))
def test_agent_v2_restart_reconciles_cancelling_atomic_item(
    tmp_path: Path,
    commit_before_exit: bool,
) -> None:
    root = tmp_path / "restart-cancelling-app"
    first = ApplicationHarness(root)
    project_id = ""

    try:
        project_id, revision = _create_open(first)
        imported = _import_dataset(
            first,
            project_id,
            revision,
            key=f"restart-cancelling-{commit_before_exit}",
        )
        confirmed = _execute_agent_create_batch(
            first,
            project_id,
            imported,
            token="restart-cancelling",
            profiles=("K01", "K02"),
            execute=False,
        )
        session = first.application._sessions[project_id]  # noqa: SLF001
        task = session.durable_tasks.get_task("task:restart-cancelling")
        running = session.durable_tasks.transition_item(
            task.task_id,
            expected_task_version=task.task_version,
            item_id=task.items[0].item_id,
            expected_item_state="staged",
            next_state="running",
            reason_code="TEST_PROCESS_EXIT_DURING_ATOMIC_ITEM",
        )
        if commit_before_exit:
            plan = session.durable_tasks.get_plan(running.task_id)
            session.task_execution._item_executor().execute_compiled_item(  # noqa: SLF001
                plan.items[0],
                running.project_revision,
            )
        cancelling = session.durable_tasks.cancel(
            running.task_id,
            expected_task_version=running.task_version,
            user_event_id="user-event:restart-cancelling-cancel",
            payload_hash="e" * 64,
        )
        assert confirmed["task"]["state"] == "executing"
        assert cancelling.state == "cancelling"
        assert cancelling.items[0].state == "running"
    finally:
        first.close()

    second = ApplicationHarness(root)
    try:
        second.call("projects.open", {"project_id": project_id})
        restored = second.call(
            "agent.tasks.get",
            {"project_id": project_id, "task_id": "task:restart-cancelling"},
        )
        assert restored["state"] == "cancelled"
        expected_states = (
            ["succeeded", "cancelled"]
            if commit_before_exit
            else ["cancelled", "cancelled"]
        )
        assert [item["state"] for item in restored["items"]] == expected_states
        plots = second.call("engine.plots.list", {"project_id": project_id})["plots"]
        assert len(plots) == (1 if commit_before_exit else 0)
        if commit_before_exit:
            assert restored["items"][0]["receipt_ids"]
            assert restored["items"][0]["verification_report_ids"]
    finally:
        second.close()


@pytest.mark.parametrize("commit_before_exit", (False, True))
def test_agent_v2_restart_resumes_confirmed_execution_at_the_atomic_boundary(
    tmp_path: Path,
    commit_before_exit: bool,
) -> None:
    root = tmp_path / f"restart-executing-{commit_before_exit}"
    first = ApplicationHarness(root)
    project_id = ""
    try:
        project_id, revision = _create_open(first)
        imported = _import_dataset(
            first,
            project_id,
            revision,
            key=f"restart-executing-{commit_before_exit}",
        )
        _execute_agent_create_batch(
            first,
            project_id,
            imported,
            token="restart-executing",
            profiles=("K01", "K02"),
            execute=False,
        )
        session = first.application._sessions[project_id]  # noqa: SLF001
        task = session.durable_tasks.get_task("task:restart-executing")
        running = session.durable_tasks.transition_item(
            task.task_id,
            expected_task_version=task.task_version,
            item_id=task.items[0].item_id,
            expected_item_state="staged",
            next_state="running",
            reason_code="TEST_PROCESS_EXIT_DURING_CONFIRMED_ITEM",
        )
        if commit_before_exit:
            plan = session.durable_tasks.get_plan(running.task_id)
            session.task_execution._item_executor().execute_compiled_item(  # noqa: SLF001
                plan.items[0],
                running.project_revision,
            )
        assert running.state == "executing"
    finally:
        first.close()

    second = ApplicationHarness(root)
    try:
        second.call("projects.open", {"project_id": project_id})
        restored = second.call(
            "agent.tasks.get",
            {"project_id": project_id, "task_id": "task:restart-executing"},
        )
        if commit_before_exit:
            assert restored["state"] == "completed_verified"
            assert [item["state"] for item in restored["items"]] == [
                "succeeded",
                "succeeded",
            ]
            assert [item["attempt_count"] for item in restored["items"]] == [1, 1]
            assert len(second.call(
                "engine.plots.list", {"project_id": project_id}
            )["plots"]) == 2
        else:
            assert restored["state"] == "partial"
            assert [item["state"] for item in restored["items"]] == [
                "repairable_failed",
                "staged",
            ]
            assert [item["attempt_count"] for item in restored["items"]] == [1, 0]
            assert tuple(second.call(
                "engine.plots.list", {"project_id": project_id}
            )["plots"]) == ()
    finally:
        second.close()


@pytest.mark.parametrize("crash_state", ("verifying", "delivering"))
def test_agent_v2_restart_finishes_verified_delivery_without_rerunning_items(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_state: str,
) -> None:
    root = tmp_path / f"restart-{crash_state}"
    first = ApplicationHarness(root)
    project_id = ""
    try:
        project_id, revision = _create_open(first)
        imported = _import_dataset(
            first,
            project_id,
            revision,
            key=f"restart-{crash_state}",
        )
        _execute_agent_create_batch(
            first,
            project_id,
            imported,
            token=f"restart-{crash_state}",
            profiles=("K01",),
            execute=False,
        )
        session = first.application._sessions[project_id]  # noqa: SLF001
        if crash_state == "verifying":
            original_advance = session.durable_tasks.advance

            def stop_before_delivery(*args: Any, **kwargs: Any) -> Any:
                if kwargs.get("next_state") == "delivering":
                    raise RuntimeError("synthetic exit before delivery")
                return original_advance(*args, **kwargs)

            monkeypatch.setattr(session.durable_tasks, "advance", stop_before_delivery)
        else:
            monkeypatch.setattr(
                session.durable_tasks,
                "complete_task",
                lambda *args, **kwargs: (_ for _ in ()).throw(
                    RuntimeError("synthetic exit before completion")
                ),
            )
        with pytest.raises(RuntimeError, match="synthetic exit"):
            session.task_execution.run(f"task:restart-{crash_state}")
        assert session.durable_tasks.get_task(
            f"task:restart-{crash_state}"
        ).state == crash_state
    finally:
        first.close()
        monkeypatch.undo()

    second = ApplicationHarness(root)
    try:
        second.call("projects.open", {"project_id": project_id})
        restored = second.call(
            "agent.tasks.get",
            {
                "project_id": project_id,
                "task_id": f"task:restart-{crash_state}",
            },
        )
        assert restored["state"] == "completed_verified"
        assert restored["items"][0]["state"] == "succeeded"
        assert restored["items"][0]["attempt_count"] == 1
        assert len(second.call(
            "engine.plots.list", {"project_id": project_id}
        )["plots"]) == 1
    finally:
        second.close()


def test_agent_v2_preserves_successful_items_when_one_batch_item_fails(
    harness: ApplicationHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="agent-v2-partial")
    execute = TaskPlanExecutor.execute_compiled_item
    injected = False

    def fail_second(
        self: TaskPlanExecutor,
        item: Any,
        revision: int,
    ) -> tuple[int, int]:
        nonlocal injected
        if item.profile_id == "K02" and not injected:
            injected = True
            raise RuntimeError("Injected deterministic renderer failure.")
        return execute(self, item, revision)

    monkeypatch.setattr(TaskPlanExecutor, "execute_compiled_item", fail_second)
    result = _execute_agent_create_batch(
        harness,
        project_id,
        imported,
        token="partial-batch",
        profiles=("K01", "K02"),
    )

    assert result["task"]["state"] == "partial"
    assert len(result["plots"]) == 1
    assert len(result["failures"]) == 1
    states = {item["item_id"]: item["state"] for item in result["task"]["items"]}
    assert states == {
        "item:partial-batch.1": "succeeded",
        "item:partial-batch.2": "repairable_failed",
    }
    assert [report["status"] for report in result["verifications"]] == [
        "passed",
        "failed",
    ]
    assert len(harness.call("engine.plots.list", {"project_id": project_id})["plots"]) == 1

    task_id = "task:partial-batch"
    directive = harness.call(
        "agent.tasks.pump.next", {"project_id": project_id, "task_id": task_id}
    )
    activation = cast(dict[str, Any], directive["activation"])
    assert activation["reason"] == "verification_failed"
    assert activation["verification_report_ids"] == [
        "verification:partial-batch.2.attempt-1"
    ]
    activation_id = cast(str, activation["activation_id"])
    harness.call(
        "agent.tasks.activation.running",
        {"project_id": project_id, "activation_id": activation_id},
    )
    prepared = harness.call(
        "agent.activations.prepare",
        {"project_id": project_id, "activation_id": activation_id},
    )
    context = cast(dict[str, Any], prepared["context"])
    assert context["verification_reports"][0]["claims"][0]["status"] == "failed"
    validated = harness.call(
        "agent.yields.validate",
        {
            "project_id": project_id,
            "activation_id": activation_id,
            "yield": {
                "outcome": "technical_repair_ready",
                "activation_id": activation_id,
                "task_id": task_id,
                "task_version": activation["task_version"],
                "proposal": {
                    "failed_report_ids": activation["verification_report_ids"],
                    "affected_item_ids": ["item:partial-batch.2"],
                    "repair_operations": ["retry_execution"],
                    "preserves_confirmed_semantics": True,
                },
            },
        },
    )
    accepted = harness.call(
        "agent.tasks.yield.accept", {"project_id": project_id, "yield": validated}
    )
    assert accepted["state"] == "executing"
    repaired = harness.call(
        "agent.tasks.execute", {"project_id": project_id, "task_id": task_id}
    )
    assert repaired["task"]["state"] == "completed_verified"
    assert len(repaired["plots"]) == 2
    attempts = {
        item["item_id"]: item["attempt_count"] for item in repaired["task"]["items"]
    }
    assert attempts == {"item:partial-batch.1": 1, "item:partial-batch.2": 2}


def test_agent_v2_formal_ui_fault_fixture_fails_once_then_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLOTAGENT_ENABLE_UI_TEST_FAULTS", "1")
    monkeypatch.setenv("PLOTAGENT_UI_TEST_FAIL_PROFILE_ONCE", "K02")
    harness = ApplicationHarness(tmp_path / "formal-ui-fault")
    try:
        project_id, revision = _create_open(harness)
        imported = _import_dataset(harness, project_id, revision, key="formal-ui-fault")
        first = _execute_agent_create_batch(
            harness,
            project_id,
            imported,
            token="formal-ui-fault",
            profiles=("K01", "K02"),
        )

        assert first["task"]["state"] == "partial"
        assert [item["state"] for item in first["task"]["items"]] == [
            "succeeded",
            "repairable_failed",
        ]
        assert first["failures"][0]["error"]["code"] == "UI_TEST_RENDERER_FAILURE"
        assert first["failures"][0]["error"]["side_effect_state"] == "known_none"
        assert len(harness.call("engine.plots.list", {"project_id": project_id})["plots"]) == 1

        _accept_scoped_retry(
            harness,
            project_id,
            "task:formal-ui-fault",
            "item:formal-ui-fault.2",
        )
        repaired = harness.call(
            "agent.tasks.execute",
            {"project_id": project_id, "task_id": "task:formal-ui-fault"},
        )
        assert repaired["task"]["state"] == "completed_verified"
        assert [item["attempt_count"] for item in repaired["task"]["items"]] == [1, 2]
        assert len(harness.call("engine.plots.list", {"project_id": project_id})["plots"]) == 2
    finally:
        harness.close()


def test_agent_v2_stops_after_a_scoped_retry_makes_no_progress(
    harness: ApplicationHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="agent-v2-no-progress")
    execute = TaskPlanExecutor.execute_compiled_item

    def always_fail_second(
        self: TaskPlanExecutor,
        item: Any,
        revision: int,
    ) -> tuple[int, int]:
        if item.profile_id == "K02":
            raise RuntimeError("Stable injected renderer failure.")
        return execute(self, item, revision)

    monkeypatch.setattr(TaskPlanExecutor, "execute_compiled_item", always_fail_second)
    first = _execute_agent_create_batch(
        harness,
        project_id,
        imported,
        token="no-progress-batch",
        profiles=("K01", "K02"),
    )
    assert first["task"]["state"] == "partial"
    _accept_scoped_retry(
        harness,
        project_id,
        "task:no-progress-batch",
        "item:no-progress-batch.2",
    )
    second = harness.call(
        "agent.tasks.execute",
        {"project_id": project_id, "task_id": "task:no-progress-batch"},
    )
    assert second["task"]["state"] == "partial"
    assert second["task"]["items"][1]["attempt_count"] == 2

    stopped = harness.call(
        "agent.tasks.pump.next",
        {"project_id": project_id, "task_id": "task:no-progress-batch"},
    )
    assert stopped == {
        "kind": "wait",
        "reason": "delivery_pending",
        "task_state": "partial",
    }
    checkpoint = harness.call(
        "agent.tasks.get",
        {"project_id": project_id, "task_id": "task:no-progress-batch"},
    )
    assert checkpoint["items"][1]["state"] == "failed"
    assert checkpoint["items"][0]["state"] == "succeeded"


def test_agent_v2_user_safe_retry_replays_failed_item_without_agent_activation(
    harness: ApplicationHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="safe-retry")
    execute = TaskPlanExecutor.execute_compiled_item

    def fail_second(
        self: TaskPlanExecutor,
        item: Any,
        current_revision: int,
    ) -> tuple[int, int]:
        if item.profile_id == "K02":
            raise RuntimeError("Stable renderer transport failure.")
        return execute(self, item, current_revision)

    monkeypatch.setattr(TaskPlanExecutor, "execute_compiled_item", fail_second)
    first = _execute_agent_create_batch(
        harness,
        project_id,
        imported,
        token="safe-retry",
        profiles=("K01", "K02"),
    )
    partial = first["task"]
    assert partial["state"] == "partial"
    assert partial["items"][1]["last_error"]["category"] == "deterministic_technical"
    events_before = harness.call(
        "agent.tasks.events",
        {"project_id": project_id, "task_id": "task:safe-retry"},
    )["events"]
    activation_count = sum(
        event["event_type"] == "agent_activation" for event in events_before
    )

    retrying = harness.call(
        "agent.tasks.retry_safe",
        {
            "project_id": project_id,
            "task_id": "task:safe-retry",
            "expected_task_version": partial["task_version"],
            "user_event_id": "user-event:safe-retry-request",
            "payload_hash": "f" * 64,
        },
    )
    assert retrying["state"] == "executing"
    retried = harness.call(
        "agent.tasks.execute",
        {"project_id": project_id, "task_id": "task:safe-retry"},
    )
    assert retried["task"]["state"] == "partial"
    assert [item["attempt_count"] for item in retried["task"]["items"]] == [1, 2]
    events_after = harness.call(
        "agent.tasks.events",
        {"project_id": project_id, "task_id": "task:safe-retry"},
    )["events"]
    assert sum(
        event["event_type"] == "agent_activation" for event in events_after
    ) == activation_count
    latest = harness.call(
        "agent.tasks.get",
        {"project_id": project_id, "task_id": "task:safe-retry"},
    )
    with pytest.raises(RpcServiceError) as repeated_retry:
        harness.call(
            "agent.tasks.retry_safe",
            {
                "project_id": project_id,
                "task_id": "task:safe-retry",
                "expected_task_version": latest["task_version"],
                "user_event_id": "user-event:safe-retry-repeated",
                "payload_hash": "e" * 64,
            },
        )
    assert repeated_retry.value.code == "VERSION_CONFLICT"
    assert "limited to one attempt" in repeated_retry.value.message


def test_agent_v2_accepts_verified_subset_without_reconfirmation_or_rerun(
    harness: ApplicationHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="accept-subset")
    execute = TaskPlanExecutor.execute_compiled_item

    def fail_second(
        self: TaskPlanExecutor,
        item: Any,
        current_revision: int,
    ) -> tuple[int, int]:
        if item.profile_id == "K02":
            raise ValueError("The second item cannot be rendered from this data.")
        return execute(self, item, current_revision)

    monkeypatch.setattr(TaskPlanExecutor, "execute_compiled_item", fail_second)
    first = _execute_agent_create_batch(
        harness,
        project_id,
        imported,
        token="accept-subset",
        profiles=("K01", "K02"),
    )
    assert first["task"]["state"] == "partial"
    successful = first["task"]["items"][0]
    project_revision_after_success = first["task"]["project_revision"]

    repair = harness.call(
        "agent.tasks.pump.next",
        {"project_id": project_id, "task_id": "task:accept-subset"},
    )
    repair_activation = cast(dict[str, Any], repair["activation"])
    repair_activation_id = cast(str, repair_activation["activation_id"])
    harness.call(
        "agent.tasks.activation.running",
        {"project_id": project_id, "activation_id": repair_activation_id},
    )
    harness.call(
        "agent.activations.prepare",
        {"project_id": project_id, "activation_id": repair_activation_id},
    )
    needs_input = harness.call(
        "agent.yields.validate",
        {
            "project_id": project_id,
            "activation_id": repair_activation_id,
            "yield": {
                "outcome": "needs_input",
                "activation_id": repair_activation_id,
                "task_id": "task:accept-subset",
                "task_version": repair_activation["task_version"],
                "questions": [
                    {
                        "question_key": "failed-item-resolution",
                        "prompt": "Should the failed item be revised or skipped?",
                        "answer_kind": "single_choice",
                        "choices": ["revise", "skip"],
                    }
                ],
            },
        },
    )
    waiting = harness.call(
        "agent.tasks.yield.accept",
        {"project_id": project_id, "yield": needs_input},
    )
    answered = harness.call(
        "agent.tasks.user_event",
        {
            "project_id": project_id,
            "task_id": "task:accept-subset",
            "expected_task_version": waiting["task_version"],
            "action": "answered",
            "user_event_id": "user-event:accept-subset-skip",
            "payload_hash": "c" * 64,
            "message": "Skip the failed item and keep the successful result.",
        },
    )
    assert answered["state"] == "investigating"
    continuation = harness.call(
        "agent.tasks.pump.next",
        {"project_id": project_id, "task_id": "task:accept-subset"},
    )
    activation = cast(dict[str, Any], continuation["activation"])
    activation_id = cast(str, activation["activation_id"])
    harness.call(
        "agent.tasks.activation.running",
        {"project_id": project_id, "activation_id": activation_id},
    )
    prepared = harness.call(
        "agent.activations.prepare",
        {"project_id": project_id, "activation_id": activation_id},
    )
    context = cast(dict[str, Any], prepared["context"])
    source_context = cast(list[dict[str, Any]], context["source_contexts"])[0]
    numeric_aliases = [
        cast(str, field["field_alias"])
        for field in cast(list[dict[str, object]], source_context["fields"])
        if field["logical_type"] == "numeric"
    ]
    revised_intent = TaskIntent(
        intent_id="intent:accept-subset",
        intent_version=2,
        task_id="task:accept-subset",
        task_version=cast(int, activation["task_version"]),
        created_by_activation_id=activation_id,
        summary="Keep the verified K01 result and skip the failed K02 item.",
        items=(
            TaskDraftItem(
                task_kind="create",
                item_id="item:accept-subset.1",
                plot_alias="plot_1",
                profile_id="K01",
                source_aliases=("data_1",),
                bindings=(
                    DraftFieldBinding(
                        role="x",
                        source_alias="data_1",
                        field_alias=numeric_aliases[0],
                    ),
                    DraftFieldBinding(
                        role="y",
                        source_alias="data_1",
                        field_alias=numeric_aliases[1],
                    ),
                ),
            ),
        ),
        profile_selections=(
            ProfileSelectionDecision(
                decision_id="decision:profile-accept-subset-1",
                item_id="item:accept-subset.1",
                profile_id="K01",
                basis="ui_selected",
            ),
        ),
        context_hash=cast(str, context["content_hash"]),
        content_hash="0" * 64,
    )
    revised_intent = revised_intent.model_copy(
        update={
            "content_hash": canonical_hash(
                revised_intent.model_dump(mode="json", exclude={"content_hash"})
            )
        }
    )
    validated = harness.call(
        "agent.yields.validate",
        {
            "project_id": project_id,
            "activation_id": activation_id,
            "yield": AgentIntentReady(
                activation_id=activation_id,
                task_id="task:accept-subset",
                task_version=cast(int, activation["task_version"]),
                intent=revised_intent,
            ).model_dump(mode="json"),
        },
    )
    completed = harness.call(
        "agent.tasks.yield.accept",
        {"project_id": project_id, "yield": validated},
    )
    assert completed["state"] == "completed_verified"
    assert completed["completion"]["outcome"] == "completed_with_skips"
    assert completed["completion"]["skipped_item_ids"] == ["item:accept-subset.2"]
    assert completed["project_revision"] == project_revision_after_success
    assert completed["items"][0]["attempt_count"] == successful["attempt_count"] == 1
    assert completed["items"][1]["attempt_count"] == 1
    assert harness.call(
        "agent.tasks.pump.next",
        {"project_id": project_id, "task_id": "task:accept-subset"},
    ) == {
        "kind": "wait",
        "reason": "terminal",
        "task_state": "completed_verified",
    }


def test_agent_v2_explicit_skip_closes_partial_without_model_or_rerun(
    harness: ApplicationHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="explicit-skip")
    execute = TaskPlanExecutor.execute_compiled_item

    def fail_second(
        self: TaskPlanExecutor,
        item: Any,
        current_revision: int,
    ) -> tuple[int, int]:
        if item.profile_id == "K02":
            raise ValueError("The second item cannot be rendered from this data.")
        return execute(self, item, current_revision)

    monkeypatch.setattr(TaskPlanExecutor, "execute_compiled_item", fail_second)
    first = _execute_agent_create_batch(
        harness,
        project_id,
        imported,
        token="explicit-skip",
        profiles=("K01", "K02"),
    )
    partial = first["task"]
    assert partial["state"] == "partial"
    revision_after_success = partial["project_revision"]
    attempts_before = {
        item["item_id"]: item["attempt_count"] for item in partial["items"]
    }

    completed = harness.call(
        "agent.tasks.user_event",
        {
            "project_id": project_id,
            "task_id": "task:explicit-skip",
            "expected_task_version": partial["task_version"],
            "action": "partial_accepted",
            "user_event_id": "user-event:explicit-skip-accept",
            "payload_hash": "d" * 64,
        },
    )
    assert completed["state"] == "completed_verified"
    assert completed["completion"]["outcome"] == "completed_with_skips"
    assert completed["completion"]["skipped_item_ids"] == [
        "item:explicit-skip.2"
    ]
    assert completed["project_revision"] == revision_after_success
    assert {
        item["item_id"]: item["attempt_count"] for item in completed["items"]
    } == attempts_before
    assert harness.call(
        "agent.tasks.pump.next",
        {"project_id": project_id, "task_id": "task:explicit-skip"},
    ) == {
        "kind": "wait",
        "reason": "terminal",
        "task_state": "completed_verified",
    }


def test_agent_v2_partial_and_completed_with_skips_survive_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "restart-partial-app"
    first = ApplicationHarness(root)
    original = TaskPlanExecutor.execute_compiled_item

    def fail_second(
        self: TaskPlanExecutor,
        item: Any,
        current_revision: int,
    ) -> tuple[int, int]:
        if item.profile_id == "K02":
            raise ValueError("The second item cannot be rendered from this data.")
        return original(self, item, current_revision)

    monkeypatch.setattr(TaskPlanExecutor, "execute_compiled_item", fail_second)
    try:
        project_id, revision = _create_open(first)
        imported = _import_dataset(first, project_id, revision, key="restart-partial")
        partial = _execute_agent_create_batch(
            first,
            project_id,
            imported,
            token="restart-partial",
            profiles=("K01", "K02"),
        )["task"]
        assert partial["state"] == "partial"
        frozen_items = [
            (
                item["item_id"],
                item["state"],
                item["attempt_count"],
                item["output_plot_id"],
                item["output_plot_version"],
            )
            for item in partial["items"]
        ]
    finally:
        first.close()

    second = ApplicationHarness(root)
    try:
        second.call("projects.open", {"project_id": project_id})
        restored_partial = second.call(
            "agent.tasks.get",
            {"project_id": project_id, "task_id": "task:restart-partial"},
        )
        assert restored_partial["state"] == "partial"
        assert [
            (
                item["item_id"],
                item["state"],
                item["attempt_count"],
                item["output_plot_id"],
                item["output_plot_version"],
            )
            for item in restored_partial["items"]
        ] == frozen_items
        completed = second.call(
            "agent.tasks.user_event",
            {
                "project_id": project_id,
                "task_id": "task:restart-partial",
                "expected_task_version": restored_partial["task_version"],
                "action": "partial_accepted",
                "user_event_id": "user-event:restart-partial-accept",
                "payload_hash": "a" * 64,
            },
        )
        assert completed["completion"]["outcome"] == "completed_with_skips"
    finally:
        second.close()

    third = ApplicationHarness(root)
    try:
        third.call("projects.open", {"project_id": project_id})
        restored_completed = third.call(
            "agent.tasks.get",
            {"project_id": project_id, "task_id": "task:restart-partial"},
        )
        assert restored_completed["state"] == "completed_verified"
        assert restored_completed["completion"]["outcome"] == "completed_with_skips"
        assert restored_completed["completion"]["skipped_item_ids"] == [
            "item:restart-partial.2"
        ]
        assert third.call(
            "agent.tasks.pump.next",
            {"project_id": project_id, "task_id": "task:restart-partial"},
        ) == {
            "kind": "wait",
            "reason": "terminal",
            "task_state": "completed_verified",
        }
    finally:
        third.close()


def test_agent_v2_retries_one_transient_failure_without_model_activation(
    harness: ApplicationHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="transient-retry")
    execute = TaskPlanExecutor.execute_compiled_item
    failed_once = False

    def timeout_once(
        self: TaskPlanExecutor,
        item: Any,
        current_revision: int,
    ) -> tuple[int, int]:
        nonlocal failed_once
        if item.profile_id == "K02" and not failed_once:
            failed_once = True
            error = RuntimeError("Temporary renderer timeout.")
            error.code = "RENDERER_TIMEOUT"  # type: ignore[attr-defined]
            raise error
        return execute(self, item, current_revision)

    monkeypatch.setattr(TaskPlanExecutor, "execute_compiled_item", timeout_once)
    first = _execute_agent_create_batch(
        harness,
        project_id,
        imported,
        token="transient-retry",
        profiles=("K01", "K02"),
    )
    assert first["task"]["state"] == "partial"
    directive = harness.call(
        "agent.tasks.pump.next",
        {"project_id": project_id, "task_id": "task:transient-retry"},
    )
    assert directive == {
        "kind": "wait",
        "reason": "execution_pending",
        "task_state": "executing",
    }
    second = harness.call(
        "agent.tasks.execute",
        {"project_id": project_id, "task_id": "task:transient-retry"},
    )
    assert second["task"]["state"] == "completed_verified"
    assert {
        item["item_id"]: item["attempt_count"] for item in second["task"]["items"]
    } == {
        "item:transient-retry.1": 1,
        "item:transient-retry.2": 2,
    }


def test_agent_v2_scoped_repair_can_request_missing_semantic_input(
    harness: ApplicationHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="repair-needs-input")
    execute = TaskPlanExecutor.execute_compiled_item

    def fail_second(
        self: TaskPlanExecutor,
        item: Any,
        revision: int,
    ) -> tuple[int, int]:
        if item.profile_id == "K02":
            raise ValueError("The second item needs a semantic correction.")
        return execute(self, item, revision)

    monkeypatch.setattr(TaskPlanExecutor, "execute_compiled_item", fail_second)
    first = _execute_agent_create_batch(
        harness,
        project_id,
        imported,
        token="repair-needs-input",
        profiles=("K01", "K02"),
    )
    assert first["task"]["state"] == "partial"
    assert first["task"]["items"][1]["last_error"]["category"] == "semantic_conflict"

    with pytest.raises(RpcServiceError):
        harness.call(
            "agent.tasks.retry_safe",
            {
                "project_id": project_id,
                "task_id": "task:repair-needs-input",
                "expected_task_version": first["task"]["task_version"],
                "user_event_id": "user-event:semantic-retry-must-not-run",
                "payload_hash": "e" * 64,
            },
        )
    assert harness.call(
        "agent.tasks.get",
        {"project_id": project_id, "task_id": "task:repair-needs-input"},
    )["state"] == "partial"

    directive = harness.call(
        "agent.tasks.pump.next",
        {"project_id": project_id, "task_id": "task:repair-needs-input"},
    )
    activation = cast(dict[str, Any], directive["activation"])
    activation_id = cast(str, activation["activation_id"])
    harness.call(
        "agent.tasks.activation.running",
        {"project_id": project_id, "activation_id": activation_id},
    )
    harness.call(
        "agent.activations.prepare",
        {"project_id": project_id, "activation_id": activation_id},
    )
    with pytest.raises(RpcServiceError) as unsafe_retry:
        harness.call(
            "agent.yields.validate",
            {
                "project_id": project_id,
                "activation_id": activation_id,
                "yield": {
                    "outcome": "technical_repair_ready",
                    "activation_id": activation_id,
                    "task_id": "task:repair-needs-input",
                    "task_version": activation["task_version"],
                    "proposal": {
                        "failed_report_ids": activation["verification_report_ids"],
                        "affected_item_ids": ["item:repair-needs-input.2"],
                        "repair_operations": ["retry_execution"],
                        "preserves_confirmed_semantics": True,
                    },
                },
            },
        )
    assert unsafe_retry.value.code == "REPAIR_SAFETY_INVALID"
    assert harness.call(
        "agent.tasks.get",
        {"project_id": project_id, "task_id": "task:repair-needs-input"},
    )["state"] == "repairing"

    validated = harness.call(
        "agent.yields.validate",
        {
            "project_id": project_id,
            "activation_id": activation_id,
            "yield": {
                "outcome": "needs_input",
                "activation_id": activation_id,
                "task_id": "task:repair-needs-input",
                "task_version": activation["task_version"],
                "questions": [
                    {
                        "question_key": "repair_second_item",
                        "prompt": "How should the second item be corrected?",
                        "answer_kind": "text",
                        "choices": [],
                    }
                ],
            },
        },
    )
    accepted = harness.call(
        "agent.tasks.yield.accept",
        {"project_id": project_id, "yield": validated},
    )
    assert accepted["state"] == "awaiting_input"
    assert {
        item["item_id"]: item["state"] for item in accepted["items"]
    } == {
        "item:repair-needs-input.1": "succeeded",
        "item:repair-needs-input.2": "repairable_failed",
    }

    answered = harness.call(
        "agent.tasks.user_event",
        {
            "project_id": project_id,
            "task_id": "task:repair-needs-input",
            "expected_task_version": accepted["task_version"],
            "action": "answered",
            "user_event_id": "user-event:repair-needs-input-answer",
            "payload_hash": "b" * 64,
            "message": "Keep the successful item and revise only the failed item.",
        },
    )
    assert answered["state"] == "investigating"
    continuation = harness.call(
        "agent.tasks.pump.next",
        {"project_id": project_id, "task_id": "task:repair-needs-input"},
    )
    revised_activation = cast(dict[str, Any], continuation["activation"])
    revised_activation_id = cast(str, revised_activation["activation_id"])
    harness.call(
        "agent.tasks.activation.running",
        {"project_id": project_id, "activation_id": revised_activation_id},
    )
    prepared = harness.call(
        "agent.activations.prepare",
        {"project_id": project_id, "activation_id": revised_activation_id},
    )
    context = cast(dict[str, Any], prepared["context"])
    source_context = cast(list[dict[str, Any]], context["source_contexts"])[0]
    numeric_aliases = [
        cast(str, field["field_alias"])
        for field in cast(list[dict[str, object]], source_context["fields"])
        if field["logical_type"] == "numeric"
    ]
    revised_intent = TaskIntent(
        intent_id="intent:repair-needs-input",
        intent_version=2,
        task_id="task:repair-needs-input",
        task_version=cast(int, revised_activation["task_version"]),
        created_by_activation_id=revised_activation_id,
        summary="Keep the successful item and revise only the failed item.",
        items=tuple(
            TaskDraftItem(
                task_kind="create",
                item_id=f"item:repair-needs-input.{position}",
                plot_alias=f"plot_{position}",
                profile_id=profile,
                source_aliases=("data_1",),
                bindings=(
                    DraftFieldBinding(
                        role="x",
                        source_alias="data_1",
                        field_alias=numeric_aliases[0],
                    ),
                    DraftFieldBinding(
                        role="y",
                        source_alias="data_1",
                        field_alias=numeric_aliases[1],
                    ),
                ),
            )
            for position, profile in enumerate(("K01", "K02"), start=1)
        ),
        profile_selections=tuple(
            ProfileSelectionDecision(
                decision_id=f"decision:profile-repair-needs-input-{position}",
                item_id=f"item:repair-needs-input.{position}",
                profile_id=profile,
                basis="ui_selected",
            )
            for position, profile in enumerate(("K01", "K02"), start=1)
        ),
        context_hash=cast(str, context["content_hash"]),
        content_hash="0" * 64,
    )
    revised_intent = revised_intent.model_copy(
        update={
            "content_hash": canonical_hash(
                revised_intent.model_dump(mode="json", exclude={"content_hash"})
            )
        }
    )
    revised_yield = AgentIntentReady(
        activation_id=revised_activation_id,
        task_id="task:repair-needs-input",
        task_version=cast(int, revised_activation["task_version"]),
        intent=revised_intent,
    )
    validated_revision = harness.call(
        "agent.yields.validate",
        {
            "project_id": project_id,
            "activation_id": revised_activation_id,
            "yield": revised_yield.model_dump(mode="json"),
        },
    )
    harness.call(
        "agent.tasks.yield.accept",
        {"project_id": project_id, "yield": validated_revision},
    )
    reconfirm = harness.call(
        "agent.tasks.pump.next",
        {"project_id": project_id, "task_id": "task:repair-needs-input"},
    )
    assert reconfirm["reason"] == "awaiting_reconfirmation"
    revised_view = harness.call(
        "agent.tasks.plan.get",
        {"project_id": project_id, "task_id": "task:repair-needs-input"},
    )
    assert revised_view["confirmation_state"] == "pending"
    harness.call(
        "agent.tasks.plan.confirm",
        {
            "project_id": project_id,
            "task_id": "task:repair-needs-input",
            "expected_task_version": revised_view["task"]["task_version"],
            "user_event_id": "user-event:repair-needs-input-reconfirm",
            "plan_hash": revised_view["plan_hash"],
        },
    )
    retried = harness.call(
        "agent.tasks.execute",
        {"project_id": project_id, "task_id": "task:repair-needs-input"},
    )
    assert retried["task"]["state"] == "partial"
    assert {
        item["item_id"]: item["attempt_count"] for item in retried["task"]["items"]
    } == {
        "item:repair-needs-input.1": 1,
        "item:repair-needs-input.2": 2,
    }


def test_multi_source_plan_structure_failure_requires_agent_revision() -> None:
    assert DurableTaskExecutionService._classify_failure(
        "WORKFLOW_SOURCES_NOT_COMBINED"
    ) == ("semantic_conflict", False, False)
    assert DurableTaskExecutionService._classify_failure(
        "WORKFLOW_NON_ISOMORPHIC"
    ) == ("semantic_conflict", False, False)
    assert DurableTaskExecutionService._classify_failure(
        "ValueError"
    ) == ("semantic_conflict", False, False)
    assert DurableTaskExecutionService._classify_failure(
        "WORKFLOW_TYPE_CONVERSION_FAILED"
    ) == ("semantic_conflict", False, False)
    assert DurableTaskExecutionService._classify_failure(
        "WORKFLOW_ALIGNMENT_X_MISMATCH"
    ) == ("semantic_conflict", False, False)


def _dataset_and_fields(imported: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    dataset = cast(dict[str, Any], cast(list[object], imported["datasets"])[0])
    numeric = [
        cast(str, item["field_id"])
        for item in cast(list[dict[str, object]], dataset["fields"])
        if item["logical_type"] == "numeric"
    ]
    assert len(numeric) >= 2
    return dataset, numeric


def _create_line(
    harness: ApplicationHarness,
    project_id: str,
    imported: dict[str, Any],
    *,
    plot_id: str,
    action_id: str,
) -> dict[str, Any]:
    dataset, numeric = _dataset_and_fields(imported)
    return harness.call(
        "engine.actions.execute",
        {
            "project_id": project_id,
            "expected_project_version": imported["project_version"],
            "action": {
                "operation": "create_plot",
                "action_id": action_id,
                "plot_id": plot_id,
                "profile_id": "K01",
                "data": {
                    "kind": "source",
                    "dataset_id": dataset["source_dataset_id"],
                    "version": dataset["source_version"],
                    "content_hash": dataset["content_hash"],
                },
                "bindings": [
                    {"role": "x", "field_id": numeric[0]},
                    {"role": "y", "field_id": numeric[1]},
                ],
            },
        },
    )


def test_projects_are_managed_without_plot_compiler_state(
    harness: ApplicationHarness,
) -> None:
    project_id, _revision = _create_open(harness)
    renamed = harness.call(
        "projects.rename",
        {"project_id": project_id, "display_name": "重命名项目"},
    )
    assert renamed["display_name"] == "重命名项目"
    assert renamed["is_open"] is True
    deleted = harness.call("projects.delete", {"project_id": project_id})
    assert deleted["status"] == "deleted"
    assert harness.call("projects.list", {}) == {"projects": []}


def test_dataset_description_returns_a_bounded_read_only_sample(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="dataset-preview")
    dataset = cast(dict[str, Any], cast(list[object], imported["datasets"])[0])

    described = harness.call(
        "datasets.describe",
        {
            "project_id": project_id,
            "source_dataset_id": dataset["source_dataset_id"],
            "source_version": dataset["source_version"],
        },
    )

    detailed = cast(dict[str, Any], described["dataset"])
    rows = cast(list[list[object]], detailed["sample_rows"])
    assert len(rows) == min(5, detailed["row_count"])
    assert all(len(row) == detailed["field_count"] for row in rows)
    assert detailed["row_count"] == dataset["row_count"]
    assert "sample_rows" not in dataset


def test_text_import_exposes_instrument_metadata_and_distinct_table_blocks(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    instrument = harness.call(
        "datasets.import",
        {
            "project_id": project_id,
            "resource_id": "resource:instrument-text",
            "source_path": str(FIXTURES / "txt_metadata.txt"),
            "idempotency_key": "instrument-text",
            "expected_version": revision,
            "options": {},
        },
    )
    instrument_dataset = cast(dict[str, Any], cast(list[object], instrument["datasets"])[0])
    assert instrument_dataset["instrument_metadata"] == {
        "Instrument": "Spectrometer",
        "Operator": "Test",
    }

    blocked = harness.call(
        "datasets.import",
        {
            "project_id": project_id,
            "resource_id": "resource:multi-block-text",
            "source_path": str(FIXTURES / "txt_multi_block.txt"),
            "idempotency_key": "multi-block-text",
            "expected_version": instrument["project_version"],
            "options": {},
        },
    )
    block_datasets = cast(list[dict[str, Any]], blocked["datasets"])
    assert len(block_datasets) == 2
    assert len({item["display_name"] for item in block_datasets}) == 2
    assert {item["source_block"] for item in block_datasets} == {"block_1", "block_2"}


def test_engine_rpc_uses_imported_data_and_restores_latest_document(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="engine-data")
    catalog = harness.call("engine.catalog.get", {"project_id": project_id})
    assert catalog["tool_name"] == "plot_engine_action"
    assert len(cast(list[object], catalog["profiles"])) == 34

    created = _create_line(
        harness,
        project_id,
        imported,
        plot_id="plot:desktop",
        action_id="action:create",
    )
    assert created["plot_version"] == 1
    assert created["document"]["schema_version"] == "2.0"
    assert Path(cast(str, created["preview"]["path"])).is_file()

    listed = harness.call("projects.list", {})
    listed_project = cast(list[dict[str, Any]], listed["projects"])[0]
    assert listed_project["project_version"] == created["project_version"]

    edited = harness.call(
        "engine.actions.execute",
        {
            "project_id": project_id,
            "expected_project_version": created["project_version"],
            "action": {
                "operation": "set_title",
                "action_id": "action:title",
                "target": "plot:desktop",
                "expected_plot_version": 1,
                "text": "Agent Native preview",
            },
        },
    )
    assert edited["plot_version"] == 2

    harness.call("projects.close", {"project_id": project_id})
    harness.call("projects.open", {"project_id": project_id})
    restored = harness.call("engine.plots.list", {"project_id": project_id})
    assert len(cast(list[object], restored["plots"])) == 1
    latest = cast(list[dict[str, Any]], restored["plots"])[0]
    assert (latest["plot_id"], latest["plot_version"]) == ("plot:desktop", 2)
    assert Path(cast(str, latest["preview"]["path"])).is_file()


def test_engine_rpc_restores_an_exact_plot_snapshot_and_can_redo_it(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="engine-history")
    created = _create_line(
        harness,
        project_id,
        imported,
        plot_id="plot:history",
        action_id="action:history.create",
    )
    edited = harness.call(
        "engine.actions.execute",
        {
            "project_id": project_id,
            "expected_project_version": created["project_version"],
            "action": {
                "operation": "set_title",
                "action_id": "action:history.title",
                "target": "plot:history",
                "expected_plot_version": 1,
                "text": "Edited title",
            },
        },
    )
    assert edited["plot_version"] == 2
    created_document = cast(dict[str, Any], created["document"])
    edited_document = cast(dict[str, Any], edited["document"])
    assert cast(list[dict[str, Any]], edited["actions"])[-1]["text"] == "Edited title"
    assert edited_document["applied_action_ids"] != created_document["applied_action_ids"]

    undone = harness.call(
        "engine.plots.restore",
        {
            "project_id": project_id,
            "expected_project_version": edited["project_version"],
            "plot_id": "plot:history",
            "expected_plot_version": 2,
            "source_plot_version": 1,
            "action_id": "action:history.undo",
        },
    )
    assert undone["plot_version"] == 3
    undone_document = cast(dict[str, Any], undone["document"])
    assert undone_document["bindings"] == created_document["bindings"]
    assert undone["actions"] == created["actions"]
    assert Path(cast(str, undone["preview"]["path"])).is_file()

    redone = harness.call(
        "engine.plots.restore",
        {
            "project_id": project_id,
            "expected_project_version": undone["project_version"],
            "plot_id": "plot:history",
            "expected_plot_version": 3,
            "source_plot_version": 2,
            "action_id": "action:history.redo",
        },
    )
    assert redone["plot_version"] == 4
    assert redone["actions"] == edited["actions"]


def test_historical_removed_plot_is_listed_as_a_tombstone(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="removed-plot")
    created = _create_line(
        harness,
        project_id,
        imported,
        plot_id="plot:removed",
        action_id="action:create-removed",
    )
    session = harness.application._sessions[project_id]  # noqa: SLF001
    connection = session.store._assert_writer()  # noqa: SLF001
    row = connection.execute(
        "SELECT document_json FROM engine_plot_document_versions WHERE plot_id = ?",
        ("plot:removed",),
    ).fetchone()
    assert row is not None
    document = json.loads(str(row[0]))
    document["profile_id"] = "K25"
    connection.execute(
        "UPDATE engine_plot_document_versions SET document_json = ? WHERE plot_id = ?",
        (json.dumps(document, ensure_ascii=False, separators=(",", ":")), "plot:removed"),
    )
    connection.commit()

    listed = harness.call("engine.plots.list", {"project_id": project_id})
    tombstone = cast(list[dict[str, Any]], listed["plots"])[0]
    assert tombstone["profile_id"] == "K25"
    assert tombstone["profile_removed"] is True
    assert "profile" not in tombstone
    assert "preview" not in tombstone
    assert listed["project_version"] == created["project_version"]


def test_public_export_action_writes_png_without_mutating_plot(
    harness: ApplicationHarness,
    tmp_path: Path,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="engine-export")
    created = _create_line(
        harness,
        project_id,
        imported,
        plot_id="plot:export",
        action_id="action:create-export",
    )
    destination = tmp_path / "agent-native.png"
    exported = harness.call(
        "engine.exports.execute",
        {
            "project_id": project_id,
            "action": {
                "operation": "export_plot",
                "action_id": "action:export",
                "target": "plot:export",
                "expected_plot_version": 1,
                "format": "png",
                "output_name": destination.name,
            },
            "destination_resource_id": "resource:export",
            "destination_path": str(destination),
        },
    )
    assert destination.is_file()
    assert exported["plot_version"] == created["plot_version"]
    assert (
        exported["artifact"]["content_hash"] == hashlib.sha256(destination.read_bytes()).hexdigest()
    )
    original = destination.read_bytes()
    with pytest.raises(RpcServiceError):
        harness.call(
            "engine.exports.execute",
            {
                "project_id": project_id,
                "action": {
                    "operation": "export_plot",
                    "action_id": "action:export-again",
                    "target": "plot:export",
                    "expected_plot_version": 1,
                    "format": "png",
                    "output_name": destination.name,
                },
                "destination_resource_id": "resource:export-again",
                "destination_path": str(destination),
            },
        )
    assert destination.read_bytes() == original
    assert (
        harness.call("engine.plots.get", {"project_id": project_id, "plot_id": "plot:export"})[
            "project_version"
        ]
        == created["project_version"]
    )


def test_opju_export_failure_is_reported_as_an_origin_error(
    harness: ApplicationHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="opju-error")
    _create_line(
        harness,
        project_id,
        imported,
        plot_id="plot:opju-error",
        action_id="action:opju-error.create",
    )

    def fail_export(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("synthetic Origin worker failure")

    monkeypatch.setattr(DesktopEngineSession, "export", fail_export)
    destination = tmp_path / "failed.opju"
    with pytest.raises(RpcServiceError) as captured:
        harness.call(
            "engine.exports.execute",
            {
                "project_id": project_id,
                "action": {
                    "operation": "export_plot",
                    "action_id": "action:opju-error.export",
                    "target": "plot:opju-error",
                    "expected_plot_version": 1,
                    "format": "opju",
                    "output_name": destination.name,
                },
                "destination_resource_id": "resource:opju-error",
                "destination_path": str(destination),
            },
        )

    assert captured.value.code == "ORIGIN_EXPORT_FAILED"
    assert "重新检测 Origin" in captured.value.message
    assert not destination.exists()
