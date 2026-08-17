"""Restart-safe task sandbox for PlotAgent engine previews and native readback."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from plotagent.contracts.agent_data import DataViewHandleId
from plotagent.contracts.agent_plots import (
    SandboxArtifactId,
    SandboxBackend,
    SandboxPlotArtifact,
    SandboxPlotEdit,
    SandboxPlotHandle,
    SandboxPlotHandleId,
    SandboxPlotLineageStep,
    SandboxPlotObject,
    SandboxPlotReadback,
)
from plotagent.contracts.agent_tasks import TaskId, TaskItemIdV2
from plotagent.contracts.canonical import JsonValue, canonical_hash, canonical_json
from plotagent.engine import (
    CreatePlot,
    EngineDataRef,
    EngineDataView,
    EngineDataViewRepository,
    FieldBinding,
    PlotDocument,
    PlotDocumentRepository,
    PlotEngineRuntime,
    PlotEngineService,
    document_ref,
)
from plotagent.engine.backends.matplotlib import default_matplotlib_backend
from plotagent.engine.backends.origin import OriginBackend, SubprocessOriginWorker
from plotagent.engine.backends.origin.backend import OriginWorker
from plotagent.engine.ports import EngineReadback, PlotBackend
from plotagent.engine.profiles import ENGINE_PROFILES
from plotagent.engine.service import EngineCatalog
from plotagent.storage.project import ProjectStore
from plotagent.tooling.data_workspace import StagedDataWorkspace

_MIN_TTL_SECONDS = 60
_MAX_TTL_SECONDS = 86_400


class SandboxPlotError(ValueError):
    def __init__(self, code: str, message: str, *, staged_side_effect: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.staged_side_effect = staged_side_effect


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class SandboxPlotWorkspace:
    """Execute public engine actions only inside a task-owned child project."""

    def __init__(
        self,
        project: ProjectStore,
        data_workspace: StagedDataWorkspace,
        *,
        task_id: TaskId,
        task_version: int,
        item_id: TaskItemIdV2 | None,
        origin_install_dir: Path | None = None,
        origin_worker: OriginWorker | None = None,
        clock: Callable[[], datetime] | None = None,
        ttl_seconds: int = 3_600,
    ) -> None:
        if not _MIN_TTL_SECONDS <= ttl_seconds <= _MAX_TTL_SECONDS:
            raise ValueError("sandbox plot TTL must be between 60 seconds and 24 hours")
        self._parent_tmp_root = project.tmp_root.resolve()
        self._data_workspace = data_workspace
        self.task_id = task_id
        self.task_version = task_version
        self.item_id = item_id
        self._origin_install_dir = (
            None if origin_install_dir is None else origin_install_dir.resolve()
        )
        self._origin_worker = origin_worker or SubprocessOriginWorker()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ttl_seconds = ttl_seconds
        self._writer_thread_id = threading.get_ident()
        scope_hash = canonical_hash(
            cast(
                JsonValue,
                {
                    "task_id": task_id,
                    "task_version": task_version,
                    "item_id": item_id,
                },
            )
        )[:32]
        self._root = self._parent_tmp_root / "agent-plot-v2" / scope_hash
        self._assert_safe_root()
        self._project = (
            ProjectStore.open(self._root)
            if (self._root / "project.sqlite3").is_file()
            else ProjectStore.create(
                self._root,
                project_id=f"project:sandbox.{scope_hash}",
            )
        )
        self._documents = PlotDocumentRepository(self._project)
        self._data_views = EngineDataViewRepository(self._project)
        self._catalog = EngineCatalog(ENGINE_PROFILES)
        self._service = PlotEngineService(self._catalog, self._documents)
        artifact_root = self._project.cache_root / "agent-sandbox"
        self._matplotlib_root = artifact_root / "matplotlib"
        self._origin_root = artifact_root / "origin"
        self._matplotlib = default_matplotlib_backend(self._matplotlib_root)
        self._connection().executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_sandbox_plot_handles_v2 (
                handle_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                task_version INTEGER NOT NULL CHECK (task_version >= 1),
                item_id TEXT,
                handle_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            ) STRICT;
            CREATE INDEX IF NOT EXISTS idx_agent_sandbox_plot_task_v2
                ON agent_sandbox_plot_handles_v2(task_id, task_version, item_id, expires_at);
            """
        )
        self._closed = False

    def __enter__(self) -> SandboxPlotWorkspace:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        remove = False
        try:
            self.cleanup_expired()
            row = (
                self._connection()
                .execute("SELECT COUNT(*) FROM agent_sandbox_plot_handles_v2")
                .fetchone()
            )
            remove = row is not None and int(row[0]) == 0
        finally:
            self._closed = True
            self._project.close()
        if remove:
            self._assert_safe_root()
            shutil.rmtree(self._root, ignore_errors=True)

    def preview(
        self,
        *,
        data_view_handle_id: DataViewHandleId,
        profile_id: str,
        bindings: tuple[FieldBinding, ...],
        backends: tuple[SandboxBackend, ...],
    ) -> SandboxPlotHandle:
        self._assert_open()
        if not backends or len(backends) != len(set(backends)):
            raise SandboxPlotError(
                "SANDBOX_BACKEND_INVALID",
                "Sandbox backends must be non-empty and unique.",
            )
        data_handle, view = self._data_workspace.get(
            data_view_handle_id,
            task_id=self.task_id,
            task_version=self.task_version,
            item_id=self.item_id,
        )
        fields = {column.field.field_id for column in view.columns}
        if any(binding.field_id not in fields for binding in bindings):
            raise SandboxPlotError(
                "SANDBOX_BINDING_FIELD_MISSING",
                "A sandbox plot binding is absent from the staged data view.",
            )
        payload = cast(
            JsonValue,
            {
                "data_view_handle_id": data_view_handle_id,
                "profile_id": profile_id,
                "bindings": tuple(binding.model_dump(mode="json") for binding in bindings),
                "backends": backends,
            },
        )
        action_hash = canonical_hash(payload)
        existing = self._find_existing(
            parent_handle_id=None,
            action_hash=action_hash,
            backends=backends,
        )
        if existing is not None:
            return existing
        generation = int(self._clock().timestamp() // self._ttl_seconds)
        plot_id = f"plot:sandbox.{action_hash[:16]}.{generation:x}"
        action = CreatePlot(
            action_id=f"action:sandbox.{action_hash[:24]}",
            plot_id=plot_id,
            profile_id=profile_id,
            data=self._register_data_view(data_handle.data_hash, view),
            bindings=bindings,
        )
        runtime = self._runtime(backends)
        try:
            result = runtime.execute(action)
        except Exception as error:
            raise SandboxPlotError(
                "SANDBOX_RENDER_FAILED",
                "The sandbox renderer rejected the staged plot request.",
                staged_side_effect=True,
            ) from error
        return self._persist(
            data_view_handle_id=data_view_handle_id,
            root_sources=data_handle.root_sources,
            staged_data_hash=data_handle.data_hash,
            document=result.document,
            backends=backends,
            readbacks=result.readbacks,
            parent=None,
            action_ids=(action.action_id,),
            action_hash=action_hash,
        )

    def apply_edit(
        self,
        handle_id: SandboxPlotHandleId,
        *,
        edit: SandboxPlotEdit,
        expected_backend: SandboxBackend,
    ) -> SandboxPlotHandle:
        parent = self.get(handle_id)
        if parent.backends != (expected_backend,):
            raise SandboxPlotError(
                "SANDBOX_BACKEND_MISMATCH",
                "The edit tool does not match the sandbox plot backend.",
            )
        if edit.expected_plot_version != parent.document.plot_version:
            raise SandboxPlotError(
                "SANDBOX_EDIT_VERSION_INVALID",
                "A sandbox edit must target the exact parent plot version.",
            )
        allowed_targets = {
            parent.document.plot_id,
            *(item.semantic_id for readback in parent.readbacks for item in readback.objects),
        }
        if edit.target not in allowed_targets:
            raise SandboxPlotError(
                "SANDBOX_EDIT_TARGET_INVALID",
                "A sandbox edit target is outside the parent plot readback.",
            )
        action_hash = canonical_hash(cast(JsonValue, edit.model_dump(mode="json")))
        existing = self._find_existing(
            parent_handle_id=parent.handle_id,
            action_hash=action_hash,
            backends=parent.backends,
        )
        if existing is not None:
            return existing
        runtime = self._runtime(parent.backends)
        try:
            result = runtime.execute(edit)
        except Exception as error:
            raise SandboxPlotError(
                "SANDBOX_EDIT_FAILED",
                "The sandbox renderer rejected an explicit public plot edit.",
                staged_side_effect=True,
            ) from error
        return self._persist(
            data_view_handle_id=parent.data_view_handle_id,
            root_sources=parent.root_sources,
            staged_data_hash=parent.staged_data_hash,
            document=result.document,
            backends=parent.backends,
            readbacks=result.readbacks,
            parent=parent,
            action_ids=(edit.action_id,),
            action_hash=action_hash,
        )

    def get(self, handle_id: SandboxPlotHandleId) -> SandboxPlotHandle:
        row = (
            self._connection()
            .execute(
                """
            SELECT handle_json FROM agent_sandbox_plot_handles_v2
            WHERE handle_id = ? AND task_id = ? AND task_version = ? AND item_id IS ?
            """,
                (handle_id, self.task_id, self.task_version, self.item_id),
            )
            .fetchone()
        )
        if row is None:
            raise SandboxPlotError(
                "SANDBOX_PLOT_NOT_FOUND",
                "The sandbox plot is missing or belongs to another task scope.",
            )
        handle = SandboxPlotHandle.model_validate_json(str(row[0]))
        if _datetime(handle.expires_at) <= self._clock():
            raise SandboxPlotError(
                "SANDBOX_PLOT_EXPIRED",
                "The sandbox plot has expired and must be rendered again.",
            )
        stored = self._documents.get(handle.document.plot_id, handle.document.plot_version)
        if stored.document != handle.document:
            raise SandboxPlotError(
                "SANDBOX_PLOT_CORRUPT",
                "The sandbox plot document differs from its immutable handle.",
            )
        readbacks = tuple(
            self._projected_readback(self._backend(backend).readback(handle.document))
            for backend in handle.backends
        )
        if readbacks != handle.readbacks or self._artifacts(handle.document, handle.backends) != (
            handle.artifacts
        ):
            raise SandboxPlotError(
                "SANDBOX_PLOT_CORRUPT",
                "Sandbox artifacts or native readback differ from the immutable handle.",
            )
        return handle

    def artifact_path(
        self,
        handle_id: SandboxPlotHandleId,
        artifact_id: SandboxArtifactId,
    ) -> Path:
        handle = self.get(handle_id)
        artifact = next(
            (item for item in handle.artifacts if item.artifact_id == artifact_id),
            None,
        )
        if artifact is None:
            raise SandboxPlotError(
                "SANDBOX_ARTIFACT_NOT_FOUND",
                "The sandbox artifact does not belong to this plot handle.",
            )
        path = self._artifact_path(handle.document, artifact.backend, artifact.format)
        if _file_hash(path) != artifact.content_hash:
            raise SandboxPlotError(
                "SANDBOX_PLOT_CORRUPT",
                "The sandbox artifact differs from its immutable receipt.",
            )
        return path

    def cleanup_expired(self) -> int:
        now = _iso(self._clock())
        connection = self._connection()
        row = connection.execute(
            "SELECT COUNT(*) FROM agent_sandbox_plot_handles_v2 WHERE expires_at <= ?",
            (now,),
        ).fetchone()
        count = 0 if row is None else int(row[0])
        if count:
            connection.execute(
                "DELETE FROM agent_sandbox_plot_handles_v2 WHERE expires_at <= ?",
                (now,),
            )
        return count

    def _find_existing(
        self,
        *,
        parent_handle_id: SandboxPlotHandleId | None,
        action_hash: str,
        backends: tuple[SandboxBackend, ...],
    ) -> SandboxPlotHandle | None:
        rows = self._connection().execute(
            """
            SELECT handle_json FROM agent_sandbox_plot_handles_v2
            WHERE task_id = ? AND task_version = ? AND item_id IS ?
            ORDER BY created_at DESC
            """,
            (self.task_id, self.task_version, self.item_id),
        )
        for row in rows:
            handle = SandboxPlotHandle.model_validate_json(str(row[0]))
            if (
                handle.parent_handle_id == parent_handle_id
                and handle.lineage[-1].action_hash == action_hash
                and handle.backends == backends
                and _datetime(handle.expires_at) > self._clock()
            ):
                return self.get(handle.handle_id)
        return None

    def _register_data_view(self, data_hash: str, view: EngineDataView) -> EngineDataRef:
        data = EngineDataRef(
            kind="prepared",
            dataset_id=f"staged:{data_hash[:24]}",
            version=1,
            content_hash=data_hash,
        )
        self._data_views.register(view.model_copy(update={"data": data}))
        return data

    def _runtime(self, backends: tuple[SandboxBackend, ...]) -> PlotEngineRuntime:
        return PlotEngineRuntime(
            self._service,
            self._data_views,
            tuple(self._backend(backend) for backend in backends),
        )

    def _backend(self, backend: SandboxBackend) -> PlotBackend:
        if backend == "matplotlib":
            return self._matplotlib
        if self._origin_install_dir is None:
            raise SandboxPlotError(
                "SANDBOX_ORIGIN_UNAVAILABLE",
                "Origin is not available to this task sandbox.",
            )
        return OriginBackend(
            self._origin_root,
            self._origin_install_dir,
            self._origin_worker,
        )

    def _persist(
        self,
        *,
        data_view_handle_id: DataViewHandleId,
        root_sources: tuple[EngineDataRef, ...],
        staged_data_hash: str,
        document: PlotDocument,
        backends: tuple[SandboxBackend, ...],
        readbacks: tuple[EngineReadback, ...],
        parent: SandboxPlotHandle | None,
        action_ids: tuple[str, ...],
        action_hash: str,
    ) -> SandboxPlotHandle:
        now = self._clock()
        artifacts = self._artifacts(document, backends)
        projected = tuple(self._projected_readback(item) for item in readbacks)
        terminal = SandboxPlotLineageStep(
            step_id=f"step:{canonical_hash(action_hash + document.plot_id)[:24]}",
            operation="preview_plot" if parent is None else "apply_plot_edits",
            input_handle_id=None if parent is None else parent.handle_id,
            action_ids=action_ids,
            action_hash=action_hash,
            output_document=document_ref(document),
            artifact_hashes=tuple(item.content_hash for item in artifacts),
        )
        handle_id: SandboxPlotHandleId = (
            "plotview:"
            + canonical_hash(
                cast(
                    JsonValue,
                    {
                        "task_id": self.task_id,
                        "task_version": self.task_version,
                        "item_id": self.item_id,
                        "parent": None if parent is None else parent.handle_id,
                        "document": document_ref(document).model_dump(mode="json"),
                        "backends": backends,
                        "action_hash": action_hash,
                    },
                )
            )[:32]
        )
        handle = SandboxPlotHandle(
            handle_id=handle_id,
            task_id=self.task_id,
            task_version=self.task_version,
            item_id=self.item_id,
            parent_handle_id=None if parent is None else parent.handle_id,
            data_view_handle_id=data_view_handle_id,
            root_sources=root_sources,
            staged_data_hash=staged_data_hash,
            document=document,
            backends=backends,
            readbacks=projected,
            artifacts=artifacts,
            lineage=(*(() if parent is None else parent.lineage), terminal),
            created_at=_iso(now),
            expires_at=_iso(now + timedelta(seconds=self._ttl_seconds)),
        )
        connection = self._connection()
        existing = connection.execute(
            "SELECT handle_json FROM agent_sandbox_plot_handles_v2 WHERE handle_id = ?",
            (handle_id,),
        ).fetchone()
        if existing is not None:
            restored = SandboxPlotHandle.model_validate_json(str(existing[0]))
            if restored.model_dump(exclude={"created_at", "expires_at"}) != handle.model_dump(
                exclude={"created_at", "expires_at"}
            ):
                raise SandboxPlotError(
                    "SANDBOX_HANDLE_IDEMPOTENCY_CONFLICT",
                    "A sandbox handle identity is already bound to another result.",
                )
            return self.get(restored.handle_id)
        connection.execute(
            """
            INSERT INTO agent_sandbox_plot_handles_v2(
                handle_id, task_id, task_version, item_id,
                handle_json, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                handle.handle_id,
                handle.task_id,
                handle.task_version,
                handle.item_id,
                canonical_json(handle),
                handle.created_at,
                handle.expires_at,
            ),
        )
        return handle

    @staticmethod
    def _projected_readback(readback: EngineReadback) -> SandboxPlotReadback:
        return SandboxPlotReadback(
            backend=readback.backend,
            document=readback.document,
            objects=tuple(
                SandboxPlotObject(
                    semantic_id=item.semantic_id,
                    object_kind=item.object_kind,
                )
                for item in readback.objects
            ),
            data_hash=readback.data_hash,
            style_hash=readback.style_hash,
        )

    def _artifacts(
        self,
        document: PlotDocument,
        backends: tuple[SandboxBackend, ...],
    ) -> tuple[SandboxPlotArtifact, ...]:
        result: list[SandboxPlotArtifact] = []
        for backend in backends:
            formats: tuple[Literal["png", "svg", "opju"], ...] = (
                ("png", "svg") if backend == "matplotlib" else ("opju",)
            )
            for format_name in formats:
                path = self._artifact_path(document, backend, format_name)
                if not path.is_file():
                    raise SandboxPlotError(
                        "SANDBOX_ARTIFACT_MISSING",
                        "The sandbox renderer did not create every required artifact.",
                        staged_side_effect=True,
                    )
                content_hash = _file_hash(path)
                artifact_identity = canonical_hash(
                    cast(JsonValue, (backend, format_name, content_hash))
                )
                result.append(
                    SandboxPlotArtifact(
                        artifact_id=f"artifact:{artifact_identity[:32]}",
                        backend=backend,
                        format=format_name,
                        content_hash=content_hash,
                        size=path.stat().st_size,
                    )
                )
        return tuple(result)

    def _artifact_path(
        self,
        document: PlotDocument,
        backend: SandboxBackend,
        format_name: str,
    ) -> Path:
        root = self._matplotlib_root if backend == "matplotlib" else self._origin_root
        version = root / document.plot_id.removeprefix("plot:") / f"v{document.plot_version}"
        filename = {"png": "preview.png", "svg": "preview.svg", "opju": "plot.opju"}[format_name]
        path = version / filename
        try:
            path.resolve().relative_to(self._root.resolve())
        except (OSError, ValueError) as error:
            raise SandboxPlotError(
                "SANDBOX_PLOT_CORRUPT",
                "A sandbox artifact escaped its task workspace.",
            ) from error
        return path

    def _connection(self) -> sqlite3.Connection:
        self._assert_open()
        return self._project._assert_writer()  # noqa: SLF001

    def _assert_open(self) -> None:
        if getattr(self, "_closed", False):
            raise SandboxPlotError("SANDBOX_WORKSPACE_CLOSED", "The sandbox workspace is closed.")
        if threading.get_ident() != self._writer_thread_id:
            raise SandboxPlotError(
                "SANDBOX_WORKSPACE_THREAD_INVALID",
                "The sandbox workspace has a different writer thread.",
            )

    def _assert_safe_root(self) -> None:
        try:
            relative = self._root.resolve().relative_to(self._parent_tmp_root)
        except (OSError, ValueError) as error:
            raise SandboxPlotError(
                "SANDBOX_WORKSPACE_PATH_INVALID",
                "The sandbox workspace escaped the parent project temp directory.",
            ) from error
        if len(relative.parts) != 2 or relative.parts[0] != "agent-plot-v2":
            raise SandboxPlotError(
                "SANDBOX_WORKSPACE_PATH_INVALID",
                "The sandbox workspace path does not match its fixed scope.",
            )
