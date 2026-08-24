from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from plotagent.desktop_core.agent_execution import DurableTaskExecutionService
from plotagent.workflows.data_ops import WorkflowDataError


@dataclass(frozen=True)
class _Item:
    item_id: str
    task_kind: str


@dataclass(frozen=True)
class _Checkpoint:
    state: str = "awaiting_confirmation"

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {"task_id": "task:preview", "state": self.state}


@dataclass(frozen=True)
class _Plan:
    items: tuple[_Item, ...]

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {
            "plan_id": "plan:preview",
            "items": [
                {"item_id": item.item_id, "task_kind": item.task_kind} for item in self.items
            ],
        }


@dataclass(frozen=True)
class _Ledger:
    plan: _Plan

    def get_task(self, task_id: str) -> _Checkpoint:
        assert task_id == "task:preview"
        return _Checkpoint()

    def get_plan_with_hash(self, task_id: str) -> tuple[_Plan, str]:
        assert task_id == "task:preview"
        return self.plan, "a" * 64


class _Workflow:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def preview_compiled_item(self, item: _Item, *, limit: int) -> dict[str, object]:
        self.calls.append(item.item_id)
        assert limit == 3
        if item.item_id == "item:invalid":
            raise WorkflowDataError(
                "WORKFLOW_NON_ISOMORPHIC",
                "整理后的字段名称、类型或单位仍不一致。",
            )
        return {
            "item_id": item.item_id,
            "output_row_count": 4,
            "output_field_count": 3,
        }


def test_plan_view_surfaces_exact_previews_and_per_item_errors_without_hiding_plan() -> None:
    plan = _Plan(
        items=(
            _Item("item:valid", "create"),
            _Item("item:invalid", "create"),
            _Item("item:edit", "edit"),
        )
    )
    workflow = _Workflow()
    service = DurableTaskExecutionService(
        store=cast(Any, None),
        domain=cast(Any, None),
        engine=cast(Any, None),
        workflow=cast(Any, workflow),
        ledger=cast(Any, _Ledger(plan)),
    )

    view = service.plan_view("task:preview")

    assert workflow.calls == ["item:valid", "item:invalid"]
    assert view["plan"] == plan.model_dump(mode="json")
    assert view["prepared_previews"] == [
        {"item_id": "item:valid", "output_row_count": 4, "output_field_count": 3}
    ]
    assert view["prepared_preview_errors"] == [
        {
            "item_id": "item:invalid",
            "code": "WORKFLOW_NON_ISOMORPHIC",
            "message": "整理后的字段名称、类型或单位仍不一致。",
        }
    ]
    assert view["confirmation_state"] == "pending"
