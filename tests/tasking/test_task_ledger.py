from __future__ import annotations

import sqlite3

import pytest

from plotagent.contracts.agent_tasks import (
    AgentActivation,
    AgentActivationEvent,
    AgentBudgetExhausted,
    AgentInformationReady,
    AgentIntentReady,
    AgentNeedsInput,
    SideEffectReceipt,
    TaskBudgetLimits,
    TaskCompletion,
    TaskContextUpdate,
    TaskEnvelope,
    TaskIntent,
    ToolReceipt,
    VerificationClaim,
    VerificationReport,
)
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.workflows import DraftFieldBinding, InputQuestion, TaskDraftItem
from plotagent.desktop_core.agent_foundation import DurableTaskCoordinator
from plotagent.storage.errors import StorageErrorCode, StorageProblem
from plotagent.storage.project import ProjectStore
from plotagent.tasking import TaskLedgerRepository
from plotagent.tasking.ledger import USER_TASK_ACTION_TRANSITIONS

HASH_A = "a" * 64
HASH_B = "b" * 64
NOW = "2026-08-18T10:00:00Z"
LATER = "2026-08-18T10:05:00Z"


def test_complete_user_action_state_matrix_is_frozen() -> None:
    assert {
        "answered": (frozenset({"awaiting_input"}), "investigating"),
        "confirmed": (
            frozenset({"awaiting_confirmation", "awaiting_reconfirmation"}),
            "executing",
        ),
        "rejected": (
            frozenset({"awaiting_confirmation", "awaiting_reconfirmation"}),
            "rejected",
        ),
        "corrected": (
            frozenset({"awaiting_confirmation", "awaiting_reconfirmation", "partial"}),
            "investigating",
        ),
        "cancel_requested": (
            frozenset({
                "created", "investigating", "awaiting_input", "intent_staged",
                "awaiting_confirmation", "executing", "verifying", "repairing",
                "awaiting_reconfirmation", "delivering", "partial", "blocked",
            }),
            "cancelling",
        ),
        "partial_accepted": (frozenset({"partial"}), None),
        "retry_requested": (frozenset({"partial"}), "executing"),
        "resumed": (frozenset({"blocked"}), "investigating"),
    } == USER_TASK_ACTION_TRANSITIONS


def envelope(*, task_id: str = "task:test") -> TaskEnvelope:
    return TaskEnvelope(
        task_id=task_id,
        task_version=1,
        project_id="project:test",
        project_revision=0,
        original_instruction="Create a line chart from the selected data.",
        selected_sources=(
            {
                "source_dataset_id": "source:test",
                "source_version": 1,
                "content_hash": HASH_A,
            },
        ),
        budget=TaskBudgetLimits(max_estimated_cost=10),
        created_at=NOW,
    )


def activation(*, task_id: str = "task:test") -> AgentActivation:
    return AgentActivation(
        activation_id="activation:test",
        task_id=task_id,
        task_version=1,
        reason="new_task",
        task_state="created",
        original_instruction="Create a line chart from the selected data.",
        allowed_tools=("inspect_source", "yield_intent"),
        permission_phase="p0_read",
        activation_budget={},
        task_budget={"limits": {"max_estimated_cost": 10}},
        deadline=LATER,
        created_at=NOW,
    )


def intent(*, task_id: str = "task:test") -> TaskIntent:
    item = TaskDraftItem(
        task_kind="create",
        item_id="item:test.1",
        plot_alias="plot_1",
        profile_id="K01",
        source_aliases=("data_1",),
        bindings=(
            DraftFieldBinding(
                role="x",
                source_alias="data_1",
                field_alias="data_1_field_1",
            ),
            DraftFieldBinding(
                role="y",
                source_alias="data_1",
                field_alias="data_1_field_2",
            ),
        ),
    )
    return TaskIntent(
        intent_id="intent:test",
        intent_version=1,
        task_id=task_id,
        task_version=1,
        created_by_activation_id="activation:test",
        summary="Create one line chart.",
        items=(item,),
        context_hash=HASH_A,
        content_hash=HASH_B,
    )


def test_task_is_idempotent_evented_and_restored_after_reopen(tmp_path) -> None:
    workspace = tmp_path / "project"
    with ProjectStore.create(workspace, project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        created = ledger.create_task(envelope())
        duplicate = ledger.create_task(envelope())
        assert duplicate == created
        assert created.state == "created"
        assert created.last_event_sequence == 1
        assert [event.event_type for event in ledger.list_events("task:test")] == [
            "task_state_transition"
        ]

    with ProjectStore.open(workspace) as reopened:
        restored = TaskLedgerRepository(reopened).get_task("task:test")
        assert restored == created
        assert TaskLedgerRepository(reopened).get_envelope("task:test") == envelope()


def test_core_rejects_illegal_and_stale_state_transitions(tmp_path) -> None:
    with ProjectStore.create(
        tmp_path / "project", project_id="project:test"
    ) as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        investigating = ledger.advance(
            "task:test",
            expected_task_version=1,
            next_state="investigating",
            reason_code="TEST_START",
        )
        assert investigating.task_version == 2

        with pytest.raises(StorageProblem) as stale:
            ledger.advance(
                "task:test",
                expected_task_version=1,
                next_state="awaiting_input",
                reason_code="STALE",
            )
        assert stale.value.code == StorageErrorCode.VERSION_CONFLICT

        with pytest.raises(StorageProblem) as illegal:
            ledger.advance(
                "task:test",
                expected_task_version=2,
                next_state="delivering",
                reason_code="SKIP_VERIFICATION",
            )
        assert illegal.value.code == StorageErrorCode.VERSION_CONFLICT
        assert ledger.get_task("task:test") == investigating


def test_activation_needs_input_and_user_answer_are_ordered(tmp_path) -> None:
    with ProjectStore.create(
        tmp_path / "project", project_id="project:test"
    ) as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        requested = ledger.start_activation(activation())
        assert requested.active_activation_id == "activation:test"
        assert ledger.start_activation(activation()) == requested
        running = ledger.mark_activation_running("activation:test")
        assert running.state == "created"
        assert running.task_version == 1
        assert running.active_activation_id == "activation:test"

        waiting = ledger.accept_yield(
            AgentNeedsInput(
                activation_id="activation:test",
                task_id="task:test",
                task_version=1,
                questions=(
                    InputQuestion(
                        question_key="question:chart",
                        prompt="Which selected column is the Y value?",
                        answer_kind="field",
                        required=True,
                    ),
                ),
            )
        )
        assert waiting.state == "awaiting_input"
        assert waiting.active_activation_id is None

        resumed = ledger.record_user_event(
            "task:test",
            expected_task_version=waiting.task_version,
            action="answered",
            user_event_id="user-event:answer.1",
            payload_hash=HASH_A,
            message="Use the second numeric column.",
        )
        assert resumed.state == "investigating"
        assert (
            ledger.record_user_event(
                "task:test",
                expected_task_version=waiting.task_version,
                action="answered",
                user_event_id="user-event:answer.1",
                payload_hash=HASH_A,
                message="Use the second numeric column.",
            )
            == resumed
        )
        with pytest.raises(StorageProblem) as conflict:
            ledger.record_user_event(
                "task:test",
                expected_task_version=resumed.task_version,
                action="answered",
                user_event_id="user-event:answer.1",
                payload_hash=HASH_B,
                message="Use the second numeric column.",
            )
        assert conflict.value.code == StorageErrorCode.IDEMPOTENCY_CONFLICT
        sequences = [event.sequence for event in ledger.list_events("task:test")]
        assert sequences == list(range(1, len(sequences) + 1))


def test_user_answer_durably_replaces_effective_context_without_mutating_envelope(
    tmp_path,
) -> None:
    workspace = tmp_path / "context-update-project"
    with ProjectStore.create(
        workspace, project_id="project:test"
    ) as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        ledger.advance(
            "task:test",
            expected_task_version=1,
            next_state="investigating",
            reason_code="TEST_START",
        )
        waiting = ledger.advance(
            "task:test",
            expected_task_version=2,
            next_state="awaiting_input",
            reason_code="TEST_QUESTION",
        )
        context_update = TaskContextUpdate(
            project_revision=2,
            selected_plots=(
                {
                    "plot_id": "plot:chosen",
                    "plot_version": 7,
                    "profile_id": "X38",
                },
            ),
            selected_profile_ids=("X38",),
        )

        answered = ledger.record_user_event(
            "task:test",
            expected_task_version=waiting.task_version,
            action="answered",
            user_event_id="user-event:context-update",
            payload_hash=HASH_B,
            message="Use @plot:chosen.",
            context_update=context_update,
        )

        assert answered.project_revision == 2
        assert ledger.get_envelope("task:test") == envelope()
        effective = ledger.get_effective_envelope("task:test")
        assert effective.project_revision == 2
        assert effective.selected_sources == envelope().selected_sources
        assert [plot.plot_id for plot in effective.selected_plots] == ["plot:chosen"]
        assert effective.selected_plots[0].plot_version == 7
        assert effective.selected_profile_ids == ("X38",)
        assert (
            ledger.record_user_event(
                "task:test",
                expected_task_version=waiting.task_version,
                action="answered",
                user_event_id="user-event:context-update",
                payload_hash=HASH_B,
                message="Use @plot:chosen.",
                context_update=context_update,
            )
            == answered
        )

    with ProjectStore.open(workspace) as reopened:
        restored = TaskLedgerRepository(reopened)
        assert restored.get_envelope("task:test") == envelope()
        effective = restored.get_effective_envelope("task:test")
        assert effective.project_revision == 2
        assert effective.selected_plots[0].plot_id == "plot:chosen"
        assert effective.selected_plots[0].plot_version == 7


def test_waiting_input_checkpoint_survives_restart_without_new_activation(
    tmp_path,
) -> None:
    workspace = tmp_path / "awaiting-input-project"
    with ProjectStore.create(workspace, project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        ledger.start_activation(activation())
        ledger.mark_activation_running("activation:test")
        waiting = ledger.accept_yield(
            AgentNeedsInput(
                activation_id="activation:test",
                task_id="task:test",
                task_version=1,
                questions=(
                    InputQuestion(
                        question_key="question:chart",
                        prompt="Which chart should be used?",
                        answer_kind="text",
                        required=True,
                    ),
                ),
            )
        )
        assert waiting.state == "awaiting_input"

    with ProjectStore.open(workspace) as reopened:
        repository = TaskLedgerRepository(reopened)
        restored = repository.get_task("task:test")
        assert restored == waiting
        assert restored.active_activation_id is None
        yielded = repository.latest_yield("task:test")
        assert isinstance(yielded, AgentNeedsInput)
        assert yielded.questions[0].prompt == "Which chart should be used?"


def test_budget_exhaustion_is_terminal_without_a_fake_resume_path(tmp_path) -> None:
    with ProjectStore.create(tmp_path / "budget-project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        ledger.start_activation(activation())
        ledger.mark_activation_running("activation:test")
        failed = ledger.accept_yield(
            AgentBudgetExhausted(
                activation_id="activation:test",
                task_id="task:test",
                task_version=1,
                exhausted_budget="model_turns",
                message="The bounded planning loop reached its turn ceiling.",
            )
        )

        assert failed.state == "failed"
        assert DurableTaskCoordinator(ledger).next_action("task:test") == {
            "kind": "wait",
            "reason": "terminal",
            "task_state": "failed",
        }
        with pytest.raises(StorageProblem):
            ledger.record_user_event(
                "task:test",
                expected_task_version=failed.task_version,
                action="resumed",
                user_event_id="user-event:budget-resume",
                payload_hash=HASH_B,
            )


def test_waiting_confirmation_checkpoint_survives_restart_without_execution(
    tmp_path,
) -> None:
    workspace = tmp_path / "awaiting-confirmation-project"
    with ProjectStore.create(workspace, project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        ledger.start_activation(activation())
        ledger.mark_activation_running("activation:test")
        staged = ledger.accept_yield(
            AgentIntentReady(
                activation_id="activation:test",
                task_id="task:test",
                task_version=1,
                intent=intent(),
            )
        )
        waiting = ledger.advance(
            "task:test",
            expected_task_version=staged.task_version,
            next_state="awaiting_confirmation",
            reason_code="INTENT_PRESENTED",
        )

    with ProjectStore.open(workspace) as reopened:
        restored = TaskLedgerRepository(reopened).get_task("task:test")
        assert restored == waiting
        assert restored.project_revision == 0
        assert all(item.attempt_count == 0 for item in restored.items)


def test_waiting_reconfirmation_checkpoint_survives_restart_without_old_grant(
    tmp_path,
) -> None:
    workspace = tmp_path / "awaiting-reconfirmation-project"
    with ProjectStore.create(workspace, project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        coordinator = DurableTaskCoordinator(ledger)
        first = coordinator.next_action("task:test")
        first_id = str(first["activation"]["activation_id"])
        ledger.mark_activation_running(first_id)
        first_intent = intent().model_copy(update={"created_by_activation_id": first_id})
        first_intent = first_intent.model_copy(
            update={
                "content_hash": canonical_hash(
                    first_intent.model_dump(mode="json", exclude={"content_hash"})
                )
            }
        )
        staged = ledger.accept_yield(
            AgentIntentReady(
                activation_id=first_id,
                task_id="task:test",
                task_version=1,
                intent=first_intent,
            )
        )
        waiting = ledger.advance(
            "task:test",
            expected_task_version=staged.task_version,
            next_state="awaiting_confirmation",
            reason_code="INTENT_PRESENTED",
        )
        ledger.record_user_event(
            "task:test",
            expected_task_version=waiting.task_version,
            action="corrected",
            user_event_id="user-event:restart-correction",
            payload_hash=HASH_B,
            message="Use a different Y binding.",
        )
        second = coordinator.next_action("task:test")
        second_id = str(second["activation"]["activation_id"])
        second_version = int(second["activation"]["task_version"])
        ledger.mark_activation_running(second_id)
        revised = intent().model_copy(
            update={
                "intent_version": 2,
                "task_version": second_version,
                "created_by_activation_id": second_id,
            }
        )
        revised = revised.model_copy(
            update={
                "content_hash": canonical_hash(
                    revised.model_dump(mode="json", exclude={"content_hash"})
                )
            }
        )
        restaged = ledger.accept_yield(
            AgentIntentReady(
                activation_id=second_id,
                task_id="task:test",
                task_version=second_version,
                intent=revised,
            )
        )
        reconfirm = ledger.advance(
            "task:test",
            expected_task_version=restaged.task_version,
            next_state="awaiting_reconfirmation",
            reason_code="REVISED_INTENT_PRESENTED",
        )
        assert reconfirm.state == "awaiting_reconfirmation"

    with ProjectStore.open(workspace) as reopened:
        restored_ledger = TaskLedgerRepository(reopened)
        restored = restored_ledger.get_task("task:test")
        assert restored == reconfirm
        assert restored.intent is not None and restored.intent.intent_version == 2
        assert all(item.attempt_count == 0 for item in restored.items)
        with pytest.raises(StorageProblem):
            restored_ledger.get_execution_grant("task:test")


def test_read_only_information_yield_completes_without_task_items(tmp_path) -> None:
    with ProjectStore.create(
        tmp_path / "project", project_id="project:test"
    ) as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        ledger.start_activation(activation())
        ledger.mark_activation_running("activation:test")
        completed = ledger.accept_yield(
            AgentInformationReady(
                activation_id="activation:test",
                task_id="task:test",
                task_version=1,
                message="共有 4 列，其中 1 个值缺失。",
            )
        )
        assert completed.state == "completed_verified"
        assert completed.items == ()
        assert completed.completion is None
        activation_value, status = ledger.get_activation("activation:test")
        assert status == "yielded"
        assert activation_value.activation_id == "activation:test"


def test_intent_yield_stages_items_and_survives_restart(tmp_path) -> None:
    workspace = tmp_path / "project"
    with ProjectStore.create(workspace, project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        ledger.start_activation(activation())
        ledger.mark_activation_running("activation:test")
        staged = ledger.accept_yield(
            AgentIntentReady(
                activation_id="activation:test",
                task_id="task:test",
                task_version=1,
                intent=intent(),
            )
        )
        assert staged.state == "intent_staged"
        assert staged.intent is not None
        assert [(item.item_id, item.state) for item in staged.items] == [
            ("item:test.1", "staged")
        ]

    with ProjectStore.open(workspace) as reopened:
        restored = TaskLedgerRepository(reopened).get_task("task:test")
        assert restored == staged


def test_intent_staged_can_be_cancelled_before_the_confirmation_card_is_projected(
    tmp_path,
) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        current = ledger.create_task(envelope())
        for next_state in ("investigating", "intent_staged"):
            current = ledger.advance(
                "task:test",
                expected_task_version=current.task_version,
                next_state=next_state,
                reason_code="TEST_STAGE",
            )

        cancelling = ledger.cancel(
            "task:test",
            expected_task_version=current.task_version,
            user_event_id="user-event:cancel-staged",
            payload_hash=HASH_A,
        )
        cancelled = ledger.finalize_cancel(
            "task:test", expected_task_version=cancelling.task_version
        )

        assert cancelling.state == "cancelling"
        assert cancelled.state == "cancelled"


def test_reconfirmation_plan_can_be_corrected_again_before_execution(tmp_path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        current = ledger.create_task(envelope())
        for next_state in (
            "investigating",
            "intent_staged",
            "awaiting_reconfirmation",
        ):
            current = ledger.advance(
                "task:test",
                expected_task_version=current.task_version,
                next_state=next_state,
                reason_code="TEST_RECONFIRMATION",
            )

        corrected = ledger.record_user_event(
            "task:test",
            expected_task_version=current.task_version,
            action="corrected",
            user_event_id="user-event:correct-reconfirmation",
            payload_hash=HASH_B,
            message="Revise the field binding once more.",
        )

        assert corrected.state == "investigating"


def test_cancel_aborts_owned_activation_and_finalizes_without_side_effects(tmp_path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        created = ledger.create_task(envelope())
        ledger.start_activation(activation())
        ledger.mark_activation_running("activation:test")

        aborted = ledger.abort_active_activation("task:test")
        assert aborted.active_activation_id is None
        _, status = ledger.get_activation("activation:test")
        assert status == "aborted"
        cancelling = ledger.cancel(
            "task:test",
            expected_task_version=created.task_version,
            user_event_id="user-event:cancel.1",
            payload_hash=HASH_A,
        )
        cancelled = ledger.finalize_cancel(
            "task:test", expected_task_version=cancelling.task_version
        )
        assert cancelled.state == "cancelled"
        phases = [
            event.phase
            for event in ledger.list_events("task:test")
            if isinstance(event, AgentActivationEvent)
        ]
        assert phases == ["requested", "started", "aborted"]


def test_cancel_waits_for_a_running_item_to_reach_its_atomic_boundary(tmp_path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        current = TaskLedgerRepository(project)
        current.create_task(envelope())
        activation_value = activation()
        current.start_activation(activation_value)
        current.mark_activation_running(activation_value.activation_id)
        staged = current.accept_yield(
            AgentIntentReady(
                activation_id=activation_value.activation_id,
                task_id="task:test",
                task_version=1,
                intent=intent(),
            )
        )
        awaiting = current.advance(
            staged.task_id,
            expected_task_version=staged.task_version,
            next_state="awaiting_confirmation",
            reason_code="TEST_AWAITING_CONFIRMATION",
        )
        executing = current.advance(
            awaiting.task_id,
            expected_task_version=awaiting.task_version,
            next_state="executing",
            reason_code="TEST_CONFIRMED",
        )
        running = current.transition_item(
            executing.task_id,
            expected_task_version=executing.task_version,
            item_id=executing.items[0].item_id,
            expected_item_state="staged",
            next_state="running",
            reason_code="TEST_RUNNING",
        )
        cancelling = current.cancel(
            running.task_id,
            expected_task_version=running.task_version,
            user_event_id="user-event:cancel-running",
            payload_hash=HASH_B,
        )
        with pytest.raises(StorageProblem, match="atomic boundary"):
            current.finalize_cancel(
                cancelling.task_id,
                expected_task_version=cancelling.task_version,
            )

        bounded = current.transition_item(
            cancelling.task_id,
            expected_task_version=cancelling.task_version,
            item_id=cancelling.items[0].item_id,
            expected_item_state="running",
            next_state="succeeded",
            reason_code="TEST_ATOMIC_COMMIT_RECORDED",
            output_plot_id="plot:test",
            output_plot_version=1,
        )
        finalized = current.finalize_cancel(
            bounded.task_id,
            expected_task_version=bounded.task_version,
        )
        assert finalized.state == "cancelled"
        assert finalized.items[0].state == "succeeded"
        assert finalized.items[0].output_plot_id == "plot:test"
        assert finalized.items[0].state == "succeeded"


def test_item_progress_is_isolated_between_batch_items(tmp_path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        ledger.start_activation(activation())
        ledger.mark_activation_running("activation:test")
        first = intent().items[0]
        second = first.model_copy(update={"item_id": "item:test.2", "plot_alias": "plot_2"})
        batch = intent().model_copy(update={"items": (first, second)})
        staged = ledger.accept_yield(
            AgentIntentReady(
                activation_id="activation:test",
                task_id="task:test",
                task_version=1,
                intent=batch,
            )
        )
        running = ledger.transition_item(
            "task:test",
            expected_task_version=staged.task_version,
            item_id="item:test.1",
            expected_item_state="staged",
            next_state="running",
            reason_code="ITEM_STARTED",
        )
        succeeded = ledger.transition_item(
            "task:test",
            expected_task_version=running.task_version,
            item_id="item:test.1",
            expected_item_state="running",
            next_state="succeeded",
            reason_code="ITEM_COMMITTED",
            output_plot_id="plot:test.1",
            output_plot_version=1,
        )
        assert [(item.item_id, item.state) for item in succeeded.items] == [
            ("item:test.1", "succeeded"),
            ("item:test.2", "staged"),
        ]


def test_receipt_and_verification_are_durable_and_idempotent(tmp_path) -> None:
    workspace = tmp_path / "project"
    with ProjectStore.create(workspace, project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        ledger.start_activation(activation())
        ledger.mark_activation_running("activation:test")
        staged = ledger.accept_yield(
            AgentIntentReady(
                activation_id="activation:test",
                task_id="task:test",
                task_version=1,
                intent=intent(),
            )
        )
        waiting = ledger.advance(
            "task:test",
            expected_task_version=staged.task_version,
            next_state="awaiting_confirmation",
            reason_code="INTENT_PRESENTED",
        )
        executing = ledger.record_user_event(
            "task:test",
            expected_task_version=waiting.task_version,
            action="confirmed",
            user_event_id="user-event:confirm.1",
            payload_hash=HASH_A,
        )
        running = ledger.transition_item(
            "task:test",
            expected_task_version=executing.task_version,
            item_id="item:test.1",
            expected_item_state="staged",
            next_state="running",
            reason_code="ITEM_STARTED",
        )
        receipt = ToolReceipt(
            receipt_id="receipt:test",
            task_id="task:test",
            task_version=running.task_version,
            item_id="item:test.1",
            tool_call_id="call:create.1",
            tool_name="create_plot",
            permission_phase="p2_confirmed",
            outcome="succeeded",
            idempotency_key="idem:create.1",
            input_hash=HASH_A,
            output_hash=HASH_B,
            project_revision_before=0,
            project_revision_after=1,
            side_effects=(
                SideEffectReceipt(
                    effect_kind="plot_version",
                    object_id="plot:test.1",
                    object_version=1,
                ),
            ),
            started_at=NOW,
            finished_at=LATER,
        )
        with_receipt = ledger.record_tool_receipt(receipt)
        assert with_receipt.items[0].receipt_ids == ("receipt:test",)
        assert with_receipt.budget.usage.tool_calls == 1
        assert ledger.record_tool_receipt(receipt) == with_receipt

        report = VerificationReport(
            report_id="verification:test",
            task_id="task:test",
            task_version=with_receipt.task_version,
            intent=with_receipt.intent,
            item_id="item:test.1",
            status="passed",
            claims=(
                VerificationClaim(
                    claim_id="source.binding",
                    status="passed",
                    expected="The confirmed fields are bound.",
                    observed="Native readback matches the confirmed fields.",
                ),
            ),
            content_hash=HASH_A,
            verified_at=LATER,
        )
        with_report = ledger.record_verification_report(report)
        assert with_report.items[0].verification_report_ids == ("verification:test",)
        succeeded = ledger.transition_item(
            "task:test",
            expected_task_version=with_report.task_version,
            item_id="item:test.1",
            expected_item_state="running",
            next_state="succeeded",
            reason_code="ITEM_VERIFIED",
            output_plot_id="plot:test.1",
            output_plot_version=1,
        )
        verifying = ledger.advance(
            "task:test",
            expected_task_version=succeeded.task_version,
            next_state="verifying",
            reason_code="EXECUTION_FINISHED",
        )
        delivering = ledger.advance(
            "task:test",
            expected_task_version=verifying.task_version,
            next_state="delivering",
            reason_code="VERIFICATION_PASSED",
        )
        completed = ledger.complete_task(
            "task:test",
            expected_task_version=delivering.task_version,
            completion=TaskCompletion(
                completed_at=LATER,
                final_project_revision=1,
                required_report_ids=("verification:test",),
                artifact_receipt_ids=("receipt:test",),
            ),
        )
        assert completed.state == "completed_verified"

    with ProjectStore.open(workspace) as reopened:
        restored = TaskLedgerRepository(reopened).get_task("task:test")
        assert restored.state == "completed_verified"
        assert restored.items[0].receipt_ids == ("receipt:test",)
        assert restored.items[0].verification_report_ids == ("verification:test",)


def test_task_lease_excludes_other_holder_and_can_be_released(tmp_path) -> None:
    with ProjectStore.create(
        tmp_path / "project", project_id="project:test"
    ) as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        token = ledger.acquire_lease("task:test", holder_id="pump:one")
        with pytest.raises(StorageProblem) as caught:
            ledger.acquire_lease("task:test", holder_id="pump:two")
        assert caught.value.code == StorageErrorCode.VERSION_CONFLICT
        with pytest.raises(StorageProblem):
            ledger.release_lease("task:test", lease_token="lease:wrong")
        ledger.release_lease("task:test", lease_token=token)
        assert ledger.acquire_lease("task:test", holder_id="pump:two")


def test_tool_receipt_budget_is_idempotent_and_rolls_back_when_exhausted(tmp_path) -> None:
    limited = envelope().model_copy(
        update={
            "budget": TaskBudgetLimits(max_tool_calls=1, max_estimated_cost=10),
        }
    )
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(limited)
        first = ToolReceipt(
            receipt_id="receipt:read.1",
            task_id="task:test",
            task_version=1,
            activation_id="activation:test",
            tool_call_id="call:read.1",
            tool_name="inspect_source",
            permission_phase="p0_read",
            outcome="succeeded",
            input_hash=HASH_A,
            output_hash=HASH_B,
            project_revision_before=0,
            project_revision_after=0,
            started_at=NOW,
            finished_at=LATER,
        )
        persisted = ledger.record_tool_receipt(first)
        assert persisted.budget.usage.tool_calls == 1
        assert ledger.record_tool_receipt(first) == persisted

        second = first.model_copy(
            update={
                "receipt_id": "receipt:read.2",
                "tool_call_id": "call:read.2",
            }
        )
        with pytest.raises(StorageProblem) as caught:
            ledger.record_tool_receipt(second)
        assert caught.value.code == StorageErrorCode.TASK_BUDGET_EXCEEDED
        assert ledger.get_task("task:test") == persisted
        stored = project._assert_writer().execute(  # noqa: SLF001
            "SELECT COUNT(*) FROM agent_tool_receipts_v2"
        ).fetchone()
        assert stored is not None and int(stored[0]) == 1


def test_duplicate_task_id_with_different_envelope_is_rejected(tmp_path) -> None:
    with ProjectStore.create(
        tmp_path / "project", project_id="project:test"
    ) as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        changed = envelope().model_copy(update={"original_instruction": "Different task."})
        with pytest.raises(StorageProblem) as caught:
            ledger.create_task(changed)
        assert caught.value.code == StorageErrorCode.IDEMPOTENCY_CONFLICT


def test_event_and_checkpoint_roll_back_together_on_storage_fault(tmp_path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        created = ledger.create_task(envelope())
        connection = project._assert_writer()  # noqa: SLF001
        connection.execute(
            """
            CREATE TRIGGER fail_second_checkpoint
            BEFORE INSERT ON agent_task_checkpoints_v2
            WHEN NEW.event_sequence = 2
            BEGIN
                SELECT RAISE(ABORT, 'injected checkpoint failure');
            END
            """
        )
        with pytest.raises(sqlite3.IntegrityError, match="injected checkpoint failure"):
            ledger.advance(
                "task:test",
                expected_task_version=1,
                next_state="investigating",
                reason_code="FAULT_TEST",
            )
        assert ledger.get_task("task:test") == created
        assert len(ledger.list_events("task:test")) == 1
        connection.execute("DROP TRIGGER fail_second_checkpoint")
        assert ledger.advance(
            "task:test",
            expected_task_version=1,
            next_state="investigating",
            reason_code="RECOVERED",
        ).last_event_sequence == 2


def test_late_yield_is_rejected_after_activation_is_superseded(tmp_path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        ledger.start_activation(activation())
        running = ledger.mark_activation_running("activation:test")
        superseded = ledger.advance(
            "task:test",
            expected_task_version=running.task_version,
            next_state="failed",
            reason_code="EXTERNAL_BLOCKER",
        )
        with pytest.raises(StorageProblem) as caught:
            ledger.accept_yield(
                AgentNeedsInput(
                    activation_id="activation:test",
                    task_id="task:test",
                    task_version=1,
                    questions=(
                        InputQuestion(
                            question_key="question:late",
                            prompt="This response arrived too late.",
                            answer_kind="text",
                        ),
                    ),
                )
            )
        assert caught.value.code == StorageErrorCode.VERSION_CONFLICT
        assert ledger.get_task("task:test") == superseded


def test_task_schema_tables_are_strict(tmp_path) -> None:
    with ProjectStore.create(
        tmp_path / "project", project_id="project:test"
    ) as project:
        rows = project._assert_writer().execute(  # noqa: SLF001
            """
            SELECT name, strict FROM pragma_table_list
            WHERE name LIKE 'agent_%_v2' ORDER BY name
            """
        ).fetchall()
        assert len(rows) == 10
        assert all(int(row[1]) == 1 for row in rows)
        assert project._assert_writer().execute("PRAGMA foreign_keys").fetchone() == (1,)  # noqa: SLF001


def _drop_task_v2_tables(connection: sqlite3.Connection) -> None:
    for table in (
        "agent_execution_grants_v2",
        "agent_task_plans_v2",
        "agent_task_leases_v2",
        "agent_verification_reports_v2",
        "agent_tool_receipts_v2",
        "agent_task_checkpoints_v2",
        "agent_task_events_v2",
        "agent_activations_v2",
        "agent_task_intents_v2",
        "agent_tasks_v2",
    ):
        connection.execute(f"DROP TABLE {table}")


@pytest.mark.parametrize("previous_version", [5, 6])
def test_previous_project_is_migrated_additively(
    tmp_path, previous_version: int
) -> None:
    workspace = tmp_path / "project"
    with ProjectStore.create(workspace, project_id="project:test"):
        pass
    database = workspace / "project.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        if previous_version == 5:
            _drop_task_v2_tables(connection)
        else:
            connection.execute("DROP TABLE agent_execution_grants_v2")
            connection.execute("DROP TABLE agent_task_plans_v2")
        connection.execute(
            "UPDATE schema_info SET value = ? WHERE key = 'schema_version'",
            (str(previous_version),),
        )
        connection.execute(f"PRAGMA user_version = {previous_version}")

    with ProjectStore.open(workspace) as migrated:
        connection = migrated._assert_writer()  # noqa: SLF001
        assert connection.execute("PRAGMA user_version").fetchone() == (7,)
        assert connection.execute(
            "SELECT value FROM schema_info WHERE key = 'schema_version'"
        ).fetchone() == ("7",)
        assert TaskLedgerRepository(migrated).create_task(envelope()).state == "created"
