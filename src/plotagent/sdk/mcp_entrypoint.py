"""Dependency-safe console entrypoint for the optional MCP transport."""

from __future__ import annotations


def main() -> None:
    try:
        from plotagent.mcp_server import McpServerSettings, create_server
    except ModuleNotFoundError as error:
        if error.name == "mcp":
            raise SystemExit(
                "PlotAgent MCP is optional. Install it with: pip install 'plotagent[mcp]'"
            ) from None
        raise
    create_server(McpServerSettings.from_environment()).run(transport="stdio")


if __name__ == "__main__":
    main()
