"""Single-writer persistence for Agent conversation and project context."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any, cast

from plotagent.contracts.agent_context import ConversationStateProjection
from plotagent.contracts.canonical import canonical_json
from plotagent.contracts.project_context import ProjectContextSnapshot
from plotagent.storage.errors import StorageErrorCode, StorageProblem
from plotagent.storage.project import ProjectStore


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _json(value: object) -> str:
    return canonical_json(cast(Any, value))


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
        return None if row is None else ConversationStateProjection.model_validate_json(str(row[0]))

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

    def latest_context_snapshot(self, conversation_id: str) -> ProjectContextSnapshot | None:
        row = self._connection.execute(
            "SELECT snapshot_json FROM project_context_snapshots "
            "WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
        return None if row is None else ProjectContextSnapshot.model_validate_json(str(row[0]))
