"""Verified full-project ``.plotproj`` snapshots and local work-copy import."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import unicodedata
import uuid
import zipfile
from collections.abc import Callable
from contextlib import closing, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Self

from pydantic import ValidationError

from plotagent.security.temp_workspace import (
    PrivateTempWorkspaceManager,
    WindowsPrivateAcl,
)
from plotagent.storage.catalog import Catalog
from plotagent.storage.errors import StorageErrorCode, StorageProblem
from plotagent.storage.models import (
    ProjectPackageExportResult,
    ProjectPackageImportResult,
    ProjectPackageManifest,
    ProjectPackageObject,
    ProjectPackageType,
)
from plotagent.storage.project import ProjectStore
from plotagent.storage.schema import PROJECT_SCHEMA_VERSION, validate_schema
from plotagent.storage.workspace import ensure_local_fixed_workspace

PACKAGE_FORMAT_VERSION = 1
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_OBJECT_PATH_PATTERN = re.compile(r"objects/sha256/([0-9a-f]{2})/([0-9a-f]{64})")
_OBJECT_DIRECTORY_PATTERN = re.compile(r"objects(?:/sha256(?:/[0-9a-f]{2})?)?")
_CHECKSUM_LINE_PATTERN = re.compile(r"([0-9a-f]{64})  ([^\r\n]+)")
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(1, 10)}
)
_TOP_LEVEL_FILES = frozenset({"manifest.json", "project.sqlite3", "checksums.sha256"})
_ALLOWED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})

type PackageFaultInjector = Callable[[str], None]


class PermissionEnforcer(Protocol):
    def make_private(self, path: Path) -> None: ...


class _PlatformPrivatePermissions:
    def make_private(self, path: Path) -> None:
        if os.name == "nt":
            WindowsPrivateAcl().make_private(path)
        else:
            path.chmod(0o700)


@dataclass(frozen=True, slots=True)
class PackageLimits:
    max_archive_size: int = 2 * 1024 * 1024 * 1024
    max_entries: int = 4096
    max_single_file_size: int = 1024 * 1024 * 1024
    max_expanded_size: int = 4 * 1024 * 1024 * 1024
    max_compression_ratio: float = 200.0
    max_manifest_size: int = 1024 * 1024
    max_checksums_size: int = 8 * 1024 * 1024

    def __post_init__(self) -> None:
        numeric = (
            self.max_archive_size,
            self.max_entries,
            self.max_single_file_size,
            self.max_expanded_size,
            self.max_manifest_size,
            self.max_checksums_size,
        )
        if any(value <= 0 for value in numeric) or self.max_compression_ratio <= 1:
            raise ValueError("package limits must be positive and ratio must exceed one")


@dataclass(frozen=True, slots=True)
class _VerifiedPackage:
    manifest: ProjectPackageManifest
    package_sha256: str
    extracted_root: Path


@dataclass(slots=True)
class OpenedProjectPackage:
    import_result: ProjectPackageImportResult
    project: ProjectStore

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.project.close()


class ProjectPackageService:
    """Pack, verify, import, and open full snapshots without running inside ZIP files."""

    def __init__(
        self,
        catalog: Catalog,
        projects_root: str | Path,
        *,
        temp_root: str | Path | None = None,
        limits: PackageLimits | None = None,
        permission_enforcer: PermissionEnforcer | None = None,
    ) -> None:
        self._catalog = catalog
        self.projects_root = ensure_local_fixed_workspace(Path(projects_root))
        self.projects_root.mkdir(parents=True, exist_ok=True)
        private_root = (
            Path(temp_root) if temp_root is not None else self.projects_root.parent / "tmp"
        )
        private_root = ensure_local_fixed_workspace(private_root)
        if private_root.anchor.casefold() != self.projects_root.anchor.casefold():
            raise StorageProblem(
                StorageErrorCode.WORKSPACE_FILESYSTEM_UNSUPPORTED,
                "项目包 temp 必须与项目工作区位于同一文件系统。",
            )
        self._temp_manager = PrivateTempWorkspaceManager(
            private_root,
            permission_enforcer=permission_enforcer or _PlatformPrivatePermissions(),
        )
        if private_root.stat().st_dev != self.projects_root.stat().st_dev:
            raise StorageProblem(
                StorageErrorCode.WORKSPACE_FILESYSTEM_UNSUPPORTED,
                "项目包 temp 必须与项目工作区位于同一文件系统。",
            )
        self._limits = limits or PackageLimits()

    def pack(
        self,
        project: ProjectStore,
        destination: str | Path,
        *,
        package_type: ProjectPackageType | str = ProjectPackageType.FULL,
        fault_injector: PackageFaultInjector | None = None,
    ) -> ProjectPackageExportResult:
        """Create and fully re-verify one same-volume temporary ZIP before replace."""

        try:
            selected_type = ProjectPackageType(package_type)
        except ValueError as error:
            raise StorageProblem(
                StorageErrorCode.PACKAGE_TYPE_UNSUPPORTED,
                "当前 build 只支持完整项目包。",
            ) from error
        if selected_type is not ProjectPackageType.FULL:
            raise StorageProblem(
                StorageErrorCode.PACKAGE_TYPE_UNSUPPORTED,
                "结果项目包尚未实现；当前 build 只交付完整项目包。",
            )

        target = Path(destination).resolve(strict=False)
        target_parent = ensure_local_fixed_workspace(target.parent)
        target_parent.mkdir(parents=True, exist_ok=True)
        target = target_parent / target.name
        staging_root = Path(tempfile.mkdtemp(prefix=f".{target.name}.pack-", dir=target.parent))
        temporary_package = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
        try:
            snapshot_database = staging_root / "project.sqlite3"
            project.backup_database(snapshot_database)
            snapshot_project_id, objects = _read_database_objects(snapshot_database)
            if snapshot_project_id != project.project_id:
                raise StorageProblem(
                    StorageErrorCode.PACKAGE_MANIFEST_INVALID,
                    "项目数据库标识在快照期间发生冲突。",
                )

            manifest_objects: list[ProjectPackageObject] = []
            object_sources: dict[str, Path] = {}
            for content_hash, media_type, size in objects:
                object_path = project.object_path(content_hash)
                actual_hash, actual_size = _hash_file(object_path)
                if actual_hash != content_hash or actual_size != size:
                    raise StorageProblem(
                        StorageErrorCode.PACKAGE_HASH_INVALID,
                        "项目引用的 CAS 对象缺失或与登记哈希不一致。",
                    )
                archive_path = _object_archive_path(content_hash)
                manifest_objects.append(
                    ProjectPackageObject(
                        path=archive_path,
                        content_hash=content_hash,
                        size=size,
                        media_type=media_type,
                    )
                )
                object_sources[archive_path] = object_path

            manifest = ProjectPackageManifest(
                package_format_version=PACKAGE_FORMAT_VERSION,
                project_schema_version=PROJECT_SCHEMA_VERSION,
                project_id=project.project_id,
                snapshot_transaction_id="snapshot:" + uuid.uuid4().hex,
                package_type=ProjectPackageType.FULL,
                created_at=_utc_timestamp(),
                created_by="plotagent/0.1.0",
                objects=tuple(manifest_objects),
            )
            manifest_bytes = (
                json.dumps(
                    manifest.model_dump(mode="json"),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
                + b"\n"
            )
            database_hash, database_size = _hash_file(snapshot_database)
            checksums: dict[str, str] = {
                "manifest.json": hashlib.sha256(manifest_bytes).hexdigest(),
                "project.sqlite3": database_hash,
            }
            checksums.update((item.path, item.content_hash) for item in manifest.objects)
            _write_archive(
                temporary_package,
                manifest_bytes=manifest_bytes,
                database_path=snapshot_database,
                database_hash=database_hash,
                database_size=database_size,
                object_sources=object_sources,
                object_manifest={item.path: item for item in manifest.objects},
                checksums=checksums,
            )
            if fault_injector:
                fault_injector("after_write")

            verification_root = staging_root / "verification"
            verification_root.mkdir()
            verified = _verify_archive(
                temporary_package,
                verification_root,
                limits=self._limits,
            )
            if verified.manifest != manifest:
                raise StorageProblem(
                    StorageErrorCode.PACKAGE_MANIFEST_INVALID,
                    "项目包复验得到不同 manifest。",
                )
            if fault_injector:
                fault_injector("before_replace")
            os.replace(temporary_package, target)
            _fsync_parent(target.parent)
            return ProjectPackageExportResult(
                destination_path=str(target),
                package_sha256=verified.package_sha256,
                project_id=project.project_id,
                object_count=len(manifest.objects),
            )
        except StorageProblem:
            raise
        except Exception as error:
            raise StorageProblem(
                StorageErrorCode.PACKAGE_EXPORT_FAILED,
                "项目包生成失败；既有目标保持不变。",
            ) from error
        finally:
            temporary_package.unlink(missing_ok=True)
            shutil.rmtree(staging_root, ignore_errors=True)

    def import_package(
        self,
        package_path: str | Path,
        *,
        as_new_copy: bool = False,
        display_name: str | None = None,
        fault_injector: PackageFaultInjector | None = None,
    ) -> ProjectPackageImportResult:
        """Verify an external package before catalog or formal workspace mutation."""

        source = Path(package_path)
        _require_regular_unlinked_file(source)
        task = self._temp_manager.create()
        published_workspace: Path | None = None
        try:
            copied_package = task.path / "input.plotproj"
            copied_hash = _copy_with_hash(
                source,
                copied_package,
                maximum_size=self._limits.max_archive_size,
            )
            extracted_root = task.path / "extracted"
            extracted_root.mkdir(mode=0o700)
            verified = _verify_archive(
                copied_package,
                extracted_root,
                limits=self._limits,
                expected_package_sha256=copied_hash,
            )
            if fault_injector:
                fault_injector("after_validate")

            source_project_id = verified.manifest.project_id
            if not as_new_copy:
                existing = self._catalog.find_imported_project(
                    package_sha256=verified.package_sha256,
                    source_project_id=source_project_id,
                )
                if existing is not None:
                    existing_workspace = Path(existing.workspace_path)
                    if not (existing_workspace / "project.sqlite3").is_file():
                        raise StorageProblem(
                            StorageErrorCode.PROJECT_NOT_FOUND,
                            "catalog 中的项目工作副本不存在。",
                        )
                    self._catalog.touch_project(existing.project_id)
                    return ProjectPackageImportResult(
                        project_id=existing.project_id,
                        source_project_id=source_project_id,
                        workspace_path=existing.workspace_path,
                        package_sha256=verified.package_sha256,
                        reused=True,
                        as_new_copy=False,
                    )

            project_id = "project:" + uuid.uuid4().hex if as_new_copy else source_project_id
            staged_workspace = task.path / "staged-project"
            staged_workspace.mkdir(mode=0o700)
            os.replace(extracted_root / "project.sqlite3", staged_workspace / "project.sqlite3")
            extracted_objects = extracted_root / "objects"
            if extracted_objects.exists():
                os.replace(extracted_objects, staged_workspace / "objects")
            else:
                (staged_workspace / "objects" / "sha256").mkdir(parents=True)
            (staged_workspace / "cache").mkdir()
            (staged_workspace / "tmp").mkdir()
            if as_new_copy:
                _rewrite_project_id(staged_workspace / "project.sqlite3", project_id)
            _validate_workspace(
                staged_workspace,
                expected_project_id=project_id,
                manifest=verified.manifest,
            )

            final_workspace = self._allocate_workspace()
            os.replace(staged_workspace, final_workspace)
            published_workspace = final_workspace
            if fault_injector:
                fault_injector("after_publish")
            self._catalog.register_project(
                project_id=project_id,
                workspace_path=final_workspace,
                display_name=display_name,
                source_project_id=source_project_id,
                package_sha256=verified.package_sha256,
            )
            published_workspace = None
            return ProjectPackageImportResult(
                project_id=project_id,
                source_project_id=source_project_id,
                workspace_path=str(final_workspace),
                package_sha256=verified.package_sha256,
                reused=False,
                as_new_copy=as_new_copy,
            )
        except StorageProblem:
            raise
        except Exception as error:
            raise StorageProblem(
                StorageErrorCode.PACKAGE_IMPORT_FAILED,
                "项目包导入失败；catalog 与正式项目工作区保持不变。",
            ) from error
        finally:
            if published_workspace is not None:
                shutil.rmtree(published_workspace, ignore_errors=True)
            self._temp_manager.cleanup(task)

    def open_package(
        self,
        package_path: str | Path,
        *,
        as_new_copy: bool = False,
        display_name: str | None = None,
    ) -> OpenedProjectPackage:
        imported = self.import_package(
            package_path,
            as_new_copy=as_new_copy,
            display_name=display_name,
        )
        return OpenedProjectPackage(
            import_result=imported,
            project=ProjectStore.open(imported.workspace_path),
        )

    def _allocate_workspace(self) -> Path:
        for _ in range(16):
            candidate = self.projects_root / uuid.uuid4().hex
            if not candidate.exists():
                return candidate
        raise StorageProblem(
            StorageErrorCode.PACKAGE_IMPORT_FAILED,
            "无法分配独立项目工作区。",
        )


def _read_database_objects(database_path: Path) -> tuple[str, tuple[tuple[str, str, int], ...]]:
    uri = f"{database_path.resolve().as_uri()}?mode=ro&immutable=1"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            validate_schema(connection, PROJECT_SCHEMA_VERSION, "plotagent-project")
            quick_check = connection.execute("PRAGMA quick_check").fetchone()
            if quick_check is None or str(quick_check[0]) != "ok":
                raise sqlite3.DatabaseError("project snapshot integrity check failed")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise sqlite3.DatabaseError("project snapshot foreign keys are invalid")
            project_rows = connection.execute("SELECT project_id FROM project_meta").fetchall()
            if len(project_rows) != 1:
                raise sqlite3.DatabaseError("project snapshot has invalid identity")
            rows = tuple(
                (str(content_hash), str(media_type), int(size))
                for content_hash, media_type, size in connection.execute(
                    """
                    SELECT DISTINCT objects.content_hash, objects.media_type, objects.size
                    FROM object_refs
                    JOIN objects USING(content_hash)
                    ORDER BY objects.content_hash
                    """
                )
            )
            return str(project_rows[0][0]), rows
    except StorageProblem:
        raise
    except sqlite3.DatabaseError as error:
        raise StorageProblem(
            StorageErrorCode.PACKAGE_MANIFEST_INVALID,
            "项目包中的 SQLite 快照无效。",
        ) from error


def _validate_workspace(
    workspace: Path,
    *,
    expected_project_id: str,
    manifest: ProjectPackageManifest,
) -> None:
    project_id, database_objects = _read_database_objects(workspace / "project.sqlite3")
    if project_id != expected_project_id:
        raise StorageProblem(
            StorageErrorCode.PACKAGE_MANIFEST_INVALID,
            "项目 UUID 与工作副本不一致。",
        )
    manifest_objects = {
        item.content_hash: (item.media_type, item.size, item.path) for item in manifest.objects
    }
    database_mapping = {
        content_hash: (media_type, size, _object_archive_path(content_hash))
        for content_hash, media_type, size in database_objects
    }
    if manifest_objects != database_mapping:
        raise StorageProblem(
            StorageErrorCode.PACKAGE_MANIFEST_INVALID,
            "manifest 对象清单与 SQLite 引用不一致。",
        )
    for content_hash, (_media_type, expected_size, _path) in manifest_objects.items():
        object_path = workspace / "objects" / "sha256" / content_hash[:2] / content_hash
        actual_hash, actual_size = _hash_file(object_path)
        if actual_hash != content_hash or actual_size != expected_size:
            raise StorageProblem(
                StorageErrorCode.PACKAGE_HASH_INVALID,
                "工作副本对象未通过完整哈希复验。",
            )


def _rewrite_project_id(database_path: Path, project_id: str) -> None:
    try:
        with closing(sqlite3.connect(database_path)) as connection:
            validate_schema(connection, PROJECT_SCHEMA_VERSION, "plotagent-project")
            connection.execute("PRAGMA journal_mode = DELETE")
            cursor = connection.execute("UPDATE project_meta SET project_id = ?", (project_id,))
            if cursor.rowcount != 1:
                raise sqlite3.DatabaseError("project identity rewrite failed")
            connection.commit()
    except StorageProblem:
        raise
    except sqlite3.DatabaseError as error:
        raise StorageProblem(
            StorageErrorCode.PACKAGE_IMPORT_FAILED,
            "无法为新副本重写项目 UUID。",
        ) from error


def _write_archive(
    destination: Path,
    *,
    manifest_bytes: bytes,
    database_path: Path,
    database_hash: str,
    database_size: int,
    object_sources: dict[str, Path],
    object_manifest: dict[str, ProjectPackageObject],
    checksums: dict[str, str],
) -> None:
    with zipfile.ZipFile(
        destination,
        mode="x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as archive:
        _write_bytes_member(archive, "manifest.json", manifest_bytes)
        _write_file_member(
            archive,
            "project.sqlite3",
            database_path,
            expected_hash=database_hash,
            expected_size=database_size,
        )
        for archive_path in sorted(object_sources):
            item = object_manifest[archive_path]
            _write_file_member(
                archive,
                archive_path,
                object_sources[archive_path],
                expected_hash=item.content_hash,
                expected_size=item.size,
            )
        checksum_bytes = "".join(
            f"{content_hash}  {path}\n" for path, content_hash in sorted(checksums.items())
        ).encode("ascii")
        _write_bytes_member(archive, "checksums.sha256", checksum_bytes)
    with destination.open("r+b") as stream:
        os.fsync(stream.fileno())


def _write_bytes_member(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = _regular_zip_info(name)
    with archive.open(info, mode="w", force_zip64=True) as target:
        target.write(data)


def _write_file_member(
    archive: zipfile.ZipFile,
    name: str,
    source_path: Path,
    *,
    expected_hash: str,
    expected_size: int,
) -> None:
    _require_regular_unlinked_file(source_path)
    digest = hashlib.sha256()
    size = 0
    info = _regular_zip_info(name)
    with source_path.open("rb") as source, archive.open(info, mode="w", force_zip64=True) as target:
        while chunk := source.read(1024 * 1024):
            target.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    if digest.hexdigest() != expected_hash or size != expected_size:
        raise StorageProblem(
            StorageErrorCode.PACKAGE_HASH_INVALID,
            "写入项目包时源对象发生变化。",
        )


def _regular_zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    return info


def _verify_archive(
    package_path: Path,
    extraction_root: Path,
    *,
    limits: PackageLimits,
    expected_package_sha256: str | None = None,
) -> _VerifiedPackage:
    package_hash, package_size = _hash_file(package_path)
    if package_size > limits.max_archive_size:
        raise StorageProblem(
            StorageErrorCode.ARCHIVE_LIMIT_EXCEEDED,
            "项目包压缩文件超过大小限制。",
        )
    if expected_package_sha256 is not None and package_hash != expected_package_sha256:
        raise StorageProblem(
            StorageErrorCode.PACKAGE_HASH_INVALID,
            "复制到私有 temp 后项目包哈希发生变化。",
        )
    try:
        with zipfile.ZipFile(package_path, mode="r") as archive:
            members = _inspect_members(archive.infolist(), limits)
            required = _TOP_LEVEL_FILES
            if not required.issubset(members):
                raise StorageProblem(
                    StorageErrorCode.PACKAGE_MANIFEST_INVALID,
                    "项目包缺少 manifest、SQLite 快照或 checksums。",
                )
            manifest_bytes = _read_bounded_member(
                archive,
                members["manifest.json"],
                limits.max_manifest_size,
            )
            manifest = _parse_manifest(manifest_bytes)
            if (
                manifest.package_format_version != PACKAGE_FORMAT_VERSION
                or manifest.project_schema_version != PROJECT_SCHEMA_VERSION
            ):
                raise StorageProblem(
                    StorageErrorCode.SCHEMA_VERSION_UNSUPPORTED,
                    "当前 build 不支持该项目包或项目 schema；原包保持不变。",
                )
            checksums_bytes = _read_bounded_member(
                archive,
                members["checksums.sha256"],
                limits.max_checksums_size,
            )
            checksums = _parse_checksums(checksums_bytes)
            file_names = set(members)
            expected_checksum_names = file_names - {"checksums.sha256"}
            if set(checksums) != expected_checksum_names:
                raise StorageProblem(
                    StorageErrorCode.PACKAGE_HASH_INVALID,
                    "checksums 与项目包文件集合不一致。",
                )
            _extract_and_verify(
                archive,
                members,
                extraction_root,
                checksums=checksums,
                limits=limits,
            )
    except StorageProblem:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        raise StorageProblem(
            StorageErrorCode.PACKAGE_MANIFEST_INVALID,
            "项目包不是受支持且完整的 ZIP 快照。",
        ) from error

    if manifest.package_type is not ProjectPackageType.FULL:
        raise StorageProblem(
            StorageErrorCode.PACKAGE_TYPE_UNSUPPORTED,
            "结果项目包尚未实现；当前 build 只支持完整项目包。",
        )
    if manifest.omitted_objects or manifest.unavailable_capabilities:
        raise StorageProblem(
            StorageErrorCode.PACKAGE_MANIFEST_INVALID,
            "完整项目包不得声明省略对象或不可用能力。",
        )
    manifest_paths = {item.path for item in manifest.objects}
    if len(manifest_paths) != len(manifest.objects):
        raise StorageProblem(
            StorageErrorCode.PACKAGE_MANIFEST_INVALID,
            "manifest 包含重复对象路径。",
        )
    archive_object_paths = set(members) - _TOP_LEVEL_FILES
    if manifest_paths != archive_object_paths:
        raise StorageProblem(
            StorageErrorCode.PACKAGE_MANIFEST_INVALID,
            "manifest 对象清单与 archive 内容不一致。",
        )
    for item in manifest.objects:
        match = _OBJECT_PATH_PATTERN.fullmatch(item.path)
        if (
            match is None
            or match.group(1) != item.content_hash[:2]
            or match.group(2) != item.content_hash
        ):
            raise StorageProblem(
                StorageErrorCode.PACKAGE_MANIFEST_INVALID,
                "manifest 对象路径不是其内容哈希地址。",
            )
        actual_hash, actual_size = _hash_file(extraction_root / item.path)
        if actual_hash != item.content_hash or actual_size != item.size:
            raise StorageProblem(
                StorageErrorCode.PACKAGE_HASH_INVALID,
                "manifest 对象大小或哈希校验失败。",
            )
    _validate_workspace(
        extraction_root,
        expected_project_id=manifest.project_id,
        manifest=manifest,
    )
    return _VerifiedPackage(
        manifest=manifest,
        package_sha256=package_hash,
        extracted_root=extraction_root,
    )


def _inspect_members(
    entries: list[zipfile.ZipInfo], limits: PackageLimits
) -> dict[str, zipfile.ZipInfo]:
    if len(entries) > limits.max_entries:
        raise StorageProblem(
            StorageErrorCode.ARCHIVE_LIMIT_EXCEEDED,
            "项目包 entry 数量超过限制。",
        )
    seen: set[str] = set()
    files: dict[str, zipfile.ZipInfo] = {}
    total_expanded = 0
    total_compressed = 0
    for entry in entries:
        name, duplicate_key = _validated_member_name(entry.filename, is_directory=entry.is_dir())
        if duplicate_key in seen:
            raise StorageProblem(
                StorageErrorCode.ARCHIVE_DUPLICATE_PATH,
                "项目包包含重复的规范化路径。",
            )
        seen.add(duplicate_key)
        _validate_entry_type(entry)
        if entry.compress_type not in _ALLOWED_COMPRESSION or entry.flag_bits & 0x1:
            raise StorageProblem(
                StorageErrorCode.PACKAGE_MANIFEST_INVALID,
                "项目包包含不支持的压缩或加密 entry。",
            )
        if entry.file_size < 0 or entry.compress_size < 0:
            raise StorageProblem(
                StorageErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                "项目包 entry 大小无效。",
            )
        if entry.file_size > limits.max_single_file_size:
            raise StorageProblem(
                StorageErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                "项目包单项展开大小超过限制。",
            )
        total_expanded += entry.file_size
        total_compressed += entry.compress_size
        if total_expanded > limits.max_expanded_size:
            raise StorageProblem(
                StorageErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                "项目包总展开大小超过限制。",
            )
        if entry.file_size and (
            entry.compress_size == 0
            or entry.file_size / entry.compress_size > limits.max_compression_ratio
        ):
            raise StorageProblem(
                StorageErrorCode.ARCHIVE_BOMB_SUSPECTED,
                "项目包 entry 压缩比异常。",
            )
        if entry.is_dir():
            if _OBJECT_DIRECTORY_PATTERN.fullmatch(name) is None:
                raise StorageProblem(
                    StorageErrorCode.ARCHIVE_UNSAFE_PATH,
                    "项目包包含未知目录。",
                )
            continue
        if name not in _TOP_LEVEL_FILES and _OBJECT_PATH_PATTERN.fullmatch(name) is None:
            raise StorageProblem(
                StorageErrorCode.ARCHIVE_UNSAFE_PATH,
                "项目包包含未知顶层路径或对象路径。",
            )
        files[name] = entry
    if total_expanded and (
        total_compressed == 0 or total_expanded / total_compressed > limits.max_compression_ratio
    ):
        raise StorageProblem(
            StorageErrorCode.ARCHIVE_BOMB_SUSPECTED,
            "项目包总压缩比异常。",
        )
    return files


def _validated_member_name(name: str, *, is_directory: bool) -> tuple[str, str]:
    if not name or "\\" in name or "\x00" in name:
        raise StorageProblem(
            StorageErrorCode.ARCHIVE_UNSAFE_PATH,
            "项目包包含空路径或非 POSIX 分隔符。",
        )
    if name.startswith("/") or name.startswith("//") or re.match(r"^[A-Za-z]:", name):
        raise StorageProblem(
            StorageErrorCode.ARCHIVE_UNSAFE_PATH,
            "项目包包含绝对路径。",
        )
    trimmed = name[:-1] if is_directory and name.endswith("/") else name
    parts = trimmed.split("/")
    if not trimmed or any(part in {"", ".", ".."} for part in parts):
        raise StorageProblem(
            StorageErrorCode.ARCHIVE_UNSAFE_PATH,
            "项目包包含空路径段或路径穿越。",
        )
    for part in parts:
        if (
            ":" in part
            or part.endswith((" ", "."))
            or any(ord(character) < 32 for character in part)
            or part.split(".", 1)[0].casefold() in _WINDOWS_RESERVED
        ):
            raise StorageProblem(
                StorageErrorCode.ARCHIVE_UNSAFE_PATH,
                "项目包包含 Windows 保留或特殊路径。",
            )
    normalized = unicodedata.normalize("NFC", trimmed)
    return normalized, normalized.casefold()


def _validate_entry_type(entry: zipfile.ZipInfo) -> None:
    unix_mode = (entry.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(unix_mode)
    reparse_attribute = entry.external_attr & 0x400
    if reparse_attribute or file_type == stat.S_IFLNK:
        raise StorageProblem(
            StorageErrorCode.ARCHIVE_LINK_REJECTED,
            "项目包 link/reparse entry 被拒绝。",
        )
    allowed_type = stat.S_IFDIR if entry.is_dir() else stat.S_IFREG
    if file_type not in {0, allowed_type}:
        raise StorageProblem(
            StorageErrorCode.ARCHIVE_LINK_REJECTED,
            "项目包 special entry 被拒绝。",
        )


def _read_bounded_member(
    archive: zipfile.ZipFile, entry: zipfile.ZipInfo, maximum_size: int
) -> bytes:
    if entry.file_size > maximum_size:
        raise StorageProblem(
            StorageErrorCode.ARCHIVE_LIMIT_EXCEEDED,
            "项目包元数据 entry 超过限制。",
        )
    with archive.open(entry, mode="r") as stream:
        value = stream.read(maximum_size + 1)
        if len(value) > maximum_size or stream.read(1):
            raise StorageProblem(
                StorageErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                "项目包元数据实际展开大小超过限制。",
            )
    return value


def _parse_manifest(data: bytes) -> ProjectPackageManifest:
    try:
        text = data.decode("utf-8")
        json.loads(text, object_pairs_hook=_reject_duplicate_json_keys)
        return ProjectPackageManifest.model_validate_json(text)
    except StorageProblem:
        raise
    except (UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
        raise StorageProblem(
            StorageErrorCode.PACKAGE_MANIFEST_INVALID,
            "manifest.json 不符合严格项目包 schema。",
        ) from error


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StorageProblem(
                StorageErrorCode.PACKAGE_MANIFEST_INVALID,
                "manifest.json 包含重复字段。",
            )
        result[key] = value
    return result


def _parse_checksums(data: bytes) -> dict[str, str]:
    try:
        text = data.decode("ascii")
    except UnicodeError as error:
        raise StorageProblem(
            StorageErrorCode.PACKAGE_HASH_INVALID,
            "checksums.sha256 不是 ASCII。",
        ) from error
    if not text or not text.endswith("\n"):
        raise StorageProblem(
            StorageErrorCode.PACKAGE_HASH_INVALID,
            "checksums.sha256 格式无效。",
        )
    checksums: dict[str, str] = {}
    normalized_paths: set[str] = set()
    for line in text.splitlines():
        match = _CHECKSUM_LINE_PATTERN.fullmatch(line)
        if match is None:
            raise StorageProblem(
                StorageErrorCode.PACKAGE_HASH_INVALID,
                "checksums.sha256 包含无效行。",
            )
        content_hash, path = match.groups()
        normalized_path, duplicate_key = _validated_member_name(path, is_directory=False)
        if duplicate_key in normalized_paths or normalized_path in checksums:
            raise StorageProblem(
                StorageErrorCode.ARCHIVE_DUPLICATE_PATH,
                "checksums.sha256 包含重复路径。",
            )
        normalized_paths.add(duplicate_key)
        checksums[normalized_path] = content_hash
    return checksums


def _extract_and_verify(
    archive: zipfile.ZipFile,
    members: dict[str, zipfile.ZipInfo],
    extraction_root: Path,
    *,
    checksums: dict[str, str],
    limits: PackageLimits,
) -> None:
    root = extraction_root.resolve()
    actual_total = 0
    for name, entry in sorted(members.items()):
        destination = (root / name).resolve(strict=False)
        try:
            destination.relative_to(root)
        except ValueError as error:
            raise StorageProblem(
                StorageErrorCode.ARCHIVE_UNSAFE_PATH,
                "项目包解包目标逃逸私有 temp。",
            ) from error
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with archive.open(entry, mode="r") as source, destination.open("xb") as target:
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                actual_total += len(chunk)
                if size > limits.max_single_file_size or actual_total > limits.max_expanded_size:
                    raise StorageProblem(
                        StorageErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                        "项目包实际展开大小超过限制。",
                    )
                target.write(chunk)
                digest.update(chunk)
            target.flush()
            os.fsync(target.fileno())
        if size != entry.file_size:
            raise StorageProblem(
                StorageErrorCode.PACKAGE_HASH_INVALID,
                "项目包 entry 声明大小与实际不一致。",
            )
        if name != "checksums.sha256" and digest.hexdigest() != checksums[name]:
            raise StorageProblem(
                StorageErrorCode.PACKAGE_HASH_INVALID,
                "项目包内容哈希校验失败。",
            )


def _copy_with_hash(source: Path, destination: Path, *, maximum_size: int) -> str:
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as input_stream, destination.open("xb") as output_stream:
        while chunk := input_stream.read(1024 * 1024):
            size += len(chunk)
            if size > maximum_size:
                raise StorageProblem(
                    StorageErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                    "外部项目包压缩文件超过大小限制。",
                )
            output_stream.write(chunk)
            digest.update(chunk)
        output_stream.flush()
        os.fsync(output_stream.fileno())
    return digest.hexdigest()


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
    except OSError as error:
        raise StorageProblem(
            StorageErrorCode.PACKAGE_HASH_INVALID,
            "项目包引用文件不可读。",
        ) from error
    return digest.hexdigest(), size


def _require_regular_unlinked_file(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise StorageProblem(
            StorageErrorCode.PROJECT_NOT_FOUND,
            "项目包或项目对象不存在。",
        ) from error
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = getattr(metadata, "st_file_attributes", 0)
    if (
        path.is_symlink()
        or file_attributes & reparse_attribute
        or not stat.S_ISREG(metadata.st_mode)
    ):
        raise StorageProblem(
            StorageErrorCode.ARCHIVE_LINK_REJECTED,
            "项目包或项目对象不能是 link/reparse/special file。",
        )


def _object_archive_path(content_hash: str) -> str:
    if _HASH_PATTERN.fullmatch(content_hash) is None:
        raise StorageProblem(
            StorageErrorCode.PACKAGE_MANIFEST_INVALID,
            "SQLite 包含无效对象哈希。",
        )
    return f"objects/sha256/{content_hash[:2]}/{content_hash}"


def _utc_timestamp() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _fsync_parent(path: Path) -> None:
    if os.name == "nt":
        return
    with suppress(OSError):
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
