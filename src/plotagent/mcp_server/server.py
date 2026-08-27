"""Typed MCP tools backed by the public Python SDK."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from pydantic import Field, StringConstraints

from plotagent.engine.contracts import ExportPlot
from plotagent.mcp_server.config import McpServerSettings
from plotagent.mcp_server.models import (
    McpApplyDataOperation,
    McpCommitDataView,
    McpDataViewRequest,
    McpImportOptions,
    McpInspectDataView,
    McpPlotAction,
    McpPreviewDataView,
    McpStageSourceData,
    McpToolResponse,
)
from plotagent.sdk import EXTERNAL_ENGINE_API_VERSION, PlotAgentSDK, PlotAgentSDKError
from plotagent.sdk.paths import authorized_export_path, authorized_import_path

ProjectId = Annotated[
    str,
    StringConstraints(pattern=r"^project:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
PlotId = Annotated[
    str,
    StringConstraints(pattern=r"^plot:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
RequestToken = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,127}$", strict=True),
]


def create_server(settings: McpServerSettings) -> MCPServer[PlotAgentSDK]:
    """Build the official in-process-testable MCP stdio server."""

    settings.export_root.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(_: MCPServer[PlotAgentSDK]) -> AsyncIterator[PlotAgentSDK]:
        with PlotAgentSDK(settings.engine_root) as sdk:
            yield sdk

    server: MCPServer[PlotAgentSDK] = MCPServer(
        "plotagent-engine",
        title="fig-agent Scientific Plotting Engine",
        description=(
            "Inspect scientific data and create, edit, version and export native plots."
        ),
        instructions=(
            "You are the planning Agent; fig-agent is the deterministic plotting engine. "
            "Inspect data and chart capabilities before constructing actions. Never invent "
            "field, project or plot identifiers. Validate an action before execution when "
            "the user has not already confirmed the exact bindings and changes. On a version "
            "conflict, re-read the project or plot before retrying."
        ),
        version=EXTERNAL_ENGINE_API_VERSION,
        lifespan=lifespan,
    )

    @server.tool()
    async def plotagent_health(ctx: Context[PlotAgentSDK, Any]) -> McpToolResponse:
        """Report engine/interface versions and workspace isolation."""
        return _call(lambda: ctx.request_context.lifespan_context.health())

    @server.tool()
    async def plotagent_projects(ctx: Context[PlotAgentSDK, Any]) -> McpToolResponse:
        """List projects in this MCP server's isolated engine root."""
        return _call(lambda: ctx.request_context.lifespan_context.list_projects())

    @server.tool()
    async def plotagent_create_project(
        idempotency_key: RequestToken,
        ctx: Context[PlotAgentSDK, Any],
        display_name: str | None = None,
    ) -> McpToolResponse:
        """Create a project; replaying the same key is safe."""
        return _call(
            lambda: ctx.request_context.lifespan_context.create_project(
                idempotency_key=idempotency_key,
                display_name=display_name,
            )
        )

    @server.tool()
    async def plotagent_open_project(
        project_id: ProjectId,
        ctx: Context[PlotAgentSDK, Any],
    ) -> McpToolResponse:
        """Open a project and return its authoritative version."""
        return _call(lambda: ctx.request_context.lifespan_context.open_project(project_id))

    @server.tool()
    async def plotagent_import_dataset(
        project_id: ProjectId,
        source_path: str,
        resource_id: RequestToken,
        idempotency_key: RequestToken,
        expected_project_version: Annotated[int, Field(ge=0)],
        ctx: Context[PlotAgentSDK, Any],
        options: McpImportOptions | None = None,
    ) -> McpToolResponse:
        """Import an authorized data file without executing formulas or macros."""
        try:
            source = authorized_import_path(source_path, settings.import_roots)
        except PlotAgentSDKError as error:
            return McpToolResponse.failure(error.code, error.message)
        return _call(
            lambda: ctx.request_context.lifespan_context.import_dataset(
                project_id,
                source,
                expected_project_version=expected_project_version,
                idempotency_key=idempotency_key,
                resource_id=resource_id,
                options=(options or McpImportOptions()).model_dump(
                    mode="json", exclude_none=True
                ),
            )
        )

    @server.tool()
    async def plotagent_datasets(
        project_id: ProjectId,
        ctx: Context[PlotAgentSDK, Any],
    ) -> McpToolResponse:
        """List imported datasets and immutable field identifiers."""
        return _call(lambda: ctx.request_context.lifespan_context.list_datasets(project_id))

    @server.tool()
    async def plotagent_inspect_data(
        project_id: ProjectId,
        source_dataset_id: str,
        source_version: Annotated[int, Field(ge=1)],
        ctx: Context[PlotAgentSDK, Any],
    ) -> McpToolResponse:
        """Read field types, units, quality, metadata and five sample rows."""
        return _call(
            lambda: ctx.request_context.lifespan_context.inspect_data(
                project_id, source_dataset_id, source_version
            )
        )

    @server.tool()
    async def plotagent_data_view(
        project_id: ProjectId,
        request: McpDataViewRequest,
        ctx: Context[PlotAgentSDK, Any],
    ) -> McpToolResponse:
        """Stage, transform, inspect, preview or commit deterministic prepared data."""
        command = request.root
        sdk = ctx.request_context.lifespan_context
        if isinstance(command, McpStageSourceData):
            return _call(
                lambda: sdk.stage_source_data(
                    project_id,
                    workspace_id=command.workspace_id,
                    source=command.source.model_dump(mode="python"),
                    field_ids=command.field_ids,
                )
            )
        if isinstance(command, McpApplyDataOperation):
            return _call(
                lambda: sdk.apply_data_operation(
                    project_id,
                    workspace_id=command.workspace_id,
                    operation=command.data_operation.model_dump(mode="python"),
                )
            )
        if isinstance(command, McpInspectDataView):
            return _call(
                lambda: sdk.inspect_data_view(
                    project_id,
                    workspace_id=command.workspace_id,
                    handle_id=command.handle_id,
                )
            )
        if isinstance(command, McpPreviewDataView):
            return _call(
                lambda: sdk.preview_data_view(
                    project_id,
                    workspace_id=command.workspace_id,
                    handle_id=command.handle_id,
                    field_ids=command.field_ids,
                    offset=command.offset,
                    limit=command.limit,
                )
            )
        if isinstance(command, McpCommitDataView):
            return _call(
                lambda: sdk.commit_data_view(
                    project_id,
                    workspace_id=command.workspace_id,
                    handle_id=command.handle_id,
                )
            )
        raise AssertionError("unhandled external data command")

    @server.tool()
    async def plotagent_chart_capabilities(
        project_id: ProjectId,
        ctx: Context[PlotAgentSDK, Any],
    ) -> McpToolResponse:
        """List chart profiles, required roles, objects and allowed edit parameters."""
        return _call(
            lambda: ctx.request_context.lifespan_context.chart_capabilities(project_id)
        )

    @server.tool()
    async def plotagent_validate_action(
        project_id: ProjectId,
        expected_project_version: Annotated[int, Field(ge=0)],
        action: McpPlotAction,
        ctx: Context[PlotAgentSDK, Any],
    ) -> McpToolResponse:
        """Validate one exact plotting action without changing the project."""
        return _call(
            lambda: ctx.request_context.lifespan_context.validate_action(
                project_id,
                action.root,
                expected_project_version=expected_project_version,
            )
        )

    @server.tool()
    async def plotagent_execute_action(
        project_id: ProjectId,
        expected_project_version: Annotated[int, Field(ge=0)],
        action: McpPlotAction,
        ctx: Context[PlotAgentSDK, Any],
    ) -> McpToolResponse:
        """Create or edit one plot using a validated, version-pinned public action."""
        return _call(
            lambda: ctx.request_context.lifespan_context.execute_action(
                project_id,
                action.root,
                expected_project_version=expected_project_version,
            )
        )

    @server.tool()
    async def plotagent_plots(
        project_id: ProjectId,
        ctx: Context[PlotAgentSDK, Any],
    ) -> McpToolResponse:
        """List the latest committed version of every plot."""
        return _call(lambda: ctx.request_context.lifespan_context.list_plots(project_id))

    @server.tool()
    async def plotagent_get_plot(
        project_id: ProjectId,
        plot_id: PlotId,
        ctx: Context[PlotAgentSDK, Any],
        plot_version: Annotated[int | None, Field(ge=1)] = None,
    ) -> McpToolResponse:
        """Read one plot document, preview, readback and action history."""
        return _call(
            lambda: ctx.request_context.lifespan_context.get_plot(
                project_id, plot_id, plot_version=plot_version
            )
        )

    @server.tool()
    async def plotagent_restore_plot(
        project_id: ProjectId,
        plot_id: PlotId,
        expected_project_version: Annotated[int, Field(ge=0)],
        expected_plot_version: Annotated[int, Field(ge=1)],
        source_plot_version: Annotated[int, Field(ge=1)],
        action_id: RequestToken,
        ctx: Context[PlotAgentSDK, Any],
    ) -> McpToolResponse:
        """Restore a prior plot version as a new immutable version."""
        return _call(
            lambda: ctx.request_context.lifespan_context.restore_plot(
                project_id,
                plot_id,
                expected_project_version=expected_project_version,
                expected_plot_version=expected_plot_version,
                source_plot_version=source_plot_version,
                action_id=action_id,
            )
        )

    @server.tool()
    async def plotagent_export_plot(
        project_id: ProjectId,
        action: ExportPlot,
        resource_id: RequestToken,
        ctx: Context[PlotAgentSDK, Any],
        expected_existing_sha256: str | None = None,
    ) -> McpToolResponse:
        """Export PNG, SVG or native editable OPJU into the authorized output root."""
        try:
            destination = authorized_export_path(action.output_name, settings.export_root)
        except PlotAgentSDKError as error:
            return McpToolResponse.failure(error.code, error.message)
        return _call(
            lambda: ctx.request_context.lifespan_context.export_plot(
                project_id,
                action,
                destination,
                resource_id=resource_id,
                expected_existing_sha256=expected_existing_sha256,
            )
        )

    return server


def _call(operation: Callable[[], dict[str, Any]]) -> McpToolResponse:
    try:
        return McpToolResponse.success(operation())
    except PlotAgentSDKError as error:
        return McpToolResponse.failure(error.code, error.message)
