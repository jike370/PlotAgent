from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from mcp.client import Client

from plotagent.mcp_server import McpServerSettings, create_server
from plotagent.sdk import PlotAgentSDK

FIXTURES = Path(__file__).parents[1] / "fixtures" / "import" / "files"


def _data(result: object) -> dict[str, Any]:
    structured = cast(Any, result).structured_content
    assert structured["ok"] is True
    return cast(dict[str, Any], structured["data"])


def _normalize(value: object) -> object:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


@pytest.mark.asyncio
async def test_sdk_and_mcp_return_the_same_catalog(tmp_path: Path) -> None:
    with PlotAgentSDK(tmp_path / "sdk") as sdk:
        project = sdk.create_project(idempotency_key="equivalent")
        project_id = cast(str, project["project_id"])
        sdk.open_project(project_id)
        expected = sdk.chart_capabilities(project_id)

    server = create_server(
        McpServerSettings(
            engine_root=tmp_path / "mcp",
            import_roots=(FIXTURES,),
            export_root=tmp_path / "exports",
        )
    )
    async with Client(server) as client:
        project = _data(
            await client.call_tool(
                "plotagent_create_project", {"idempotency_key": "equivalent"}
            )
        )
        project_id = cast(str, project["project_id"])
        await client.call_tool("plotagent_open_project", {"project_id": project_id})
        actual = _data(
            await client.call_tool(
                "plotagent_chart_capabilities", {"project_id": project_id}
            )
        )
    assert _normalize(actual) == _normalize(expected)
    profiles = cast(list[dict[str, object]], actual["profiles"])
    assert len(profiles) == 34
    assert all(profile["capabilities"] for profile in profiles)
