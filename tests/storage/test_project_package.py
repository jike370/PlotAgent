from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import warnings
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from plotagent.storage import (
    Catalog,
    ImportResource,
    ProjectImportService,
    ProjectPackageService,
    ProjectPackageType,
    ProjectStore,
)
from plotagent.storage.errors import StorageErrorCode, StorageProblem

FILES_ROOT = Path(__file__).parents[1] / "fixtures" / "import" / "files"


class _TestPermissions:
    def make_private(self, path: Path) -> None:
        if os.name != "nt":
            path.chmod(0o700)


def _service(catalog: Catalog, root: Path) -> ProjectPackageService:
    return ProjectPackageService(
        catalog,
        root / "projects",
        temp_root=root / "package-tmp",
        permission_enforcer=_TestPermissions(),
    )


def _create_package(root: Path, *, project_id: str = "project:portable") -> Path:
    package_path = root / "portable.plotproj"
    with (
        Catalog.create(root / "source-catalog.sqlite3") as catalog,
        ProjectStore.create(root / "source-workspace", project_id=project_id) as project,
    ):
        result = ProjectImportService(project).import_resource(
            ImportResource(resource_id="resource:basic", path=FILES_ROOT / "csv_basic.csv")
        )
        assert result.kind == "committed"
        _service(catalog, root / "source-service").pack(project, package_path)
    return package_path


def _copy_archive(
    source: Path,
    destination: Path,
    *,
    transform: Callable[[str, bytes], bytes] | None = None,
    extras: tuple[tuple[zipfile.ZipInfo | str, bytes], ...] = (),
) -> None:
    with (
        zipfile.ZipFile(source, "r") as input_archive,
        zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as output_archive,
    ):
        for entry in input_archive.infolist():
            data = input_archive.read(entry)
            if transform is not None:
                data = transform(entry.filename, data)
            output_archive.writestr(entry, data)
        for name_or_info, data in extras:
            output_archive.writestr(name_or_info, data)


def _rewrite_manifest(source: Path, destination: Path, **updates: object) -> None:
    with zipfile.ZipFile(source, "r") as archive:
        entries = {entry.filename: archive.read(entry) for entry in archive.infolist()}
        infos = {entry.filename: entry for entry in archive.infolist()}
    manifest = json.loads(entries["manifest.json"])
    manifest.update(updates)
    manifest_bytes = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    checksums = {}
    for line in entries["checksums.sha256"].decode("ascii").splitlines():
        content_hash, name = line.split("  ", 1)
        checksums[name] = content_hash
    checksums["manifest.json"] = hashlib.sha256(manifest_bytes).hexdigest()
    entries["manifest.json"] = manifest_bytes
    entries["checksums.sha256"] = "".join(
        f"{content_hash}  {name}\n" for name, content_hash in sorted(checksums.items())
    ).encode("ascii")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(infos[name], data)


def test_full_package_roundtrip_contains_only_snapshot_database_and_references(
    storage_root: Path,
) -> None:
    package_path = _create_package(storage_root)
    with zipfile.ZipFile(package_path) as archive:
        names = set(archive.namelist())
    assert {"manifest.json", "project.sqlite3", "checksums.sha256"} <= names
    assert any(name.startswith("objects/sha256/") for name in names)
    assert not any(
        name.endswith(("-wal", "-shm"))
        or name.startswith(("cache/", "tmp/"))
        or name == "project.lock"
        for name in names
    )

    target_root = storage_root / "target"
    with Catalog.create(target_root / "catalog.sqlite3") as catalog:
        service = _service(catalog, target_root)
        with service.open_package(package_path) as opened:
            assert opened.import_result.reused is False
            assert opened.project.project_id == "project:portable"
            assert opened.project.state_counts()["source_dataset_versions"] == 1
            assert opened.project.verify_registered_objects()
            assert opened.project.journal_mode().casefold() == "wal"


def test_online_backup_captures_committed_wal_state(storage_root: Path) -> None:
    package_path = storage_root / "wal.plotproj"
    with (
        Catalog.create(storage_root / "catalog.sqlite3") as catalog,
        ProjectStore.create(storage_root / "project", project_id="project:wal") as project,
    ):
        ProjectImportService(project).import_resource(
            ImportResource(resource_id="resource:wal", path=FILES_ROOT / "csv_basic.csv")
        )
        wal_path = project.database_path.with_name("project.sqlite3-wal")
        assert wal_path.is_file() and wal_path.stat().st_size > 0
        _service(catalog, storage_root / "service").pack(project, package_path)

    snapshot_path = storage_root / "snapshot.sqlite3"
    with zipfile.ZipFile(package_path) as archive:
        snapshot_path.write_bytes(archive.read("project.sqlite3"))
    with sqlite3.connect(snapshot_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM source_dataset_versions").fetchone()
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()
    assert count == (1,)
    assert journal_mode is not None and str(journal_mode[0]).casefold() == "delete"


def test_pack_atomic_overwrite_preserves_existing_target_on_failure(storage_root: Path) -> None:
    package_path = storage_root / "atomic.plotproj"
    with (
        Catalog.create(storage_root / "catalog.sqlite3") as catalog,
        ProjectStore.create(storage_root / "project", project_id="project:atomic") as project,
    ):
        service = _service(catalog, storage_root / "service")
        ProjectImportService(project).import_resource(
            ImportResource(resource_id="resource:first", path=FILES_ROOT / "csv_basic.csv")
        )
        service.pack(project, package_path)
        original = package_path.read_bytes()
        ProjectImportService(project).import_resource(
            ImportResource(resource_id="resource:second", path=FILES_ROOT / "csv_quoted.csv")
        )

        def fail_before_replace(stage: str) -> None:
            if stage == "before_replace":
                raise RuntimeError("injected replace failure")

        with pytest.raises(StorageProblem) as caught:
            service.pack(project, package_path, fault_injector=fail_before_replace)
        assert caught.value.code == StorageErrorCode.PACKAGE_EXPORT_FAILED
        assert package_path.read_bytes() == original

        service.pack(project, package_path)
        assert package_path.read_bytes() != original


def _tampered(source: Path, destination: Path) -> None:
    _copy_archive(
        source,
        destination,
        transform=lambda name, data: data + b"tampered" if name == "project.sqlite3" else data,
    )


def _traversal(source: Path, destination: Path) -> None:
    _copy_archive(source, destination, extras=(("../escaped.txt", b"escape"),))


def _unknown_top_level(source: Path, destination: Path) -> None:
    _copy_archive(source, destination, extras=(("cache/secret.bin", b"secret"),))


def _duplicate_normalized(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(source) as archive:
        duplicate = archive.read("manifest.json")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        _copy_archive(source, destination, extras=(("MANIFEST.JSON", duplicate),))


def _symlink(source: Path, destination: Path) -> None:
    content_hash = hashlib.sha256(b"link target").hexdigest()
    info = zipfile.ZipInfo(f"objects/sha256/{content_hash[:2]}/{content_hash}")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    _copy_archive(source, destination, extras=((info, b"target"),))


def _bomb(source: Path, destination: Path) -> None:
    payload = b"0" * (1024 * 1024)
    content_hash = hashlib.sha256(payload).hexdigest()
    _copy_archive(
        source,
        destination,
        extras=((f"objects/sha256/{content_hash[:2]}/{content_hash}", payload),),
    )


def _future_schema(source: Path, destination: Path) -> None:
    _rewrite_manifest(source, destination, package_format_version=999)


def _result_package(source: Path, destination: Path) -> None:
    _rewrite_manifest(source, destination, package_type=ProjectPackageType.RESULT.value)


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (_tampered, StorageErrorCode.PACKAGE_HASH_INVALID),
        (_traversal, StorageErrorCode.ARCHIVE_UNSAFE_PATH),
        (_unknown_top_level, StorageErrorCode.ARCHIVE_UNSAFE_PATH),
        (_duplicate_normalized, StorageErrorCode.ARCHIVE_DUPLICATE_PATH),
        (_symlink, StorageErrorCode.ARCHIVE_LINK_REJECTED),
        (_bomb, StorageErrorCode.ARCHIVE_BOMB_SUSPECTED),
        (_future_schema, StorageErrorCode.SCHEMA_VERSION_UNSUPPORTED),
        (_result_package, StorageErrorCode.PACKAGE_TYPE_UNSUPPORTED),
    ],
)
def test_unsafe_or_unsupported_package_fails_without_catalog_or_workspace_pollution(
    storage_root: Path,
    mutator: Callable[[Path, Path], None],
    expected_code: StorageErrorCode,
) -> None:
    package_path = _create_package(storage_root)
    unsafe_package = storage_root / "unsafe.plotproj"
    mutator(package_path, unsafe_package)
    target_root = storage_root / "target"
    with Catalog.create(target_root / "catalog.sqlite3") as catalog:
        service = _service(catalog, target_root)
        with pytest.raises(StorageProblem) as caught:
            service.import_package(unsafe_package)
        assert caught.value.code == expected_code
        assert catalog.list_projects() == ()
        assert not tuple((target_root / "projects").iterdir())
        assert not tuple((target_root / "package-tmp").iterdir())
    assert not (storage_root / "escaped.txt").exists()


def test_reopen_reuses_catalog_identity_and_as_new_copy_rewrites_uuid(
    storage_root: Path,
) -> None:
    package_path = _create_package(storage_root)
    target_root = storage_root / "target"
    with Catalog.create(target_root / "catalog.sqlite3") as catalog:
        service = _service(catalog, target_root)
        first = service.import_package(package_path)
        reopened = service.import_package(package_path)
        assert reopened.reused is True
        assert reopened.project_id == first.project_id
        assert reopened.workspace_path == first.workspace_path

        repacked_path = storage_root / "repacked.plotproj"
        shutil_bytes = package_path.read_bytes()
        repacked_path.write_bytes(shutil_bytes)
        with zipfile.ZipFile(repacked_path, "a") as archive:
            archive.comment = b"different package bytes"
        by_source_id = service.import_package(repacked_path)
        assert by_source_id.reused is True
        assert by_source_id.project_id == first.project_id

        copied = service.import_package(package_path, as_new_copy=True)
        assert copied.reused is False
        assert copied.as_new_copy is True
        assert copied.project_id != first.project_id
        assert copied.source_project_id == first.source_project_id
        assert copied.workspace_path != first.workspace_path
        with ProjectStore.open(copied.workspace_path) as project:
            assert project.project_id == copied.project_id
            assert project.state_counts()["source_dataset_versions"] == 1
            assert project.verify_registered_objects()
        assert len(catalog.list_projects()) == 2


def test_import_publish_fault_rolls_back_workspace_and_catalog(storage_root: Path) -> None:
    package_path = _create_package(storage_root)
    target_root = storage_root / "target"

    def fail_after_publish(stage: str) -> None:
        if stage == "after_publish":
            raise RuntimeError("injected catalog-boundary failure")

    with Catalog.create(target_root / "catalog.sqlite3") as catalog:
        service = _service(catalog, target_root)
        with pytest.raises(StorageProblem) as caught:
            service.import_package(package_path, fault_injector=fail_after_publish)
        assert caught.value.code == StorageErrorCode.PACKAGE_IMPORT_FAILED
        assert catalog.list_projects() == ()
        assert not tuple((target_root / "projects").iterdir())
        assert not tuple((target_root / "package-tmp").iterdir())


def test_result_package_export_is_stably_unsupported(storage_root: Path) -> None:
    destination = storage_root / "result.plotproj"
    with (
        Catalog.create(storage_root / "catalog.sqlite3") as catalog,
        ProjectStore.create(storage_root / "project") as project,
        pytest.raises(StorageProblem) as caught,
    ):
        _service(catalog, storage_root / "service").pack(
            project,
            destination,
            package_type=ProjectPackageType.RESULT,
        )
    assert caught.value.code == StorageErrorCode.PACKAGE_TYPE_UNSUPPORTED
    assert not destination.exists()
