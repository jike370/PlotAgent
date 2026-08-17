"""Single-writer per-project SQLite metadata and immutable object storage."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from contextlib import closing, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel

from plotagent.contracts.datasets import SourceDataset
from plotagent.storage.errors import StorageErrorCode, StorageProblem
from plotagent.storage.models import (
    DatasetRegistration,
    ImportCommitResult,
    SourceDatasetRecord,
    StagedObject,
)
from plotagent.storage.schema import (
    PROJECT_SCHEMA_VERSION,
    initialize_project_schema,
    migrate_project_schema,
    validate_schema,
)
from plotagent.storage.workspace import ensure_local_fixed_workspace

type FaultInjector = Callable[[str], None]
type ImportResponseFactory = Callable[[ImportCommitResult, int], dict[str, Any]]

_LOCK_RECOVERY_GRACE_SECONDS = 2.0
_LOCK_RECOVERY_RETRIES = 10


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _json(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _lock_owner_pid(path: Path) -> int | None:
    try:
        encoded = path.read_text(encoding="ascii").strip()
    except OSError:
        return None
    if encoded.isdecimal():
        return int(encoded)
    try:
        value = json.loads(encoded)
    except (TypeError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    pid = value.get("pid")
    return pid if isinstance(pid, int) and pid > 0 else None


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # ``os.kill(pid, 0)`` is not a safe existence probe on Windows. Querying the
        # process handle is read-only and works for the same-user desktop Core.
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        error_invalid_parameter = 87
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return ctypes.get_last_error() != error_invalid_parameter
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _recover_stale_lock(lock_path: Path) -> bool:
    """Remove a crash-left lock while serializing competing recovery attempts."""

    recovery_path = lock_path.with_name(lock_path.name + ".recovery")
    recovery_fd: int | None = None
    for _attempt in range(_LOCK_RECOVERY_RETRIES):
        try:
            recovery_fd = os.open(recovery_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(recovery_fd, str(os.getpid()).encode("ascii"))
            os.fsync(recovery_fd)
            break
        except FileExistsError:
            recovery_owner = _lock_owner_pid(recovery_path)
            if recovery_owner is not None and not _pid_is_running(recovery_owner):
                with suppress(OSError):
                    recovery_path.unlink()
                continue
            time.sleep(0.02)
    if recovery_fd is None:
        return False
    try:
        if not lock_path.exists():
            return True
        owner = _lock_owner_pid(lock_path)
        if owner is not None:
            if _pid_is_running(owner):
                return False
        else:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                return True
            if age < _LOCK_RECOVERY_GRACE_SECONDS:
                return False
        with suppress(OSError):
            lock_path.unlink()
        return not lock_path.exists()
    finally:
        os.close(recovery_fd)
        with suppress(OSError):
            recovery_path.unlink()


def read_project_revision(workspace: str | Path) -> int:
    """Read one project revision without taking its single-writer lock."""

    resolved = ensure_local_fixed_workspace(Path(workspace))
    database_path = resolved / "project.sqlite3"
    if not database_path.is_file():
        raise StorageProblem(StorageErrorCode.PROJECT_NOT_FOUND, "项目数据不存在。")
    uri = database_path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        row = connection.execute("SELECT revision FROM project_meta LIMIT 1").fetchone()
    if row is None:
        raise StorageProblem(StorageErrorCode.PROJECT_NOT_FOUND, "项目版本信息不存在。")
    revision = int(row[0])
    if revision < 0:
        raise StorageProblem(StorageErrorCode.PROJECT_NOT_FOUND, "项目版本信息无效。")
    return revision


def _source_dataset_record(row: tuple[object, ...]) -> SourceDatasetRecord:
    contract_json, logical_id, recipe_id, created_at, metadata_json = row
    try:
        metadata = json.loads(str(metadata_json))
    except (TypeError, ValueError):
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}

    def identity(key: str) -> str | None:
        value = metadata.get(key)
        return value if isinstance(value, str) and value else None

    return SourceDatasetRecord(
        source_dataset=SourceDataset.model_validate_json(str(contract_json)),
        logical_source_id=str(logical_id),
        import_recipe_id=str(recipe_id),
        created_at=str(created_at),
        display_name=identity("__plotagent_display_name"),
        source_file_name=identity("__plotagent_source_file_name"),
        sheet_name=identity("__plotagent_sheet_name"),
        source_block=identity("__plotagent_source_block"),
        instrument_metadata={
            str(key): str(value)
            for key, value in metadata.items()
            if not str(key).startswith("__plotagent_")
            and isinstance(value, (str, int, float, bool))
        },
    )


class ProjectStore:
    """The only API allowed to mutate one active project workspace."""

    def __init__(self, workspace: Path, *, initialize: bool, project_id: str | None) -> None:
        self.workspace = ensure_local_fixed_workspace(workspace)
        self.database_path = self.workspace / "project.sqlite3"
        self.objects_root = self.workspace / "objects" / "sha256"
        self.cache_root = self.workspace / "cache"
        self.tmp_root = self.workspace / "tmp"
        self.lock_path = self.workspace / "project.lock"
        self._writer_thread_id = threading.get_ident()
        self._closed = False
        self._lock_fd: int | None = None
        self._lock_payload: str | None = None
        self._connection: sqlite3.Connection | None = None

        for attempt in range(2):
            try:
                self._lock_fd = os.open(
                    self.lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                self._lock_payload = json.dumps(
                    {"pid": os.getpid(), "token": uuid.uuid4().hex},
                    separators=(",", ":"),
                    sort_keys=True,
                )
                os.write(self._lock_fd, self._lock_payload.encode("ascii"))
                os.fsync(self._lock_fd)
                break
            except FileExistsError as exc:
                if attempt == 0 and _recover_stale_lock(self.lock_path):
                    continue
                raise StorageProblem(
                    StorageErrorCode.PROJECT_ALREADY_OPEN,
                    "项目工作区已有写入器。",
                ) from exc

        try:
            self._connection = sqlite3.connect(
                self.database_path,
                isolation_level=None,
                check_same_thread=True,
            )
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA synchronous = FULL")
            self._connection.execute("PRAGMA busy_timeout = 5000")
            journal_mode = self._connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if str(journal_mode).casefold() != "wal":
                raise sqlite3.DatabaseError("WAL mode was not activated")
            if initialize:
                if project_id is None:
                    raise ValueError("project_id is required when initializing")
                initialize_project_schema(self._connection, project_id, _utc_now())
            else:
                migrate_project_schema(self._connection)
                validate_schema(
                    self._connection,
                    PROJECT_SCHEMA_VERSION,
                    "plotagent-project",
                )
            self.project_id = str(
                self._connection.execute("SELECT project_id FROM project_meta").fetchone()[0]
            )
        except Exception:
            self.close()
            raise

    @classmethod
    def create(cls, workspace: str | Path, *, project_id: str | None = None) -> Self:
        root = ensure_local_fixed_workspace(Path(workspace))
        if root.exists():
            raise StorageProblem(
                StorageErrorCode.PROJECT_ALREADY_EXISTS,
                "项目工作区已经存在。",
            )
        root.mkdir(parents=True)
        (root / "objects" / "sha256").mkdir(parents=True)
        (root / "cache").mkdir()
        (root / "tmp").mkdir()
        identifier = project_id or "project:" + uuid.uuid4().hex
        try:
            return cls(root, initialize=True, project_id=identifier)
        except Exception:
            shutil.rmtree(root, ignore_errors=True)
            raise

    @classmethod
    def open(cls, workspace: str | Path) -> Self:
        root = ensure_local_fixed_workspace(Path(workspace))
        if not (root / "project.sqlite3").is_file():
            raise StorageProblem(
                StorageErrorCode.PROJECT_NOT_FOUND,
                "项目工作区不存在。",
            )
        return cls(root, initialize=False, project_id=None)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _assert_writer(self) -> sqlite3.Connection:
        if self._closed or self._connection is None:
            raise StorageProblem(StorageErrorCode.PROJECT_CLOSED, "项目已经关闭。")
        if threading.get_ident() != self._writer_thread_id:
            raise StorageProblem(
                StorageErrorCode.PROJECT_WRITER_THREAD,
                "项目写入只能在创建 ProjectStore 的单一线程执行。",
            )
        return self._connection

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None
        if self._lock_payload is not None:
            try:
                owns_lock = self.lock_path.read_text(encoding="ascii") == self._lock_payload
            except OSError:
                owns_lock = False
            if owns_lock:
                with suppress(OSError):
                    self.lock_path.unlink(missing_ok=True)
            self._lock_payload = None

    def journal_mode(self) -> str:
        return str(self._assert_writer().execute("PRAGMA journal_mode").fetchone()[0])

    def backup_database(self, destination: Path) -> None:
        """Create a consistent package snapshot with SQLite Online Backup."""

        source = self._assert_writer()
        if destination.exists():
            raise FileExistsError(destination)
        with closing(sqlite3.connect(destination)) as target:
            source.backup(target)
            target.execute("PRAGMA journal_mode = DELETE")
            result = target.execute("PRAGMA quick_check").fetchone()
            if result is None or str(result[0]) != "ok":
                raise sqlite3.DatabaseError("SQLite snapshot integrity check failed")

    def _new_task_dir(self) -> Path:
        self._assert_writer()
        task_dir = self.tmp_root / uuid.uuid4().hex
        task_dir.mkdir()
        return task_dir

    def stage_source(self, source_path: Path) -> StagedObject:
        """Copy an authorized source into isolated project temp while hashing it."""

        self._assert_writer()
        task_dir = self._new_task_dir()
        destination = task_dir / source_path.name
        digest = hashlib.sha256()
        size = 0
        try:
            with source_path.open("rb") as source, destination.open("xb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                target.flush()
                os.fsync(target.fileno())
        except Exception:
            self.cleanup_staged_task(task_dir)
            raise
        return StagedObject(
            token=uuid.uuid4().hex,
            path=destination,
            content_hash=digest.hexdigest(),
            size=size,
            media_type="application/octet-stream",
            task_dir=task_dir,
        )

    def stage_bytes(
        self,
        data: bytes,
        *,
        media_type: str,
        task_dir: Path | None = None,
    ) -> StagedObject:
        self._assert_writer()
        parent = task_dir or self._new_task_dir()
        resolved_parent = parent.resolve()
        resolved_tmp = self.tmp_root.resolve()
        if resolved_parent.parent != resolved_tmp and resolved_parent != resolved_tmp:
            raise StorageProblem(
                StorageErrorCode.STAGED_OBJECT_INVALID,
                "暂存对象不在项目 temp 中。",
            )
        token = uuid.uuid4().hex
        path = parent / f"{token}.staged"
        with path.open("xb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        return StagedObject(
            token=token,
            path=path,
            content_hash=hashlib.sha256(data).hexdigest(),
            size=len(data),
            media_type=media_type,
            task_dir=parent,
        )

    def cleanup_staged_task(self, task_dir: Path) -> None:
        try:
            resolved = task_dir.resolve()
            if resolved.parent == self.tmp_root.resolve():
                shutil.rmtree(resolved, ignore_errors=True)
        except OSError:
            pass

    def object_path(self, content_hash: str) -> Path:
        return self.objects_root / content_hash[:2] / content_hash

    def stable_source_dataset_id(self, logical_source_id: str) -> str:
        digest = hashlib.sha256(f"{self.project_id}\0{logical_source_id}".encode()).hexdigest()
        return "source:" + digest[:24]

    def next_source_version(self, logical_source_id: str) -> int:
        row = (
            self._assert_writer()
            .execute(
                """
            SELECT COALESCE(MAX(source_version), 0) + 1
            FROM source_dataset_versions
            WHERE logical_source_id = ?
            """,
                (logical_source_id,),
            )
            .fetchone()
        )
        return int(row[0])

    def _validate_staged(self, staged: StagedObject) -> None:
        try:
            relative = staged.path.resolve().relative_to(self.tmp_root.resolve())
        except (OSError, ValueError) as exc:
            raise StorageProblem(
                StorageErrorCode.STAGED_OBJECT_INVALID,
                "暂存对象不在项目 temp 中。",
            ) from exc
        if not relative.parts or not staged.path.is_file():
            raise StorageProblem(
                StorageErrorCode.STAGED_OBJECT_INVALID,
                "暂存对象不存在。",
            )
        actual_hash, actual_size = _hash_file(staged.path)
        if actual_hash != staged.content_hash or actual_size != staged.size:
            raise StorageProblem(
                StorageErrorCode.STAGED_OBJECT_INVALID,
                "暂存对象哈希或大小与登记值不一致。",
            )

    def _promote(self, staged: StagedObject) -> tuple[Path, bool]:
        self._validate_staged(staged)
        destination = self.object_path(staged.content_hash)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            actual_hash, actual_size = _hash_file(destination)
            if actual_hash != staged.content_hash or actual_size != staged.size:
                raise StorageProblem(
                    StorageErrorCode.STAGED_OBJECT_INVALID,
                    "CAS 中已有对象与内容哈希不一致。",
                )
            return destination, False
        os.replace(staged.path, destination)
        return destination, True

    def commit_import(
        self,
        *,
        resource_id: str,
        source_object: StagedObject,
        registrations: Iterable[DatasetRegistration],
        fault_injector: FaultInjector | None = None,
        expected_revision: int | None = None,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
        response_factory: ImportResponseFactory | None = None,
    ) -> ImportCommitResult:
        """Promote immutable objects and register every dataset in one SQLite transaction."""

        connection = self._assert_writer()
        items = tuple(registrations)
        if not items:
            raise StorageProblem(StorageErrorCode.COMMIT_FAILED, "没有可提交的数据集。")
        if any(
            item.source_dataset.source_object_hash != source_object.content_hash for item in items
        ):
            raise StorageProblem(
                StorageErrorCode.SOURCE_OBJECT_MISSING,
                "SourceDataset 未绑定当前暂存源对象。",
            )

        staged_objects = (source_object,) + tuple(item.table_object for item in items)
        promoted: dict[str, tuple[Path, bool, StagedObject]] = {}
        created_paths: list[Path] = []
        session_id = "import:" + uuid.uuid4().hex
        now = _utc_now()
        records: list[SourceDatasetRecord] = []
        try:
            for staged in staged_objects:
                if staged.content_hash in promoted:
                    self._validate_staged(staged)
                    continue
                path, created = self._promote(staged)
                promoted[staged.content_hash] = (path, created, staged)
                if created:
                    created_paths.append(path)
            if fault_injector:
                fault_injector("after_promote")

            connection.execute("BEGIN IMMEDIATE")
            if expected_revision is not None:
                row = connection.execute("SELECT revision FROM project_meta").fetchone()
                if row is None or int(row[0]) != expected_revision:
                    raise StorageProblem(
                        StorageErrorCode.VERSION_CONFLICT,
                        "The project changed after the import request was created.",
                    )
            for _path, _created, staged in promoted.values():
                connection.execute(
                    """
                    INSERT INTO objects(content_hash, media_type, size, ref_count, created_at)
                    VALUES (?, ?, ?, 0, ?)
                    ON CONFLICT(content_hash) DO NOTHING
                    """,
                    (staged.content_hash, staged.media_type, staged.size, now),
                )
                stored = connection.execute(
                    "SELECT size FROM objects WHERE content_hash = ?",
                    (staged.content_hash,),
                ).fetchone()
                if stored is None or int(stored[0]) != staged.size:
                    raise StorageProblem(
                        StorageErrorCode.STAGED_OBJECT_INVALID,
                        "对象登记与 CAS 内容不一致。",
                    )
            if fault_injector:
                fault_injector("after_object_rows")

            connection.execute(
                """
                INSERT INTO import_sessions(session_id, resource_id, dataset_count, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, resource_id, len(items), now),
            )
            for item in items:
                recipe_json = _json(item.artifact.recipe)
                recipe_hash = hashlib.sha256(recipe_json.encode("utf-8")).hexdigest()
                recipe_id = "recipe:" + recipe_hash[:24]
                connection.execute(
                    """
                    INSERT INTO import_recipes(
                        import_recipe_id, recipe_hash, recipe_json, created_at
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(recipe_hash) DO NOTHING
                    """,
                    (recipe_id, recipe_hash, recipe_json, now),
                )
                dataset = item.source_dataset
                dataset_identity = {
                    "__plotagent_display_name": item.artifact.display_name,
                    "__plotagent_source_file_name": source_object.path.name,
                    **(
                        {"__plotagent_sheet_name": item.artifact.recipe.sheet}
                        if item.artifact.recipe.sheet is not None
                        else {}
                    ),
                    **(
                        {"__plotagent_source_block": item.artifact.recipe.block}
                        if item.artifact.recipe.block is not None
                        else {}
                    ),
                }
                connection.execute(
                    """
                    INSERT INTO source_dataset_versions(
                        source_dataset_id, source_version, logical_source_id,
                        source_object_hash, table_object_hash, import_recipe_id,
                        contract_json, metadata_json, provenance_json, session_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dataset.source_dataset_id,
                        dataset.source_version,
                        item.logical_source_id,
                        source_object.content_hash,
                        item.table_object.content_hash,
                        recipe_id,
                        _json(dataset),
                        _json({**item.artifact.instrument_metadata, **dataset_identity}),
                        _json(
                            [value.model_dump(mode="json") for value in item.artifact.provenance]
                        ),
                        session_id,
                        now,
                    ),
                )
                owner_id = f"{dataset.source_dataset_id}@{dataset.source_version}"
                for role, content_hash in (
                    ("source", source_object.content_hash),
                    ("table", item.table_object.content_hash),
                ):
                    connection.execute(
                        """
                        INSERT INTO object_refs(owner_type, owner_id, role, content_hash)
                        VALUES ('source_dataset', ?, ?, ?)
                        """,
                        (owner_id, role, content_hash),
                    )
                    connection.execute(
                        "UPDATE objects SET ref_count = ref_count + 1 WHERE content_hash = ?",
                        (content_hash,),
                    )
                records.append(
                    SourceDatasetRecord(
                        source_dataset=dataset,
                        logical_source_id=item.logical_source_id,
                        import_recipe_id=recipe_id,
                        created_at=now,
                        display_name=item.artifact.display_name,
                        source_file_name=source_object.path.name,
                        sheet_name=item.artifact.recipe.sheet,
                        source_block=item.artifact.recipe.block,
                        instrument_metadata=item.artifact.instrument_metadata,
                    )
                )
            if fault_injector:
                fault_injector("after_dataset_rows")
                fault_injector("before_commit")
            result = ImportCommitResult(
                session_id=session_id,
                datasets=tuple(records),
            )
            idempotency_values = (
                idempotency_key,
                request_hash,
                response_factory,
            )
            if any(value is not None for value in idempotency_values):
                if (
                    expected_revision is None
                    or idempotency_key is None
                    or request_hash is None
                    or response_factory is None
                ):
                    raise ValueError("incomplete import idempotency arguments")
                cursor = connection.execute(
                    "UPDATE project_meta SET revision = revision + 1 WHERE revision = ?",
                    (expected_revision,),
                )
                if cursor.rowcount != 1:
                    raise StorageProblem(
                        StorageErrorCode.VERSION_CONFLICT,
                        "The project changed during import commit.",
                    )
                response = response_factory(result, expected_revision + 1)
                connection.execute(
                    """
                    INSERT INTO idempotency_records(
                        operation, idempotency_key, request_hash, response_json, created_at
                    ) VALUES ('datasets.import', ?, ?, ?, ?)
                    """,
                    (idempotency_key, request_hash, _json(response), now),
                )
            connection.commit()
        except Exception as exc:
            if connection.in_transaction:
                connection.rollback()
            for path in created_paths:
                try:
                    path.unlink(missing_ok=True)
                    path.parent.rmdir()
                except OSError:
                    pass
            for staged in staged_objects:
                self.cleanup_staged_task(staged.task_dir)
            if isinstance(exc, StorageProblem):
                raise
            raise StorageProblem(
                StorageErrorCode.COMMIT_FAILED,
                "导入提交失败；正式项目状态保持不变。",
            ) from exc

        for staged in staged_objects:
            self.cleanup_staged_task(staged.task_dir)
        return result

    def list_source_datasets(
        self, logical_source_id: str | None = None
    ) -> tuple[SourceDatasetRecord, ...]:
        connection = self._assert_writer()
        sql = """
            SELECT contract_json, logical_source_id, import_recipe_id, created_at, metadata_json
            FROM source_dataset_versions
        """
        parameters: tuple[str, ...] = ()
        if logical_source_id is not None:
            sql += " WHERE logical_source_id = ?"
            parameters = (logical_source_id,)
        sql += " ORDER BY logical_source_id, source_version"
        return tuple(_source_dataset_record(row) for row in connection.execute(sql, parameters))

    def state_counts(self) -> dict[str, int]:
        connection = self._assert_writer()
        tables = (
            "objects",
            "object_refs",
            "import_recipes",
            "import_sessions",
            "source_dataset_versions",
        )
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }

    def object_hashes(self) -> tuple[str, ...]:
        return tuple(
            str(row[0])
            for row in self._assert_writer().execute(
                "SELECT content_hash FROM objects ORDER BY content_hash"
            )
        )

    def verify_registered_objects(self) -> bool:
        for content_hash in self.object_hashes():
            path = self.object_path(content_hash)
            if not path.is_file() or _hash_file(path)[0] != content_hash:
                return False
        return True
