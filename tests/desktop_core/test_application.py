from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from plotagent.desktop_core.application import DesktopApplication
from plotagent.desktop_core.engine_session import DesktopEngineSession
from plotagent.desktop_core.protocol import JsonValue
from plotagent.desktop_core.services import RpcContext, RpcServiceError, ServiceRegistry
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
    assert (
        harness.call("engine.plots.get", {"project_id": project_id, "plot_id": "plot:export"})[
            "project_version"
        ]
        == created["project_version"]
    )


def test_workflow_deterministic_create_requires_confirmation_and_executes(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="workflow-create")
    dataset = cast(list[dict[str, Any]], imported["datasets"])[0]
    prepared = harness.call(
        "workflow.prepare",
        {
            "project_id": project_id,
            "expected_project_version": imported["project_version"],
            "instruction": "用 K01 折线图绘制这张表",
            "selected_sources": [
                {
                    "dataset_id": dataset["source_dataset_id"],
                    "source_version": dataset["source_version"],
                }
            ],
            "selected_profile_ids": ["K01"],
        },
    )
    assert prepared["outcome"] == "draft_ready"
    task_plan = cast(dict[str, Any], prepared["task_plan"])
    assert task_plan["state"] == "awaiting_confirmation"
    plan_id = cast(str, cast(dict[str, Any], task_plan["plan"])["plan_id"])

    confirmed = harness.call(
        "workflow.plans.confirm", {"project_id": project_id, "plan_id": plan_id}
    )
    assert confirmed["state"] == "ready"
    completed = harness.call(
        "workflow.plans.run", {"project_id": project_id, "plan_id": plan_id}
    )
    assert completed["state"] == "succeeded"
    progress = cast(list[dict[str, Any]], completed["item_progress"])
    assert progress[0]["output_plot_version"] == 1


def test_workflow_agent_handoff_exposes_profile_contract_and_core_owns_route(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="workflow-agent-route")
    dataset = cast(list[dict[str, Any]], imported["datasets"])[0]
    prepared = harness.call(
        "workflow.prepare",
        {
            "project_id": project_id,
            "expected_project_version": imported["project_version"],
            "instruction": "用 K01 折线图绘制，标题为测试，字体改成 Comic Sans",
            "selected_sources": [
                {
                    "dataset_id": dataset["source_dataset_id"],
                    "source_version": dataset["source_version"],
                }
            ],
            "selected_profile_ids": ["K01"],
        },
    )
    assert prepared["outcome"] == "agent_required"
    assert prepared["route"] == "agent_single_turn"
    prompt = cast(str, prepared["system_prompt"])
    assert '"profile_id":"K01"' in prompt
    assert '"required_roles":["x","y"]' in prompt
    assert '"authoritative_route":"agent_single_turn"' in prompt

    context = cast(dict[str, Any], prepared["workflow_context"])
    assert cast(list[dict[str, Any]], context["sources"])[0]["display_name"] == (
        "excel_two_sheets.xlsx > Run A"
    )
    fields = cast(list[dict[str, Any]], context["fields"])
    numeric = [field for field in fields if field["logical_type"] == "numeric"][:2]
    source_alias = cast(str, cast(list[dict[str, Any]], context["sources"])[0]["source_alias"])
    run_id = cast(str, prepared["workflow_run_id"])
    submitted = harness.call(
        "workflow.submit_draft",
        {
            "project_id": project_id,
            "workflow_run_id": run_id,
            "task_draft": {
                "draft_id": "draft:agent-route",
                "workflow_run_id": run_id,
                # A model-supplied route is never authoritative.
                "route": "deterministic",
                "summary": "创建测试折线图",
                "items": [
                    {
                        "task_kind": "create",
                        "item_id": "item:agent-route.1",
                        "plot_alias": "plot_1",
                        "profile_id": "K01",
                        "source_aliases": [source_alias],
                        "bindings": [
                            {
                                "role": "x",
                                "source_alias": source_alias,
                                "field_alias": numeric[0]["field_alias"],
                            },
                            {
                                "role": "y",
                                "source_alias": source_alias,
                                "field_alias": numeric[1]["field_alias"],
                            },
                        ],
                        "visual_actions": [
                            {"operation": "set_title", "text": "测试"}
                        ],
                    }
                ],
                "confidence": 1,
            },
        },
    )
    assert cast(dict[str, Any], submitted["draft"])["route"] == "agent_single_turn"


def test_workflow_recipe_requires_a_real_export_and_replays_without_agent(
    harness: ApplicationHarness,
    tmp_path: Path,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="workflow-recipe")
    dataset = cast(list[dict[str, Any]], imported["datasets"])[0]
    request = {
        "project_id": project_id,
        "expected_project_version": imported["project_version"],
        "instruction": "用 K01 折线图绘制这张表",
        "selected_sources": [
            {
                "dataset_id": dataset["source_dataset_id"],
                "source_version": dataset["source_version"],
            }
        ],
        "selected_profile_ids": ["K01"],
    }
    prepared = harness.call("workflow.prepare", request)
    task_plan = cast(dict[str, Any], prepared["task_plan"])
    plan_id = cast(str, cast(dict[str, Any], task_plan["plan"])["plan_id"])
    harness.call("workflow.plans.confirm", {"project_id": project_id, "plan_id": plan_id})
    completed = harness.call(
        "workflow.plans.run", {"project_id": project_id, "plan_id": plan_id}
    )
    progress = cast(list[dict[str, Any]], completed["item_progress"])[0]
    plot_id = cast(str, progress["output_plot_id"])
    plot_version = cast(int, progress["output_plot_version"])

    with pytest.raises(RpcServiceError) as captured:
        harness.call(
            "workflow.recipes.save",
            {
                "project_id": project_id,
                "plan_id": plan_id,
                "display_name": "折线图标准流程",
                "export_hash": "f" * 64,
            },
        )
    assert captured.value.code == "WORKFLOW_RECIPE_EXPORT_UNVERIFIED"

    destination = tmp_path / "workflow-recipe.png"
    exported = harness.call(
        "engine.exports.execute",
        {
            "project_id": project_id,
            "action": {
                "operation": "export_plot",
                "action_id": "action:workflow-recipe.export",
                "target": plot_id,
                "expected_plot_version": plot_version,
                "format": "png",
                "output_name": destination.name,
            },
            "destination_resource_id": "resource:workflow-recipe",
            "destination_path": str(destination),
        },
    )
    export_hash = cast(str, cast(dict[str, Any], exported["artifact"])["content_hash"])
    recipe = harness.call(
        "workflow.recipes.save",
        {
            "project_id": project_id,
            "plan_id": plan_id,
            "display_name": "折线图标准流程",
            "export_hash": export_hash,
        },
    )
    assert recipe["created_from_export_hash"] == export_hash

    replayed = harness.call(
        "workflow.prepare",
        {
            **request,
            "expected_project_version": completed["current_project_revision"],
        },
    )
    assert replayed["outcome"] == "draft_ready"
    assert replayed["route"] == "recipe_replay"
    assert replayed["recipe_id"] == recipe["recipe_id"]


def test_workflow_program_first_edit_changes_the_selected_plot_without_a_source(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import_dataset(harness, project_id, revision, key="workflow-edit")
    created = _create_line(
        harness,
        project_id,
        imported,
        plot_id="plot:workflow-edit",
        action_id="action:workflow-edit.create",
    )
    prepared = harness.call(
        "workflow.prepare",
        {
            "project_id": project_id,
            "expected_project_version": created["project_version"],
            "instruction": "把当前图标题改为响应曲线",
            "selected_sources": [],
            "selected_plot_ids": ["plot:workflow-edit"],
        },
    )
    assert prepared["outcome"] == "draft_ready"
    assert prepared["route"] == "deterministic"
    task_plan = cast(dict[str, Any], prepared["task_plan"])
    plan_id = cast(str, cast(dict[str, Any], task_plan["plan"])["plan_id"])
    harness.call(
        "workflow.plans.confirm", {"project_id": project_id, "plan_id": plan_id}
    )
    completed = harness.call(
        "workflow.plans.run", {"project_id": project_id, "plan_id": plan_id}
    )
    assert completed["state"] == "succeeded"
    plot = harness.call(
        "engine.plots.get", {"project_id": project_id, "plot_id": "plot:workflow-edit"}
    )
    assert cast(dict[str, Any], plot["document"])["plot_version"] == 2


def test_workflow_log10_rejects_non_positive_data_before_creating_a_plot(
    harness: ApplicationHarness,
) -> None:
    project_id, revision = _create_open(harness)
    imported = harness.call(
        "datasets.import",
        {
            "project_id": project_id,
            "resource_id": "resource:workflow-log10",
            "source_path": str(FIXTURES / "tsv_zero_false.tsv"),
            "idempotency_key": "workflow-log10",
            "expected_version": revision,
            "options": {},
        },
    )
    dataset = cast(list[dict[str, Any]], imported["datasets"])[0]
    prepared = harness.call(
        "workflow.prepare",
        {
            "project_id": project_id,
            "expected_project_version": imported["project_version"],
            "instruction": "创建 K01 折线图，index 映射 x，value 映射 y；y 轴改为 log10。",
            "selected_sources": [
                {
                    "dataset_id": dataset["source_dataset_id"],
                    "source_version": dataset["source_version"],
                }
            ],
            "selected_profile_ids": ["K01"],
        },
    )
    task_plan = cast(dict[str, Any], prepared["task_plan"])
    plan_id = cast(str, cast(dict[str, Any], task_plan["plan"])["plan_id"])
    harness.call("workflow.plans.confirm", {"project_id": project_id, "plan_id": plan_id})
    completed = harness.call(
        "workflow.plans.run", {"project_id": project_id, "plan_id": plan_id}
    )

    assert completed["state"] == "failed"
    progress = cast(list[dict[str, Any]], completed["item_progress"])
    assert progress[0]["error_code"] == "LOG_SCALE_NON_POSITIVE"
    assert progress[0]["error_message"] == (
        "Log10 轴包含 0 或负值；任务未执行，项目没有发生变化。"
    )
    assert progress[0]["error_retryable"] is False
    assert completed["current_project_revision"] == imported["project_version"]
    assert not harness.call("engine.plots.list", {"project_id": project_id})["plots"]


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
