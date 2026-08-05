from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from plotagent.desktop_core.application import DesktopApplication
from plotagent.desktop_core.protocol import JsonValue
from plotagent.desktop_core.services import RpcContext, ServiceRegistry
from plotagent.desktop_core.tasks import BoundedWorkerExecutor, TaskRegistry

FIXTURES = Path(__file__).parents[1] / "fixtures" / "import" / "files"


class ApplicationHarness:
    def __init__(self, root: Path) -> None:
        self.application = DesktopApplication(root)
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
