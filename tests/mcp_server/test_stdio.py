from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

FIXTURES = Path(__file__).parents[1] / "fixtures" / "import" / "files"


@pytest.mark.asyncio
async def test_mcp_entrypoint_negotiates_over_stdio(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONPATH": str(Path(__file__).parents[2] / "src"),
            "PLOTAGENT_ENGINE_ROOT": str(tmp_path / "engine"),
            "PLOTAGENT_ENGINE_IMPORT_ROOTS": str(FIXTURES),
            "PLOTAGENT_ENGINE_EXPORT_ROOT": str(tmp_path / "exports"),
        }
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "plotagent.mcp_server"],
        env=environment,
        cwd=Path(__file__).parents[2],
    )
    async with (
        stdio_client(parameters) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        initialized = await session.initialize()
        tools = await session.list_tools()
        health = await session.call_tool("plotagent_health", {})

    assert initialized.server_info.name == "plotagent-engine"
    assert len(tools.tools) == 15
    assert health.structured_content == {
        "ok": True,
        "data": {
            "status": "ok",
            "engine_api_version": "1.0",
            "plotagent_version": "0.1.0",
            "desktop_workspace_isolated": True,
        },
        "error": None,
    }
