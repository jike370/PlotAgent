"""Preview-first, local-only diagnostic bundle construction."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
import zipfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Final, NoReturn, Self

from plotagent.diagnostics.logging import PerformanceBucket, TaskState, scrub_stack_trace
from plotagent.security.errors import LocalSecurityError

_VERSION: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+\-]{0,63}$")
_NAME: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-]{0,63}$")
_STABLE_CODE: Final = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_SHA256: Final = re.compile(r"^[a-f0-9]{64}$")
_WINDOWS_PATH: Final = re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\[^\\]+\\[^\\]+)")
_POSIX_USER_PATH: Final = re.compile(r"(?:/home/|/Users/|/var/folders/)[^\s\"']+")
_SECRET_VALUE: Final = re.compile(
    r"(?i)(?:bearer\s+[a-z0-9._\-]+|sk-[a-z0-9_\-]{8,}|"
    r"(?:api[_ -]?key|password|credential|invite[_ -]?code|authorization)\s*[:=]|"
    r"-----BEGIN [A-Z ]+PRIVATE KEY-----)"
)
_RELATIVE_PATH: Final = re.compile(r"(?:^|\s)[A-Za-z0-9_.\-]+[/\\][A-Za-z0-9_.\-]+")
_RULES_VERSION: Final = "sanitized-column-summary-v1"
_RULES: Final = (
    "column_names_sha256",
    "no_data_values",
    "numeric_sign_counts_only",
    "text_counts_only",
    "paths_and_secrets_absent",
)


@dataclass(frozen=True, slots=True)
class VersionInfo:
    app: str
    os: str
    python: str
    schema: str
    origin: str | None = None
    dependencies: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value in (self.app, self.os, self.python, self.schema, self.origin):
            if value is not None and _VERSION.fullmatch(value) is None:
                _violation("diagnostic_schema")
        dependencies = dict(self.dependencies)
        for name, version in dependencies.items():
            if _NAME.fullmatch(name) is None or _VERSION.fullmatch(version) is None:
                _violation("diagnostic_schema")
        object.__setattr__(self, "dependencies", MappingProxyType(dependencies))


@dataclass(frozen=True, slots=True)
class StructureSummary:
    object_type: str
    row_count: int
    column_count: int
    primitive_count: int
    content_hash: str

    def __post_init__(self) -> None:
        if _STABLE_CODE.fullmatch(self.object_type) is None:
            _violation("diagnostic_schema")
        if min(self.row_count, self.column_count, self.primitive_count) < 0:
            _violation("diagnostic_schema")
        if _SHA256.fullmatch(self.content_hash) is None:
            _violation("diagnostic_schema")


@dataclass(frozen=True, slots=True)
class SanitizedError:
    code: str
    scrubbed_stack: str | None = None

    def __post_init__(self) -> None:
        if _STABLE_CODE.fullmatch(self.code) is None:
            _violation("diagnostic_schema")
        if self.scrubbed_stack is not None and _contains_forbidden_text(self.scrubbed_stack):
            _violation("diagnostic_schema")

    @classmethod
    def from_stack(cls, code: str, stack_trace: str) -> Self:
        return cls(code=code, scrubbed_stack=scrub_stack_trace(stack_trace) or None)


@dataclass(frozen=True, slots=True)
class TaskTransition:
    state: TaskState
    stage: str

    def __post_init__(self) -> None:
        if _STABLE_CODE.fullmatch(self.stage) is None:
            _violation("diagnostic_schema")


@dataclass(frozen=True, slots=True)
class DiagnosticSnapshot:
    versions: VersionInfo
    structures: tuple[StructureSummary, ...] = ()
    errors: tuple[SanitizedError, ...] = ()
    task_transitions: tuple[TaskTransition, ...] = ()
    performance_buckets: tuple[PerformanceBucket, ...] = ()
    config_flags: Mapping[str, bool] = field(default_factory=dict)
    origin_capability: str | None = None

    def __post_init__(self) -> None:
        flags = dict(self.config_flags)
        for name, enabled in flags.items():
            if _STABLE_CODE.fullmatch(name) is None or not isinstance(enabled, bool):
                _violation("diagnostic_schema")
        if (
            self.origin_capability is not None
            and _STABLE_CODE.fullmatch(self.origin_capability) is None
        ):
            _violation("diagnostic_schema")
        object.__setattr__(self, "config_flags", MappingProxyType(flags))

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> Self:
        _only_keys(
            value,
            {
                "versions",
                "structures",
                "errors",
                "task_transitions",
                "performance_buckets",
                "config_flags",
                "origin_capability",
            },
            required={"versions"},
        )
        versions_raw = _mapping(value["versions"])
        _only_keys(
            versions_raw,
            {"app", "os", "python", "schema", "origin", "dependencies"},
            required={"app", "os", "python", "schema"},
        )
        versions = VersionInfo(
            app=_string(versions_raw["app"]),
            os=_string(versions_raw["os"]),
            python=_string(versions_raw["python"]),
            schema=_string(versions_raw["schema"]),
            origin=_optional_string(versions_raw.get("origin")),
            dependencies=_string_mapping(versions_raw.get("dependencies", {})),
        )
        structures = tuple(
            _parse_structure(item) for item in _sequence(value.get("structures", ()))
        )
        errors = tuple(_parse_error(item) for item in _sequence(value.get("errors", ())))
        transitions = tuple(
            _parse_transition(item) for item in _sequence(value.get("task_transitions", ()))
        )
        try:
            performance = tuple(
                PerformanceBucket(_string(item))
                for item in _sequence(value.get("performance_buckets", ()))
            )
        except ValueError as error:
            raise LocalSecurityError(
                "DIAGNOSTIC_SCHEMA_VIOLATION", category="diagnostic_schema"
            ) from error
        flags_raw = _mapping(value.get("config_flags", {}))
        flags: dict[str, bool] = {}
        for name, enabled in flags_raw.items():
            if not isinstance(name, str):
                _violation("diagnostic_schema")
            if not isinstance(enabled, bool):
                _violation("diagnostic_schema")
            flags[name] = enabled
        return cls(
            versions=versions,
            structures=structures,
            errors=errors,
            task_transitions=transitions,
            performance_buckets=performance,
            config_flags=flags,
            origin_capability=_optional_string(value.get("origin_capability")),
        )


@dataclass(frozen=True, slots=True)
class PreviewFile:
    logical_name: str
    purpose: str
    content: bytes
    sha256: str

    @property
    def size(self) -> int:
        return len(self.content)

    @property
    def exact_json(self) -> str:
        return self.content.decode("utf-8")


@dataclass(frozen=True, slots=True)
class DiagnosticPreview:
    preview_id: str
    files: tuple[PreviewFile, ...]
    sanitized_data_rules_hash: str | None
    _issuer: object = field(repr=False, compare=False)

    @property
    def requires_sanitized_data_consent(self) -> bool:
        return self.sanitized_data_rules_hash is not None


class SanitizedDataConsent:
    """An in-memory, preview-bound, single-use confirmation."""

    __slots__ = ("_preview_id", "_rules_hash", "_used")
    _preview_id: str
    _rules_hash: str
    _used: bool

    def __init__(self) -> None:
        raise TypeError("use SanitizedDataConsent.confirm")

    @classmethod
    def confirm(cls, preview: DiagnosticPreview, *, explicitly_confirmed: bool) -> Self:
        if explicitly_confirmed is not True or preview.sanitized_data_rules_hash is None:
            raise LocalSecurityError(
                "DIAGNOSTIC_DATA_CONSENT_REQUIRED", category="diagnostic_consent"
            )
        consent = object.__new__(cls)
        consent._preview_id = preview.preview_id
        consent._rules_hash = preview.sanitized_data_rules_hash
        consent._used = False
        return consent

    def consume(self, preview: DiagnosticPreview) -> None:
        if (
            self._used
            or self._preview_id != preview.preview_id
            or self._rules_hash != preview.sanitized_data_rules_hash
        ):
            raise LocalSecurityError(
                "DIAGNOSTIC_DATA_CONSENT_REQUIRED", category="diagnostic_consent"
            )
        self._used = True


class LocalDiagnosticBundleBuilder:
    """Build exact previews and atomically save a ZIP without any network API."""

    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self._issuer = object()

    def preview(
        self,
        snapshot: DiagnosticSnapshot | Mapping[str, object],
        *,
        sanitized_columns: Mapping[str, Sequence[object]] | None = None,
    ) -> DiagnosticPreview:
        parsed = (
            snapshot
            if isinstance(snapshot, DiagnosticSnapshot)
            else DiagnosticSnapshot.from_mapping(snapshot)
        )
        payloads: list[PreviewFile] = []
        default_content = _json_bytes(_snapshot_payload(parsed))
        _scan_output(json.loads(default_content))
        payloads.append(
            _preview_file("diagnostics.json", "ALLOWLISTED_DIAGNOSTICS", default_content)
        )

        rules_hash: str | None = None
        if sanitized_columns is not None:
            sanitized_payload = _sanitized_column_payload(sanitized_columns)
            sanitized_content = _json_bytes(sanitized_payload)
            _scan_output(json.loads(sanitized_content))
            payloads.append(
                _preview_file(
                    "sanitized-data.json",
                    "ONE_BUNDLE_SANITIZED_DATA",
                    sanitized_content,
                )
            )
            rules_hash = hashlib.sha256(_json_bytes(list(_RULES))).hexdigest()

        manifest = {
            "schema_version": "1",
            "generated_at": self._now().astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "app_build": parsed.versions.app,
            "files": [
                {
                    "logical_name": item.logical_name,
                    "purpose": item.purpose,
                    "size": item.size,
                    "sha256": item.sha256,
                }
                for item in payloads
            ],
            "allowed_field_counts": _field_counts(
                [json.loads(item.content) for item in payloads]
            ),
            "sanitized_data_consent": "this_bundle" if rules_hash else "absent",
            "forbidden_scan_result": "passed",
        }
        if rules_hash is not None:
            manifest["sanitized_data_rules_hash"] = rules_hash
        manifest_content = _json_bytes(manifest)
        _scan_output(manifest)
        manifest_file = _preview_file("manifest.json", "BUNDLE_MANIFEST", manifest_content)
        files = (manifest_file, *payloads)
        preview_id = hashlib.sha256(b"".join(item.content for item in files)).hexdigest()
        return DiagnosticPreview(preview_id, files, rules_hash, self._issuer)

    def save_local(
        self,
        preview: DiagnosticPreview,
        output_path: Path,
        *,
        consent: SanitizedDataConsent | None = None,
    ) -> Path:
        self._validate_preview(preview)
        if preview.requires_sanitized_data_consent:
            if consent is None:
                raise LocalSecurityError(
                    "DIAGNOSTIC_DATA_CONSENT_REQUIRED", category="diagnostic_consent"
                )
            consent.consume(preview)
        parent = output_path.parent
        if not parent.is_dir():
            raise FileNotFoundError(parent)
        temporary_path: Path | None = None
        try:
            descriptor, name = tempfile.mkstemp(
                prefix=".plotagent-diagnostic-", suffix=".tmp", dir=parent
            )
            os.close(descriptor)
            temporary_path = Path(name)
            os.chmod(temporary_path, stat.S_IREAD | stat.S_IWRITE)
            with zipfile.ZipFile(
                temporary_path, mode="w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                for item in preview.files:
                    archive.writestr(item.logical_name, item.content)
            with temporary_path.open("r+b") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary_path, output_path)
            temporary_path = None
            return output_path
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _validate_preview(self, preview: DiagnosticPreview) -> None:
        if preview._issuer is not self._issuer:
            _violation("diagnostic_schema")
        expected_names = ["manifest.json", "diagnostics.json"]
        if preview.requires_sanitized_data_consent:
            expected_names.append("sanitized-data.json")
        if [item.logical_name for item in preview.files] != expected_names:
            _violation("diagnostic_schema")
        for item in preview.files:
            if hashlib.sha256(item.content).hexdigest() != item.sha256:
                _violation("diagnostic_schema")
            try:
                content = json.loads(item.content)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise LocalSecurityError(
                    "DIAGNOSTIC_SCHEMA_VIOLATION", category="diagnostic_schema"
                ) from error
            _scan_output(content)
        expected_preview_id = hashlib.sha256(
            b"".join(item.content for item in preview.files)
        ).hexdigest()
        if preview.preview_id != expected_preview_id:
            _violation("diagnostic_schema")


def _snapshot_payload(snapshot: DiagnosticSnapshot) -> dict[str, object]:
    return {
        "versions": {
            "app": snapshot.versions.app,
            "os": snapshot.versions.os,
            "python": snapshot.versions.python,
            "schema": snapshot.versions.schema,
            "origin": snapshot.versions.origin,
            "dependencies": dict(snapshot.versions.dependencies),
        },
        "origin_capability": snapshot.origin_capability,
        "structures": [
            {
                "object_type": item.object_type,
                "row_count": item.row_count,
                "column_count": item.column_count,
                "primitive_count": item.primitive_count,
                "content_hash": item.content_hash,
            }
            for item in snapshot.structures
        ],
        "errors": [
            {"code": item.code, "scrubbed_stack": item.scrubbed_stack}
            for item in snapshot.errors
        ],
        "task_transitions": [
            {"state": item.state.value, "stage": item.stage}
            for item in snapshot.task_transitions
        ],
        "performance_buckets": [item.value for item in snapshot.performance_buckets],
        "config_flags": dict(snapshot.config_flags),
    }


def _sanitized_column_payload(
    columns: Mapping[str, Sequence[object]],
) -> dict[str, object]:
    summaries: list[dict[str, object]] = []
    if any(not isinstance(name, str) for name in columns):
        _violation("diagnostic_schema")
    ordered_names = sorted(
        columns, key=lambda item: hashlib.sha256(item.encode("utf-8")).hexdigest()
    )
    for name in ordered_names:
        if not isinstance(name, str):
            _violation("diagnostic_schema")
        if isinstance(columns[name], (str, bytes)):
            _violation("diagnostic_schema")
        counts: Counter[str] = Counter()
        numeric = True
        distinct_types: set[str] = set()
        for value in columns[name]:
            if value is None:
                counts["missing"] += 1
                continue
            if isinstance(value, bool):
                distinct_types.add("boolean")
                numeric = False
                counts["boolean"] += 1
            elif isinstance(value, int):
                distinct_types.add("numeric")
                if value < 0:
                    counts["negative"] += 1
                elif value == 0:
                    counts["zero"] += 1
                else:
                    counts["positive"] += 1
            elif isinstance(value, float):
                distinct_types.add("numeric")
                if not math.isfinite(value):
                    counts["nonfinite"] += 1
                elif value < 0:
                    counts["negative"] += 1
                elif value == 0:
                    counts["zero"] += 1
                else:
                    counts["positive"] += 1
            else:
                distinct_types.add("text")
                numeric = False
                counts["text"] += 1
        logical_type = "numeric" if numeric and distinct_types <= {"numeric"} else "mixed"
        if distinct_types == {"text"}:
            logical_type = "text"
        elif distinct_types == {"boolean"}:
            logical_type = "boolean"
        elif not distinct_types:
            logical_type = "empty"
        summaries.append(
            {
                "column_name_hash": hashlib.sha256(name.encode("utf-8")).hexdigest(),
                "logical_type": logical_type,
                "count": sum(counts.values()),
                "value_class_counts": dict(sorted(counts.items())),
            }
        )
    return {
        "schema_version": "1",
        "rules_version": _RULES_VERSION,
        "rules": list(_RULES),
        "columns": summaries,
    }


def _preview_file(logical_name: str, purpose: str, content: bytes) -> PreviewFile:
    return PreviewFile(logical_name, purpose, content, hashlib.sha256(content).hexdigest())


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")


def _field_counts(payloads: Sequence[object]) -> dict[str, int]:
    counts: Counter[str] = Counter()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                counts[str(key)] += 1
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    for payload in payloads:
        visit(payload)
    return dict(sorted(counts.items()))


def _scan_output(value: object, *, key: str | None = None) -> None:
    if isinstance(value, dict):
        for nested_key, nested_value in value.items():
            if not isinstance(nested_key, str):
                _violation("diagnostic_schema")
            _scan_output(nested_value, key=nested_key)
    elif isinstance(value, list):
        for nested_value in value:
            _scan_output(nested_value, key=key)
    elif isinstance(value, str):
        if key in {"code", "error_code"}:
            return
        if _contains_forbidden_text(value):
            _violation("diagnostic_schema")


def _contains_forbidden_text(value: str) -> bool:
    if "://" in value or value.startswith(("/", "\\")):
        return True
    patterns = (_WINDOWS_PATH, _POSIX_USER_PATH, _RELATIVE_PATH, _SECRET_VALUE)
    return any(pattern.search(value) is not None for pattern in patterns)


def _parse_structure(value: object) -> StructureSummary:
    item = _mapping(value)
    _only_keys(
        item,
        {"object_type", "row_count", "column_count", "primitive_count", "content_hash"},
        required={"object_type", "row_count", "column_count", "primitive_count", "content_hash"},
    )
    return StructureSummary(
        object_type=_string(item["object_type"]),
        row_count=_integer(item["row_count"]),
        column_count=_integer(item["column_count"]),
        primitive_count=_integer(item["primitive_count"]),
        content_hash=_string(item["content_hash"]),
    )


def _parse_error(value: object) -> SanitizedError:
    item = _mapping(value)
    _only_keys(item, {"code", "stack_trace"}, required={"code"})
    code = _string(item["code"])
    stack = _optional_string(item.get("stack_trace"))
    return SanitizedError.from_stack(code, stack) if stack is not None else SanitizedError(code)


def _parse_transition(value: object) -> TaskTransition:
    item = _mapping(value)
    _only_keys(item, {"state", "stage"}, required={"state", "stage"})
    try:
        state = TaskState(_string(item["state"]))
    except ValueError as error:
        raise LocalSecurityError(
            "DIAGNOSTIC_SCHEMA_VIOLATION", category="diagnostic_schema"
        ) from error
    return TaskTransition(state=state, stage=_string(item["stage"]))


def _only_keys(
    value: Mapping[str, object], allowed: set[str], *, required: set[str]
) -> None:
    if set(value) - allowed or required - set(value):
        _violation("diagnostic_schema")


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _violation("diagnostic_schema")
    return value


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _violation("diagnostic_schema")
    return value


def _string(value: object) -> str:
    if not isinstance(value, str):
        _violation("diagnostic_schema")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _string(value)


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _violation("diagnostic_schema")
    return value


def _string_mapping(value: object) -> Mapping[str, str]:
    result: dict[str, str] = {}
    for name, nested in _mapping(value).items():
        if not isinstance(name, str):
            _violation("diagnostic_schema")
        result[name] = _string(nested)
    return result


def _violation(category: str) -> NoReturn:
    raise LocalSecurityError("DIAGNOSTIC_SCHEMA_VIOLATION", category=category)
