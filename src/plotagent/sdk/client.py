"""In-process Python SDK over the same Core services used by PlotAgent Desktop.

The SDK owns an isolated workspace and exposes only plotting-engine operations.
It does not start the built-in Pi runtime and it cannot execute arbitrary Python,
Matplotlib, LabTalk, or Origin code.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from threading import RLock
from typing import cast

from plotagent import __version__
from plotagent.desktop_core.protocol import JsonValue
from plotagent.desktop_core.services import RpcContext, RpcServiceError, ServiceRegistry
from plotagent.desktop_core.tasks import BoundedWorkerExecutor, TaskControlError, TaskRegistry
from plotagent.engine import EngineActionCodec, EngineCatalog
from plotagent.engine.contracts import CreatePlot, ExportPlot, PlotEngineAction
from plotagent.engine.profiles import ENGINE_PROFILES
from plotagent.sdk.errors import PlotAgentSDKError
from plotagent.sdk.extension_core import ExternalEngineCore, external_data_error
from plotagent.security import InMemoryCredentialStore

EXTERNAL_ENGINE_API_VERSION = "1.0"


class PlotAgentSDK:
    """Own one headless PlotAgent workspace without touching Desktop state."""

    def __init__(
        self,
        root: str | Path,
        *,
        maximum_workers: int = 2,
        maximum_pending: int = 4,
    ) -> None:
        self.root = Path(root).resolve()
        self._application = ExternalEngineCore(
            self.root,
            credential_store=InMemoryCredentialStore(),
        )
        self._registry = ServiceRegistry()
        self._workers = BoundedWorkerExecutor(
            max_workers=maximum_workers,
            maximum_pending=maximum_pending,
        )
        self._tasks = TaskRegistry()
        self._application.configure_services(self._registry, self._tasks, self._workers)
        self._catalog = EngineCatalog(ENGINE_PROFILES)
        self._codec = EngineActionCodec(self._catalog)
        self._closed = False
        self._lock = RLock()

    def __enter__(self) -> PlotAgentSDK:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._workers.shutdown()
        self._application.close()

    def health(self) -> dict[str, JsonValue]:
        return {
            "status": "ok",
            "engine_api_version": EXTERNAL_ENGINE_API_VERSION,
            "plotagent_version": __version__,
            "desktop_workspace_isolated": True,
        }

    def create_project(
        self,
        *,
        idempotency_key: str,
        display_name: str | None = None,
    ) -> dict[str, JsonValue]:
        return self._call(
            "projects.create",
            {
                "idempotency_key": idempotency_key,
                **({"display_name": display_name} if display_name is not None else {}),
            },
        )

    def list_projects(self) -> dict[str, JsonValue]:
        return self._call("projects.list", {})

    def open_project(self, project_id: str) -> dict[str, JsonValue]:
        return self._call("projects.open", {"project_id": project_id})

    def close_project(self, project_id: str) -> dict[str, JsonValue]:
        return self._call("projects.close", {"project_id": project_id})

    def import_dataset(
        self,
        project_id: str,
        source_path: str | Path,
        *,
        expected_project_version: int,
        idempotency_key: str,
        resource_id: str,
        options: Mapping[str, JsonValue] | None = None,
    ) -> dict[str, JsonValue]:
        return self._call(
            "datasets.import",
            {
                "project_id": project_id,
                "resource_id": resource_id,
                "source_path": str(Path(source_path).resolve()),
                "idempotency_key": idempotency_key,
                "expected_version": expected_project_version,
                "options": dict(options or {}),
            },
        )

    def list_datasets(self, project_id: str) -> dict[str, JsonValue]:
        return self._call("datasets.list", {"project_id": project_id})

    def inspect_data(
        self,
        project_id: str,
        source_dataset_id: str,
        source_version: int,
    ) -> dict[str, JsonValue]:
        return self._call(
            "datasets.describe",
            {
                "project_id": project_id,
                "source_dataset_id": source_dataset_id,
                "source_version": source_version,
            },
        )

    describe_dataset = inspect_data

    def stage_source_data(
        self,
        project_id: str,
        *,
        workspace_id: str,
        source: Mapping[str, object],
        field_ids: tuple[str, ...],
    ) -> dict[str, JsonValue]:
        return self._external_data_call(
            self._application.stage_source_data,
            project_id,
            workspace_id=workspace_id,
            source=source,
            field_ids=field_ids,
        )

    def apply_data_operation(
        self,
        project_id: str,
        *,
        workspace_id: str,
        operation: Mapping[str, object],
    ) -> dict[str, JsonValue]:
        return self._external_data_call(
            self._application.apply_data_operation,
            project_id,
            workspace_id=workspace_id,
            operation=operation,
        )

    def inspect_data_view(
        self,
        project_id: str,
        *,
        workspace_id: str,
        handle_id: str,
    ) -> dict[str, JsonValue]:
        return self._external_data_call(
            self._application.inspect_data_view,
            project_id,
            workspace_id=workspace_id,
            handle_id=handle_id,
        )

    def preview_data_view(
        self,
        project_id: str,
        *,
        workspace_id: str,
        handle_id: str,
        field_ids: tuple[str, ...],
        offset: int = 0,
        limit: int = 5,
    ) -> dict[str, JsonValue]:
        return self._external_data_call(
            self._application.preview_data_view,
            project_id,
            workspace_id=workspace_id,
            handle_id=handle_id,
            field_ids=field_ids,
            offset=offset,
            limit=limit,
        )

    def commit_data_view(
        self,
        project_id: str,
        *,
        workspace_id: str,
        handle_id: str,
    ) -> dict[str, JsonValue]:
        return self._external_data_call(
            self._application.commit_data_view,
            project_id,
            workspace_id=workspace_id,
            handle_id=handle_id,
        )

    def chart_capabilities(self, project_id: str) -> dict[str, JsonValue]:
        return self._call("engine.catalog.get", {"project_id": project_id})

    catalog = chart_capabilities

    def validate_action(
        self,
        project_id: str,
        action: PlotEngineAction | Mapping[str, object],
        *,
        expected_project_version: int,
    ) -> dict[str, JsonValue]:
        """Validate structure, profile capability and current versions without mutation."""

        current = self.open_project(project_id)
        current_project_version = cast(int, current["project_version"])
        if current_project_version != expected_project_version:
            raise PlotAgentSDKError("ENGINE_VERSION_CONFLICT", "project version is stale")
        arguments = self._action_arguments(action)
        try:
            decoded = self._codec.decode(arguments)
            if isinstance(decoded, CreatePlot):
                profile = self._catalog.validate_create(decoded)
                current_plot_version: int | None = None
            else:
                target = cast(str, arguments.get("target"))
                plot = self.get_plot(project_id, target)
                current_plot_version = cast(int, plot["plot_version"])
                expected_plot_version = cast(int | None, arguments.get("expected_plot_version"))
                if expected_plot_version != current_plot_version:
                    raise PlotAgentSDKError(
                        "ENGINE_VERSION_CONFLICT", "plot version is stale"
                    )
                profile = self._catalog.get(cast(str, plot["profile_id"]))
                self._catalog.validate_action(profile, decoded)
        except PlotAgentSDKError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise PlotAgentSDKError("INVALID_PARAMS", str(error)) from None
        return {
            "valid": True,
            "project_id": project_id,
            "project_version": current_project_version,
            "plot_version": current_plot_version,
            "profile_id": profile.profile_id,
            "action": cast(JsonValue, decoded.model_dump(mode="json")),
        }

    def execute_action(
        self,
        project_id: str,
        action: PlotEngineAction | Mapping[str, object],
        *,
        expected_project_version: int,
        request_id: str | None = None,
    ) -> dict[str, JsonValue]:
        return self._call(
            "engine.actions.execute",
            {
                "project_id": project_id,
                "action": cast(JsonValue, self._action_arguments(action)),
                "expected_project_version": expected_project_version,
            },
            request_id=request_id,
        )

    create_plot = execute_action
    edit_plot = execute_action

    def list_plots(self, project_id: str) -> dict[str, JsonValue]:
        return self._call("engine.plots.list", {"project_id": project_id})

    def get_plot(
        self,
        project_id: str,
        plot_id: str,
        *,
        plot_version: int | None = None,
    ) -> dict[str, JsonValue]:
        return self._call(
            "engine.plots.get",
            {
                "project_id": project_id,
                "plot_id": plot_id,
                **({"plot_version": plot_version} if plot_version is not None else {}),
            },
        )

    inspect_plot = get_plot

    def restore_plot(
        self,
        project_id: str,
        plot_id: str,
        *,
        expected_project_version: int,
        expected_plot_version: int,
        source_plot_version: int,
        action_id: str,
    ) -> dict[str, JsonValue]:
        return self._call(
            "engine.plots.restore",
            {
                "project_id": project_id,
                "plot_id": plot_id,
                "expected_project_version": expected_project_version,
                "expected_plot_version": expected_plot_version,
                "source_plot_version": source_plot_version,
                "action_id": action_id,
            },
        )

    def export_plot(
        self,
        project_id: str,
        action: ExportPlot | Mapping[str, object],
        destination: str | Path,
        *,
        resource_id: str,
        expected_existing_sha256: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, JsonValue]:
        return self._call(
            "engine.exports.execute",
            {
                "project_id": project_id,
                "action": cast(JsonValue, self._action_arguments(action)),
                "destination_resource_id": resource_id,
                "destination_path": str(Path(destination).resolve()),
                **(
                    {"expected_existing_sha256": expected_existing_sha256}
                    if expected_existing_sha256 is not None
                    else {}
                ),
            },
            request_id=request_id,
        )

    @staticmethod
    def _action_arguments(
        action: PlotEngineAction | Mapping[str, object],
    ) -> dict[str, object]:
        if hasattr(action, "model_dump"):
            return cast(dict[str, object], action.model_dump(mode="python"))
        return dict(action)

    def _call(
        self,
        method: str,
        params: dict[str, JsonValue],
        *,
        request_id: str | None = None,
    ) -> dict[str, JsonValue]:
        if self._closed:
            raise PlotAgentSDKError("SDK_CLOSED", "The PlotAgent SDK is closed.")
        context = RpcContext(
            request_id=request_id or "req:sdk." + uuid.uuid4().hex,
            tasks=self._tasks,
            workers=self._workers,
        )
        try:
            with self._lock:
                result = self._registry.dispatch(method, context, params)
        except (RpcServiceError, TaskControlError) as error:
            raise PlotAgentSDKError(error.code, error.message) from None
        if not isinstance(result, dict):
            raise PlotAgentSDKError(
                "SDK_RESPONSE_INVALID",
                "The PlotAgent engine returned an invalid response.",
            )
        return result

    def _external_data_call(
        self,
        callback: Callable[..., dict[str, object]],
        *args: object,
        **kwargs: object,
    ) -> dict[str, JsonValue]:
        if self._closed:
            raise PlotAgentSDKError("SDK_CLOSED", "The PlotAgent SDK is closed.")
        try:
            with self._lock:
                result = callback(*args, **kwargs)
        except Exception as error:
            raise external_data_error(error) from None
        return cast(dict[str, JsonValue], result)
