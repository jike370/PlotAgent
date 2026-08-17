"""Single-writer persistence for workflow runs, drafts, plans and recipes."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any, cast

from plotagent.contracts.canonical import canonical_hash, canonical_json
from plotagent.contracts.workflows import (
    InputQuestion,
    InspectionAudit,
    TaskDraft,
    TaskItemProgress,
    TaskPlan,
    TaskPlanSnapshot,
    WorkflowContext,
    WorkflowRecipe,
    WorkflowRunSnapshot,
)
from plotagent.storage.errors import StorageErrorCode, StorageProblem
from plotagent.storage.project import ProjectStore


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


_STATE_TO_STORAGE = {"agent": "agent_exploration", "direct": "deterministic_attempt"}
_STATE_FROM_STORAGE = {
    "agent_single_turn": "agent",
    "agent_exploration": "agent",
    "recipe_matching": "agent",
    "deterministic_attempt": "direct",
}
_ROUTE_TO_STORAGE = {"agent": "agent_exploration", "direct": "deterministic"}
_ROUTE_FROM_STORAGE = {
    "agent_single_turn": "agent",
    "agent_exploration": "agent",
    "needs_input": "agent",
    "unsupported": "agent",
    "deterministic": "direct",
}


class WorkflowRepository:
    """Persist only the new workflow contract; no old Agent state is accepted."""

    def __init__(self, project: ProjectStore) -> None:
        self.project = project

    @property
    def _connection(self) -> sqlite3.Connection:
        return self.project._assert_writer()  # noqa: SLF001

    def create_run(self, context: WorkflowContext) -> WorkflowRunSnapshot:
        now = _utc_now()
        context_json = canonical_json(context.model_dump(mode="json"))
        context_hash = canonical_hash(context.model_dump(mode="json"))
        connection = self._connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                """
                INSERT INTO workflow_runs (
                    workflow_run_id, project_id, state, route, context_hash,
                    draft_id, plan_id, model_turn_count, tool_call_count,
                    input_token_count, output_token_count, estimated_cost,
                    created_at, updated_at
                ) VALUES (?, ?, 'routing', NULL, ?, NULL, NULL, 0, 0, 0, 0, 0, ?, ?)
                """,
                (
                    context.workflow_run_id,
                    context.project_id,
                    context_hash,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO workflow_contexts (
                    workflow_run_id, project_revision, context_hash, context_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    context.workflow_run_id,
                    context.project_revision,
                    context_hash,
                    context_json,
                    now,
                ),
            )
            self._event(connection, context.workflow_run_id, "workflow.created", {})
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        return self.get_run(context.workflow_run_id)

    def get_context(self, workflow_run_id: str) -> WorkflowContext:
        row = self._connection.execute(
            "SELECT context_json FROM workflow_contexts WHERE workflow_run_id = ?",
            (workflow_run_id,),
        ).fetchone()
        if row is None:
            raise self._not_found("Workflow context was not found.")
        return WorkflowContext.model_validate_json(str(row[0]))

    def get_run(self, workflow_run_id: str) -> WorkflowRunSnapshot:
        row = self._connection.execute(
            """
            SELECT workflow_run_id, project_id, state, route, context_hash,
                   draft_id, plan_id, model_turn_count, tool_call_count,
                   input_token_count, output_token_count, estimated_cost,
                   created_at, updated_at
            FROM workflow_runs WHERE workflow_run_id = ?
            """,
            (workflow_run_id,),
        ).fetchone()
        if row is None:
            raise self._not_found("Workflow run was not found.")
        return WorkflowRunSnapshot(
            workflow_run_id=str(row[0]),
            project_id=str(row[1]),
            state=cast(Any, _STATE_FROM_STORAGE.get(str(row[2]), str(row[2]))),
            route=cast(
                Any,
                None if row[3] is None else _ROUTE_FROM_STORAGE.get(str(row[3]), str(row[3])),
            ),
            context_hash=cast(str | None, row[4]),
            draft_id=cast(str | None, row[5]),
            plan_id=cast(str | None, row[6]),
            model_turn_count=int(row[7]),
            tool_call_count=int(row[8]),
            input_token_count=int(row[9]),
            output_token_count=int(row[10]),
            estimated_cost=float(row[11]),
            created_at=str(row[12]),
            updated_at=str(row[13]),
        )

    def transition_run(
        self,
        workflow_run_id: str,
        *,
        state: str,
        route: str | None = None,
        model_turn_count: int | None = None,
        tool_call_count: int | None = None,
        input_token_count: int | None = None,
        output_token_count: int | None = None,
        estimated_cost: float | None = None,
    ) -> WorkflowRunSnapshot:
        current = self.get_run(workflow_run_id)
        now = _utc_now()
        storage_state = _STATE_TO_STORAGE.get(state, state)
        storage_route = None if route is None else _ROUTE_TO_STORAGE.get(route, route)
        self._connection.execute(
            """
            UPDATE workflow_runs SET
                state = ?, route = COALESCE(?, route),
                model_turn_count = COALESCE(?, model_turn_count),
                tool_call_count = COALESCE(?, tool_call_count),
                input_token_count = COALESCE(?, input_token_count),
                output_token_count = COALESCE(?, output_token_count),
                estimated_cost = COALESCE(?, estimated_cost), updated_at = ?
            WHERE workflow_run_id = ?
            """,
            (
                storage_state,
                storage_route,
                model_turn_count,
                tool_call_count,
                input_token_count,
                output_token_count,
                estimated_cost,
                now,
                workflow_run_id,
            ),
        )
        self._event(
            self._connection,
            workflow_run_id,
            "workflow.transition",
            {"from": current.state, "to": state, "route": route},
        )
        return self.get_run(workflow_run_id)

    def save_draft(self, draft: TaskDraft) -> TaskDraft:
        run = self.get_run(draft.workflow_run_id)
        payload = canonical_json(draft.model_dump(mode="json"))
        digest = canonical_hash(draft.model_dump(mode="json"))
        now = _utc_now()
        connection = self._connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            existing = connection.execute(
                "SELECT draft_hash, draft_json FROM task_drafts WHERE draft_id = ?",
                (draft.draft_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != digest or str(existing[1]) != payload:
                    raise StorageProblem(
                        StorageErrorCode.IDEMPOTENCY_CONFLICT,
                        "Task draft id was already used for different content.",
                    )
            else:
                connection.execute(
                    """
                    INSERT INTO task_drafts (
                        draft_id, workflow_run_id, draft_hash, draft_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (draft.draft_id, draft.workflow_run_id, digest, payload, now),
                )
            connection.execute(
                """
                UPDATE workflow_runs
                SET state = 'draft_ready', route = ?, draft_id = ?, updated_at = ?
                WHERE workflow_run_id = ?
                """,
                (
                    _ROUTE_TO_STORAGE.get(draft.route, draft.route),
                    draft.draft_id,
                    now,
                    draft.workflow_run_id,
                ),
            )
            self._event(
                connection,
                draft.workflow_run_id,
                "draft.saved",
                {"draft_id": draft.draft_id, "draft_hash": digest, "previous": run.draft_id},
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        return draft

    def get_draft(self, draft_id: str) -> TaskDraft:
        row = self._connection.execute(
            "SELECT draft_json FROM task_drafts WHERE draft_id = ?", (draft_id,)
        ).fetchone()
        if row is None:
            raise self._not_found("Task draft was not found.")
        return TaskDraft.model_validate_json(str(row[0]))

    def save_plan(self, plan: TaskPlan) -> TaskPlanSnapshot:
        run = self.get_run(plan.workflow_run_id)
        if run.draft_id is None:
            raise StorageProblem(
                StorageErrorCode.OBJECT_NOT_FOUND,
                "A task plan requires one persisted draft.",
            )
        payload = canonical_json(plan.model_dump(mode="json"))
        now = _utc_now()
        connection = self._connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                """
                INSERT INTO workflow_task_plans (
                    plan_id, workflow_run_id, expected_project_revision,
                    plan_hash, plan_json, state, confirmation_state,
                    current_project_revision, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'awaiting_confirmation', 'pending', ?, ?, ?)
                """,
                (
                    plan.plan_id,
                    plan.workflow_run_id,
                    plan.expected_project_revision,
                    canonical_hash(plan.model_dump(mode="json")),
                    payload,
                    plan.expected_project_revision,
                    now,
                    now,
                ),
            )
            for position, item in enumerate(plan.items):
                connection.execute(
                    """
                    INSERT INTO workflow_task_items (
                        plan_id, item_id, position, state, attempt_count,
                        error_code, error_message, error_retryable,
                        output_plot_id, output_plot_version, updated_at
                    ) VALUES (?, ?, ?, 'pending', 0, NULL, NULL, NULL, NULL, NULL, ?)
                    """,
                    (plan.plan_id, item.item_id, position, now),
                )
            connection.execute(
                """
                UPDATE workflow_runs SET state = 'awaiting_confirmation', plan_id = ?,
                    updated_at = ? WHERE workflow_run_id = ?
                """,
                (plan.plan_id, now, plan.workflow_run_id),
            )
            self._event(
                connection,
                plan.workflow_run_id,
                "plan.saved",
                {"plan_id": plan.plan_id},
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        return self.get_plan(plan.plan_id)

    def get_plan(self, plan_id: str) -> TaskPlanSnapshot:
        row = self._connection.execute(
            """
            SELECT plan_json, state, current_project_revision, created_at, updated_at
            FROM workflow_task_plans WHERE plan_id = ?
            """,
            (plan_id,),
        ).fetchone()
        if row is None:
            raise self._not_found("Task plan was not found.")
        plan = TaskPlan.model_validate_json(str(row[0]))
        progress_rows = self._connection.execute(
            """
            SELECT item_id, state, attempt_count, error_code, error_message,
                   error_retryable, output_plot_id, output_plot_version
            FROM workflow_task_items WHERE plan_id = ? ORDER BY position
            """,
            (plan_id,),
        ).fetchall()
        progress = tuple(
            TaskItemProgress(
                item_id=str(item[0]),
                state=cast(str, item[1]),  # type: ignore[arg-type]
                attempt_count=int(item[2]),
                error_code=cast(str | None, item[3]),
                error_message=cast(str | None, item[4]),
                error_retryable=(None if item[5] is None else bool(item[5])),
                output_plot_id=cast(str | None, item[6]),
                output_plot_version=cast(int | None, item[7]),
            )
            for item in progress_rows
        )
        return TaskPlanSnapshot(
            plan=plan,
            state=cast(str, row[1]),  # type: ignore[arg-type]
            current_project_revision=int(row[2]),
            item_progress=progress,
            created_at=str(row[3]),
            updated_at=str(row[4]),
        )

    def confirm(self, plan_id: str) -> TaskPlanSnapshot:
        snapshot = self.get_plan(plan_id)
        if snapshot.state != "awaiting_confirmation":
            raise StorageProblem(
                StorageErrorCode.VERSION_CONFLICT,
                "Only a pending task plan can be confirmed.",
            )
        now = _utc_now()
        self._connection.execute(
            """
            UPDATE workflow_task_plans
            SET state = 'ready', confirmation_state = 'confirmed', updated_at = ?
            WHERE plan_id = ?
            """,
            (now, plan_id),
        )
        self._event(
            self._connection,
            snapshot.plan.workflow_run_id,
            "plan.confirmed",
            {"plan_id": plan_id},
        )
        return self.get_plan(plan_id)

    def reject(self, plan_id: str) -> TaskPlanSnapshot:
        snapshot = self.get_plan(plan_id)
        if snapshot.state != "awaiting_confirmation":
            raise StorageProblem(
                StorageErrorCode.VERSION_CONFLICT,
                "Only a pending task plan can be rejected.",
            )
        now = _utc_now()
        self._connection.execute(
            """
            UPDATE workflow_task_plans
            SET state = 'rejected', confirmation_state = 'rejected', updated_at = ?
            WHERE plan_id = ?
            """,
            (now, plan_id),
        )
        self._connection.execute(
            "UPDATE workflow_runs SET state = 'cancelled', updated_at = ? "
            "WHERE workflow_run_id = ?",
            (now, snapshot.plan.workflow_run_id),
        )
        return self.get_plan(plan_id)

    def set_plan_state(
        self,
        plan_id: str,
        state: str,
        *,
        project_revision: int | None = None,
    ) -> TaskPlanSnapshot:
        now = _utc_now()
        self._connection.execute(
            """
            UPDATE workflow_task_plans SET state = ?,
                current_project_revision = COALESCE(?, current_project_revision),
                updated_at = ? WHERE plan_id = ?
            """,
            (state, project_revision, now, plan_id),
        )
        return self.get_plan(plan_id)

    def set_item_state(
        self,
        plan_id: str,
        item_id: str,
        state: str,
        *,
        increment_attempt: bool = False,
        error_code: str | None = None,
        error_message: str | None = None,
        error_retryable: bool | None = None,
        output_plot_id: str | None = None,
        output_plot_version: int | None = None,
    ) -> TaskPlanSnapshot:
        now = _utc_now()
        cursor = self._connection.execute(
            """
            UPDATE workflow_task_items SET state = ?,
                attempt_count = attempt_count + ?, error_code = ?,
                error_message = ?, error_retryable = ?,
                output_plot_id = ?, output_plot_version = ?, updated_at = ?
            WHERE plan_id = ? AND item_id = ?
            """,
            (
                state,
                1 if increment_attempt else 0,
                error_code,
                error_message,
                None if error_retryable is None else int(error_retryable),
                output_plot_id,
                output_plot_version,
                now,
                plan_id,
                item_id,
            ),
        )
        if cursor.rowcount == 0:
            raise self._not_found("Task item was not found.")
        return self.get_plan(plan_id)

    def list_plans(self) -> tuple[TaskPlanSnapshot, ...]:
        rows = self._connection.execute(
            "SELECT plan_id FROM workflow_task_plans ORDER BY created_at, plan_id"
        ).fetchall()
        return tuple(self.get_plan(str(row[0])) for row in rows)

    def save_recipe(self, recipe: WorkflowRecipe) -> WorkflowRecipe:
        self._connection.execute(
            """
            INSERT INTO workflow_recipes (
                recipe_id, recipe_version, structure_fingerprint,
                goal_signature, recipe_hash, recipe_json, archived, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recipe.recipe_id,
                recipe.recipe_version,
                recipe.structure_fingerprint,
                recipe.structure_fingerprint,
                canonical_hash(recipe.model_dump(mode="json")),
                canonical_json(recipe.model_dump(mode="json")),
                int(recipe.archived),
                _utc_now(),
            ),
        )
        return recipe

    def find_recipes(self, structure_fingerprint: str) -> tuple[WorkflowRecipe, ...]:
        rows = self._connection.execute(
            """
            SELECT recipe_json FROM workflow_recipes
            WHERE structure_fingerprint = ? AND archived = 0
            ORDER BY recipe_id, recipe_version DESC
            """,
            (structure_fingerprint,),
        ).fetchall()
        return tuple(WorkflowRecipe.model_validate_json(str(row[0])) for row in rows)

    def get_recipe(self, recipe_id: str) -> WorkflowRecipe:
        row = self._connection.execute(
            """
            SELECT recipe_json FROM workflow_recipes
            WHERE recipe_id = ? AND archived = 0
            ORDER BY recipe_version DESC LIMIT 1
            """,
            (recipe_id,),
        ).fetchone()
        if row is None:
            raise self._not_found("Workflow recipe was not found.")
        return WorkflowRecipe.model_validate_json(str(row[0]))

    def list_recipes(self) -> tuple[WorkflowRecipe, ...]:
        rows = self._connection.execute(
            """
            SELECT recipe_json FROM workflow_recipes
            WHERE archived = 0
            ORDER BY created_at DESC, recipe_id, recipe_version DESC
            """
        ).fetchall()
        return tuple(WorkflowRecipe.model_validate_json(str(row[0])) for row in rows)

    def record_questions(
        self,
        workflow_run_id: str,
        questions: tuple[InputQuestion, ...],
    ) -> None:
        """Persist an Agent clarification request without interpreting it."""

        self._event(
            self._connection,
            workflow_run_id,
            "workflow.questions",
            {"questions": [item.model_dump(mode="json") for item in questions]},
        )

    def record_inspection_audit(self, audit: InspectionAudit) -> None:
        """Persist disclosure counts without copying inspected values into the event log."""

        now = _utc_now()
        self._connection.execute(
            """
            UPDATE workflow_runs
            SET tool_call_count = tool_call_count + 1, updated_at = ?
            WHERE workflow_run_id = ?
            """,
            (now, audit.workflow_run_id),
        )
        self._event(
            self._connection,
            audit.workflow_run_id,
            "workflow.tool_audit",
            audit.model_dump(mode="json"),
        )

    def record_clarification_answer(self, workflow_run_id: str, answer: str) -> None:
        """Append the user's verbatim answer to the latest unanswered question set."""

        run = self.get_run(workflow_run_id)
        if run.state != "needs_input":
            raise StorageProblem(
                StorageErrorCode.VERSION_CONFLICT,
                "Workflow is not waiting for a clarification answer.",
            )
        latest_question = self._connection.execute(
            """
            SELECT rowid FROM workflow_events
            WHERE workflow_run_id = ? AND event_type = 'workflow.questions'
            ORDER BY rowid DESC LIMIT 1
            """,
            (workflow_run_id,),
        ).fetchone()
        latest_answer = self._connection.execute(
            """
            SELECT rowid FROM workflow_events
            WHERE workflow_run_id = ? AND event_type = 'workflow.answer'
            ORDER BY rowid DESC LIMIT 1
            """,
            (workflow_run_id,),
        ).fetchone()
        if latest_question is None or (
            latest_answer is not None and int(latest_answer[0]) > int(latest_question[0])
        ):
            raise StorageProblem(
                StorageErrorCode.VERSION_CONFLICT,
                "Workflow does not have an unanswered clarification request.",
            )
        self._event(
            self._connection,
            workflow_run_id,
            "workflow.answer",
            {"answer_text": answer},
        )

    def clarification_history(self, workflow_run_id: str) -> tuple[dict[str, object], ...]:
        rows = self._connection.execute(
            """
            SELECT event_type, payload_json FROM workflow_events
            WHERE workflow_run_id = ?
              AND event_type IN ('workflow.questions', 'workflow.answer')
            ORDER BY rowid
            """,
            (workflow_run_id,),
        ).fetchall()
        return tuple(
            {
                "kind": "questions" if str(row[0]) == "workflow.questions" else "answer",
                **cast(dict[str, object], json.loads(str(row[1]))),
            }
            for row in rows
        )

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        workflow_run_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        connection.execute(
            """
            INSERT INTO workflow_events (
                workflow_run_id, event_type, payload_json, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                workflow_run_id,
                event_type,
                canonical_json(cast(Any, payload)),
                _utc_now(),
            ),
        )

    @staticmethod
    def _not_found(message: str) -> StorageProblem:
        return StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, message)
