"""Append-only execution evidence for sealed Origin renderer workers."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any


def _json_value(value: Any) -> Any:
    """Return a deterministic, JSON-safe diagnostic value."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return repr(value)


@dataclass(slots=True)
class OriginExecutionTrace:
    """Write ordered renderer steps next to the staged OPJU artifact."""

    path: Path
    profile_id: str
    plot_id: str
    plot_version: int
    _sequence: int = field(default=0, init=False)
    _started_at: float = field(default_factory=perf_counter, init=False)

    def reset(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")
        self._sequence = 0
        self._started_at = perf_counter()

    def record(
        self,
        step: str,
        status: str,
        *,
        details: Mapping[str, Any] | None = None,
        duration_seconds: float | None = None,
        error: BaseException | None = None,
    ) -> None:
        self._sequence += 1
        payload: dict[str, Any] = {
            "schema_version": 1,
            "sequence": self._sequence,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "elapsed_seconds": round(perf_counter() - self._started_at, 6),
            "worker_pid": os.getpid(),
            "profile_id": self.profile_id,
            "plot_id": self.plot_id,
            "plot_version": self.plot_version,
            "step": step,
            "status": status,
            "details": _json_value(details or {}),
        }
        if duration_seconds is not None:
            payload["duration_seconds"] = round(duration_seconds, 6)
        if error is not None:
            payload["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            stream.write("\n")

    @contextmanager
    def activate(self) -> Iterator[None]:
        token: Token[OriginExecutionTrace | None] = _ACTIVE_TRACE.set(self)
        try:
            yield
        finally:
            _ACTIVE_TRACE.reset(token)

    @contextmanager
    def step(
        self, step: str, *, details: Mapping[str, Any] | None = None
    ) -> Iterator[None]:
        started_at = perf_counter()
        self.record(step, "started", details=details)
        try:
            yield
        except BaseException as exc:
            self.record(
                step,
                "failed",
                details=details,
                duration_seconds=perf_counter() - started_at,
                error=exc,
            )
            raise
        self.record(
            step,
            "completed",
            details=details,
            duration_seconds=perf_counter() - started_at,
        )


_ACTIVE_TRACE: ContextVar[OriginExecutionTrace | None] = ContextVar(
    "plotagent_origin_execution_trace", default=None
)


@contextmanager
def origin_trace_step(
    step: str, *, details: Mapping[str, Any] | None = None
) -> Iterator[None]:
    """Record a renderer step when called inside a sealed worker."""

    trace = _ACTIVE_TRACE.get()
    if trace is None:
        yield
        return
    with trace.step(step, details=details):
        yield


def record_origin_trace(
    step: str, status: str, *, details: Mapping[str, Any] | None = None
) -> None:
    trace = _ACTIVE_TRACE.get()
    if trace is not None:
        trace.record(step, status, details=details)
