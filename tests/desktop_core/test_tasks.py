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


def test_progress_update_keeps_state_and_increments_event_sequence() -> None:
    events: list[dict[str, object]] = []
    registry = TaskRegistry(events.append)
    registry.register("task:progress", state="running")

    registry.update_progress(
        "task:progress",
        {"completed": 2, "total": 5, "unit": "steps"},
    )

    assert events[-1]["state"] == "running"
    assert events[-1]["sequence"] == 1
    assert events[-1]["progress"] == {"completed": 2, "total": 5, "unit": "steps"}


def test_task_metadata_and_failure_reason_are_preserved_in_events_and_snapshot() -> None:
    events: list[dict[str, object]] = []
    registry = TaskRegistry(events.append)
    registry.register(
        "task:import",
        kind="import",
        label="导入 measurements.csv",
    )
    registry.transition("task:import", "preparing")
    registry.fail(
        "task:import",
        code="IMPORT_HEADER_AMBIGUOUS",
        message="无法确定表头，请指定表头行。",
    )

    assert events[-1]["task_kind"] == "import"
    assert events[-1]["label"] == "导入 measurements.csv"
    assert events[-1]["error"] == {
        "code": "IMPORT_HEADER_AMBIGUOUS",
        "message": "无法确定表头，请指定表头行。",
    }
    assert registry.snapshot()["tasks"] == [
        {
            "task_id": "task:import",
            "sequence": 2,
            "state": "failed",
            "cancellable": False,
            "task_kind": "import",
            "label": "导入 measurements.csv",
            "error": {
                "code": "IMPORT_HEADER_AMBIGUOUS",
                "message": "无法确定表头，请指定表头行。",
            },
        }
    ]


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
