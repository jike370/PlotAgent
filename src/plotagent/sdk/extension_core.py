"""External-only Core extensions that are intentionally absent from Desktop RPC.

Shared project, import, plotting and export services remain authoritative. This
module only exposes deterministic staged-data preparation to external Agents.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from pydantic import TypeAdapter, ValidationError

from plotagent.contracts.agent_data import DataViewOperation
from plotagent.desktop_core.application import DesktopApplication
from plotagent.engine.contracts import EngineDataRef
from plotagent.engine.data import ProjectEngineDataProvider
from plotagent.sdk.errors import PlotAgentSDKError
from plotagent.storage.project import ProjectStore
from plotagent.tooling.data_workspace import StagedDataWorkspace
from plotagent.tooling.data_workspace_ops import DataWorkspaceError

_OPERATION_ADAPTER: TypeAdapter[DataViewOperation] = TypeAdapter(DataViewOperation)


class ExternalEngineCore(DesktopApplication):
    """Desktop-compatible Core host plus isolated external data preparation."""

    def stage_source_data(
        self,
        project_id: str,
        *,
        workspace_id: str,
        source: EngineDataRef | Mapping[str, object],
        field_ids: tuple[str, ...],
    ) -> dict[str, Any]:
        session = self._external_session(project_id)
        data_ref = (
            source if isinstance(source, EngineDataRef) else EngineDataRef.model_validate(source)
        )
        with self._external_workspace(session.store) as workspace:
            handle = workspace.stage_source(
                task_id=self._task_id(project_id, workspace_id),
                task_version=1,
                item_id=None,
                source=data_ref,
                field_ids=field_ids,
                provider=ProjectEngineDataProvider(session.store),
            )
        return {
            "project_id": project_id,
            "project_version": session.domain.revision,
            "workspace_id": workspace_id,
            "handle": handle.model_dump(mode="json"),
        }

    def apply_data_operation(
        self,
        project_id: str,
        *,
        workspace_id: str,
        operation: DataViewOperation | Mapping[str, object],
    ) -> dict[str, Any]:
        session = self._external_session(project_id)
        parsed = (
            operation
            if not isinstance(operation, Mapping)
            else _OPERATION_ADAPTER.validate_python(dict(operation))
        )
        with self._external_workspace(session.store) as workspace:
            handle = workspace.apply(
                task_id=self._task_id(project_id, workspace_id),
                task_version=1,
                item_id=None,
                operation=parsed,
            )
        return {
            "project_id": project_id,
            "project_version": session.domain.revision,
            "workspace_id": workspace_id,
            "handle": handle.model_dump(mode="json"),
        }

    def inspect_data_view(
        self,
        project_id: str,
        *,
        workspace_id: str,
        handle_id: str,
    ) -> dict[str, Any]:
        session = self._external_session(project_id)
        with self._external_workspace(session.store) as workspace:
            handle = workspace.inspect(
                handle_id,
                task_id=self._task_id(project_id, workspace_id),
                task_version=1,
                item_id=None,
            )
        return {
            "project_id": project_id,
            "project_version": session.domain.revision,
            "workspace_id": workspace_id,
            "handle": handle.model_dump(mode="json"),
        }

    def preview_data_view(
        self,
        project_id: str,
        *,
        workspace_id: str,
        handle_id: str,
        field_ids: tuple[str, ...],
        offset: int = 0,
        limit: int = 5,
    ) -> dict[str, Any]:
        session = self._external_session(project_id)
        with self._external_workspace(session.store) as workspace:
            preview = workspace.preview(
                handle_id,
                task_id=self._task_id(project_id, workspace_id),
                task_version=1,
                item_id=None,
                field_ids=field_ids,
                offset=offset,
                limit=limit,
            )
        return {
            "project_id": project_id,
            "project_version": session.domain.revision,
            "workspace_id": workspace_id,
            "preview": preview.model_dump(mode="json"),
        }

    def commit_data_view(
        self,
        project_id: str,
        *,
        workspace_id: str,
        handle_id: str,
    ) -> dict[str, Any]:
        """Publish one prepared view so a subsequent CreatePlot can bind it."""

        session = self._external_session(project_id)
        with self._external_workspace(session.store) as workspace:
            handle, view = workspace.get(
                handle_id,
                task_id=self._task_id(project_id, workspace_id),
                task_version=1,
                item_id=None,
            )
        persisted = (
            view if view.data.kind == "source" else session.engine.data_views.register(view)
        )
        return {
            "project_id": project_id,
            "project_version": session.domain.revision,
            "workspace_id": workspace_id,
            "data": persisted.data.model_dump(mode="json"),
            "fields": tuple(column.field.model_dump(mode="json") for column in persisted.columns),
            "row_count": len(persisted.row_ids),
            "lineage": tuple(item.model_dump(mode="json") for item in handle.lineage),
        }

    def display_plot_ref(self, project_id: str, plot_id: str) -> str:
        """Return a stable external-only @图N alias for one committed plot."""

        session = self._external_session(project_id)
        session.engine.documents.get(plot_id)
        connection = session.store._assert_writer()  # noqa: SLF001
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS external_plot_display_refs (
                plot_id TEXT PRIMARY KEY,
                ordinal INTEGER NOT NULL UNIQUE CHECK (ordinal >= 1)
            ) STRICT
            """
        )
        row = connection.execute(
            "SELECT ordinal FROM external_plot_display_refs WHERE plot_id = ?",
            (plot_id,),
        ).fetchone()
        if row is None:
            next_row = connection.execute(
                "SELECT COALESCE(MAX(ordinal), 0) + 1 FROM external_plot_display_refs"
            ).fetchone()
            ordinal = 1 if next_row is None else int(next_row[0])
            connection.execute(
                "INSERT INTO external_plot_display_refs(plot_id, ordinal) VALUES (?, ?)",
                (plot_id, ordinal),
            )
        else:
            ordinal = int(row[0])
        return f"@图{ordinal}"

    def _external_session(self, project_id: str):  # type: ignore[no-untyped-def]
        try:
            return self._session(project_id)
        except Exception as error:
            code = getattr(error, "code", "PROJECT_NOT_OPEN")
            message = getattr(error, "message", "The project is not open.")
            raise PlotAgentSDKError(str(code), str(message)) from None

    def _external_workspace(self, project_store: ProjectStore) -> StagedDataWorkspace:
        return StagedDataWorkspace(
            project_store,
            workspace_root=self.root / "external-data-v1",
        )

    @staticmethod
    def _task_id(project_id: str, workspace_id: str) -> str:
        if not workspace_id or len(workspace_id) > 128:
            raise PlotAgentSDKError(
                "DATA_WORKSPACE_INVALID", "The data workspace identifier was invalid."
            )
        suffix = hashlib.sha256(f"{project_id}\0{workspace_id}".encode()).hexdigest()[:24]
        return f"task:external.{suffix}"


def external_data_error(error: Exception) -> PlotAgentSDKError:
    if isinstance(error, PlotAgentSDKError):
        return error
    if isinstance(error, DataWorkspaceError):
        return PlotAgentSDKError(error.code, error.message)
    if isinstance(error, ValidationError):
        return PlotAgentSDKError("INVALID_PARAMS", "The data operation was invalid.")
    if isinstance(error, OSError):
        return PlotAgentSDKError(
            "DATA_WORKSPACE_IO_FAILED",
            "The external data workspace could not persist the prepared view.",
        )
    return PlotAgentSDKError("DATA_PREPARATION_FAILED", "Data preparation failed safely.")
