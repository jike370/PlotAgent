from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from plotagent.agent.context import ConversationState
from plotagent.agent.project_context import ProjectContextService
from plotagent.contracts.agent_context import ContextObjectRef
from plotagent.contracts.project_context import ContextFieldBinding
from plotagent.desktop_core.application import DesktopApplication
from plotagent.desktop_core.protocol import JsonValue
from plotagent.desktop_core.services import RpcContext, ServiceRegistry
from plotagent.desktop_core.tasks import BoundedWorkerExecutor, TaskRegistry
from plotagent.security.credentials import InMemoryCredentialStore

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


def _create_open(harness: ApplicationHarness) -> tuple[str, int]:
    created = harness.call(
        "projects.create",
        {"display_name": "Agent Native 测试", "idempotency_key": "project-key"},
    )
    project_id = cast(str, created["project_id"])
    opened = harness.call("projects.open", {"project_id": project_id})
    return project_id, cast(int, opened["project_version"])


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
                "components": [],
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


def test_engine_rpc_uses_imported_data_and_restores_latest_document(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="engine-data")
    catalog = harness.call("engine.catalog.get", {"project_id": project_id})
    assert catalog["tool_name"] == "plot_engine_action"
    assert len(cast(list[object], catalog["profiles"])) == 35

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


def test_agent_context_contains_each_explicitly_selected_dataset(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="agent-selected-data")
    datasets = cast(list[dict[str, Any]], imported["datasets"])
    assert len(datasets) == 2

    result = harness.call(
        "agent.engine.decide",
        {
            "project_id": project_id,
            "source_dataset_id": datasets[0]["source_dataset_id"],
            "source_version": datasets[0]["source_version"],
            "selected_source_datasets": [
                {
                    "source_dataset_id": item["source_dataset_id"],
                    "source_version": item["source_version"],
                }
                for item in datasets
            ],
            "selected_profile_id": "K01",
            "user_instruction": "为选中的两张数据表分别绘制折线图",
            "client_model_run_id": "model-run:selected-data",
            "expected_version": imported["project_version"],
        },
    )
    assert result["accepted"] is False
    assert cast(dict[str, object], result["error"])["code"] == "PROVIDER_NOT_CONFIGURED"

    session = harness.application._sessions[project_id]  # noqa: SLF001
    snapshot = session.agent_runtime.latest_context_snapshot(
        harness.application._default_conversation_id(project_id)  # noqa: SLF001
    )
    assert snapshot is not None
    source_ids = {
        item.object_id
        for item in snapshot.known_objects
        if item.object_type == "source_dataset"
    }
    assert source_ids == {item["source_dataset_id"] for item in datasets}
    assert {item.source_dataset_id for item in snapshot.field_bindings} == source_ids
    assert all(item.field_alias.startswith("data_") for item in snapshot.field_bindings)


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
    assert exported["artifact"]["content_hash"] == hashlib.sha256(
        destination.read_bytes()
    ).hexdigest()
    assert harness.call("engine.plots.get", {"project_id": project_id, "plot_id": "plot:export"})[
        "project_version"
    ] == created["project_version"]


def test_bound_plan_requires_confirmation_and_persists_completion(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="engine-plan")
    dataset, numeric = _dataset_and_fields(imported)
    source = ContextObjectRef(
        object_alias="active_data",
        object_id=cast(str, dataset["source_dataset_id"]),
        object_version=cast(int, dataset["source_version"]),
        object_type="source_dataset",
        content_hash=cast(str, dataset["content_hash"]),
    )
    state = ConversationState(current_target=source)
    snapshot = ProjectContextService().build_snapshot(
        project_id=project_id,
        project_revision=cast(int, imported["project_version"]),
        conversation_id="conversation:engine-plan",
        conversation_state=state.project(),
        known_objects=(source,),
        field_bindings=(
            ContextFieldBinding(
                field_alias="x",
                field_id=numeric[0],
                source_dataset_id=cast(str, dataset["source_dataset_id"]),
                source_version=cast(int, dataset["source_version"]),
            ),
            ContextFieldBinding(
                field_alias="y",
                field_id=numeric[1],
                source_dataset_id=cast(str, dataset["source_dataset_id"]),
                source_version=cast(int, dataset["source_version"]),
            ),
        ),
    )
    session = harness.application._sessions[project_id]  # noqa: SLF001
    session.agent_runtime.save_conversation_state(
        "conversation:engine-plan", state.project(), expected_state_version=None
    )
    session.agent_runtime.save_context_snapshot(snapshot)

    plan = harness.call(
        "agent.engine.plans.create",
        {
            "project_id": project_id,
            "context_snapshot_id": snapshot.snapshot_id,
            "proposal": {
                "plan_id": "plan:desktop",
                "target_alias": "active_data",
                "actions": (
                    {
                        "operation": "create_plot",
                        "action_id": "action:create",
                        "plot_alias": "result",
                        "profile_id": "K01",
                        "source_alias": "active_data",
                        "bindings": (
                            {"role": "x", "field_alias": "x"},
                            {"role": "y", "field_alias": "y"},
                        ),
                    },
                    {
                        "operation": "set_title",
                        "action_id": "action:title",
                        "plot_alias": "result",
                        "text": "Bound locally",
                    },
                ),
            },
        },
    )
    assert plan["state"] == "needs_confirmation"
    harness.call(
        "agent.engine.plans.confirm",
        {"project_id": project_id, "plan_id": "plan:desktop"},
    )
    completed = harness.call(
        "agent.engine.plans.run",
        {"project_id": project_id, "plan_id": "plan:desktop"},
    )
    assert completed["state"] == "succeeded"
    assert completed["next_action_index"] == 2
    restored = harness.call(
        "agent.engine.plans.get",
        {"project_id": project_id, "plan_id": "plan:desktop"},
    )
    assert restored["state"] == "succeeded"
