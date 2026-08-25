from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from mcp.client import Client

from plotagent.mcp_server import McpServerSettings, create_server

FIXTURES = Path(__file__).parents[1] / "fixtures" / "import" / "files"


def _data(result: object) -> dict[str, Any]:
    structured = cast(Any, result).structured_content
    assert structured["ok"] is True
    return cast(dict[str, Any], structured["data"])


@pytest.mark.asyncio
async def test_mcp_discovers_complete_bounded_surface(tmp_path: Path) -> None:
    server = create_server(
        McpServerSettings(
            engine_root=tmp_path / "engine",
            import_roots=(FIXTURES,),
            export_root=tmp_path / "exports",
        )
    )
    async with Client(server) as client:
        listed = await client.list_tools()
    assert {tool.name for tool in listed.tools} == {
        "plotagent_health",
        "plotagent_projects",
        "plotagent_create_project",
        "plotagent_open_project",
        "plotagent_import_dataset",
        "plotagent_datasets",
        "plotagent_inspect_data",
        "plotagent_data_view",
        "plotagent_chart_capabilities",
        "plotagent_validate_action",
        "plotagent_execute_action",
        "plotagent_plots",
        "plotagent_get_plot",
        "plotagent_restore_plot",
        "plotagent_export_plot",
    }


@pytest.mark.asyncio
async def test_mcp_uses_sdk_engine_and_confines_paths(tmp_path: Path) -> None:
    export_root = tmp_path / "exports"
    server = create_server(
        McpServerSettings(
            engine_root=tmp_path / "engine",
            import_roots=(FIXTURES,),
            export_root=export_root,
        )
    )
    outside = tmp_path / "outside.csv"
    outside.write_text("x,y\n1,2\n", encoding="utf-8")
    async with Client(server) as client:
        project = _data(
            await client.call_tool("plotagent_create_project", {"idempotency_key": "mcp"})
        )
        project_id = cast(str, project["project_id"])
        opened = _data(
            await client.call_tool("plotagent_open_project", {"project_id": project_id})
        )
        denied = await client.call_tool(
            "plotagent_import_dataset",
            {
                "project_id": project_id,
                "source_path": str(outside),
                "resource_id": "resource:outside",
                "idempotency_key": "outside",
                "expected_project_version": opened["project_version"],
            },
        )
        denied_payload = cast(Any, denied).structured_content
        assert denied_payload["error"]["code"] == "IMPORT_PATH_NOT_AUTHORIZED"

        imported = _data(
            await client.call_tool(
                "plotagent_import_dataset",
                {
                    "project_id": project_id,
                    "source_path": str(FIXTURES / "excel_two_sheets.xlsx"),
                    "resource_id": "resource:mcp-input",
                    "idempotency_key": "mcp-import",
                    "expected_project_version": opened["project_version"],
                },
            )
        )
        dataset = cast(dict[str, Any], cast(list[object], imported["datasets"])[0])
        numeric = [
            cast(str, field["field_id"])
            for field in cast(list[dict[str, object]], dataset["fields"])
            if field["logical_type"] == "numeric"
        ]
        action = {
            "operation": "create_plot",
            "action_id": "action:mcp.create",
            "plot_id": "plot:mcp",
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
        }
        validated = _data(
            await client.call_tool(
                "plotagent_validate_action",
                {
                    "project_id": project_id,
                    "expected_project_version": imported["project_version"],
                    "action": action,
                },
            )
        )
        assert validated["valid"] is True
        created = _data(
            await client.call_tool(
                "plotagent_execute_action",
                {
                    "project_id": project_id,
                    "expected_project_version": imported["project_version"],
                    "action": action,
                },
            )
        )
        assert created["plot_version"] == 1
        exported = _data(
            await client.call_tool(
                "plotagent_export_plot",
                {
                    "project_id": project_id,
                    "resource_id": "resource:mcp-export",
                    "action": {
                        "operation": "export_plot",
                        "action_id": "action:mcp.export",
                        "target": "plot:mcp",
                        "expected_plot_version": 1,
                        "format": "png",
                        "output_name": "mcp.png",
                    },
                },
            )
        )
        assert exported["artifact"]["path"] == str(export_root / "mcp.png")
        assert (export_root / "mcp.png").is_file()
