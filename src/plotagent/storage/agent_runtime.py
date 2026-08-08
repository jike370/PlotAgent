"""Single-writer persistence for project context and recoverable Agent plans."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import TypeAdapter

from plotagent.contracts.agent_context import ConversationStateProjection
from plotagent.contracts.canonical import JsonValue, canonical_hash, canonical_json
from plotagent.contracts.decisions import ActionPlan, BusinessAction
from plotagent.contracts.project_context import ProjectContextSnapshot
from plotagent.contracts.task_runtime import (
    ConfirmationState,
    TaskAttemptSnapshot,
    TaskFailure,
    TaskItemSnapshot,
    TaskItemState,
    TaskOutputRef,
    TaskPlanSnapshot,
    TaskPlanState,
)
from plotagent.storage.errors import StorageErrorCode, StorageProblem
from plotagent.storage.project import ProjectStore

_ACTION_ADAPTER: TypeAdapter[BusinessAction] = TypeAdapter(BusinessAction)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _json(value: object) -> str:
    return canonical_json(cast(Any, value))


@dataclass(frozen=True, slots=True)
class StoredTaskEvent:
    event_id: int
    plan_id: str
    task_item_id: str | None
    event_type: str
    payload: dict[str, JsonValue]
    created_at: str


_ITEM_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"ready", "blocked", "stale", "skipped", "cancelled"}),
    "ready": frozenset({"running", "blocked", "stale", "cancelled"}),
    "running": frozenset({"committing", "succeeded", "failed", "interrupted", "cancelled"}),
    "committing": frozenset({"succeeded", "failed", "interrupted"}),
    "failed": frozenset({"ready", "stale", "cancelled"}),
    "interrupted": frozenset({"ready", "stale", "cancelled"}),
    "blocked": frozenset({"ready", "stale", "skipped", "cancelled"}),
    "stale": frozenset({"cancelled"}),
    "skipped": frozenset(),
    "cancelled": frozenset(),
    "succeeded": frozenset(),
}

_PLAN_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"needs_confirmation", "ready", "cancelled"}),
    "needs_confirmation": frozenset({"ready", "cancelled"}),
    "ready": frozenset({"running", "needs_input", "stale", "cancelled"}),
    "running": frozenset(
        {
            "partial_success",
            "succeeded",
            "failed",
            "interrupted",
            "needs_input",
            "stale",
            "cancelled",
        }
    ),
    "partial_success": frozenset(
        {"running", "succeeded", "failed", "interrupted", "stale", "cancelled"}
    ),
    "failed": frozenset({"ready", "stale", "cancelled"}),
    "interrupted": frozenset({"ready", "running", "stale", "cancelled"}),
    "needs_input": frozenset({"ready", "stale", "cancelled"}),
    "stale": frozenset({"cancelled"}),
    "cancelled": frozenset(),
    "succeeded": frozenset(),
}


class AgentRuntimeRepository:
    """Persist only typed conversation/context/task objects in the project DB."""

    def __init__(self, project: ProjectStore) -> None:
        self.project = project

    @property
    def _connection(self) -> sqlite3.Connection:
        return self.project._assert_writer()  # noqa: SLF001

    def save_conversation_state(
        self,
        conversation_id: str,
        state: ConversationStateProjection,
        *,
        expected_state_version: int | None,
        context_hash: str | None = None,
    ) -> None:
        connection = self._connection
        now = _utc_now()
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute(
                "SELECT state_version FROM conversation_states WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if row is None:
                if expected_state_version is not None:
                    raise StorageProblem(
                        StorageErrorCode.VERSION_CONFLICT,
                        "Conversation state does not exist at the expected version.",
                    )
                connection.execute(
                    "INSERT INTO conversations(conversation_id, created_at, updated_at) "
                    "VALUES (?, ?, ?)",
                    (conversation_id, now, now),
                )
                connection.execute(
                    "INSERT INTO conversation_states("
                    "conversation_id, state_version, state_json, context_hash, updated_at"
                    ") VALUES (?, ?, ?, ?, ?)",
                    (conversation_id, state.state_version, _json(state), context_hash, now),
                )
            else:
                current = int(row[0])
                if expected_state_version != current or state.state_version <= current:
                    raise StorageProblem(
                        StorageErrorCode.VERSION_CONFLICT,
                        "Conversation state version is stale.",
                    )
                connection.execute(
                    "UPDATE conversation_states SET state_version = ?, state_json = ?, "
                    "context_hash = ?, updated_at = ? WHERE conversation_id = ?",
                    (state.state_version, _json(state), context_hash, now, conversation_id),
                )
                connection.execute(
                    "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
                    (now, conversation_id),
                )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise

    def get_conversation_state(self, conversation_id: str) -> ConversationStateProjection | None:
        row = self._connection.execute(
            "SELECT state_json FROM conversation_states WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        return (
            None
            if row is None
            else ConversationStateProjection.model_validate_json(str(row[0]))
        )

    def save_context_snapshot(self, snapshot: ProjectContextSnapshot) -> None:
        connection = self._connection
        existing = connection.execute(
            "SELECT snapshot_hash, snapshot_json FROM project_context_snapshots "
            "WHERE snapshot_id = ?",
            (snapshot.snapshot_id,),
        ).fetchone()
        payload = _json(snapshot)
        if existing is not None:
            if str(existing[0]) != snapshot.snapshot_hash or str(existing[1]) != payload:
                raise StorageProblem(
                    StorageErrorCode.IDEMPOTENCY_CONFLICT,
                    "Context snapshot id was already used for different state.",
                )
            return
        connection.execute(
            "INSERT INTO project_context_snapshots("
            "snapshot_id, conversation_id, project_revision, snapshot_hash, "
            "snapshot_json, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?)",
            (
                snapshot.snapshot_id,
                snapshot.conversation_id,
                snapshot.project_revision,
                snapshot.snapshot_hash,
                payload,
                _utc_now(),
            ),
        )

    def get_context_snapshot(self, snapshot_id: str) -> ProjectContextSnapshot:
        row = self._connection.execute(
            "SELECT snapshot_json FROM project_context_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            raise StorageProblem(
                StorageErrorCode.OBJECT_NOT_FOUND,
                "Context snapshot was not found.",
            )
        return ProjectContextSnapshot.model_validate_json(str(row[0]))

    def create_plan(self, plan: TaskPlanSnapshot) -> None:
        connection = self._connection
        existing = connection.execute(
            "SELECT source_plan_hash FROM task_plans WHERE plan_id = ?", (plan.plan_id,)
        ).fetchone()
        if existing is not None:
            if str(existing[0]) != plan.source_plan_hash:
                raise StorageProblem(
                    StorageErrorCode.IDEMPOTENCY_CONFLICT,
                    "Plan id was already used for a different plan.",
                )
            return
        now = _utc_now()
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                "INSERT INTO task_plans("
                "plan_id, conversation_id, context_snapshot_id, context_hash, project_revision, "
                "source_plan_hash, source_plan_json, state, confirmation_state, "
                "created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    plan.plan_id,
                    plan.conversation_id,
                    plan.context_snapshot_id,
                    plan.context_hash,
                    plan.project_revision,
                    plan.source_plan_hash,
                    _json(plan.source_plan),
                    plan.state,
                    plan.confirmation_state,
                    now,
                    now,
                ),
            )
            for position, item in enumerate(plan.items):
                connection.execute(
                    "INSERT INTO task_items("
                    "task_item_id, plan_id, position, action_id, action_type, action_json, state, "
                    "depends_on_json, expected_objects_json, idempotency_key, output_slots_json, "
                    "outputs_json, attempt_count, failure_json, updated_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.task_item_id,
                        plan.plan_id,
                        position,
                        item.action.action_id,
                        item.action.action_type,
                        _json(item.action),
                        item.state,
                        _json(item.depends_on),
                        _json(item.expected_objects),
                        item.idempotency_key,
                        _json(item.output_slots),
                        _json(item.outputs),
                        item.attempt_count,
                        None if item.failure is None else _json(item.failure),
                        now,
                    ),
                )
            self._append_event(
                connection,
                plan.plan_id,
                None,
                "plan.created",
                {"state": plan.state, "item_count": len(plan.items)},
                now,
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise

    def get_plan(self, plan_id: str) -> TaskPlanSnapshot:
        plan_row = self._connection.execute(
            "SELECT conversation_id, context_snapshot_id, context_hash, project_revision, "
            "source_plan_hash, source_plan_json, state, confirmation_state "
            "FROM task_plans WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
        if plan_row is None:
            raise StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, "Task plan was not found.")
        item_rows = self._connection.execute(
            "SELECT task_item_id, action_json, state, depends_on_json, expected_objects_json, "
            "idempotency_key, output_slots_json, outputs_json, attempt_count, failure_json "
            "FROM task_items WHERE plan_id = ? ORDER BY position",
            (plan_id,),
        ).fetchall()
        items = tuple(self._item_from_row(row) for row in item_rows)
        return TaskPlanSnapshot(
            plan_id=plan_id,
            conversation_id=str(plan_row[0]),
            context_snapshot_id=str(plan_row[1]),
            context_hash=str(plan_row[2]),
            project_revision=int(plan_row[3]),
            source_plan=ActionPlan.model_validate_json(str(plan_row[5])),
            source_plan_hash=str(plan_row[4]),
            state=cast(TaskPlanState, str(plan_row[6])),
            confirmation_state=cast(ConfirmationState, str(plan_row[7])),
            items=items,
        )

    def list_plans(self, conversation_id: str) -> tuple[TaskPlanSnapshot, ...]:
        rows = self._connection.execute(
            "SELECT plan_id FROM task_plans WHERE conversation_id = ? ORDER BY created_at",
            (conversation_id,),
        ).fetchall()
        return tuple(self.get_plan(str(row[0])) for row in rows)

    def confirm_plan(self, plan_id: str, *, accept: bool) -> TaskPlanSnapshot:
        plan = self.get_plan(plan_id)
        if plan.state != "needs_confirmation" or plan.confirmation_state != "pending":
            raise StorageProblem(
                StorageErrorCode.VERSION_CONFLICT,
                "Plan is not awaiting confirmation.",
            )
        connection = self._connection
        now = _utc_now()
        connection.execute("BEGIN IMMEDIATE")
        try:
            if accept:
                connection.execute(
                    "UPDATE task_plans SET state = 'ready', confirmation_state = 'confirmed', "
                    "updated_at = ? WHERE plan_id = ?",
                    (now, plan_id),
                )
                connection.execute(
                    "UPDATE task_items SET state = "
                    "CASE WHEN position = 0 THEN 'ready' ELSE 'pending' END, "
                    "updated_at = ? WHERE plan_id = ?",
                    (now, plan_id),
                )
                event_type = "plan.confirmed"
            else:
                connection.execute(
                    "UPDATE task_plans SET state = 'cancelled', confirmation_state = 'rejected', "
                    "updated_at = ? WHERE plan_id = ?",
                    (now, plan_id),
                )
                connection.execute(
                    "UPDATE task_items SET state = 'cancelled', updated_at = ? WHERE plan_id = ?",
                    (now, plan_id),
                )
                event_type = "plan.rejected"
            self._append_event(connection, plan_id, None, event_type, {}, now)
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        return self.get_plan(plan_id)

    def transition_item(self, task_item_id: str, state: str) -> TaskItemSnapshot:
        connection = self._connection
        row = connection.execute(
            "SELECT plan_id, state FROM task_items WHERE task_item_id = ?", (task_item_id,)
        ).fetchone()
        if row is None:
            raise StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, "Task item was not found.")
        plan_id, current = str(row[0]), str(row[1])
        if state not in _ITEM_TRANSITIONS.get(current, frozenset()):
            raise StorageProblem(
                StorageErrorCode.VERSION_CONFLICT,
                f"Task item transition is invalid: {current} -> {state}.",
            )
        now = _utc_now()
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                "UPDATE task_items SET state = ?, updated_at = ? WHERE task_item_id = ?",
                (state, now, task_item_id),
            )
            if state == "running":
                self._set_plan_state(connection, plan_id, "running", now)
            elif state == "ready" and current in {"failed", "interrupted", "blocked"}:
                self._set_plan_state(connection, plan_id, "ready", now)
            self._append_event(
                connection,
                plan_id,
                task_item_id,
                "item.state_changed",
                {"from": current, "to": state},
                now,
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        return self._get_item(task_item_id)

    def begin_attempt(self, task_item_id: str) -> TaskAttemptSnapshot:
        item = self._get_item(task_item_id)
        if item.state not in {"ready", "failed", "interrupted"}:
            raise StorageProblem(StorageErrorCode.VERSION_CONFLICT, "Task item is not resumable.")
        connection = self._connection
        now = _utc_now()
        attempt_number = item.attempt_count + 1
        attempt_id = f"attempt:{uuid.uuid4().hex}"
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                "UPDATE task_items SET state = 'running', attempt_count = ?, failure_json = NULL, "
                "updated_at = ? WHERE task_item_id = ?",
                (attempt_number, now, task_item_id),
            )
            connection.execute(
                "INSERT INTO task_attempts("
                "attempt_id, task_item_id, attempt_number, state, started_at"
                ") VALUES (?, ?, ?, 'running', ?)",
                (attempt_id, task_item_id, attempt_number, now),
            )
            plan_id = self._plan_id_for_item(connection, task_item_id)
            self._set_plan_state(connection, plan_id, "running", now)
            self._append_event(
                connection,
                plan_id,
                task_item_id,
                "item.attempt_started",
                {"attempt_id": attempt_id, "attempt_number": attempt_number},
                now,
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        return TaskAttemptSnapshot(
            attempt_id=attempt_id,
            task_item_id=task_item_id,
            attempt_number=attempt_number,
            state="running",
            started_at=now,
        )

    def finish_attempt(
        self,
        attempt_id: str,
        *,
        outputs: tuple[TaskOutputRef, ...] = (),
        failure: TaskFailure | None = None,
    ) -> TaskPlanSnapshot:
        connection = self._connection
        row = connection.execute(
            "SELECT task_item_id, state FROM task_attempts WHERE attempt_id = ?", (attempt_id,)
        ).fetchone()
        if row is None:
            raise StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, "Task attempt was not found.")
        task_item_id, attempt_state = str(row[0]), str(row[1])
        if attempt_state != "running":
            raise StorageProblem(
                StorageErrorCode.VERSION_CONFLICT,
                "Task attempt is already terminal.",
            )
        item = self._get_item(task_item_id)
        if item.state not in {"running", "committing"}:
            raise StorageProblem(StorageErrorCode.VERSION_CONFLICT, "Task item is not active.")
        terminal = "failed" if failure is not None else "succeeded"
        now = _utc_now()
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                "UPDATE task_attempts SET state = ?, ended_at = ?, failure_json = ? "
                "WHERE attempt_id = ?",
                (terminal, now, None if failure is None else _json(failure), attempt_id),
            )
            connection.execute(
                "UPDATE task_items SET state = ?, outputs_json = ?, failure_json = ?, "
                "updated_at = ? WHERE task_item_id = ?",
                (
                    terminal,
                    _json(outputs),
                    None if failure is None else _json(failure),
                    now,
                    task_item_id,
                ),
            )
            plan_id = self._plan_id_for_item(connection, task_item_id)
            self._append_event(
                connection,
                plan_id,
                task_item_id,
                "item.attempt_finished",
                {"attempt_id": attempt_id, "state": terminal},
                now,
            )
            self._refresh_ready_items(connection, plan_id, now)
            self._refresh_plan_state(connection, plan_id, now)
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        return self.get_plan(plan_id)

    def save_checkpoint(
        self,
        *,
        plan_id: str,
        task_item_id: str,
        checkpoint_key: str,
        payload: dict[str, JsonValue],
    ) -> str:
        payload_hash = canonical_hash(payload)
        payload_json = canonical_json(payload)
        existing = self._connection.execute(
            "SELECT payload_hash FROM task_checkpoints WHERE plan_id = ? "
            "AND task_item_id = ? AND checkpoint_key = ?",
            (plan_id, task_item_id, checkpoint_key),
        ).fetchone()
        if existing is not None:
            if str(existing[0]) != payload_hash:
                raise StorageProblem(
                    StorageErrorCode.IDEMPOTENCY_CONFLICT,
                    "Checkpoint key was already used for different payload.",
                )
            return payload_hash
        self._connection.execute(
            "INSERT INTO task_checkpoints("
            "plan_id, task_item_id, checkpoint_key, payload_json, payload_hash, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?)",
            (plan_id, task_item_id, checkpoint_key, payload_json, payload_hash, _utc_now()),
        )
        return payload_hash

    def recover_interrupted(self) -> tuple[str, ...]:
        """Mark process-bound active work interrupted; keep committed successes."""

        connection = self._connection
        rows = connection.execute(
            "SELECT plan_id FROM task_plans WHERE state IN ('running', 'partial_success') "
            "ORDER BY plan_id"
        ).fetchall()
        plan_ids = tuple(str(row[0]) for row in rows)
        if not plan_ids:
            return ()
        now = _utc_now()
        connection.execute("BEGIN IMMEDIATE")
        try:
            for plan_id in plan_ids:
                connection.execute(
                    "UPDATE task_attempts SET state = 'interrupted', ended_at = ? "
                    "WHERE state = 'running' AND task_item_id IN ("
                    "SELECT task_item_id FROM task_items WHERE plan_id = ?)",
                    (now, plan_id),
                )
                connection.execute(
                    "UPDATE task_items SET state = 'interrupted', updated_at = ? "
                    "WHERE plan_id = ? AND state IN ('running', 'committing')",
                    (now, plan_id),
                )
                connection.execute(
                    "UPDATE task_plans SET state = 'interrupted', updated_at = ? WHERE plan_id = ?",
                    (now, plan_id),
                )
                self._append_event(
                    connection,
                    plan_id,
                    None,
                    "plan.process_interrupted",
                    {},
                    now,
                )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        return plan_ids

    def list_events(self, plan_id: str) -> tuple[StoredTaskEvent, ...]:
        rows = self._connection.execute(
            "SELECT event_id, task_item_id, event_type, payload_json, created_at "
            "FROM task_events WHERE plan_id = ? ORDER BY event_id",
            (plan_id,),
        ).fetchall()
        return tuple(
            StoredTaskEvent(
                event_id=int(row[0]),
                plan_id=plan_id,
                task_item_id=None if row[1] is None else str(row[1]),
                event_type=str(row[2]),
                payload=cast(dict[str, JsonValue], json.loads(str(row[3]))),
                created_at=str(row[4]),
            )
            for row in rows
        )

    def _get_item(self, task_item_id: str) -> TaskItemSnapshot:
        row = self._connection.execute(
            "SELECT task_item_id, action_json, state, depends_on_json, expected_objects_json, "
            "idempotency_key, output_slots_json, outputs_json, attempt_count, failure_json "
            "FROM task_items WHERE task_item_id = ?",
            (task_item_id,),
        ).fetchone()
        if row is None:
            raise StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, "Task item was not found.")
        return self._item_from_row(row)

    @staticmethod
    def _item_from_row(row: sqlite3.Row | tuple[Any, ...]) -> TaskItemSnapshot:
        return TaskItemSnapshot(
            task_item_id=str(row[0]),
            action=_ACTION_ADAPTER.validate_json(str(row[1])),
            state=cast(TaskItemState, str(row[2])),
            depends_on=tuple(json.loads(str(row[3]))),
            expected_objects=tuple(json.loads(str(row[4]))),
            idempotency_key=str(row[5]),
            output_slots=tuple(json.loads(str(row[6]))),
            outputs=tuple(json.loads(str(row[7]))),
            attempt_count=int(row[8]),
            failure=None if row[9] is None else json.loads(str(row[9])),
        )

    @staticmethod
    def _plan_id_for_item(connection: sqlite3.Connection, task_item_id: str) -> str:
        row = connection.execute(
            "SELECT plan_id FROM task_items WHERE task_item_id = ?", (task_item_id,)
        ).fetchone()
        if row is None:
            raise StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, "Task item was not found.")
        return str(row[0])

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        plan_id: str,
        task_item_id: str | None,
        event_type: str,
        payload: dict[str, JsonValue],
        now: str,
    ) -> None:
        connection.execute(
            "INSERT INTO task_events("
            "plan_id, task_item_id, event_type, payload_json, created_at"
            ") VALUES (?, ?, ?, ?, ?)",
            (plan_id, task_item_id, event_type, _json(payload), now),
        )

    @staticmethod
    def _set_plan_state(
        connection: sqlite3.Connection, plan_id: str, state: str, now: str
    ) -> None:
        row = connection.execute(
            "SELECT state FROM task_plans WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        if row is None:
            raise StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, "Task plan was not found.")
        current = str(row[0])
        if current == state:
            return
        if state not in _PLAN_TRANSITIONS.get(current, frozenset()):
            raise StorageProblem(
                StorageErrorCode.VERSION_CONFLICT,
                f"Task plan transition is invalid: {current} -> {state}.",
            )
        connection.execute(
            "UPDATE task_plans SET state = ?, updated_at = ? WHERE plan_id = ?",
            (state, now, plan_id),
        )

    @staticmethod
    def _refresh_ready_items(
        connection: sqlite3.Connection, plan_id: str, now: str
    ) -> None:
        rows = connection.execute(
            "SELECT task_item_id, depends_on_json FROM task_items "
            "WHERE plan_id = ? AND state = 'pending' ORDER BY position",
            (plan_id,),
        ).fetchall()
        succeeded = {
            str(row[0])
            for row in connection.execute(
                "SELECT task_item_id FROM task_items WHERE plan_id = ? AND state = 'succeeded'",
                (plan_id,),
            ).fetchall()
        }
        for task_item_id, dependency_json in rows:
            dependencies = set(json.loads(str(dependency_json)))
            if dependencies.issubset(succeeded):
                connection.execute(
                    "UPDATE task_items SET state = 'ready', updated_at = ? "
                    "WHERE task_item_id = ?",
                    (now, str(task_item_id)),
                )

    @staticmethod
    def _refresh_plan_state(
        connection: sqlite3.Connection, plan_id: str, now: str
    ) -> None:
        states = [
            str(row[0])
            for row in connection.execute(
                "SELECT state FROM task_items WHERE plan_id = ? ORDER BY position", (plan_id,)
            ).fetchall()
        ]
        if states and all(state in {"succeeded", "skipped"} for state in states):
            target = "succeeded"
        elif "succeeded" in states and any(
            state in {"failed", "interrupted", "blocked", "stale"} for state in states
        ):
            target = "partial_success"
        elif any(state in {"running", "committing"} for state in states):
            target = "running"
        elif "interrupted" in states:
            target = "interrupted"
        elif "failed" in states and not any(state in {"pending", "ready"} for state in states):
            target = "failed"
        else:
            target = "running"
        connection.execute(
            "UPDATE task_plans SET state = ?, updated_at = ? WHERE plan_id = ?",
            (target, now, plan_id),
        )
