from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import pytest

from plotagent.sdk import PlotAgentSDK, PlotAgentSDKError

FIXTURES = Path(__file__).parents[1] / "fixtures" / "import" / "files"


def _line_action(imported: dict[str, Any]) -> dict[str, Any]:
    dataset = cast(dict[str, Any], cast(list[object], imported["datasets"])[0])
    numeric = [
        cast(str, item["field_id"])
        for item in cast(list[dict[str, object]], dataset["fields"])
        if item["logical_type"] == "numeric"
    ]
    return {
        "operation": "create_plot",
        "action_id": "action:sdk.create",
        "plot_id": "plot:sdk",
        "profile_id": "K01",
        "data": {
            "kind": "source",
            "dataset_id": dataset["source_dataset_id"],
            "version": dataset["source_version"],
            "content_hash": dataset["content_hash"],
        },
        "bindings": (
            {"role": "x", "field_id": numeric[0]},
            {"role": "y", "field_id": numeric[1]},
        ),
    }


def test_sdk_lifecycle_validation_persistence_and_export(tmp_path: Path) -> None:
    root = tmp_path / "external-engine"
    destination = tmp_path / "sdk.png"
    with PlotAgentSDK(root) as sdk:
        health = sdk.health()
        assert health["desktop_workspace_isolated"] is True
        project = sdk.create_project(idempotency_key="sdk", display_name="SDK")
        project_id = cast(str, project["project_id"])
        opened = sdk.open_project(project_id)
        imported = cast(
            dict[str, Any],
            sdk.import_dataset(
                project_id,
                FIXTURES / "excel_two_sheets.xlsx",
                expected_project_version=cast(int, opened["project_version"]),
                idempotency_key="sdk-import",
                resource_id="resource:sdk-input",
            ),
        )
        dataset = cast(dict[str, Any], cast(list[object], imported["datasets"])[0])
        inspected = sdk.inspect_data(
            project_id,
            cast(str, dataset["source_dataset_id"]),
            cast(int, dataset["source_version"]),
        )
        assert cast(dict[str, Any], inspected["dataset"])["sample_rows"]
        assert len(cast(list[object], sdk.chart_capabilities(project_id)["profiles"])) == 34

        action = _line_action(imported)
        validated = sdk.validate_action(
            project_id,
            action,
            expected_project_version=cast(int, imported["project_version"]),
        )
        assert validated["valid"] is True
        assert not sdk.list_plots(project_id)["plots"]
        created = sdk.execute_action(
            project_id,
            action,
            expected_project_version=cast(int, imported["project_version"]),
        )
        assert (created["profile_id"], created["plot_version"]) == ("K01", 1)
        assert created["display_ref"] == "@图1"

        exported = sdk.export_plot(
            project_id,
            {
                "operation": "export_plot",
                "action_id": "action:sdk.export",
                "target": "plot:sdk",
                "expected_plot_version": 1,
                "format": "png",
                "output_name": destination.name,
            },
            destination,
            resource_id="resource:sdk-export",
        )
        assert destination.is_file()
        assert exported["display_ref"] == "@图1"
        artifact = cast(dict[str, object], exported["artifact"])
        assert artifact["content_hash"] == hashlib.sha256(destination.read_bytes()).hexdigest()
        sdk.close_project(project_id)

    with PlotAgentSDK(root) as reopened:
        reopened.open_project(project_id)
        plots = cast(list[dict[str, Any]], reopened.list_plots(project_id)["plots"])
        assert [(item["plot_id"], item["plot_version"]) for item in plots] == [
            ("plot:sdk", 1)
        ]
        assert plots[0]["display_ref"] == "@图1"


def test_sdk_does_not_touch_a_desktop_workspace(tmp_path: Path) -> None:
    desktop_root = tmp_path / "desktop"
    desktop_root.mkdir()
    sentinel = desktop_root / "sentinel.txt"
    sentinel.write_text("desktop", encoding="utf-8")
    with PlotAgentSDK(tmp_path / "external") as sdk:
        sdk.create_project(idempotency_key="isolated")
    assert list(desktop_root.iterdir()) == [sentinel]
    assert sentinel.read_text(encoding="utf-8") == "desktop"


def test_sdk_rejects_stale_validation_without_mutation(tmp_path: Path) -> None:
    with PlotAgentSDK(tmp_path / "external") as sdk:
        project = sdk.create_project(idempotency_key="stale")
        project_id = cast(str, project["project_id"])
        opened = sdk.open_project(project_id)
        imported = cast(
            dict[str, Any],
            sdk.import_dataset(
                project_id,
                FIXTURES / "excel_two_sheets.xlsx",
                expected_project_version=cast(int, opened["project_version"]),
                idempotency_key="stale-import",
                resource_id="resource:stale",
            ),
        )
        with pytest.raises(PlotAgentSDKError) as failure:
            sdk.validate_action(
                project_id,
                _line_action(imported),
                expected_project_version=0,
            )
        assert failure.value.code == "ENGINE_VERSION_CONFLICT"
        assert not sdk.list_plots(project_id)["plots"]


def test_sdk_prepares_and_commits_deterministic_data_for_the_renderer(
    tmp_path: Path,
) -> None:
    base = (Path(".pytest-tmp") / "external-sdk").resolve()
    unique_prefix = (
        "sdk-prepare-" + hashlib.sha256(str(tmp_path).encode()).hexdigest()[:12] + "-"
    )
    padding = "x" * max(8, 128 - len(str(base)) - len(unique_prefix) - 1)
    deep_root = base / f"{unique_prefix}{padding}"
    assert len(str(deep_root)) >= 128
    with PlotAgentSDK(deep_root) as sdk:
        project = sdk.create_project(idempotency_key="prepare")
        project_id = cast(str, project["project_id"])
        opened = sdk.open_project(project_id)
        imported = cast(
            dict[str, Any],
            sdk.import_dataset(
                project_id,
                FIXTURES / "excel_two_sheets.xlsx",
                expected_project_version=cast(int, opened["project_version"]),
                idempotency_key="prepare-import",
                resource_id="resource:prepare",
            ),
        )
        dataset = cast(dict[str, Any], cast(list[object], imported["datasets"])[0])
        numeric = tuple(
            cast(str, field["field_id"])
            for field in cast(list[dict[str, object]], dataset["fields"])
            if field["logical_type"] == "numeric"
        )[:2]
        source = {
            "kind": "source",
            "dataset_id": dataset["source_dataset_id"],
            "version": dataset["source_version"],
            "content_hash": dataset["content_hash"],
        }
        staged = sdk.stage_source_data(
            project_id,
            workspace_id="prepare-line",
            source=source,
            field_ids=numeric,
        )
        assert (deep_root / "external-data-v1" / "index.sqlite3").is_file()
        assert not any((deep_root / "projects").glob("*/tmp/agent-data-v2"))
        source_handle = cast(dict[str, Any], staged["handle"])
        transformed = sdk.apply_data_operation(
            project_id,
            workspace_id="prepare-line",
            operation={
                "kind": "select_fields",
                "input_handle_id": source_handle["handle_id"],
                "field_ids": numeric,
            },
        )
        prepared_handle = cast(dict[str, Any], transformed["handle"])
        preview = sdk.preview_data_view(
            project_id,
            workspace_id="prepare-line",
            handle_id=cast(str, prepared_handle["handle_id"]),
            field_ids=numeric,
            limit=3,
        )
        assert len(cast(dict[str, Any], preview["preview"])["rows"]) == 2
        committed = sdk.commit_data_view(
            project_id,
            workspace_id="prepare-line",
            handle_id=cast(str, prepared_handle["handle_id"]),
        )
        data = cast(dict[str, Any], committed["data"])
        assert data["kind"] == "prepared"
        created = sdk.create_plot(
            project_id,
            {
                "operation": "create_plot",
                "action_id": "action:prepared.create",
                "plot_id": "plot:prepared",
                "profile_id": "K01",
                "data": data,
                "bindings": (
                    {"role": "x", "field_id": numeric[0]},
                    {"role": "y", "field_id": numeric[1]},
                ),
            },
            expected_project_version=cast(int, committed["project_version"]),
        )
        assert created["plot_version"] == 1
