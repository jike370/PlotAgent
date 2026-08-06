"""Default-deny schema compatibility and exact-pair one-time migrations."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
from collections.abc import Callable, Iterable
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from plotagent.security.errors import LocalSecurityError
from plotagent.security.temp_workspace import (
    PrivateTempWorkspaceManager,
    TaskWorkspace,
)


class MigrationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MigrationPhase(StrEnum):
    COPY = "copy"
    MIGRATE = "migrate"
    VALIDATE = "validate"
    SWITCH = "switch"


class MigrationCancelled(Exception):
    """Raised by an injected checkpoint or known migration at a safe cancel boundary."""


@dataclass(frozen=True, slots=True)
class SemanticFingerprint:
    """All invariants that a storage-only migration must preserve."""

    science_hash: str
    visual_hash: str
    object_hashes: tuple[str, ...]
    object_count: int
    reference_hash: str
    row_count: int
    column_count: int
    version_dag_hash: str
    current_pointer_hash: str


class MigrationValidator(Protocol):
    def validate(self, project: Path) -> None: ...

    def fingerprint(self, project: Path) -> SemanticFingerprint: ...


class ProjectSnapshotter(Protocol):
    def snapshot(self, source_project: Path, destination_project: Path) -> None: ...


class MigrationWorkspaceProvider(Protocol):
    def create(self) -> TaskWorkspace: ...

    def cleanup(self, workspace: TaskWorkspace) -> bool: ...


class DirectoryPublisher(Protocol):
    def publish(self, staged_project: Path, target_project: Path) -> None: ...


class FaultCheckpoint(Protocol):
    def __call__(self, phase: MigrationPhase) -> None: ...


@dataclass(frozen=True, slots=True)
class KnownMigration:
    source_schema_version: str
    target_schema_version: str
    implementation_version: str
    migrate: Callable[[Path], None]

    def __post_init__(self) -> None:
        if self.source_schema_version == self.target_schema_version:
            raise ValueError("migration versions must differ")
        if not all(
            value and not any(character.isspace() for character in value)
            for value in (
                self.source_schema_version,
                self.target_schema_version,
                self.implementation_version,
            )
        ):
            raise ValueError("migration versions must be stable non-empty tokens")


class KnownMigrationRegistry:
    """An exact-pair allowlist; it never searches or chains migration steps."""

    def __init__(self, migrations: Iterable[KnownMigration] = ()) -> None:
        self._entries: dict[tuple[str, str], KnownMigration] = {}
        for migration in migrations:
            key = (migration.source_schema_version, migration.target_schema_version)
            if key in self._entries:
                raise ValueError("duplicate known migration pair")
            self._entries[key] = migration

    def resolve(self, source_version: str, target_version: str) -> KnownMigration:
        try:
            return self._entries[(source_version, target_version)]
        except KeyError as error:
            raise LocalSecurityError(
                "KNOWN_MIGRATION_PAIR_UNAVAILABLE", category="migration_pair"
            ) from error


class SchemaCompatibilityGate:
    def __init__(
        self,
        supported_versions: Iterable[str],
        registry: KnownMigrationRegistry | None = None,
    ) -> None:
        self._supported = frozenset(supported_versions)
        if not self._supported:
            raise ValueError("at least one supported schema is required")
        self._registry = registry or KnownMigrationRegistry()

    def require_supported(self, schema_version: str) -> None:
        if schema_version not in self._supported:
            raise LocalSecurityError("SCHEMA_VERSION_UNSUPPORTED", category="schema_version")

    def require_known_pair(self, source_version: str, target_version: str) -> KnownMigration:
        return self._registry.resolve(source_version, target_version)

    @staticmethod
    def require_legacy_component(*, available: bool) -> None:
        if not available:
            raise LocalSecurityError("LEGACY_COMPONENT_MISSING", category="legacy_component")


@dataclass(frozen=True, slots=True)
class KnownVersionMigrationRecord:
    source_schema_version: str
    target_schema_version: str
    migration_implementation_version: str
    source_snapshot_hash: str
    validation_hash: str
    status: MigrationStatus
    started_at: str
    completed_at: str


class KnownMigrationError(LocalSecurityError):
    def __init__(
        self,
        code: str,
        *,
        category: str,
        record: KnownVersionMigrationRecord,
    ) -> None:
        super().__init__(code, category=category)
        self.record = record


class ManagedMigrationWorkspaceProvider:
    """Adapt the private temp manager without exposing its paths to records/errors."""

    def __init__(self, manager: PrivateTempWorkspaceManager) -> None:
        self._manager = manager

    def create(self) -> TaskWorkspace:
        return self._manager.create()

    def cleanup(self, workspace: TaskWorkspace) -> bool:
        return self._manager.cleanup(workspace).cleaned


class SQLiteProjectSnapshotter:
    """Copy immutable project files and use SQLite Online Backup for the active DB."""

    _SKIP_NAMES = frozenset({"tmp", "cache", "project.lock"})
    _DB_NAME = "project.sqlite3"

    def snapshot(self, source_project: Path, destination_project: Path) -> None:
        if destination_project.exists():
            raise FileExistsError(destination_project)
        destination_project.mkdir(mode=0o700)
        for source in source_project.iterdir():
            if source.name in self._SKIP_NAMES or source.name in {
                self._DB_NAME,
                f"{self._DB_NAME}-wal",
                f"{self._DB_NAME}-shm",
            }:
                continue
            self._copy_entry(source, destination_project / source.name)

        source_database = source_project / self._DB_NAME
        destination_database = destination_project / self._DB_NAME
        if not source_database.is_file() or source_database.is_symlink():
            raise OSError("project database is unavailable")
        source_uri = f"{source_database.resolve().as_uri()}?mode=ro"
        with (
            closing(sqlite3.connect(source_uri, uri=True)) as source_connection,
            closing(sqlite3.connect(destination_database)) as destination_connection,
        ):
            source_connection.backup(destination_connection)
            result = destination_connection.execute("PRAGMA quick_check").fetchone()
            if result is None or result[0] != "ok":
                raise OSError("SQLite snapshot integrity check failed")

    def _copy_entry(self, source: Path, destination: Path) -> None:
        metadata = source.lstat()
        file_attributes = getattr(metadata, "st_file_attributes", 0)
        reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if source.is_symlink() or file_attributes & reparse_attribute:
            raise OSError("linked project entry rejected")
        if stat.S_ISDIR(metadata.st_mode):
            destination.mkdir(mode=0o700)
            for child in source.iterdir():
                self._copy_entry(child, destination / child.name)
        elif stat.S_ISREG(metadata.st_mode):
            shutil.copyfile(source, destination)
        else:
            raise OSError("special project entry rejected")


class AtomicDirectoryPublisher:
    """Publish a new work copy atomically; an existing target is never overwritten."""

    def publish(self, staged_project: Path, target_project: Path) -> None:
        if target_project.exists():
            raise FileExistsError(target_project)
        if staged_project.anchor.lower() != target_project.anchor.lower():
            raise OSError("migration target must use the staging filesystem")
        os.replace(staged_project, target_project)


class KnownMigrationRunner:
    def __init__(
        self,
        registry: KnownMigrationRegistry,
        *,
        workspace_provider: MigrationWorkspaceProvider,
        validator: MigrationValidator,
        snapshotter: ProjectSnapshotter | None = None,
        publisher: DirectoryPublisher | None = None,
        checkpoint: FaultCheckpoint | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._registry = registry
        self._workspace_provider = workspace_provider
        self._validator = validator
        self._snapshotter = snapshotter or SQLiteProjectSnapshotter()
        self._publisher = publisher or AtomicDirectoryPublisher()
        self._checkpoint = checkpoint or (lambda phase: None)
        self._now = now or (lambda: datetime.now(UTC))

    def migrate(
        self,
        source_project: Path,
        target_project: Path,
        *,
        source_version: str,
        target_version: str,
    ) -> KnownVersionMigrationRecord:
        migration = self._registry.resolve(source_version, target_version)
        actual_source_version = read_schema_version(source_project)
        if actual_source_version != source_version:
            raise LocalSecurityError("SCHEMA_VERSION_UNSUPPORTED", category="schema_version")
        if target_project.exists():
            raise LocalSecurityError("MIGRATION_FAILED", category="migration_switch")

        started_at = _timestamp(self._now())
        workspace = self._workspace_provider.create()
        staged_project = workspace.path / "project"
        source_snapshot_hash = ""
        validation_hash = ""
        phase = MigrationPhase.COPY
        try:
            self._checkpoint(phase)
            self._snapshotter.snapshot(source_project, staged_project)
            if read_schema_version(staged_project) != source_version:
                raise _ValidationFailure
            source_snapshot_hash = _tree_hash(staged_project)
            source_fingerprint = self._validator.fingerprint(staged_project)

            phase = MigrationPhase.MIGRATE
            self._checkpoint(phase)
            migration.migrate(staged_project)

            phase = MigrationPhase.VALIDATE
            self._checkpoint(phase)
            if read_schema_version(staged_project) != target_version:
                raise _ValidationFailure
            self._validator.validate(staged_project)
            target_fingerprint = self._validator.fingerprint(staged_project)
            if target_fingerprint != source_fingerprint:
                raise _ValidationFailure
            validation_hash = _fingerprint_hash(target_fingerprint)

            phase = MigrationPhase.SWITCH
            self._checkpoint(phase)
            self._publisher.publish(staged_project, target_project)
            return KnownVersionMigrationRecord(
                source_schema_version=source_version,
                target_schema_version=target_version,
                migration_implementation_version=migration.implementation_version,
                source_snapshot_hash=source_snapshot_hash,
                validation_hash=validation_hash,
                status=MigrationStatus.SUCCEEDED,
                started_at=started_at,
                completed_at=_timestamp(self._now()),
            )
        except MigrationCancelled as error:
            raise self._error(
                "MIGRATION_CANCELLED",
                "migration_execute",
                migration,
                source_snapshot_hash,
                validation_hash,
                MigrationStatus.CANCELLED,
                started_at,
            ) from error
        except _ValidationFailure as error:
            raise self._error(
                "MIGRATION_VALIDATION_FAILED",
                "migration_validate",
                migration,
                source_snapshot_hash,
                validation_hash,
                MigrationStatus.FAILED,
                started_at,
            ) from error
        except KnownMigrationError:
            raise
        except Exception as error:
            category = {
                MigrationPhase.COPY: "migration_copy",
                MigrationPhase.MIGRATE: "migration_execute",
                MigrationPhase.VALIDATE: "migration_validate",
                MigrationPhase.SWITCH: "migration_switch",
            }[phase]
            code = (
                "MIGRATION_VALIDATION_FAILED"
                if phase is MigrationPhase.VALIDATE
                else "MIGRATION_FAILED"
            )
            raise self._error(
                code,
                category,
                migration,
                source_snapshot_hash,
                validation_hash,
                MigrationStatus.FAILED,
                started_at,
            ) from error
        finally:
            self._workspace_provider.cleanup(workspace)

    def _error(
        self,
        code: str,
        category: str,
        migration: KnownMigration,
        source_snapshot_hash: str,
        validation_hash: str,
        status: MigrationStatus,
        started_at: str,
    ) -> KnownMigrationError:
        return KnownMigrationError(
            code,
            category=category,
            record=KnownVersionMigrationRecord(
                source_schema_version=migration.source_schema_version,
                target_schema_version=migration.target_schema_version,
                migration_implementation_version=migration.implementation_version,
                source_snapshot_hash=source_snapshot_hash,
                validation_hash=validation_hash,
                status=status,
                started_at=started_at,
                completed_at=_timestamp(self._now()),
            ),
        )


class _ValidationFailure(Exception):
    pass


def read_schema_version(project: Path) -> str:
    manifest_path = project / "manifest.json"
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LocalSecurityError("SCHEMA_VERSION_UNSUPPORTED", category="schema_version") from error
    if not isinstance(raw, dict):
        raise LocalSecurityError("SCHEMA_VERSION_UNSUPPORTED", category="schema_version")
    schema_version = raw.get("schema_version")
    if not isinstance(schema_version, str):
        raise LocalSecurityError("SCHEMA_VERSION_UNSUPPORTED", category="schema_version")
    return schema_version


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise OSError("unsupported snapshot entry")
        digest.update(b"D" if path.is_dir() else b"F")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        if path.is_file():
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
    return digest.hexdigest()


def _fingerprint_hash(fingerprint: SemanticFingerprint) -> str:
    encoded = json.dumps(
        asdict(fingerprint), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
