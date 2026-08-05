from __future__ import annotations

import csv
import hashlib
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest

from plotagent.agent.providers import (
    OutputCapability,
    ProviderCapabilities,
    ProviderDecisionRequest,
    ProviderIdentity,
    ProviderProtocol,
    ProviderUsage,
    ProviderWireResponse,
)
from plotagent.contracts.registry import CHART_REGISTRY
from plotagent.desktop_core.application import DesktopApplication
from plotagent.desktop_core.protocol import JsonValue
from plotagent.desktop_core.services import RpcContext, ServiceRegistry
from plotagent.desktop_core.tasks import BoundedWorkerExecutor, TaskRegistry
from plotagent.origin.models import OriginEnvironment, OriginExportSuccess
from plotagent.security.credentials import InMemoryCredentialStore
from plotagent.security.network import NetworkMode

FIXTURES = Path(__file__).parents[1] / "fixtures" / "import" / "files"


@dataclass
class FakeProvider:
    responses: list[str]
    requests: list[ProviderDecisionRequest] = field(default_factory=list)

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            provider_type="custom",
            provider_config_id="custom-test",
            endpoint_origin="https://models.example.test:443",
            model_id="synthetic-model",
            model_profile="fixed-test",
        )

    async def resolve_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(OutputCapability.P1, ProviderProtocol.RESPONSES)

    async def decide(self, request: ProviderDecisionRequest) -> ProviderWireResponse:
        self.requests.append(request)
        return ProviderWireResponse(
            provider_request_id=f"request-{len(self.requests)}",
            output_text=self.responses.pop(0),
            usage=ProviderUsage(10, 5, "provider"),
        )

    async def repair(
        self,
        request: ProviderDecisionRequest,
        *,
        invalid_candidate: str,
        schema_error_categories: tuple[str, ...],
    ) -> ProviderWireResponse:
        del request, invalid_candidate, schema_error_categories
        raise AssertionError("P1 must not repair")

    async def cancel(self, client_model_run_id: str) -> None:
        del client_model_run_id


class ApplicationHarness:
    def __init__(self, root: Path, provider: FakeProvider | None = None) -> None:
        self.credentials = InMemoryCredentialStore()
        self.application = DesktopApplication(
            root,
            provider_factory=(None if provider is None else lambda _mode, _params: provider),
            credential_store=self.credentials,
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
        {"display_name": "纵向测试", "idempotency_key": "project-key"},
    )
    project_id = cast(str, created["project_id"])
    opened = harness.call("projects.open", {"project_id": project_id})
    return project_id, cast(int, opened["project_version"])


def _import(
    harness: ApplicationHarness,
    project_id: str,
    revision: int,
    file_name: str,
    key: str,
) -> dict[str, Any]:
    return harness.call(
        "datasets.import",
        {
            "project_id": project_id,
            "resource_id": "resource:" + key,
            "source_path": str(FIXTURES / file_name),
            "idempotency_key": key,
            "expected_version": revision,
            "options": {},
        },
    )


def _install_fake_origin_export(
    monkeypatch: pytest.MonkeyPatch,
    captured: list[Any],
    *,
    on_export: Any | None = None,
) -> None:
    def fake_export(plan: Any, destination: Path, **_kwargs: Any) -> OriginExportSuccess:
        captured.append(plan)
        if on_export is not None:
            on_export()
        payload = b"PlotAgent native Origin test project"
        destination.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        environment = OriginEnvironment(
            display_name="Origin2024 SR1",
            display_version="10.10.178",
            install_dir=r"D:\origin",
            executable_path=r"D:\origin\Origin64.exe",
            origin_bitness=64,
            python_bitness=64,
            originpro_version="1.1.15",
            runtime_version=10.100178,
            template_sha256="0" * 64,
            license_available=True,
        )
        return OriginExportSuccess(
            status="succeeded",
            target_path=str(destination),
            file_sha256=digest,
            file_size=len(payload),
            render_plan_sha256=plan.render_plan_hash,
            validation_report_sha256="1" * 64,
            build_validation={},
            reopen_validation={},
            environment=environment,
            elapsed_seconds=0.01,
        )

    monkeypatch.setattr("plotagent.desktop_core.application.export_origin", fake_export)


def test_project_import_describe_k01_patch_render_and_exports(
    harness: ApplicationHarness, tmp_path: Path
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import(harness, project_id, revision, "excel_two_sheets.xlsx", "excel")
    assert imported["kind"] == "committed"
    assert len(imported["datasets"]) == 2
    revision = imported["project_version"]

    first = imported["datasets"][0]
    described = harness.call(
        "datasets.describe",
        {
            "project_id": project_id,
            "source_dataset_id": first["source_dataset_id"],
            "source_version": first["source_version"],
        },
    )
    fields = described["dataset"]["fields"]
    numeric = [item["field_id"] for item in fields if item["logical_type"] == "numeric"]
    assert len(numeric) >= 2

    created = harness.call(
        "plots.create",
        {
            "project_id": project_id,
            "plot_id": "plot:vertical",
            "chart_type_id": "K01",
            "source_dataset_id": first["source_dataset_id"],
            "source_version": first["source_version"],
            "field_mapping": {"x": numeric[0], "y": numeric[1]},
            "idempotency_key": "plot-create",
            "expected_version": revision,
        },
    )
    assert created["chart_type_id"] == "K01"
    assert created["plot_version"] == 1

    preview = harness.call(
        "plots.render",
        {"project_id": project_id, "plot_id": "plot:vertical", "plot_version": 1},
    )
    preview_path = Path(preview["artifact"]["path"])
    assert preview_path.is_file()
    assert preview_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    patched = harness.call(
        "plots.patch",
        {
            "project_id": project_id,
            "plot_id": "plot:vertical",
            "expected_version": 1,
            "idempotency_key": "plot-patch",
            "patch": {
                "operation": "set_axis_label",
                "target_id": "axis:y",
                "expected_plot_version": 1,
                "label": {"nodes": [{"kind": "plain", "text": "Response"}]},
            },
        },
    )
    assert patched["plot_version"] == 2

    for output_format in ("png", "svg"):
        destination = tmp_path / f"vertical.{output_format}"
        exported = harness.call(
            "exports.png_svg",
            {
                "project_id": project_id,
                "plot_id": "plot:vertical",
                "plot_version": 2,
                "format": output_format,
                "destination_resource_id": f"resource:export-{output_format}",
                "destination_path": str(destination),
                "idempotency_key": f"export-{output_format}",
                "expected_version": 2,
            },
        )
        assert exported["format"] == output_format
        assert destination.is_file()


def test_text_import_is_committed_and_listed(harness: ApplicationHarness) -> None:
    project_id, revision = _create_open(harness)
    imported = _import(harness, project_id, revision, "txt_metadata.txt", "text")
    assert imported["kind"] == "committed"
    listed = harness.call("datasets.list", {"project_id": project_id})
    assert len(listed["datasets"]) == len(imported["datasets"])
    assert listed["project_version"] == imported["project_version"]


def test_authorized_plotproj_is_verified_imported_and_opened(
    harness: ApplicationHarness, tmp_path: Path
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import(harness, project_id, revision, "txt_metadata.txt", "package-source")
    assert imported["kind"] == "committed"
    package_path = tmp_path / "transfer.plotproj"
    source_session = harness.application._sessions[project_id]
    harness.application._packages.pack(source_session.store, package_path)

    recipient = ApplicationHarness(tmp_path / "recipient")
    try:
        opened = recipient.call(
            "projects.open",
            {
                "resource_id": "resource:authorized-package",
                "source_path": str(package_path),
            },
        )
        assert opened["project_id"] == project_id
        assert opened["status"] == "open"
        assert opened["package"]["reused"] is False
        listed = recipient.call("datasets.list", {"project_id": project_id})
        assert len(listed["datasets"]) == 1

        replayed = recipient.call(
            "projects.open",
            {
                "resource_id": "resource:authorized-package-again",
                "source_path": str(package_path),
            },
        )
        assert replayed["project_id"] == project_id
        assert replayed["package"]["reused"] is True
    finally:
        recipient.close()


def test_custom_provider_configuration_is_persisted_without_exposing_secret(
    harness: ApplicationHarness,
) -> None:
    initial = harness.call("provider.status", {})
    assert initial == {
        "mode": "local_only",
        "configured": False,
        "retention_acknowledged": False,
    }

    configured = harness.call(
        "provider.configure",
        {
            "mode": "custom_provider",
            "provider_config_id": "custom.default",
            "base_url": "https://models.example.test/v1",
            "model_id": "science-model",
            "api_key": "test-secret-key",
            "retention_acknowledged": True,
        },
    )
    assert configured["configured"] is True
    assert configured["mode"] == "custom_provider"
    assert "api_key" not in configured
    assert harness.credentials.get_custom_api_key("custom.default") == "test-secret-key"

    saved_config = harness.application._saved_provider_config()
    assert saved_config is not None
    runtime_provider = harness.application._create_production_provider(
        NetworkMode.CUSTOM_PROVIDER,
        saved_config,
    )
    assert runtime_provider.identity.model_id == "science-model"
    assert (
        harness.application._create_production_provider(
            NetworkMode.CUSTOM_PROVIDER,
            saved_config,
        )
        is runtime_provider
    )

    cleared = harness.call("provider.clear", {})
    assert cleared["mode"] == "local_only"
    assert harness.credentials.get_custom_api_key("custom.default") is None


def test_agent_can_create_any_registered_plot_and_edit_an_active_plot(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(
        responses=[
            json.dumps(
                {
                    "schema_version": "1.0",
                    "decision_type": "action_plan",
                    "plan_id": "plan:create-k02",
                    "target_alias": "active_target",
                    "actions": [
                        {
                            "action_type": "create_plot",
                            "action_id": "action:create",
                            "target_alias": "active_target",
                            "chart_type_id": "K02",
                            "field_selections": [
                                {"role": "x", "context_field_alias": "x_field"},
                                {"role": "y", "context_field_alias": "y_field"},
                            ],
                        }
                    ],
                }
            ),
            json.dumps(
                {
                    "schema_version": "1.0",
                    "decision_type": "action_plan",
                    "plan_id": "plan:edit-k02",
                    "target_alias": "active_target",
                    "actions": [
                        {
                            "action_type": "patch_plot",
                            "action_id": "action:label",
                            "target_alias": "active_target",
                            "patches": [
                                {
                                    "operation": "set_axis_label",
                                    "target_alias": "y_axis",
                                    "label": "Normalized signal",
                                }
                            ],
                        }
                    ],
                }
            ),
            json.dumps(
                {
                    "schema_version": "1.0",
                    "decision_type": "action_plan",
                    "plan_id": "plan:edit-batch",
                    "target_alias": "active_target",
                    "actions": [
                        {
                            "action_type": "patch_plot",
                            "action_id": "action:batch-label",
                            "target_alias": "active_target",
                            "patches": [
                                {
                                    "operation": "set_axis_label",
                                    "target_alias": "y_axis",
                                    "label": "Shared batch signal",
                                }
                            ],
                        }
                    ],
                }
            ),
        ]
    )
    app = ApplicationHarness(tmp_path / "agent-app", provider)
    try:
        project_id, revision = _create_open(app)
        imported = _import(app, project_id, revision, "excel_two_sheets.xlsx", "agent")
        dataset = imported["datasets"][0]
        revision = imported["project_version"]
        common = {
            "project_id": project_id,
            "source_dataset_id": dataset["source_dataset_id"],
            "source_version": dataset["source_version"],
            "network_mode": "custom_provider",
            "provider": {},
            "retention_acknowledged": True,
        }
        created = app.call(
            "agent.decide",
            {
                **common,
                "user_instruction": "用第二列对第一列画散点图",
                "client_model_run_id": "model-run:create",
                "expected_version": revision,
            },
        )
        assert created["accepted"] is True
        execution = created["execution"]
        assert execution["chart_type_id"] == "K02"
        assert len(provider.requests[0].envelope.chart_capabilities.allowed_chart_type_ids) == 30

        edited = app.call(
            "agent.decide",
            {
                **common,
                "user_instruction": "把 y 轴标题改成 Normalized signal",
                "client_model_run_id": "model-run:edit",
                "expected_version": execution["project_version"],
                "target": {"kind": "plot", "id": execution["plot_id"]},
                "scope": "current",
            },
        )
        assert edited["accepted"] is True
        assert edited["execution"]["plot_version"] == 2
        stored = app.call(
            "plots.get",
            {"project_id": project_id, "plot_id": execution["plot_id"]},
        )
        assert stored["spec"]["axes"][1]["label"]["nodes"][0]["text"] == ("Normalized signal")

        described = app.call(
            "datasets.describe",
            {
                "project_id": project_id,
                "source_dataset_id": dataset["source_dataset_id"],
                "source_version": dataset["source_version"],
            },
        )
        numeric = [
            field["field_id"]
            for field in described["dataset"]["fields"]
            if field["logical_type"] == "numeric"
        ]
        batch_created = app.call(
            "batch.create",
            {
                "project_id": project_id,
                "task_id": "task:agent-batch",
                "batch_id": "batch:agent",
                "source_datasets": [
                    {
                        "source_dataset_id": item["source_dataset_id"],
                        "source_version": item["source_version"],
                    }
                    for item in imported["datasets"]
                ],
                "chart_type_id": "K01",
                "field_mapping": {"x": numeric[0], "y": numeric[1]},
                "idempotency_key": "agent-batch-create",
                "expected_version": edited["execution"]["project_version"],
            },
        )
        completed = app.call(
            "batch.run",
            {
                "project_id": project_id,
                "task_id": batch_created["task_id"],
                "idempotency_key": "agent-batch-run",
                "expected_version": batch_created["project_version"],
            },
        )
        batch_edited = app.call(
            "agent.decide",
            {
                **common,
                "user_instruction": "把整个批次的 y 轴标题统一为 Shared batch signal",
                "client_model_run_id": "model-run:batch-edit",
                "expected_version": completed["project_version"],
                "target": {"kind": "batch", "id": "batch:agent"},
                "scope": "batch",
            },
        )
        assert batch_edited["accepted"] is True
        assert len(batch_edited["executions"]) == 2
        assert {item["plot_version"] for item in batch_edited["executions"]} == {2}
        assert batch_edited["scope_execution"]["target_version"] == 2
        updated_batch = app.call(
            "batch.get",
            {"project_id": project_id, "batch_id": "batch:agent"},
        )
        assert updated_batch["batch"]["batch_version"] == 2
        assert {
            item["plot_version_ref"]["plot_version"]
            for item in updated_batch["batch"]["item_states"]
        } == {2}
        assert provider.requests[2].envelope.target_snapshot.object_type == "batch"
    finally:
        app.close()


def test_desktop_application_creates_and_renders_exact_31_chart_surface(
    harness: ApplicationHarness,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin_plans: list[Any] = []
    _install_fake_origin_export(monkeypatch, origin_plans)
    categorical_roles = {
        "group",
        "category",
        "component",
        "event",
        "row",
        "column",
        "row_label",
        "column_label",
        "facet",
        "panel",
        "label",
        "parameter",
        "peak_label",
        "actual",
        "predicted",
    }
    roles = sorted(
        {
            role
            for chart in CHART_REGISTRY
            if chart.chart_type_id != "K25"
            for role in chart.required_roles
        }
    )
    source_path = tmp_path / "all-charts.csv"
    with source_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=roles)
        writer.writeheader()
        for index in range(12):
            row: dict[str, object] = {}
            for role in roles:
                if role in categorical_roles:
                    if role == "category":
                        row[role] = f"C{index + 1}"
                    elif role in {"row", "row_label"}:
                        row[role] = f"R{index // 3 + 1}"
                    elif role in {"column", "column_label"}:
                        row[role] = f"C{index % 3 + 1}"
                    elif role in {"component", "predicted"}:
                        row[role] = "A" if index % 2 == 0 else "B"
                    else:
                        row[role] = "A" if (index // 2) % 2 == 0 else "B"
                elif role == "lower":
                    row[role] = 0.5 + index
                elif role == "upper":
                    row[role] = 1.5 + index
                elif role in {"dose", "frequency"}:
                    row[role] = 10 ** ((index % 4) - 1)
                elif role == "survival":
                    row[role] = max(0.05, 1.0 - index * 0.07)
                elif role == "x":
                    row[role] = float(index // 3)
                elif role == "y":
                    row[role] = float(index % 3)
                else:
                    row[role] = 1.0 + index
            writer.writerow(row)

    project_id, revision = _create_open(harness)
    imported = harness.call(
        "datasets.import",
        {
            "project_id": project_id,
            "resource_id": "resource:all-charts",
            "source_path": str(source_path),
            "idempotency_key": "all-charts-import",
            "expected_version": revision,
            "options": {},
        },
    )
    dataset = imported["datasets"][0]
    revision = imported["project_version"]
    described = harness.call(
        "datasets.describe",
        {
            "project_id": project_id,
            "source_dataset_id": dataset["source_dataset_id"],
            "source_version": dataset["source_version"],
        },
    )
    field_by_name = {field["name"]: field["field_id"] for field in described["dataset"]["fields"]}
    plot_refs: list[dict[str, object]] = []
    for chart in CHART_REGISTRY:
        if chart.chart_type_id == "K25":
            continue
        plot_id = f"plot:matrix.{chart.chart_type_id.lower()}"
        created = harness.call(
            "plots.create",
            {
                "project_id": project_id,
                "plot_id": plot_id,
                "chart_type_id": chart.chart_type_id,
                "source_dataset_id": dataset["source_dataset_id"],
                "source_version": dataset["source_version"],
                "field_mapping": {
                    role: field_by_name[role]
                    for role in (*chart.required_roles, *chart.optional_roles)
                    if role in field_by_name
                },
                "idempotency_key": f"create-{chart.chart_type_id}",
                "expected_version": revision,
            },
        )
        revision = created["project_version"]
        preview = harness.call(
            "plots.render",
            {"project_id": project_id, "plot_id": plot_id, "plot_version": 1},
        )
        assert Path(preview["artifact"]["path"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        plot_refs.append({"plot_id": plot_id, "plot_version": 1})

    figure = harness.call(
        "figures.create",
        {
            "project_id": project_id,
            "figure_id": "figure:matrix.k25",
            "plot_refs": plot_refs[:2],
            "layout": "1x2",
            "idempotency_key": "create-K25",
            "expected_version": revision,
        },
    )
    assert len(figure["figure"]["panels"]) == 2
    preview = harness.call(
        "figures.render",
        {"project_id": project_id, "figure_id": "figure:matrix.k25"},
    )
    assert Path(preview["artifact"]["path"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert len(plot_refs) + 1 == 31

    plot_destination = tmp_path / "non-k01.opju"
    exported_plot = harness.call(
        "exports.origin",
        {
            "project_id": project_id,
            "plot_id": plot_refs[2]["plot_id"],
            "plot_version": plot_refs[2]["plot_version"],
            "target_kind": "plot",
            "destination_resource_id": "resource:origin-plot",
            "destination_path": str(plot_destination),
            "idempotency_key": "origin-plot",
            "expected_version": plot_refs[2]["plot_version"],
        },
    )
    assert exported_plot["target_kind"] == "plot"
    assert origin_plans[-1].manifest.chart_type_ids == ("K03",)

    figure_destination = tmp_path / "figure.opju"
    exported_figure = harness.call(
        "exports.origin",
        {
            "project_id": project_id,
            "plot_id": "figure:matrix.k25",
            "plot_version": figure["figure"]["figure_version"],
            "target_kind": "figure",
            "destination_resource_id": "resource:origin-figure",
            "destination_path": str(figure_destination),
            "idempotency_key": "origin-figure",
            "expected_version": figure["figure"]["figure_version"],
        },
    )
    assert exported_figure["target_scope"] == "figure"
    assert origin_plans[-1].manifest.chart_type_ids == ("K25",)


def test_isomorphic_batch_runs_from_one_confirmed_mapping(
    harness: ApplicationHarness,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin_plans: list[Any] = []
    _install_fake_origin_export(monkeypatch, origin_plans)
    project_id, revision = _create_open(harness)
    imported = _import(harness, project_id, revision, "excel_two_sheets.xlsx", "batch")
    datasets = imported["datasets"]
    assert len(datasets) == 2
    first = harness.call(
        "datasets.describe",
        {
            "project_id": project_id,
            "source_dataset_id": datasets[0]["source_dataset_id"],
            "source_version": datasets[0]["source_version"],
        },
    )
    numeric = [
        field["field_id"]
        for field in first["dataset"]["fields"]
        if field["logical_type"] == "numeric"
    ]
    submitted = harness.call(
        "batch.create",
        {
            "project_id": project_id,
            "task_id": "task:batch-test",
            "batch_id": "batch:test",
            "source_datasets": [
                {
                    "source_dataset_id": item["source_dataset_id"],
                    "source_version": item["source_version"],
                }
                for item in datasets
            ],
            "chart_type_id": "K01",
            "field_mapping": {"x": numeric[0], "y": numeric[1]},
            "idempotency_key": "batch-create",
            "expected_version": imported["project_version"],
        },
    )
    assert submitted["state"] == "queued"
    completed = harness.call(
        "batch.run",
        {
            "project_id": project_id,
            "task_id": "task:batch-test",
            "idempotency_key": "batch-run",
            "expected_version": imported["project_version"],
        },
    )
    assert completed["state"] == "succeeded"
    assert [item["state"] for item in completed["items"]] == ["succeeded", "succeeded"]
    stored = harness.call("batch.get", {"project_id": project_id, "batch_id": "batch:test"})
    assert len(stored["batch"]["item_states"]) == 2
    destination = tmp_path / "batch.opju"
    exported = harness.call(
        "exports.origin",
        {
            "project_id": project_id,
            "plot_id": "batch:test",
            "plot_version": stored["batch"]["batch_version"],
            "target_kind": "batch",
            "destination_resource_id": "resource:origin-batch",
            "destination_path": str(destination),
            "idempotency_key": "origin-batch",
            "expected_version": stored["batch"]["batch_version"],
        },
    )
    assert exported["target_scope"] == "batch"
    assert exported["graph_count"] == 2
    assert origin_plans[-1].manifest.chart_type_ids == ("K01", "K01")


def test_origin_publication_race_finishes_the_export_record(
    harness: ApplicationHarness,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, revision = _create_open(harness)
    imported = _import(harness, project_id, revision, "csv_basic.csv", "origin-race")
    dataset = imported["datasets"][0]
    described = harness.call(
        "datasets.describe",
        {
            "project_id": project_id,
            "source_dataset_id": dataset["source_dataset_id"],
            "source_version": dataset["source_version"],
        },
    )
    numeric = [
        field["field_id"]
        for field in described["dataset"]["fields"]
        if field["logical_type"] == "numeric"
    ]
    created = harness.call(
        "plots.create",
        {
            "project_id": project_id,
            "plot_id": "plot:origin-race",
            "chart_type_id": "K01",
            "source_dataset_id": dataset["source_dataset_id"],
            "source_version": dataset["source_version"],
            "field_mapping": {"x": numeric[0], "y": numeric[1]},
            "idempotency_key": "plot-origin-race",
            "expected_version": imported["project_version"],
        },
    )

    def cancel_after_publication() -> None:
        running = [
            item
            for item in harness.tasks.snapshot()["tasks"]
            if item["state"] == "running"
        ]
        assert len(running) == 1
        harness.tasks.cancel(cast(str, running[0]["task_id"]))

    captured: list[Any] = []
    _install_fake_origin_export(
        monkeypatch,
        captured,
        on_export=cancel_after_publication,
    )
    exported = harness.call(
        "exports.origin",
        {
            "project_id": project_id,
            "plot_id": "plot:origin-race",
            "plot_version": created["plot_version"],
            "destination_resource_id": "resource:origin-race",
            "destination_path": str(tmp_path / "origin-race.opju"),
            "idempotency_key": "origin-race-export",
            "expected_version": created["plot_version"],
        },
    )
    task = next(
        item
        for item in harness.tasks.snapshot()["tasks"]
        if item["task_id"] == exported["task_id"]
    )
    assert task["state"] == "succeeded"
    assert exported["export_id"] is not None
    assert captured
