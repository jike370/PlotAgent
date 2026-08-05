from __future__ import annotations

import threading

import pytest

from plotagent.desktop_core.tasks import (
    BoundedWorkerExecutor,
    TaskControlError,
    TaskRegistry,
    WorkerCapacityError,
)


def test_cooperative_cancel_sets_token_and_emits_task_state() -> None:
    events: list[dict[str, object]] = []
    registry = TaskRegistry(events.append)
    token = registry.register("task:running", state="running")

    result = registry.cancel("task:running")

    assert token.is_cancelled
    assert result == {
        "task_id": "task:running",
        "state": "cancelling",
        "cancel_requested": True,
    }
    assert events[-1] == {
        "schema_version": "1.0",
        "event_type": "task.state",
        "task_id": "task:running",
        "sequence": 1,
        "state": "cancelling",
    }
    assert registry.snapshot()["active_task_count"] == 1


def test_committing_task_is_not_cancellable() -> None:
    registry = TaskRegistry()
    registry.register("task:commit", state="committing")
    with pytest.raises(TaskControlError, match="TASK_NOT_CANCELLABLE"):
        registry.cancel("task:commit")


def test_worker_executor_rejects_work_beyond_its_bound() -> None:
    release = threading.Event()
    executor = BoundedWorkerExecutor(max_workers=1, maximum_pending=1)
    first = executor.submit(release.wait, 2)
    try:
        with pytest.raises(WorkerCapacityError):
            executor.submit(lambda: None)
    finally:
        release.set()
        first.result(timeout=2)
        executor.shutdown()
