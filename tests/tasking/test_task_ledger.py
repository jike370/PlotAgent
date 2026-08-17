from __future__ import annotations

import sqlite3

import pytest

from plotagent.contracts.agent_tasks import (
    AgentActivation,
    AgentIntentReady,
    AgentNeedsInput,
    SideEffectReceipt,
    TaskBudgetLimits,
    TaskCompletion,
    TaskEnvelope,
    TaskIntent,
    ToolReceipt,
    VerificationClaim,
    VerificationReport,
)
from plotagent.contracts.workflows import DraftFieldBinding, InputQuestion, TaskDraftItem
from plotagent.storage.errors import StorageErrorCode, StorageProblem
from plotagent.storage.project import ProjectStore
from plotagent.tasking import TaskLedgerRepository

HASH_A = "a" * 64
HASH_B = "b" * 64
NOW = "2026-08-18T10:00:00Z"
LATER = "2026-08-18T10:05:00Z"


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
                next_state="completed_verified",
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
        )
        assert resumed.state == "investigating"
        assert (
            ledger.record_user_event(
                "task:test",
                expected_task_version=waiting.task_version,
                action="answered",
                user_event_id="user-event:answer.1",
                payload_hash=HASH_A,
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
            )
        assert conflict.value.code == StorageErrorCode.IDEMPOTENCY_CONFLICT
        sequences = [event.sequence for event in ledger.list_events("task:test")]
        assert sequences == list(range(1, len(sequences) + 1))


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
