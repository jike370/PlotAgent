"""Transactional, append-only persistence for Agent foundation v2 tasks."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from pydantic import ValidationError

from plotagent.contracts.agent_tasks import (
    AGENT_YIELD_ADAPTER,
    ALLOWED_TASK_TRANSITIONS,
    TASK_EVENT_ADAPTER,
    AgentActivation,
    AgentActivationEvent,
    AgentBlocked,
    AgentYield,
    ExecutionGrant,
    IntentRef,
    TaskBudgetSnapshot,
    TaskBudgetUsage,
    TaskCheckpoint,
    TaskCompletion,
    TaskContextUpdate,
    TaskEnvelope,
    TaskError,
    TaskEvent,
    TaskIntent,
    TaskItemSnapshot,
    TaskItemState,
    TaskItemTransitionEvent,
    TaskState,
    TaskStateTransitionEvent,
    ToolReceipt,
    ToolReceiptEvent,
    UserTaskEvent,
    VerificationReport,
    VerificationReportEvent,
    is_legal_task_item_transition,
    is_legal_task_transition,
)
from plotagent.contracts.canonical import JsonValue, canonical_hash, canonical_json
from plotagent.contracts.workflows import TaskPlan
from plotagent.storage.errors import StorageErrorCode, StorageProblem
from plotagent.storage.project import ProjectStore


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _checkpoint_hash(checkpoint: TaskCheckpoint) -> str:
    payload = checkpoint.model_dump(mode="json")
    payload.pop("content_hash", None)
    return canonical_hash(payload)


def _verified_json_object(
    payload: str,
    expected_hash: str,
    *,
    error_message: str,
    embedded_hash_field: str | None = None,
) -> dict[str, JsonValue]:
    """Verify persisted bytes before current contracts add defaulted fields.

    Durable hashes authenticate the JSON that was written at the time, not a
    later Pydantic serialization.  Re-serializing an older record with a newer
    contract can add default-valued fields and must not make an untampered
    project unreadable.
    """

    try:
        value = json.loads(payload)
    except (TypeError, ValueError) as error:
        raise sqlite3.DatabaseError(error_message) from error
    if not isinstance(value, dict):
        raise sqlite3.DatabaseError(error_message)
    authenticated = dict(value)
    if (
        embedded_hash_field is not None
        and authenticated.pop(embedded_hash_field, None) != expected_hash
    ):
        raise sqlite3.DatabaseError(error_message)
    if canonical_hash(cast(JsonValue, authenticated)) != expected_hash:
        raise sqlite3.DatabaseError(error_message)
    return cast(dict[str, JsonValue], value)


def _event_json(event: TaskEvent) -> str:
    return canonical_json(cast(JsonValue, event.model_dump(mode="json")))


def _apply_tool_budget(
    current: TaskBudgetSnapshot,
    delta: TaskBudgetUsage,
) -> TaskBudgetSnapshot:
    usage = current.usage
    try:
        return TaskBudgetSnapshot(
            limits=current.limits,
            usage=TaskBudgetUsage(
                model_calls=usage.model_calls + delta.model_calls,
                model_turns=usage.model_turns + delta.model_turns,
                input_tokens=usage.input_tokens + delta.input_tokens,
                output_tokens=usage.output_tokens + delta.output_tokens,
                tool_calls=usage.tool_calls + delta.tool_calls,
                disclosed_scalars=usage.disclosed_scalars + delta.disclosed_scalars,
                origin_sessions=usage.origin_sessions + delta.origin_sessions,
                repair_attempts=usage.repair_attempts + delta.repair_attempts,
                wall_time_ms=usage.wall_time_ms + delta.wall_time_ms,
                estimated_cost=usage.estimated_cost + delta.estimated_cost,
            ),
        )
    except ValidationError as error:
        raise StorageProblem(
            StorageErrorCode.TASK_BUDGET_EXCEEDED,
            "Tool receipt would exceed the durable task budget.",
        ) from error


type UserTaskAction = Literal[
    "answered",
    "confirmed",
    "rejected",
    "corrected",
    "cancel_requested",
    "partial_accepted",
    "retry_requested",
    "resumed",
]


USER_TASK_ACTION_TRANSITIONS: dict[
    UserTaskAction,
    tuple[frozenset[TaskState], TaskState | None],
] = {
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
        frozenset(
            {
                "created",
                "investigating",
                "awaiting_input",
                "intent_staged",
                "awaiting_confirmation",
                "executing",
                "verifying",
                "repairing",
                "awaiting_reconfirmation",
                "delivering",
                "partial",
                "blocked",
            }
        ),
        "cancelling",
    ),
    # Accepting a verified subset is a terminal resolution distinct from
    # both waiting in ``partial`` and explicit task cancellation.
    "partial_accepted": (frozenset({"partial"}), None),
    "retry_requested": (frozenset({"partial"}), "executing"),
    "resumed": (frozenset({"blocked"}), "investigating"),
}


class TaskLedgerRepository:
    """Core-owned source of truth for durable Agent task state.

    Every mutation appends an event and replaces the current checkpoint in the
    same SQLite transaction. The Agent and desktop can propose outcomes, but
    they cannot write task state directly.
    """

    def __init__(self, project: ProjectStore) -> None:
        self.project = project

    @property
    def _connection(self) -> sqlite3.Connection:
        return self.project._assert_writer()  # noqa: SLF001

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise

    def create_task(self, envelope: TaskEnvelope) -> TaskCheckpoint:
        if envelope.project_id != self.project.project_id:
            raise self._conflict("Task envelope belongs to a different project.")
        now = _utc_now()
        event = TaskStateTransitionEvent(
            event_id=self._new_id("event"),
            task_id=envelope.task_id,
            task_version=envelope.task_version,
            sequence=1,
            occurred_at=now,
            previous_state="created",
            next_state="created",
            reason_code="TASK_CREATED",
        )
        checkpoint = self._new_checkpoint(
            task_id=envelope.task_id,
            task_version=envelope.task_version,
            state="created",
            project_revision=envelope.project_revision,
            event_sequence=1,
            budget=TaskBudgetSnapshot(limits=envelope.budget),
            updated_at=now,
        )
        envelope_payload = canonical_json(envelope)
        envelope_hash = canonical_hash(envelope)
        checkpoint_payload = canonical_json(checkpoint)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT envelope_hash FROM agent_tasks_v2 WHERE task_id = ?",
                (envelope.task_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != envelope_hash:
                    raise self._idempotency("Task id already has different content.")
                return self.get_task(envelope.task_id)
            connection.execute(
                """
                INSERT INTO agent_tasks_v2 (
                    task_id, task_version, project_id, state, project_revision,
                    envelope_hash, envelope_json, checkpoint_hash, checkpoint_json,
                    next_event_sequence, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 2, ?, ?)
                """,
                (
                    envelope.task_id,
                    envelope.task_version,
                    envelope.project_id,
                    checkpoint.state,
                    checkpoint.project_revision,
                    envelope_hash,
                    envelope_payload,
                    checkpoint.content_hash,
                    checkpoint_payload,
                    now,
                    now,
                ),
            )
            self._insert_event(connection, event)
            self._insert_checkpoint(connection, checkpoint, now)
        return checkpoint

    def get_envelope(self, task_id: str) -> TaskEnvelope:
        row = self._connection.execute(
            "SELECT envelope_json, envelope_hash FROM agent_tasks_v2 WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise self._not_found("Agent task was not found.")
        _verified_json_object(
            str(row[0]),
            str(row[1]),
            error_message="Agent task envelope hash does not match its content",
        )
        return TaskEnvelope.model_validate_json(str(row[0]))

    def get_effective_envelope(self, task_id: str) -> TaskEnvelope:
        """Fold durable user-authorized context updates over the immutable envelope."""

        envelope = self.get_envelope(task_id)
        for event in self.list_events(task_id):
            if not isinstance(event, UserTaskEvent) or event.context_update is None:
                continue
            envelope = self._replace_task_context(envelope, event.context_update)
        return envelope

    def get_task(self, task_id: str) -> TaskCheckpoint:
        row = self._connection.execute(
            "SELECT checkpoint_json, checkpoint_hash FROM agent_tasks_v2 WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise self._not_found("Agent task was not found.")
        return self._decode_checkpoint(str(row[0]), expected_hash=str(row[1]))

    def get_intent(self, task_id: str) -> TaskIntent:
        checkpoint = self.get_task(task_id)
        if checkpoint.intent is None:
            raise self._not_found("Agent task intent was not found.")
        row = self._connection.execute(
            """
            SELECT intent_json, content_hash FROM agent_task_intents_v2
            WHERE task_id = ? AND intent_id = ? AND intent_version = ?
            """,
            (
                task_id,
                checkpoint.intent.intent_id,
                checkpoint.intent.intent_version,
            ),
        ).fetchone()
        if row is None:
            raise self._not_found("Agent task intent was not found.")
        _verified_json_object(
            str(row[0]),
            str(row[1]),
            error_message="Agent task intent hash does not match its content",
            embedded_hash_field="content_hash",
        )
        return TaskIntent.model_validate_json(str(row[0]))

    def stage_plan(self, task_id: str, plan: TaskPlan) -> TaskPlan:
        """Persist one pure plan projection for the task's current immutable intent."""

        with self._transaction() as connection:
            current = self._get_task_in_transaction(connection, task_id)
            if current.state not in {"intent_staged", "awaiting_confirmation"}:
                raise self._conflict("Only a staged intent can receive a task plan.")
            if current.intent is None:
                raise self._conflict("Task plan requires a current intent.")
            if plan.expected_project_revision != current.project_revision:
                raise self._conflict("Task plan project revision is stale.")
            if tuple(item.item_id for item in plan.items) != tuple(
                item.item_id for item in current.items
            ):
                raise self._conflict("Task plan items differ from the staged intent.")
            payload = canonical_json(plan)
            digest = canonical_hash(plan)
            existing = connection.execute(
                "SELECT plan_hash, plan_json FROM agent_task_plans_v2 WHERE plan_id = ?",
                (plan.plan_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != digest or str(existing[1]) != payload:
                    raise self._idempotency("Task plan id already has different content.")
                return plan
            current_for_intent = connection.execute(
                """
                SELECT plan_id, plan_hash, plan_json FROM agent_task_plans_v2
                WHERE task_id = ? AND intent_id = ? AND intent_version = ?
                """,
                (
                    task_id,
                    current.intent.intent_id,
                    current.intent.intent_version,
                ),
            ).fetchone()
            if current_for_intent is not None:
                if (
                    str(current_for_intent[0]) != plan.plan_id
                    or str(current_for_intent[1]) != digest
                    or str(current_for_intent[2]) != payload
                ):
                    raise self._idempotency("Task intent already has a different plan.")
                return plan
            connection.execute(
                """
                INSERT INTO agent_task_plans_v2 (
                    plan_id, task_id, intent_id, intent_version, intent_hash,
                    plan_hash, plan_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.plan_id,
                    task_id,
                    current.intent.intent_id,
                    current.intent.intent_version,
                    current.intent.content_hash,
                    digest,
                    payload,
                    _utc_now(),
                ),
            )
        return plan

    def get_plan_with_hash(self, task_id: str) -> tuple[TaskPlan, str]:
        """Return the validated plan and its original persisted authority hash."""

        current = self.get_task(task_id)
        if current.intent is None:
            raise self._not_found("Agent task plan was not found.")
        row = self._connection.execute(
            """
            SELECT plan_json, plan_hash, intent_hash FROM agent_task_plans_v2
            WHERE task_id = ? AND intent_id = ? AND intent_version = ?
            """,
            (task_id, current.intent.intent_id, current.intent.intent_version),
        ).fetchone()
        if row is None:
            raise self._not_found("Agent task plan was not found.")
        plan_hash = str(row[1])
        _verified_json_object(
            str(row[0]),
            plan_hash,
            error_message="Agent task plan authority does not match its content",
        )
        if str(row[2]) != current.intent.content_hash:
            raise sqlite3.DatabaseError("Agent task plan authority does not match its content")
        return TaskPlan.model_validate_json(str(row[0])), plan_hash

    def get_plan(self, task_id: str) -> TaskPlan:
        return self.get_plan_with_hash(task_id)[0]

    def get_execution_grant(self, task_id: str) -> ExecutionGrant:
        plan = self.get_plan(task_id)
        row = self._connection.execute(
            """
            SELECT grant_json, grant_hash FROM agent_execution_grants_v2
            WHERE task_id = ? AND plan_id = ?
            """,
            (task_id, plan.plan_id),
        ).fetchone()
        if row is None:
            raise self._not_found("Execution grant was not found.")
        _verified_json_object(
            str(row[0]),
            str(row[1]),
            error_message="Execution grant hash does not match its content",
            embedded_hash_field="content_hash",
        )
        return ExecutionGrant.model_validate_json(str(row[0]))

    def get_activation(self, activation_id: str) -> tuple[AgentActivation, str]:
        """Return one immutable activation and its runtime status."""

        row = self._connection.execute(
            """
            SELECT activation_json, status
            FROM agent_activations_v2 WHERE activation_id = ?
            """,
            (activation_id,),
        ).fetchone()
        if row is None:
            raise self._not_found("Agent activation was not found.")
        return AgentActivation.model_validate_json(str(row[0])), str(row[1])

    def list_tasks(
        self,
        *,
        state: TaskState | None = None,
        limit: int = 100,
    ) -> tuple[TaskCheckpoint, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("task list limit must be between 1 and 1000")
        if state is not None and state not in ALLOWED_TASK_TRANSITIONS:
            raise ValueError("task list state was invalid")
        if state is None:
            rows = self._connection.execute(
                """
                SELECT checkpoint_json, checkpoint_hash FROM agent_tasks_v2
                ORDER BY updated_at DESC, task_id LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                """
                SELECT checkpoint_json, checkpoint_hash FROM agent_tasks_v2
                WHERE state = ? ORDER BY updated_at DESC, task_id LIMIT ?
                """,
                (state, limit),
            ).fetchall()
        return tuple(
            self._decode_checkpoint(str(row[0]), expected_hash=str(row[1]))
            for row in rows
        )

    def latest_yield(self, task_id: str) -> AgentYield | None:
        """Return the newest durable Agent yield without reactivating the task."""

        self.get_task(task_id)
        row = self._connection.execute(
            """
            SELECT yield_json FROM agent_activations_v2
            WHERE task_id = ? AND yield_json IS NOT NULL
            ORDER BY updated_at DESC, activation_id DESC LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        return None if row is None else AGENT_YIELD_ADAPTER.validate_json(str(row[0]))

    def recover_inflight_activations(self) -> tuple[str, ...]:
        """Abort activations owned by a previous desktop process.

        A project writer is exclusive, so opening a new writer proves that no
        prior Main process can still own these persisted activations. Recovery
        is process-bound and does not depend on an arbitrary wall-clock lease.
        """

        rows = self._connection.execute(
            "SELECT checkpoint_json, checkpoint_hash FROM agent_tasks_v2 ORDER BY task_id"
        ).fetchall()
        task_ids = tuple(
            checkpoint.task_id
            for row in rows
            if (
                checkpoint := self._decode_checkpoint(
                    str(row[0]), expected_hash=str(row[1])
                )
            ).active_activation_id
            is not None
        )
        recovered: list[str] = []
        for task_id in task_ids:
            checkpoint = self.get_task(task_id)
            activation_id = checkpoint.active_activation_id
            if activation_id is None:
                continue
            _activation, status = self.get_activation(activation_id)
            if status not in {"requested", "running"}:
                continue
            self.abort_active_activation(task_id)
            recovered.append(task_id)
        return tuple(recovered)

    def list_events(self, task_id: str, *, after_sequence: int = 0) -> tuple[TaskEvent, ...]:
        self.get_task(task_id)
        rows = self._connection.execute(
            """
            SELECT event_json FROM agent_task_events_v2
            WHERE task_id = ? AND sequence > ? ORDER BY sequence
            """,
            (task_id, after_sequence),
        ).fetchall()
        return tuple(TASK_EVENT_ADAPTER.validate_json(str(row[0])) for row in rows)

    def advance(
        self,
        task_id: str,
        *,
        expected_task_version: int,
        next_state: TaskState,
        reason_code: str,
        project_revision: int | None = None,
    ) -> TaskCheckpoint:
        if next_state == "completed_verified":
            raise self._conflict(
                "Verified completion requires complete_task and explicit evidence."
            )
        with self._transaction() as connection:
            current = self._get_task_in_transaction(connection, task_id)
            self._expect_version(current, expected_task_version)
            return self._transition(
                connection,
                current,
                next_state=next_state,
                reason_code=reason_code,
                project_revision=project_revision,
            )

    def complete_task(
        self,
        task_id: str,
        *,
        expected_task_version: int,
        completion: TaskCompletion,
    ) -> TaskCheckpoint:
        with self._transaction() as connection:
            current = self._get_task_in_transaction(connection, task_id)
            self._expect_version(current, expected_task_version)
            if current.state != "delivering":
                raise self._conflict("Only a delivering task can complete.")
            if completion.final_project_revision != current.project_revision:
                raise self._conflict(
                    "Completion revision must match the task project revision."
                )
            rows = connection.execute(
                """
                SELECT report_id, status FROM agent_verification_reports_v2
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchall()
            report_status = {str(row[0]): str(row[1]) for row in rows}
            if any(
                report_status.get(report_id) != "passed"
                for report_id in completion.required_report_ids
            ):
                raise self._conflict(
                    "Verified completion requires every declared report to pass."
                )
            return self._transition(
                connection,
                current,
                next_state="completed_verified",
                reason_code="VERIFICATION_COMPLETED",
                completion=completion,
            )

    def start_activation(self, activation: AgentActivation) -> TaskCheckpoint:
        with self._transaction() as connection:
            current = self._get_task_in_transaction(connection, activation.task_id)
            payload = canonical_json(activation)
            existing = connection.execute(
                "SELECT activation_json FROM agent_activations_v2 WHERE activation_id = ?",
                (activation.activation_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != payload:
                    raise self._idempotency("Activation id already has different content.")
                return current
            self._expect_version(current, activation.task_version)
            if activation.task_state != current.state:
                raise self._conflict("Agent activation task state is stale.")
            if current.active_activation_id is not None:
                raise self._conflict("Agent task already has an active activation.")
            now = _utc_now()
            connection.execute(
                """
                INSERT INTO agent_activations_v2 (
                    activation_id, task_id, task_version, status,
                    activation_json, yield_json, created_at, updated_at
                ) VALUES (?, ?, ?, 'requested', ?, NULL, ?, ?)
                """,
                (
                    activation.activation_id,
                    activation.task_id,
                    activation.task_version,
                    payload,
                    now,
                    now,
                ),
            )
            sequence = self._next_sequence(connection, current.task_id)
            event = AgentActivationEvent(
                event_id=self._new_id("event"),
                task_id=current.task_id,
                task_version=current.task_version,
                sequence=sequence,
                occurred_at=now,
                activation_id=activation.activation_id,
                phase="requested",
            )
            updated = self._copy_checkpoint(
                current,
                event_sequence=sequence,
                active_activation_id=activation.activation_id,
                updated_at=now,
            )
            self._append_event_and_checkpoint(connection, event, updated, now)
            return updated

    def mark_activation_running(self, activation_id: str) -> TaskCheckpoint:
        with self._transaction() as connection:
            activation, current, status = self._activation_context(connection, activation_id)
            if status == "running":
                return current
            if status != "requested":
                raise self._conflict("Only a requested activation can start running.")
            now = _utc_now()
            connection.execute(
                "UPDATE agent_activations_v2 SET status = 'running', updated_at = ? "
                "WHERE activation_id = ?",
                (now, activation_id),
            )
            sequence = self._next_sequence(connection, current.task_id)
            event = AgentActivationEvent(
                event_id=self._new_id("event"),
                task_id=current.task_id,
                task_version=current.task_version,
                sequence=sequence,
                occurred_at=now,
                activation_id=activation.activation_id,
                phase="started",
            )
            updated = self._copy_checkpoint(
                current,
                event_sequence=sequence,
                active_activation_id=current.active_activation_id,
                updated_at=now,
            )
            self._append_event_and_checkpoint(connection, event, updated, now)
            return updated

    def abort_active_activation(self, task_id: str) -> TaskCheckpoint:
        """Durably terminate only the activation currently owned by this task."""

        with self._transaction() as connection:
            current = self._get_task_in_transaction(connection, task_id)
            activation_id = current.active_activation_id
            if activation_id is None:
                return current
            row = connection.execute(
                "SELECT status FROM agent_activations_v2 WHERE activation_id = ?",
                (activation_id,),
            ).fetchone()
            if row is None:
                raise self._not_found("Agent activation was not found.")
            status = str(row[0])
            if status not in {"requested", "running", "aborted"}:
                raise self._conflict("A completed activation cannot be aborted.")
            now = _utc_now()
            if status != "aborted":
                connection.execute(
                    "UPDATE agent_activations_v2 SET status = 'aborted', updated_at = ? "
                    "WHERE activation_id = ?",
                    (now, activation_id),
                )
                sequence = self._next_sequence(connection, task_id)
                event = AgentActivationEvent(
                    event_id=self._new_id("event"),
                    task_id=task_id,
                    task_version=current.task_version,
                    sequence=sequence,
                    occurred_at=now,
                    activation_id=activation_id,
                    phase="aborted",
                )
                current = self._copy_checkpoint(
                    current,
                    event_sequence=sequence,
                    active_activation_id=None,
                    updated_at=now,
                )
                self._append_event_and_checkpoint(connection, event, current, now)
            return current

    def accept_yield(
        self,
        yielded: AgentYield,
        *,
        scope_reduction_item_ids: tuple[str, ...] = (),
    ) -> TaskCheckpoint:
        with self._transaction() as connection:
            activation, current, status = self._activation_context(
                connection, yielded.activation_id
            )
            if status == "yielded":
                stored = connection.execute(
                    "SELECT yield_json FROM agent_activations_v2 WHERE activation_id = ?",
                    (yielded.activation_id,),
                ).fetchone()
                if stored is not None and str(stored[0]) == canonical_json(
                    cast(JsonValue, yielded.model_dump(mode="json"))
                ):
                    return current
                raise self._idempotency("Activation already yielded different content.")
            if status != "running":
                raise self._conflict("Activation cannot accept a yield in its current state.")
            if (
                yielded.task_id != activation.task_id
                or yielded.task_version != activation.task_version
                or current.active_activation_id != yielded.activation_id
            ):
                raise self._conflict("Agent yield is stale or belongs to another task.")

            now = _utc_now()
            yield_payload = canonical_json(
                cast(JsonValue, yielded.model_dump(mode="json"))
            )
            connection.execute(
                """
                UPDATE agent_activations_v2
                SET status = ?, yield_json = ?, updated_at = ?
                WHERE activation_id = ?
                """,
                (
                    "runtime_failed" if yielded.outcome == "runtime_failed" else "yielded",
                    yield_payload,
                    now,
                    yielded.activation_id,
                ),
            )
            sequence = self._next_sequence(connection, current.task_id)
            phase: Literal["runtime_failed", "yielded"] = (
                "runtime_failed" if yielded.outcome == "runtime_failed" else "yielded"
            )
            activation_event = AgentActivationEvent(
                event_id=self._new_id("event"),
                task_id=current.task_id,
                task_version=current.task_version,
                sequence=sequence,
                occurred_at=now,
                activation_id=activation.activation_id,
                phase=phase,
                yield_outcome=yielded.outcome if phase == "yielded" else None,
            )
            checkpoint = self._copy_checkpoint(
                current,
                event_sequence=sequence,
                active_activation_id=None,
                updated_at=now,
            )
            self._append_event_and_checkpoint(connection, activation_event, checkpoint, now)

            # The activation, ContextSnapshot and every ToolInvocation remain bound
            # to the task version on which the activation was requested. Advancing
            # created -> investigating in mark_activation_running made that authority
            # stale before Pi could use a single tool. Record the investigation state
            # only after the activation has terminated, immediately before projecting
            # its typed outcome.
            if activation.reason in {"new_task", "resume_after_restart"} and (
                checkpoint.state == "created"
            ):
                checkpoint = self._transition(
                    connection,
                    checkpoint,
                    next_state="investigating",
                    reason_code="AGENT_INVESTIGATION_COMPLETED",
                )

            next_state = self._yield_state(yielded)
            if isinstance(yielded, AgentBlocked) and not yielded.retryable:
                next_state = "failed"
            intent_ref: IntentRef | None = checkpoint.intent
            items = checkpoint.items
            completion: TaskCompletion | None = None
            if yielded.outcome == "intent_ready":
                intent = yielded.intent
                connection.execute(
                    """
                    INSERT INTO agent_task_intents_v2 (
                        intent_id, intent_version, task_id, task_version,
                        content_hash, intent_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        intent.intent_id,
                        intent.intent_version,
                        intent.task_id,
                        intent.task_version,
                        intent.content_hash,
                        canonical_json(intent),
                        now,
                    ),
                )
                intent_ref = IntentRef(
                    intent_id=intent.intent_id,
                    intent_version=intent.intent_version,
                    content_hash=intent.content_hash,
                )
                prior_items = {item.item_id: item for item in checkpoint.items}
                if scope_reduction_item_ids:
                    skipped = set(scope_reduction_item_ids)
                    if skipped != {
                        item.item_id for item in checkpoint.items if item.state != "succeeded"
                    }:
                        raise self._conflict(
                            "Scope reduction must identify every unfinished or failed item."
                        )
                    succeeded = tuple(
                        item for item in checkpoint.items if item.state == "succeeded"
                    )
                    if not succeeded or any(
                        not item.verification_report_ids for item in succeeded
                    ):
                        raise self._conflict(
                            "Scope reduction requires verified successful results to retain."
                        )
                    report_ids = tuple(
                        item.verification_report_ids[-1] for item in succeeded
                    )
                    rows = connection.execute(
                        """
                        SELECT report_id, status FROM agent_verification_reports_v2
                        WHERE task_id = ?
                        """,
                        (checkpoint.task_id,),
                    ).fetchall()
                    report_status = {str(row[0]): str(row[1]) for row in rows}
                    if any(report_status.get(report_id) != "passed" for report_id in report_ids):
                        raise self._conflict(
                            "Retained results require passed verification reports."
                        )
                    next_state = "completed_verified"
                    items = checkpoint.items
                    completion = TaskCompletion(
                        outcome="completed_with_skips",
                        completed_at=now,
                        final_project_revision=checkpoint.project_revision,
                        required_report_ids=report_ids,
                        artifact_receipt_ids=tuple(
                            item.receipt_ids[-1]
                            for item in succeeded
                            if item.receipt_ids
                        ),
                        skipped_item_ids=scope_reduction_item_ids,
                    )
                else:
                    items = tuple(
                        prior_items[item.item_id]
                        if item.item_id in prior_items
                        and prior_items[item.item_id].state == "succeeded"
                        else prior_items[item.item_id].model_copy(
                            update={"state": "staged", "last_error": None}
                        )
                        if item.item_id in prior_items
                        else TaskItemSnapshot(item_id=item.item_id, state="staged")
                        for item in intent.items
                    )

            updated = self._transition(
                connection,
                checkpoint,
                next_state=next_state,
                reason_code=(
                    "USER_ACCEPTED_VERIFIED_SUBSET"
                    if scope_reduction_item_ids
                    else f"AGENT_{yielded.outcome.upper()}"
                ),
                intent=intent_ref,
                items=items,
                completion=completion,
            )
            if yielded.outcome == "cancelled":
                return self._transition(
                    connection,
                    updated,
                    next_state="cancelled",
                    reason_code="AGENT_CANCELLED_FINALIZED",
                )
            return updated

    def record_user_event(
        self,
        task_id: str,
        *,
        expected_task_version: int,
        action: UserTaskAction,
        user_event_id: str,
        payload_hash: str,
        message: str | None = None,
        context_update: TaskContextUpdate | None = None,
    ) -> TaskCheckpoint:
        if action not in USER_TASK_ACTION_TRANSITIONS:
            raise ValueError("unsupported user task action")
        allowed_states, next_state = USER_TASK_ACTION_TRANSITIONS[action]
        with self._transaction() as connection:
            current = self._get_task_in_transaction(connection, task_id)
            existing = connection.execute(
                """
                SELECT event_json FROM agent_task_events_v2
                WHERE task_id = ? AND event_type = 'user_task_event'
                """,
                (task_id,),
            ).fetchall()
            decoded = tuple(TASK_EVENT_ADAPTER.validate_json(str(row[0])) for row in existing)
            duplicate = next(
                (
                    event
                    for event in decoded
                    if isinstance(event, UserTaskEvent)
                    and event.user_event_id == user_event_id
                ),
                None,
            )
            if duplicate is not None:
                if (
                    duplicate.action != action
                    or duplicate.payload_hash != payload_hash
                    or duplicate.message != message
                    or duplicate.context_update != context_update
                ):
                    raise self._idempotency(
                        "User event id already has different content."
                    )
                return current
            self._expect_version(current, expected_task_version)
            if current.state not in allowed_states:
                raise self._conflict("User action is not valid in the current task state.")
            if (
                context_update is not None
                and context_update.project_revision < current.project_revision
            ):
                raise self._conflict("Task context cannot move the project revision backwards.")
            if context_update is not None:
                try:
                    self._replace_task_context(
                        self.get_effective_envelope(task_id), context_update
                    )
                except ValueError as error:
                    raise self._conflict(
                        "Task context update would leave the task without a valid scope."
                    ) from error
            if action == "resumed":
                latest = connection.execute(
                    """
                    SELECT activation_json, yield_json FROM agent_activations_v2
                    WHERE task_id = ? AND yield_json IS NOT NULL
                    ORDER BY updated_at DESC, activation_id DESC LIMIT 1
                    """,
                    (task_id,),
                ).fetchone()
                if latest is None:
                    raise self._conflict("A blocked task is missing its durable blocker.")
                activation = AgentActivation.model_validate_json(str(latest[0]))
                yielded = AGENT_YIELD_ADAPTER.validate_json(str(latest[1]))
                if not isinstance(yielded, AgentBlocked) or not yielded.retryable:
                    raise self._conflict("This blocked task has no retryable external condition.")
                next_state = (
                    "repairing" if activation.task_state == "repairing" else "investigating"
                )
            if action == "retry_requested":
                retryable = tuple(
                    item for item in current.items if item.state == "repairable_failed"
                )
                if not retryable or any(
                    item.last_error is None
                    or item.last_error.category != "deterministic_technical"
                    or not item.last_error.retryable
                    or item.last_error.requires_user
                    or item.last_error.side_effect_state != "known_none"
                    for item in retryable
                ):
                    raise self._conflict(
                        "Only unchanged, side-effect-free failed items can be retried "
                        "without Agent revision."
                    )
                if any(item.attempt_count >= 2 for item in retryable):
                    raise self._conflict(
                        "An unchanged technical retry is limited to one attempt; "
                        "revise the task or stop it after the repeated failure."
                    )
            now = _utc_now()
            sequence = self._next_sequence(connection, task_id)
            event = UserTaskEvent(
                event_id=self._new_id("event"),
                task_id=task_id,
                task_version=current.task_version,
                sequence=sequence,
                occurred_at=now,
                action=action,
                user_event_id=user_event_id,
                payload_hash=payload_hash,
                message=message,
                context_update=context_update,
            )
            updated = self._copy_checkpoint(
                current,
                event_sequence=sequence,
                updated_at=now,
                project_revision=(
                    None if context_update is None else context_update.project_revision
                ),
            )
            self._append_event_and_checkpoint(connection, event, updated, now)
            if action == "partial_accepted":
                succeeded = tuple(
                    item for item in updated.items if item.state == "succeeded"
                )
                skipped = tuple(
                    item for item in updated.items if item.state != "succeeded"
                )
                if (
                    not succeeded
                    or not skipped
                    or any(item.state == "running" for item in skipped)
                    or any(not item.verification_report_ids for item in succeeded)
                ):
                    raise self._conflict(
                        "A partial result can close only after verified successes "
                        "and an atomic boundary."
                    )
                report_ids = tuple(
                    item.verification_report_ids[-1] for item in succeeded
                )
                rows = connection.execute(
                    """
                    SELECT report_id, status FROM agent_verification_reports_v2
                    WHERE task_id = ?
                    """,
                    (task_id,),
                ).fetchall()
                report_status = {str(row[0]): str(row[1]) for row in rows}
                if any(report_status.get(report_id) != "passed" for report_id in report_ids):
                    raise self._conflict(
                        "Retained results require passed verification reports."
                    )
                return self._transition(
                    connection,
                    updated,
                    next_state="completed_verified",
                    reason_code="USER_ACCEPTED_VERIFIED_SUBSET",
                    completion=TaskCompletion(
                        outcome="completed_with_skips",
                        completed_at=now,
                        final_project_revision=updated.project_revision,
                        required_report_ids=report_ids,
                        artifact_receipt_ids=tuple(
                            item.receipt_ids[-1]
                            for item in succeeded
                            if item.receipt_ids
                        ),
                        skipped_item_ids=tuple(item.item_id for item in skipped),
                    ),
                )
            if next_state is None:
                return updated
            return self._transition(
                connection,
                updated,
                next_state=next_state,
                reason_code=f"USER_{action.upper()}",
            )

    def latest_user_event(self, task_id: str) -> UserTaskEvent | None:
        rows = self._connection.execute(
            """
            SELECT event_json FROM agent_task_events_v2
            WHERE task_id = ? AND event_type = 'user_task_event'
            ORDER BY sequence DESC LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        if rows is None:
            return None
        event = TASK_EVENT_ADAPTER.validate_json(str(rows[0]))
        return event if isinstance(event, UserTaskEvent) else None

    def confirm_plan(
        self,
        task_id: str,
        *,
        expected_task_version: int,
        user_event_id: str,
        payload_hash: str,
        grant: ExecutionGrant,
    ) -> TaskCheckpoint:
        """Atomically bind user confirmation, state transition and least-privilege grant."""

        with self._transaction() as connection:
            current = self._get_task_in_transaction(connection, task_id)
            self._expect_version(current, expected_task_version)
            if current.state not in {
                "awaiting_confirmation",
                "awaiting_reconfirmation",
            } or current.intent is None:
                raise self._conflict("Task is not awaiting plan confirmation.")
            plan_row = connection.execute(
                """
                SELECT plan_id, plan_hash FROM agent_task_plans_v2
                WHERE task_id = ? AND intent_id = ? AND intent_version = ?
                """,
                (task_id, current.intent.intent_id, current.intent.intent_version),
            ).fetchone()
            if plan_row is None:
                raise self._conflict("Task confirmation requires a staged plan.")
            if payload_hash != str(plan_row[1]):
                raise self._conflict("Confirmation does not match the current task plan.")
            expected_grant_hash = canonical_hash(
                grant.model_dump(mode="json", exclude={"content_hash"})
            )
            if grant.content_hash != expected_grant_hash:
                raise self._conflict("Execution grant content hash is invalid.")
            if (
                grant.task_id != task_id
                or grant.task_version != current.task_version + 1
                or grant.intent != current.intent
                or grant.expected_project_revision != current.project_revision
                or grant.grant_id
                != f"grant:{str(plan_row[0]).removeprefix('plan:')}"
            ):
                raise self._conflict("Execution grant does not match the confirmed task plan.")
            item_ids = tuple(item.item_id for item in current.items)
            if tuple(scope.item_id for scope in grant.scopes) != item_ids:
                raise self._conflict("Execution grant scope differs from the task items.")

            existing_events = connection.execute(
                """
                SELECT event_json FROM agent_task_events_v2
                WHERE task_id = ? AND event_type = 'user_task_event'
                """,
                (task_id,),
            ).fetchall()
            for row in existing_events:
                event = TASK_EVENT_ADAPTER.validate_json(str(row[0]))
                if isinstance(event, UserTaskEvent) and event.user_event_id == user_event_id:
                    if event.action != "confirmed" or event.payload_hash != payload_hash:
                        raise self._idempotency(
                            "User event id already has different content."
                        )
                    existing = connection.execute(
                        """
                        SELECT grant_json FROM agent_execution_grants_v2
                        WHERE task_id = ? AND plan_id = ?
                        """,
                        (task_id, str(plan_row[0])),
                    ).fetchone()
                    if existing is None or str(existing[0]) != canonical_json(grant):
                        raise self._idempotency(
                            "Confirmed task does not retain the same execution grant."
                        )
                    return current

            now = _utc_now()
            sequence = self._next_sequence(connection, task_id)
            event = UserTaskEvent(
                event_id=self._new_id("event"),
                task_id=task_id,
                task_version=current.task_version,
                sequence=sequence,
                occurred_at=now,
                action="confirmed",
                user_event_id=user_event_id,
                payload_hash=payload_hash,
            )
            checkpoint = self._copy_checkpoint(
                current,
                event_sequence=sequence,
                updated_at=now,
            )
            self._append_event_and_checkpoint(connection, event, checkpoint, now)
            updated = self._transition(
                connection,
                checkpoint,
                next_state="executing",
                reason_code="USER_CONFIRMED",
            )
            if updated.task_version != grant.task_version:
                raise self._conflict("Execution grant task version is stale.")
            connection.execute(
                """
                INSERT INTO agent_execution_grants_v2 (
                    grant_id, task_id, plan_id, grant_hash, grant_json, issued_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    grant.grant_id,
                    task_id,
                    str(plan_row[0]),
                    grant.content_hash,
                    canonical_json(grant),
                    grant.issued_at,
                ),
            )
            return updated

    def cancel(
        self,
        task_id: str,
        *,
        expected_task_version: int,
        user_event_id: str,
        payload_hash: str,
    ) -> TaskCheckpoint:
        return self.record_user_event(
            task_id,
            expected_task_version=expected_task_version,
            action="cancel_requested",
            user_event_id=user_event_id,
            payload_hash=payload_hash,
        )

    def finalize_cancel(self, task_id: str, *, expected_task_version: int) -> TaskCheckpoint:
        """Stop at an item boundary and preserve already committed batch outputs."""

        current = self.get_task(task_id)
        self._expect_version(current, expected_task_version)
        if current.state != "cancelling":
            raise self._conflict("Only a cancelling task can be finalized.")
        if any(item.state == "running" for item in current.items):
            raise self._conflict(
                "A cancelling task cannot finalize before its running item "
                "reaches an atomic boundary."
            )
        for item in current.items:
            if item.state in {"succeeded", "failed", "cancelled"}:
                continue
            current = self.transition_item(
                task_id,
                expected_task_version=current.task_version,
                item_id=item.item_id,
                expected_item_state=item.state,
                next_state="cancelled",
                reason_code="USER_CANCELLED_REMAINING_ITEM",
            )
        return self.advance(
            task_id,
            expected_task_version=current.task_version,
            next_state="cancelled",
            reason_code=(
                "CANCELLED_AFTER_PARTIAL_COMMIT"
                if any(item.state == "succeeded" for item in current.items)
                else "USER_CANCELLED_FINALIZED"
            ),
        )

    def transition_item(
        self,
        task_id: str,
        *,
        expected_task_version: int,
        item_id: str,
        expected_item_state: TaskItemState,
        next_state: TaskItemState,
        reason_code: str,
        error: TaskError | None = None,
        output_plot_id: str | None = None,
        output_plot_version: int | None = None,
    ) -> TaskCheckpoint:
        with self._transaction() as connection:
            current = self._get_task_in_transaction(connection, task_id)
            self._expect_version(current, expected_task_version)
            position = next(
                (index for index, item in enumerate(current.items) if item.item_id == item_id),
                None,
            )
            if position is None:
                raise self._not_found("Agent task item was not found.")
            item = current.items[position]
            if item.state != expected_item_state:
                raise self._conflict("Agent task item state is stale.")
            if not is_legal_task_item_transition(item.state, next_state):
                raise self._conflict(
                    f"Illegal task item transition: {item.state} -> {next_state}."
                )
            updated_item = TaskItemSnapshot(
                item_id=item.item_id,
                state=next_state,
                attempt_count=item.attempt_count + (1 if next_state == "running" else 0),
                last_error=error,
                output_plot_id=output_plot_id or item.output_plot_id,
                output_plot_version=output_plot_version or item.output_plot_version,
                receipt_ids=item.receipt_ids,
                verification_report_ids=item.verification_report_ids,
            )
            items = list(current.items)
            items[position] = updated_item
            now = _utc_now()
            sequence = self._next_sequence(connection, task_id)
            event = TaskItemTransitionEvent(
                event_id=self._new_id("event"),
                task_id=task_id,
                task_version=current.task_version,
                sequence=sequence,
                occurred_at=now,
                item_id=item_id,
                previous_state=item.state,
                next_state=next_state,
                reason_code=reason_code,
            )
            updated = self._copy_checkpoint(
                current,
                event_sequence=sequence,
                items=tuple(items),
                active_activation_id=current.active_activation_id,
                updated_at=now,
            )
            self._append_event_and_checkpoint(connection, event, updated, now)
            return updated

    def record_tool_receipt(self, receipt: ToolReceipt) -> TaskCheckpoint:
        with self._transaction() as connection:
            current = self._get_task_in_transaction(connection, receipt.task_id)
            payload = canonical_json(receipt)
            existing = connection.execute(
                "SELECT receipt_json FROM agent_tool_receipts_v2 WHERE receipt_id = ?",
                (receipt.receipt_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != payload:
                    raise self._idempotency("Receipt id already has different content.")
                return current
            self._expect_version(current, receipt.task_version)
            if receipt.project_revision_before != current.project_revision:
                raise self._conflict("Tool receipt project revision is stale.")
            updated_budget = _apply_tool_budget(current.budget, receipt.budget_delta)
            now = _utc_now()
            connection.execute(
                """
                INSERT INTO agent_tool_receipts_v2 (
                    receipt_id, task_id, task_version, tool_call_id,
                    input_hash, receipt_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.receipt_id,
                    receipt.task_id,
                    receipt.task_version,
                    receipt.tool_call_id,
                    receipt.input_hash,
                    payload,
                    now,
                ),
            )
            items = self._append_item_receipt(current.items, receipt)
            sequence = self._next_sequence(connection, current.task_id)
            event = ToolReceiptEvent(
                event_id=self._new_id("event"),
                task_id=current.task_id,
                task_version=current.task_version,
                sequence=sequence,
                occurred_at=now,
                receipt=receipt,
            )
            updated = self._copy_checkpoint(
                current,
                event_sequence=sequence,
                items=items,
                project_revision=receipt.project_revision_after,
                budget=updated_budget,
                active_activation_id=current.active_activation_id,
                updated_at=now,
            )
            self._append_event_and_checkpoint(connection, event, updated, now)
            return updated

    def get_tool_receipt(self, receipt_id: str) -> ToolReceipt:
        row = self._connection.execute(
            "SELECT receipt_json FROM agent_tool_receipts_v2 WHERE receipt_id = ?",
            (receipt_id,),
        ).fetchone()
        if row is None:
            raise self._not_found("Agent tool receipt was not found.")
        return ToolReceipt.model_validate_json(str(row[0]))

    def record_verification_report(self, report: VerificationReport) -> TaskCheckpoint:
        with self._transaction() as connection:
            current = self._get_task_in_transaction(connection, report.task_id)
            payload = canonical_json(report)
            existing = connection.execute(
                """
                SELECT report_json FROM agent_verification_reports_v2
                WHERE report_id = ?
                """,
                (report.report_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != payload:
                    raise self._idempotency("Report id already has different content.")
                return current
            self._expect_version(current, report.task_version)
            now = _utc_now()
            connection.execute(
                """
                INSERT INTO agent_verification_reports_v2 (
                    report_id, task_id, task_version, item_id, status,
                    content_hash, report_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.report_id,
                    report.task_id,
                    report.task_version,
                    report.item_id,
                    report.status,
                    report.content_hash,
                    payload,
                    now,
                ),
            )
            items = self._append_item_report(current.items, report)
            sequence = self._next_sequence(connection, current.task_id)
            event = VerificationReportEvent(
                event_id=self._new_id("event"),
                task_id=current.task_id,
                task_version=current.task_version,
                sequence=sequence,
                occurred_at=now,
                report=report,
            )
            updated = self._copy_checkpoint(
                current,
                event_sequence=sequence,
                items=items,
                active_activation_id=current.active_activation_id,
                updated_at=now,
            )
            self._append_event_and_checkpoint(connection, event, updated, now)
            return updated

    def get_verification_report(self, report_id: str) -> VerificationReport:
        row = self._connection.execute(
            """SELECT report_json, content_hash FROM agent_verification_reports_v2
            WHERE report_id = ?""",
            (report_id,),
        ).fetchone()
        if row is None:
            raise self._not_found("Agent verification report was not found.")
        _verified_json_object(
            str(row[0]),
            str(row[1]),
            error_message="Agent verification report hash does not match its content",
            embedded_hash_field="content_hash",
        )
        return VerificationReport.model_validate_json(str(row[0]))

    def acquire_lease(
        self,
        task_id: str,
        *,
        holder_id: str,
        ttl_seconds: int = 120,
    ) -> str:
        if not 1 <= ttl_seconds <= 3600:
            raise ValueError("task lease ttl must be between 1 and 3600 seconds")
        with self._transaction() as connection:
            self._get_task_in_transaction(connection, task_id)
            now_value = datetime.now(UTC)
            now = now_value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
            existing = connection.execute(
                """
                SELECT lease_token, holder_id, expires_at
                FROM agent_task_leases_v2 WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if existing is not None:
                expires_at = datetime.fromisoformat(str(existing[2]).replace("Z", "+00:00"))
                if expires_at > now_value and str(existing[1]) != holder_id:
                    raise self._conflict("Agent task has an active writer lease.")
            lease_token = self._new_id("lease")
            expires = (now_value + timedelta(seconds=ttl_seconds)).isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z")
            connection.execute(
                """
                INSERT INTO agent_task_leases_v2 (
                    task_id, lease_token, holder_id, expires_at, acquired_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    lease_token = excluded.lease_token,
                    holder_id = excluded.holder_id,
                    expires_at = excluded.expires_at,
                    acquired_at = excluded.acquired_at
                """,
                (task_id, lease_token, holder_id, expires, now),
            )
            return lease_token

    def release_lease(self, task_id: str, *, lease_token: str) -> None:
        with self._transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM agent_task_leases_v2 WHERE task_id = ? AND lease_token = ?",
                (task_id, lease_token),
            )
            if cursor.rowcount == 0:
                raise self._conflict("Agent task lease is stale or not owned by this caller.")

    def _transition(
        self,
        connection: sqlite3.Connection,
        current: TaskCheckpoint,
        *,
        next_state: TaskState,
        reason_code: str,
        project_revision: int | None = None,
        intent: IntentRef | None = None,
        items: tuple[TaskItemSnapshot, ...] | None = None,
        preserve_activation: bool = False,
        completion: TaskCompletion | None = None,
    ) -> TaskCheckpoint:
        if not is_legal_task_transition(current.state, next_state):
            raise self._conflict(
                f"Illegal task transition: {current.state} -> {next_state}."
            )
        if project_revision is not None and project_revision < current.project_revision:
            raise self._conflict("Task project revision cannot move backwards.")
        now = _utc_now()
        sequence = self._next_sequence(connection, current.task_id)
        task_version = current.task_version + (0 if next_state == current.state else 1)
        event = TaskStateTransitionEvent(
            event_id=self._new_id("event"),
            task_id=current.task_id,
            task_version=task_version,
            sequence=sequence,
            occurred_at=now,
            previous_state=current.state,
            next_state=next_state,
            reason_code=reason_code,
        )
        updated = self._copy_checkpoint(
            current,
            task_version=task_version,
            state=next_state,
            project_revision=(
                current.project_revision if project_revision is None else project_revision
            ),
            event_sequence=sequence,
            intent=current.intent if intent is None else intent,
            items=current.items if items is None else items,
            active_activation_id=(current.active_activation_id if preserve_activation else None),
            completion=completion,
            updated_at=now,
        )
        self._append_event_and_checkpoint(connection, event, updated, now)
        return updated

    def _append_event_and_checkpoint(
        self,
        connection: sqlite3.Connection,
        event: TaskEvent,
        checkpoint: TaskCheckpoint,
        now: str,
    ) -> None:
        self._insert_event(connection, event)
        self._insert_checkpoint(connection, checkpoint, now)
        cursor = connection.execute(
            """
            UPDATE agent_tasks_v2 SET
                task_version = ?, state = ?, project_revision = ?,
                checkpoint_hash = ?, checkpoint_json = ?,
                next_event_sequence = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (
                checkpoint.task_version,
                checkpoint.state,
                checkpoint.project_revision,
                checkpoint.content_hash,
                canonical_json(checkpoint),
                checkpoint.last_event_sequence + 1,
                now,
                checkpoint.task_id,
            ),
        )
        if cursor.rowcount != 1:
            raise self._not_found("Agent task was not found while updating its checkpoint.")

    @staticmethod
    def _insert_event(connection: sqlite3.Connection, event: TaskEvent) -> None:
        connection.execute(
            """
            INSERT INTO agent_task_events_v2 (
                event_id, task_id, task_version, sequence,
                event_type, event_json, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.task_id,
                event.task_version,
                event.sequence,
                event.event_type,
                _event_json(event),
                event.occurred_at,
            ),
        )

    @staticmethod
    def _insert_checkpoint(
        connection: sqlite3.Connection,
        checkpoint: TaskCheckpoint,
        now: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO agent_task_checkpoints_v2 (
                checkpoint_id, task_id, task_version, event_sequence,
                content_hash, checkpoint_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checkpoint.checkpoint_id,
                checkpoint.task_id,
                checkpoint.task_version,
                checkpoint.last_event_sequence,
                checkpoint.content_hash,
                canonical_json(checkpoint),
                now,
            ),
        )

    def _get_task_in_transaction(
        self, connection: sqlite3.Connection, task_id: str
    ) -> TaskCheckpoint:
        row = connection.execute(
            "SELECT checkpoint_json, checkpoint_hash FROM agent_tasks_v2 WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise self._not_found("Agent task was not found.")
        return self._decode_checkpoint(str(row[0]), expected_hash=str(row[1]))

    @staticmethod
    def _decode_checkpoint(
        payload: str, *, expected_hash: str | None = None
    ) -> TaskCheckpoint:
        try:
            decoded = json.loads(payload)
        except (TypeError, ValueError) as error:
            raise sqlite3.DatabaseError(
                "Agent task checkpoint hash does not match its content"
            ) from error
        if not isinstance(decoded, dict):
            raise sqlite3.DatabaseError(
                "Agent task checkpoint hash does not match its content"
            )
        embedded = decoded.get("content_hash")
        if not isinstance(embedded, str):
            raise sqlite3.DatabaseError(
                "Agent task checkpoint hash does not match its content"
            )
        _verified_json_object(
            payload,
            embedded,
            error_message="Agent task checkpoint hash does not match its content",
            embedded_hash_field="content_hash",
        )
        if expected_hash is not None and embedded != expected_hash:
            raise sqlite3.DatabaseError(
                "Agent task checkpoint hash does not match its content"
            )
        return TaskCheckpoint.model_validate_json(payload)

    def _activation_context(
        self,
        connection: sqlite3.Connection,
        activation_id: str,
    ) -> tuple[AgentActivation, TaskCheckpoint, str]:
        row = connection.execute(
            """
            SELECT activation_json, status, task_id
            FROM agent_activations_v2 WHERE activation_id = ?
            """,
            (activation_id,),
        ).fetchone()
        if row is None:
            raise self._not_found("Agent activation was not found.")
        activation = AgentActivation.model_validate_json(str(row[0]))
        current = self._get_task_in_transaction(connection, str(row[2]))
        return activation, current, str(row[1])

    @staticmethod
    def _next_sequence(connection: sqlite3.Connection, task_id: str) -> int:
        row = connection.execute(
            "SELECT next_event_sequence FROM agent_tasks_v2 WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, "Agent task was not found.")
        return int(row[0])

    @staticmethod
    def _expect_version(checkpoint: TaskCheckpoint, expected: int) -> None:
        if checkpoint.task_version != expected:
            raise StorageProblem(
                StorageErrorCode.VERSION_CONFLICT,
                "Agent task version is stale.",
            )

    @staticmethod
    def _yield_state(yielded: AgentYield) -> TaskState:
        states: dict[str, TaskState] = {
            "intent_ready": "intent_staged",
            "needs_input": "awaiting_input",
            "information_ready": "completed_verified",
            "technical_repair_ready": "executing",
            "unsupported": "unsupported",
            "blocked": "blocked",
            # A task-wide budget has no in-place mutation or extension control.
            # Treat exhaustion as an explicit terminal failure; retrying means a
            # new task with a fresh, auditable budget rather than a fake resume.
            "budget_exhausted": "failed",
            "cancelled": "cancelling",
            "runtime_failed": "failed",
        }
        return states[yielded.outcome]

    @staticmethod
    def _append_item_receipt(
        items: tuple[TaskItemSnapshot, ...], receipt: ToolReceipt
    ) -> tuple[TaskItemSnapshot, ...]:
        if receipt.item_id is None:
            return items
        found = False
        updated: list[TaskItemSnapshot] = []
        for item in items:
            if item.item_id != receipt.item_id:
                updated.append(item)
                continue
            found = True
            updated.append(
                item.model_copy(update={"receipt_ids": (*item.receipt_ids, receipt.receipt_id)})
            )
        if not found:
            raise StorageProblem(StorageErrorCode.VERSION_CONFLICT, "Receipt task item is stale.")
        return tuple(updated)

    @staticmethod
    def _append_item_report(
        items: tuple[TaskItemSnapshot, ...], report: VerificationReport
    ) -> tuple[TaskItemSnapshot, ...]:
        if report.item_id is None:
            return items
        found = False
        updated: list[TaskItemSnapshot] = []
        for item in items:
            if item.item_id != report.item_id:
                updated.append(item)
                continue
            found = True
            updated.append(
                item.model_copy(
                    update={
                        "verification_report_ids": (
                            *item.verification_report_ids,
                            report.report_id,
                        )
                    }
                )
            )
        if not found:
            raise StorageProblem(StorageErrorCode.VERSION_CONFLICT, "Report task item is stale.")
        return tuple(updated)

    @staticmethod
    def _new_checkpoint(
        *,
        task_id: str,
        task_version: int,
        state: TaskState,
        project_revision: int,
        event_sequence: int,
        budget: TaskBudgetSnapshot,
        updated_at: str,
        intent: IntentRef | None = None,
        active_activation_id: str | None = None,
        items: tuple[TaskItemSnapshot, ...] = (),
        completion: TaskCompletion | None = None,
    ) -> TaskCheckpoint:
        draft = TaskCheckpoint(
            checkpoint_id=TaskLedgerRepository._new_id("checkpoint"),
            task_id=task_id,
            task_version=task_version,
            state=state,
            project_revision=project_revision,
            last_event_sequence=event_sequence,
            intent=intent,
            active_activation_id=active_activation_id,
            items=items,
            budget=budget,
            completion=completion,
            updated_at=updated_at,
            content_hash="0" * 64,
        )
        return draft.model_copy(update={"content_hash": _checkpoint_hash(draft)})

    @staticmethod
    def _replace_task_context(
        envelope: TaskEnvelope,
        context: TaskContextUpdate,
    ) -> TaskEnvelope:
        payload = envelope.model_dump(mode="python")
        payload["project_revision"] = context.project_revision
        if context.selected_sources is not None:
            payload["selected_sources"] = context.selected_sources
        if context.selected_plots is not None:
            payload["selected_plots"] = context.selected_plots
        if context.selected_profile_ids is not None:
            payload["selected_profile_ids"] = context.selected_profile_ids
        return TaskEnvelope.model_validate(payload)

    @staticmethod
    def _copy_checkpoint(
        current: TaskCheckpoint,
        *,
        task_version: int | None = None,
        state: TaskState | None = None,
        project_revision: int | None = None,
        budget: TaskBudgetSnapshot | None = None,
        event_sequence: int,
        intent: IntentRef | None = None,
        active_activation_id: str | None = None,
        items: tuple[TaskItemSnapshot, ...] | None = None,
        completion: TaskCompletion | None = None,
        updated_at: str,
    ) -> TaskCheckpoint:
        return TaskLedgerRepository._new_checkpoint(
            task_id=current.task_id,
            task_version=current.task_version if task_version is None else task_version,
            state=current.state if state is None else state,
            project_revision=(
                current.project_revision if project_revision is None else project_revision
            ),
            event_sequence=event_sequence,
            budget=current.budget if budget is None else budget,
            updated_at=updated_at,
            intent=current.intent if intent is None else intent,
            active_activation_id=active_activation_id,
            items=current.items if items is None else items,
            completion=completion,
        )

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}:{uuid.uuid4().hex}"

    @staticmethod
    def _not_found(message: str) -> StorageProblem:
        return StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, message)

    @staticmethod
    def _conflict(message: str) -> StorageProblem:
        return StorageProblem(StorageErrorCode.VERSION_CONFLICT, message)

    @staticmethod
    def _idempotency(message: str) -> StorageProblem:
        return StorageProblem(StorageErrorCode.IDEMPOTENCY_CONFLICT, message)


def decode_agent_yield(payload: str) -> AgentYield:
    """Validate a persisted/runtime payload at the ledger boundary."""

    return AGENT_YIELD_ADAPTER.validate_json(payload)
