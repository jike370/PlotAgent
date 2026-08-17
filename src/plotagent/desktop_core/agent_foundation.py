"""Core-owned next-action projection for Agent foundation v2."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal, TypedDict

from plotagent.contracts.agent_tasks import (
    TERMINAL_TASK_STATES,
    ActivationBudget,
    AgentActivation,
    TaskCheckpoint,
    TaskState,
)
from plotagent.tasking import TaskLedgerRepository

_INVESTIGATION_TOOLS = (
    "list_chart_catalog",
    "get_chart_knowledge",
    "compare_chart_profiles",
    "get_calculation_contract",
    "get_domain_example",
    "list_sources",
    "inspect_source",
    "preview_rows",
    "sample_rows",
    "profile_field",
    "search_values",
    "compare_schemas",
    "inspect_instrument_metadata",
)

type WaitReason = Literal[
    "idle",
    "awaiting_input",
    "awaiting_confirmation",
    "awaiting_reconfirmation",
    "blocked",
    "terminal",
    "execution_pending",
    "verification_pending",
    "delivery_pending",
]


class RunActivationDirective(TypedDict):
    kind: Literal["run_activation"]
    activation: dict[str, object]


class WaitDirective(TypedDict):
    kind: Literal["wait"]
    reason: WaitReason
    task_state: TaskState


type TaskPumpDirective = RunActivationDirective | WaitDirective


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class DurableTaskCoordinator:
    """Decide one durable next action without delegating state authority to Main."""

    def __init__(
        self,
        ledger: TaskLedgerRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._ledger = ledger
        self._clock = clock or (lambda: datetime.now(UTC))

    def next_action(self, task_id: str) -> TaskPumpDirective:
        checkpoint = self._ledger.get_task(task_id)
        if checkpoint.active_activation_id is not None:
            activation, status = self._ledger.get_activation(checkpoint.active_activation_id)
            if status in {"requested", "running"}:
                return {
                    "kind": "run_activation",
                    "activation": activation.model_dump(mode="json"),
                }
            raise RuntimeError("active activation has a terminal runtime status")

        if checkpoint.state == "created":
            activation = self._new_activation(checkpoint)
            self._ledger.start_activation(activation)
            return {
                "kind": "run_activation",
                "activation": activation.model_dump(mode="json"),
            }
        if checkpoint.state == "intent_staged":
            checkpoint = self._ledger.advance(
                task_id,
                expected_task_version=checkpoint.task_version,
                next_state="awaiting_confirmation",
                reason_code="INTENT_PRESENTED",
            )
        return self._wait(checkpoint)

    def _new_activation(self, checkpoint: TaskCheckpoint) -> AgentActivation:
        envelope = self._ledger.get_envelope(checkpoint.task_id)
        now = self._clock().astimezone(UTC)
        budget = ActivationBudget()
        return AgentActivation(
            activation_id=f"activation:{uuid.uuid4().hex}",
            task_id=checkpoint.task_id,
            task_version=checkpoint.task_version,
            reason="new_task",
            task_state=checkpoint.state,
            original_instruction=envelope.original_instruction,
            allowed_tools=_INVESTIGATION_TOOLS,
            permission_phase="p0_read",
            activation_budget=budget,
            task_budget=checkpoint.budget,
            deadline=_iso(now + timedelta(milliseconds=budget.timeout_ms)),
            created_at=_iso(now),
        )

    @staticmethod
    def _wait(checkpoint: TaskCheckpoint) -> WaitDirective:
        if checkpoint.state == "awaiting_input":
            reason: WaitReason = "awaiting_input"
        elif checkpoint.state == "awaiting_confirmation":
            reason = "awaiting_confirmation"
        elif checkpoint.state == "awaiting_reconfirmation":
            reason = "awaiting_reconfirmation"
        elif checkpoint.state == "blocked":
            reason = "blocked"
        elif checkpoint.state == "executing":
            reason = "execution_pending"
        elif checkpoint.state in {"verifying", "repairing"}:
            reason = "verification_pending"
        elif checkpoint.state in {"delivering", "partial"}:
            reason = "delivery_pending"
        elif checkpoint.state in TERMINAL_TASK_STATES or checkpoint.state == "cancelling":
            reason = "terminal"
        else:
            reason = "idle"
        return {"kind": "wait", "reason": reason, "task_state": checkpoint.state}
