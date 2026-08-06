"""Minimal cooperative task controls and bounded worker capacity."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import ParamSpec, TypeVar

from plotagent.desktop_core.protocol import JsonValue, is_identifier

_P = ParamSpec("_P")
_R = TypeVar("_R")

_ACTIVE_STATES = {"queued", "preparing", "running", "committing", "cancelling"}
_CANCELLABLE_STATES = {"queued", "preparing", "running"}
_PROGRESS_UNITS = {"rows", "files", "plots", "bytes", "steps"}
_LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"preparing", "cancelling", "interrupted"}),
    "preparing": frozenset({"running", "cancelling", "failed", "interrupted"}),
    "running": frozenset({"committing", "cancelling", "failed", "interrupted"}),
    "committing": frozenset({"succeeded", "failed", "partially_succeeded", "interrupted"}),
    "cancelling": frozenset({"cancelled", "committing", "partially_succeeded", "interrupted"}),
    "succeeded": frozenset(),
    "cancelled": frozenset(),
    "failed": frozenset(),
    "partially_succeeded": frozenset(),
    "interrupted": frozenset(),
}


class TaskControlError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise TaskControlError("TASK_CANCELLED", "The task was cancelled.")


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    state: str
    sequence: int
    token: CancellationToken
    progress: dict[str, JsonValue] | None = None


type TaskNotifier = Callable[[dict[str, JsonValue]], None]


class TaskRegistry:
    """Own task state and cooperative tokens on the synchronous control channel."""

    def __init__(self, notifier: TaskNotifier | None = None) -> None:
        self._notifier = notifier or (lambda _event: None)
        self._records: dict[str, TaskRecord] = {}
        self._lock = threading.RLock()

    def register(self, task_id: str, *, state: str = "queued") -> CancellationToken:
        if not is_identifier(task_id) or state not in _LEGAL_TRANSITIONS:
            raise ValueError("invalid task registration")
        with self._lock:
            if task_id in self._records:
                raise ValueError("task id is already registered")
            token = CancellationToken()
            record = TaskRecord(task_id=task_id, state=state, sequence=0, token=token)
            self._records[task_id] = record
            event = self._event(record)
        self._notifier(event)
        return token

    def transition(
        self,
        task_id: str,
        state: str,
        *,
        progress: dict[str, JsonValue] | None = None,
    ) -> None:
        _validate_progress(progress)
        with self._lock:
            record = self._require(task_id)
            if state not in _LEGAL_TRANSITIONS[record.state]:
                raise TaskControlError(
                    "TASK_STATE_INVALID",
                    "The requested task state transition was invalid.",
                )
            record.state = state
            record.sequence += 1
            record.progress = progress
            event = self._event(record)
        self._notifier(event)

    def cancel(self, task_id: str) -> dict[str, JsonValue]:
        with self._lock:
            record = self._require(task_id)
            if record.state not in _CANCELLABLE_STATES:
                raise TaskControlError(
                    "TASK_NOT_CANCELLABLE",
                    "The task cannot be cancelled in its current state.",
                )
            record.token.cancel()
            previous_state = record.state
            record.state = "cancelling"
            record.sequence += 1
            cancelling_event = self._event(record)
        self._notifier(cancelling_event)

        if previous_state == "queued":
            self.transition(task_id, "cancelled")
        with self._lock:
            current = self._require(task_id)
            return {
                "task_id": current.task_id,
                "state": current.state,
                "cancel_requested": True,
            }

    def cancel_all(self) -> tuple[str, ...]:
        with self._lock:
            task_ids = [
                record.task_id
                for record in self._records.values()
                if record.state in _CANCELLABLE_STATES
            ]
        for task_id in task_ids:
            self.cancel(task_id)
        return tuple(task_ids)

    def snapshot(self) -> dict[str, JsonValue]:
        with self._lock:
            tasks: list[JsonValue] = [
                {
                    "task_id": record.task_id,
                    "sequence": record.sequence,
                    "state": record.state,
                    "cancellable": record.state in _CANCELLABLE_STATES,
                    **({"progress": record.progress} if record.progress is not None else {}),
                }
                for record in self._records.values()
            ]
            return {
                "tasks": tasks,
                "active_task_count": sum(
                    record.state in _ACTIVE_STATES for record in self._records.values()
                ),
                "has_committing_task": any(
                    record.state == "committing" for record in self._records.values()
                ),
            }

    def token(self, task_id: str) -> CancellationToken:
        with self._lock:
            return self._require(task_id).token

    def state(self, task_id: str) -> str:
        with self._lock:
            return self._require(task_id).state

    def _require(self, task_id: str) -> TaskRecord:
        record = self._records.get(task_id)
        if record is None:
            raise TaskControlError("TASK_NOT_FOUND", "The requested task was not found.")
        return record

    @staticmethod
    def _event(record: TaskRecord) -> dict[str, JsonValue]:
        return {
            "schema_version": "1.0",
            "event_type": "task.state",
            "task_id": record.task_id,
            "sequence": record.sequence,
            "state": record.state,
            **({"progress": record.progress} if record.progress is not None else {}),
        }


class WorkerCapacityError(Exception):
    pass


class BoundedWorkerExecutor:
    """Thread executor with a hard bound on running plus queued work."""

    def __init__(self, max_workers: int = 2, maximum_pending: int = 4) -> None:
        if max_workers < 1 or maximum_pending < max_workers:
            raise ValueError("invalid worker capacity")
        self.max_workers = max_workers
        self.maximum_pending = maximum_pending
        self._slots = threading.BoundedSemaphore(maximum_pending)
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="plotagent-core-worker",
        )
        self._closed = False
        self._lock = threading.Lock()

    def submit(self, function: Callable[_P, _R], *args: _P.args, **kwargs: _P.kwargs) -> Future[_R]:
        with self._lock:
            if self._closed or not self._slots.acquire(blocking=False):
                raise WorkerCapacityError("worker capacity is exhausted")
            try:
                future = self._executor.submit(function, *args, **kwargs)
            except BaseException:
                self._slots.release()
                raise
        future.add_done_callback(lambda _future: self._slots.release())
        return future

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=True)


def _validate_progress(progress: dict[str, JsonValue] | None) -> None:
    if progress is None:
        return
    if set(progress) not in ({"completed", "unit"}, {"completed", "total", "unit"}):
        raise ValueError("invalid task progress")
    completed = progress["completed"]
    total = progress.get("total")
    unit = progress["unit"]
    if (
        not isinstance(completed, int)
        or isinstance(completed, bool)
        or completed < 0
        or not isinstance(unit, str)
        or unit not in _PROGRESS_UNITS
        or (
            total is not None
            and (not isinstance(total, int) or isinstance(total, bool) or total < completed)
        )
    ):
        raise ValueError("invalid task progress")
