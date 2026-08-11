from __future__ import annotations

import json
from pathlib import Path

import pytest

from plotagent.engine.backends.origin.trace import (
    OriginExecutionTrace,
    origin_trace_step,
)


def _rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_execution_trace_records_order_duration_and_failure(tmp_path: Path) -> None:
    trace = OriginExecutionTrace(
        path=tmp_path / "execution-trace.jsonl",
        profile_id="K24",
        plot_id="plot:k24",
        plot_version=2,
    )
    trace.reset()
    with trace.activate():
        with origin_trace_step("workbook_create", details={"columns": 3}):
            pass
        with pytest.raises(RuntimeError, match="readback failed"), origin_trace_step(
            "fresh_readback"
        ):
            raise RuntimeError("readback failed")

    rows = _rows(trace.path)
    assert [(row["step"], row["status"]) for row in rows] == [
        ("workbook_create", "started"),
        ("workbook_create", "completed"),
        ("fresh_readback", "started"),
        ("fresh_readback", "failed"),
    ]
    assert [row["sequence"] for row in rows] == [1, 2, 3, 4]
    assert rows[1]["details"] == {"columns": 3}
    assert isinstance(rows[1]["duration_seconds"], float)
    assert rows[-1]["error"] == {
        "message": "readback failed",
        "type": "RuntimeError",
    }
    assert all(row["profile_id"] == "K24" for row in rows)
    assert all(row["plot_version"] == 2 for row in rows)


def test_trace_step_is_noop_outside_worker_context() -> None:
    with origin_trace_step("unscoped"):
        pass
