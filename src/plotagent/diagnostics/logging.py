"""Strict allowlist-only local structured logging."""

from __future__ import annotations

import json
import os
import re
import stat
import uuid
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Final

from plotagent.security.errors import LocalSecurityError


class TaskState(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    COMMITTING = "committing"
    SUCCEEDED = "succeeded"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"
    PARTIALLY_SUCCEEDED = "partially_succeeded"
    INTERRUPTED = "interrupted"


class CountBucket(StrEnum):
    ZERO = "0"
    ONE = "1"
    TWO_TO_NINE = "2-9"
    TEN_TO_99 = "10-99"
    HUNDRED_TO_999 = "100-999"
    THOUSAND_TO_9999 = "1k-9k"
    TEN_THOUSAND_TO_99999 = "10k-99k"
    HUNDRED_THOUSAND_PLUS = "100k+"


class PerformanceBucket(StrEnum):
    UNDER_100_MS = "under_100_ms"
    UNDER_1_S = "100_ms_to_1_s"
    UNDER_10_S = "1_s_to_10_s"
    UNDER_60_S = "10_s_to_60_s"
    SIXTY_S_PLUS = "60_s_plus"


_STABLE_TOKEN: Final = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_VERSION_TOKEN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+\-]{0,63}$")
_CHART_ID: Final = re.compile(r"^[A-Z][0-9]{2}$")
_SECRETISH: Final = re.compile(
    r"(?i)(?:^sk-|api[_-]?key|password|credential|authorization|bearer)"
)
_SEGMENT_STAMP: Final = re.compile(r"^plotagent-(\d{8}T\d{6})-[a-f0-9]{32}\.jsonl$")
_STACK_FILE: Final = re.compile(
    r'^\s*File\s+["\'].*?["\'],\s+line\s+(\d+),\s+in\s+([A-Za-z_][A-Za-z0-9_]*)\s*$'
)
_EXCEPTION_TYPE: Final = re.compile(
    r"^(?:[A-Za-z_][A-Za-z0-9_]*\.)*[A-Za-z_][A-Za-z0-9_]*(?=:)"
)


@dataclass(frozen=True, slots=True)
class LocalLogRecord:
    """The only fields allowed to reach local log storage."""

    event_code: str
    app_version: str | None = None
    protocol_version: str | None = None
    schema_version: str | None = None
    renderer_version: str | None = None
    adapter_version: str | None = None
    dependency_version: str | None = None
    task_state: TaskState | None = None
    task_stage: str | None = None
    object_type: str | None = None
    chart_id: str | None = None
    duration_bucket: PerformanceBucket | None = None
    performance_bucket: PerformanceBucket | None = None
    row_count_bucket: CountBucket | None = None
    column_count_bucket: CountBucket | None = None
    primitive_count_bucket: CountBucket | None = None
    error_code: str | None = None
    feature_enabled: bool | None = None
    stack_trace: str | None = None

    def __post_init__(self) -> None:
        _require_stable_token(self.event_code)
        for value in (
            self.app_version,
            self.protocol_version,
            self.schema_version,
            self.renderer_version,
            self.adapter_version,
            self.dependency_version,
        ):
            if value is not None and (
                _VERSION_TOKEN.fullmatch(value) is None or _SECRETISH.search(value)
            ):
                raise LocalSecurityError("LOG_SCHEMA_VIOLATION", category="log_schema")
        for value in (self.task_stage, self.object_type, self.error_code):
            if value is not None:
                _require_stable_token(value)
        if self.chart_id is not None and _CHART_ID.fullmatch(self.chart_id) is None:
            raise LocalSecurityError("LOG_SCHEMA_VIOLATION", category="log_schema")

    def to_storage_dict(self, timestamp: datetime) -> dict[str, object]:
        result: dict[str, object] = {
            "timestamp": timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "event_code": self.event_code,
        }
        for item in fields(self):
            if item.name in {"event_code", "stack_trace"}:
                continue
            value = getattr(self, item.name)
            if value is not None:
                result[item.name] = value.value if isinstance(value, StrEnum) else value
        if self.stack_trace is not None:
            scrubbed = scrub_stack_trace(self.stack_trace)
            if scrubbed:
                result["scrubbed_stack"] = scrubbed
        return result


@dataclass(frozen=True, slots=True)
class LogRetentionPolicy:
    max_age: timedelta = timedelta(days=14)
    max_total_bytes: int = 100 * 1024 * 1024
    max_segment_bytes: int = 5 * 1024 * 1024

    def __post_init__(self) -> None:
        if not timedelta(0) < self.max_age <= timedelta(days=14):
            raise ValueError("log retention cannot exceed 14 days")
        if not 0 < self.max_total_bytes <= 100 * 1024 * 1024:
            raise ValueError("log retention cannot exceed 100 MB")
        if not 0 < self.max_segment_bytes <= self.max_total_bytes:
            raise ValueError("segment size must fit within total retention")


class StructuredLocalLogger:
    """Append canonical JSON records and enforce age/size retention on every write."""

    def __init__(
        self,
        log_directory: Path,
        *,
        retention: LogRetentionPolicy | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._directory = log_directory
        self._retention = retention or LogRetentionPolicy()
        self._now = now or (lambda: datetime.now(UTC))
        self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._active_created_at = self._now().astimezone(UTC)
        self._active = self._new_segment_path(self._active_created_at)
        self._active.touch(exist_ok=False)
        os.chmod(self._active, stat.S_IREAD | stat.S_IWRITE)
        self.prune()

    def write(self, record: LocalLogRecord) -> None:
        timestamp = self._now().astimezone(UTC)
        encoded = (
            json.dumps(
                record.to_storage_dict(timestamp),
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
            + b"\n"
        )
        if len(encoded) > self._retention.max_segment_bytes:
            raise LocalSecurityError("LOG_RECORD_TOO_LARGE", category="log_schema")
        if timestamp - self._active_created_at >= self._retention.max_age:
            self._active_created_at = timestamp
            self._active = self._new_segment_path(timestamp)
            self._active.touch(exist_ok=False)
            os.chmod(self._active, stat.S_IREAD | stat.S_IWRITE)
        self.prune()
        if self._active.stat().st_size + len(encoded) > self._retention.max_segment_bytes:
            self._active_created_at = timestamp
            self._active = self._new_segment_path(timestamp)
            self._active.touch(exist_ok=False)
            os.chmod(self._active, stat.S_IREAD | stat.S_IWRITE)
        with self._active.open("ab") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        self.prune()

    def prune(self) -> None:
        now = self._now().astimezone(UTC)
        candidates = self._segments()
        for path in candidates:
            created = self._segment_created_at(path)
            if now - created >= self._retention.max_age and path != self._active:
                path.unlink()

        candidates = self._segments()
        total = sum(path.stat().st_size for path in candidates)
        for path in sorted(candidates, key=lambda candidate: candidate.stat().st_mtime):
            if total <= self._retention.max_total_bytes:
                break
            if path == self._active:
                continue
            size = path.stat().st_size
            path.unlink()
            total -= size

    def _segments(self) -> list[Path]:
        result: list[Path] = []
        for path in self._directory.glob("plotagent-*.jsonl"):
            try:
                mode = path.lstat().st_mode
            except OSError:
                continue
            if stat.S_ISREG(mode) and not path.is_symlink():
                result.append(path)
        return result

    def _new_segment_path(self, created_at: datetime) -> Path:
        stamp = created_at.strftime("%Y%m%dT%H%M%S")
        return self._directory / f"plotagent-{stamp}-{uuid.uuid4().hex}.jsonl"

    @staticmethod
    def _segment_created_at(path: Path) -> datetime:
        match = _SEGMENT_STAMP.fullmatch(path.name)
        if match is not None:
            return datetime.strptime(match.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        return datetime.fromtimestamp(path.stat().st_mtime, UTC)


def scrub_stack_trace(stack_trace: str) -> str:
    """Keep frame shape and exception type, dropping paths, code, and messages."""

    sanitized: list[str] = []
    for line in stack_trace.splitlines():
        frame = _STACK_FILE.match(line)
        if frame is not None:
            sanitized.append(f'File "<path>", line {frame.group(1)}, in {frame.group(2)}')
            continue
        exception_type = _EXCEPTION_TYPE.match(line.strip())
        if exception_type is not None:
            sanitized.append(exception_type.group(0))
    return "\n".join(sanitized)


def _require_stable_token(value: str) -> None:
    if _STABLE_TOKEN.fullmatch(value) is None:
        raise LocalSecurityError("LOG_SCHEMA_VIOLATION", category="log_schema")
