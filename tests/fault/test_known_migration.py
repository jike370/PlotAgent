from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from plotagent.compatibility import (
    KnownMigration,
    KnownMigrationError,
    KnownMigrationRegistry,
    KnownMigrationRunner,
    ManagedMigrationWorkspaceProvider,
    MigrationCancelled,
    MigrationPhase,
    MigrationStatus,
    SchemaCompatibilityGate,
    SemanticFingerprint,
)
from plotagent.security import LocalSecurityError, PrivateTempWorkspaceManager


class AllowPrivatePermissions:
    def make_private(self, path: Path) -> None:
        assert path.is_dir()


class InvariantValidator:
    def validate(self, project: Path) -> None:
        with closing(sqlite3.connect(project / "project.sqlite3")) as connection:
            assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
            assert connection.execute("SELECT COUNT(*) FROM records").fetchone() == (2,)
        assert (project / "objects" / "sha256" / ("b" * 64)).read_bytes() == b"object"

    def fingerprint(self, project: Path) -> SemanticFingerprint:
        raw = json.loads((project / "invariants.json").read_text(encoding="utf-8"))
        return SemanticFingerprint(
            science_hash=raw["science_hash"],
            visual_hash=raw["visual_hash"],
            object_hashes=tuple(raw["object_hashes"]),
            object_count=raw["object_count"],
            reference_hash=raw["reference_hash"],
            row_count=raw["row_count"],
            column_count=raw["column_count"],
            version_dag_hash=raw["version_dag_hash"],
            current_pointer_hash=raw["current_pointer_hash"],
        )


def _create_source(root: Path) -> tuple[Path, sqlite3.Connection]:
    project = root / "source"
    (project / "objects" / "sha256").mkdir(parents=True)
    (project / "manifest.json").write_text(
        json.dumps({"schema_version": "beta-1", "project_id": "project-1"}),
        encoding="utf-8",
    )
    invariants = {
        "science_hash": "1" * 64,
        "visual_hash": "2" * 64,
        "object_hashes": ["b" * 64],
        "object_count": 1,
        "reference_hash": "3" * 64,
        "row_count": 2,
        "column_count": 1,
        "version_dag_hash": "4" * 64,
        "current_pointer_hash": "5" * 64,
    }
    (project / "invariants.json").write_text(json.dumps(invariants), encoding="utf-8")
    (project / "objects" / "sha256" / ("b" * 64)).write_bytes(b"object")
    writer = sqlite3.connect(project / "project.sqlite3")
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute("CREATE TABLE records (value INTEGER NOT NULL)")
    writer.executemany("INSERT INTO records VALUES (?)", [(1,), (2,)])
    writer.commit()
    return project, writer


def _storage_only_migration(project: Path) -> None:
    manifest_path = project / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "beta-2"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with closing(sqlite3.connect(project / "project.sqlite3")) as connection:
        connection.execute("ALTER TABLE records ADD COLUMN storage_note TEXT DEFAULT ''")
        connection.commit()


def _registry(migrate: object = _storage_only_migration) -> KnownMigrationRegistry:
    assert callable(migrate)
    return KnownMigrationRegistry([KnownMigration("beta-1", "beta-2", "one-time-1", migrate)])


def _runner(
    tmp_path: Path,
    registry: KnownMigrationRegistry,
    *,
    checkpoint: object | None = None,
) -> KnownMigrationRunner:
    manager = PrivateTempWorkspaceManager(
        tmp_path / "migration-temp", permission_enforcer=AllowPrivatePermissions()
    )
    assert checkpoint is None or callable(checkpoint)
    return KnownMigrationRunner(
        registry,
        workspace_provider=ManagedMigrationWorkspaceProvider(manager),
        validator=InvariantValidator(),
        checkpoint=checkpoint,
    )


def _file_hashes(project: Path) -> dict[str, str]:
    return {
        path.relative_to(project).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in project.rglob("*")
        if path.is_file() and not path.name.endswith("-shm")
    }


def test_unknown_schema_and_unregistered_pairs_are_default_denied() -> None:
    registry = _registry()
    gate = SchemaCompatibilityGate({"beta-2"}, registry)

    with pytest.raises(LocalSecurityError) as unsupported:
        gate.require_supported("future-99")
    assert unsupported.value.code == "SCHEMA_VERSION_UNSUPPORTED"

    with pytest.raises(LocalSecurityError) as unavailable:
        gate.require_known_pair("beta-0", "beta-2")
    assert unavailable.value.code == "KNOWN_MIGRATION_PAIR_UNAVAILABLE"
    with pytest.raises(LocalSecurityError):
        gate.require_known_pair("beta-2", "beta-1")


def test_known_pair_uses_online_backup_validates_semantics_and_publishes_atomically(
    tmp_path: Path,
) -> None:
    source, writer = _create_source(tmp_path)
    try:
        source_before = _file_hashes(source)
        target = tmp_path / "migrated-project"

        record = _runner(tmp_path, _registry()).migrate(
            source,
            target,
            source_version="beta-1",
            target_version="beta-2",
        )

        assert record.status is MigrationStatus.SUCCEEDED
        assert len(record.source_snapshot_hash) == 64
        assert len(record.validation_hash) == 64
        assert json.loads((target / "manifest.json").read_text())["schema_version"] == "beta-2"
        with closing(sqlite3.connect(target / "project.sqlite3")) as connection:
            columns = connection.execute("PRAGMA table_info(records)").fetchall()
            assert [column[1] for column in columns] == ["value", "storage_note"]
            assert connection.execute("SELECT value FROM records ORDER BY value").fetchall() == [
                (1,),
                (2,),
            ]
        assert InvariantValidator().fingerprint(target) == InvariantValidator().fingerprint(source)
        assert _file_hashes(source) == source_before
        assert list((tmp_path / "migration-temp").glob("task-*")) == []
    finally:
        writer.close()


@pytest.mark.parametrize("failed_phase", list(MigrationPhase))
def test_fault_at_every_phase_keeps_original_and_publishes_nothing(
    tmp_path: Path, failed_phase: MigrationPhase
) -> None:
    source, writer = _create_source(tmp_path)
    try:
        source_before = _file_hashes(source)
        target = tmp_path / "migrated-project"

        def checkpoint(phase: MigrationPhase) -> None:
            if phase is failed_phase:
                raise RuntimeError("injected phase fault")

        with pytest.raises(KnownMigrationError) as captured:
            _runner(tmp_path, _registry(), checkpoint=checkpoint).migrate(
                source,
                target,
                source_version="beta-1",
                target_version="beta-2",
            )

        expected = (
            "MIGRATION_VALIDATION_FAILED"
            if failed_phase is MigrationPhase.VALIDATE
            else "MIGRATION_FAILED"
        )
        assert captured.value.code == expected
        assert captured.value.record.status is MigrationStatus.FAILED
        assert not target.exists()
        assert _file_hashes(source) == source_before
        assert list((tmp_path / "migration-temp").glob("task-*")) == []
    finally:
        writer.close()


def test_semantic_hash_change_fails_validation_without_damaging_source(tmp_path: Path) -> None:
    source, writer = _create_source(tmp_path)
    try:
        source_before = _file_hashes(source)

        def corrupt_semantics(project: Path) -> None:
            _storage_only_migration(project)
            path = project / "invariants.json"
            invariants = json.loads(path.read_text(encoding="utf-8"))
            invariants["science_hash"] = "9" * 64
            path.write_text(json.dumps(invariants), encoding="utf-8")

        target = tmp_path / "migrated-project"
        with pytest.raises(KnownMigrationError) as captured:
            _runner(tmp_path, _registry(corrupt_semantics)).migrate(
                source,
                target,
                source_version="beta-1",
                target_version="beta-2",
            )

        assert captured.value.code == "MIGRATION_VALIDATION_FAILED"
        assert not target.exists()
        assert _file_hashes(source) == source_before
    finally:
        writer.close()


def test_cancelled_known_migration_leaves_source_and_target_untouched(tmp_path: Path) -> None:
    source, writer = _create_source(tmp_path)
    try:
        source_before = _file_hashes(source)
        target = tmp_path / "migrated-project"

        def cancel(phase: MigrationPhase) -> None:
            if phase is MigrationPhase.MIGRATE:
                raise MigrationCancelled

        with pytest.raises(KnownMigrationError) as captured:
            _runner(tmp_path, _registry(), checkpoint=cancel).migrate(
                source,
                target,
                source_version="beta-1",
                target_version="beta-2",
            )

        assert captured.value.code == "MIGRATION_CANCELLED"
        assert captured.value.record.status is MigrationStatus.CANCELLED
        assert not target.exists()
        assert _file_hashes(source) == source_before
    finally:
        writer.close()
