from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from plotagent.contracts.agent_tasks import AgentIntentReady, TaskEnvelope, TaskIntent
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.workflows import DraftFieldBinding, TaskDraftItem
from plotagent.desktop_core.agent_foundation import DurableTaskCoordinator
from plotagent.storage import ProjectStore
from plotagent.tasking import TaskLedgerRepository

NOW = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)


def envelope() -> TaskEnvelope:
    return TaskEnvelope(
        task_id="task:test",
        task_version=1,
        project_id="project:test",
        project_revision=0,
        original_instruction="Create one K01 line chart.",
        selected_sources=(
            {
                "source_dataset_id": "source:test",
                "source_version": 1,
                "content_hash": "a" * 64,
            },
        ),
        selected_profile_ids=("K01",),
        budget={},
        created_at="2026-08-18T10:00:00Z",
    )


def intent(activation_id: str) -> TaskIntent:
    item = TaskDraftItem(
        task_kind="create",
        item_id="item:test.1",
        plot_alias="plot_1",
        profile_id="K01",
        source_aliases=("data_1",),
        bindings=(
            DraftFieldBinding(
                role="x", source_alias="data_1", field_alias="data_1_field_1"
            ),
            DraftFieldBinding(
                role="y", source_alias="data_1", field_alias="data_1_field_2"
            ),
        ),
    )
    raw = {
        "intent_id": "intent:test",
        "intent_version": 1,
        "task_id": "task:test",
        "task_version": 1,
        "created_by_activation_id": activation_id,
        "summary": "Create one K01 line chart.",
        "items": (item,),
        "context_hash": "a" * 64,
    }
    return TaskIntent(**raw, content_hash=canonical_hash(raw))


def test_next_action_creates_one_idempotent_activation(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        coordinator = DurableTaskCoordinator(ledger, clock=lambda: NOW)

        first = coordinator.next_action("task:test")
        second = coordinator.next_action("task:test")
        assert first == second
        assert first["kind"] == "run_activation"
        activation = first["activation"]
        assert activation["task_version"] == 1
        assert activation["task_state"] == "created"
        assert activation["permission_phase"] == "p0_read"
        assert "inspect_source" in activation["allowed_tools"]
        assert ledger.get_task("task:test").active_activation_id == activation["activation_id"]


def test_context_authority_stays_current_until_yield_then_waits_for_confirmation(
    tmp_path: Path,
) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        coordinator = DurableTaskCoordinator(ledger, clock=lambda: NOW)
        directive = coordinator.next_action("task:test")
        assert directive["kind"] == "run_activation"
        activation_id = str(directive["activation"]["activation_id"])

        running = ledger.mark_activation_running(activation_id)
        assert running.state == "created"
        assert running.task_version == 1
        staged = ledger.accept_yield(
            AgentIntentReady(
                activation_id=activation_id,
                task_id="task:test",
                task_version=1,
                intent=intent(activation_id),
            )
        )
        assert staged.state == "intent_staged"
        assert staged.task_version == 3

        waiting = coordinator.next_action("task:test")
        assert waiting == {
            "kind": "wait",
            "reason": "awaiting_confirmation",
            "task_state": "awaiting_confirmation",
        }
        assert ledger.get_task("task:test").task_version == 4
