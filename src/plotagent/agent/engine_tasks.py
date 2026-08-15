"""Persistent execution of locally bound Agent Native engine plans."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, cast

from pydantic import TypeAdapter

from plotagent.agent.engine_client import BoundEnginePlan, EngineAgentPlan
from plotagent.engine import ExportPlot, PlotEngineAction
from plotagent.storage.project import ProjectStore

_ACTION_ADAPTER: TypeAdapter[PlotEngineAction] = TypeAdapter(PlotEngineAction)

_ENGINE_PLAN_TABLE_SQL = """
CREATE TABLE engine_agent_task_plans (
    plan_id TEXT PRIMARY KEY,
    proposal_json TEXT NOT NULL,
    bound_plan_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'needs_confirmation', 'ready', 'running',
        'partially_failed', 'succeeded', 'cancelled'
    )),
    confirmation_state TEXT NOT NULL CHECK (confirmation_state IN (
        'pending', 'confirmed', 'rejected', 'not_required'
    )),
    next_action_index INTEGER NOT NULL CHECK (next_action_index >= 0),
    current_project_revision INTEGER NOT NULL CHECK (current_project_revision >= 0),
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

EngineTaskPlanState = Literal[
    "needs_confirmation",
    "ready",
    "running",
    "partially_failed",
    "succeeded",
    "cancelled",
]
EngineActionState = Literal["pending", "running", "succeeded", "failed", "blocked"]

_ENGINE_ACTION_PROGRESS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS engine_agent_task_action_progress (
    plan_id TEXT NOT NULL,
    action_index INTEGER NOT NULL CHECK (action_index >= 0),
    state TEXT NOT NULL CHECK (state IN (
        'pending', 'running', 'succeeded', 'failed', 'blocked'
    )),
    attempt_count INTEGER NOT NULL CHECK (attempt_count >= 0),
    error_code TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (plan_id, action_index)
)
"""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class EngineTaskExecutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EngineActionExecutor(Protocol):
    def execute_action(
        self,
        action: PlotEngineAction,
        *,
        expected_project_revision: int,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class EngineActionProgress:
    action_index: int
    state: EngineActionState
    attempt_count: int
    error_code: str | None


@dataclass(frozen=True, slots=True)
class EngineTaskPlanSnapshot:
    proposal: EngineAgentPlan
    bound: BoundEnginePlan
    state: EngineTaskPlanState
    confirmation_state: Literal["pending", "confirmed", "rejected", "not_required"]
    next_action_index: int
    current_project_revision: int
    error_code: str | None
    action_progress: tuple[EngineActionProgress, ...]
    created_at: str
    updated_at: str

    @property
    def completed_action_count(self) -> int:
        return sum(item.state == "succeeded" for item in self.action_progress)


class EngineAgentPlanRepository:
    """Project-local plan store, separate from legacy ActionPlan rows."""

    def __init__(self, project: ProjectStore) -> None:
        self._project = project
        writer = project._assert_writer()  # noqa: SLF001
        create_sql = _ENGINE_PLAN_TABLE_SQL.replace(
            "CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1
        )
        writer.execute(create_sql)
        schema_row = writer.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("engine_agent_task_plans",),
        ).fetchone()
        schema_sql = "" if schema_row is None else str(schema_row[0])
        if "'cancelled'" not in schema_sql or "'rejected'" not in schema_sql:
            writer.executescript(
                f"""
                BEGIN IMMEDIATE;
                ALTER TABLE engine_agent_task_plans RENAME TO engine_agent_task_plans_legacy;
                {_ENGINE_PLAN_TABLE_SQL};
                INSERT INTO engine_agent_task_plans
                SELECT * FROM engine_agent_task_plans_legacy;
                DROP TABLE engine_agent_task_plans_legacy;
                COMMIT;
                """
            )
        writer.execute(_ENGINE_ACTION_PROGRESS_TABLE_SQL)

    def create(
        self,
        proposal: EngineAgentPlan,
        bound: BoundEnginePlan,
        *,
        confirmation_required: bool = True,
    ) -> EngineTaskPlanSnapshot:
        if proposal.plan_id != bound.plan_id:
            raise ValueError("bound engine plan does not match its provider proposal")
        now = _utc_now()
        self._project._assert_writer().execute(  # noqa: SLF001
            """
            INSERT INTO engine_agent_task_plans (
                plan_id, proposal_json, bound_plan_json, state, confirmation_state,
                next_action_index, current_project_revision, error_code, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?, NULL, ?, ?)
            """,
            (
                proposal.plan_id,
                proposal.model_dump_json(),
                bound.model_dump_json(),
                "needs_confirmation" if confirmation_required else "ready",
                "pending" if confirmation_required else "not_required",
                bound.expected_project_revision,
                now,
                now,
            ),
        )
        self._project._assert_writer().executemany(  # noqa: SLF001
            """
            INSERT INTO engine_agent_task_action_progress (
                plan_id, action_index, state, attempt_count, error_code, updated_at
            ) VALUES (?, ?, 'pending', 0, NULL, ?)
            """,
            tuple((proposal.plan_id, index, now) for index in range(len(bound.actions))),
        )
        return self.get(proposal.plan_id)

    def get(self, plan_id: str) -> EngineTaskPlanSnapshot:
        row = self._project._assert_writer().execute(  # noqa: SLF001
            """
            SELECT proposal_json, bound_plan_json, state, confirmation_state,
                   next_action_index, current_project_revision, error_code,
                   created_at, updated_at
            FROM engine_agent_task_plans WHERE plan_id = ?
            """,
            (plan_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"engine Agent plan was not found: {plan_id}")
        bound = BoundEnginePlan.model_validate_json(str(row[1]))
        action_progress = self._action_progress(
            plan_id,
            action_count=len(bound.actions),
            legacy_state=str(row[2]),
            legacy_next_action_index=int(row[4]),
            legacy_error_code=None if row[6] is None else str(row[6]),
        )
        return EngineTaskPlanSnapshot(
            proposal=EngineAgentPlan.model_validate_json(str(row[0])),
            bound=bound,
            state=cast(EngineTaskPlanState, row[2]),
            confirmation_state=cast(
                Literal["pending", "confirmed", "rejected", "not_required"], row[3]
            ),
            next_action_index=int(row[4]),
            current_project_revision=int(row[5]),
            error_code=None if row[6] is None else str(row[6]),
            action_progress=action_progress,
            created_at=str(row[7]),
            updated_at=str(row[8]),
        )

    def update_action(
        self,
        plan_id: str,
        action_index: int,
        *,
        state: EngineActionState,
        attempt_count: int,
        error_code: str | None,
    ) -> None:
        cursor = self._project._assert_writer().execute(  # noqa: SLF001
            """
            UPDATE engine_agent_task_action_progress
            SET state = ?, attempt_count = ?, error_code = ?, updated_at = ?
            WHERE plan_id = ? AND action_index = ?
            """,
            (state, attempt_count, error_code, _utc_now(), plan_id, action_index),
        )
        if cursor.rowcount != 1:
            raise KeyError(f"engine Agent action progress was not found: {plan_id}@{action_index}")

    def _action_progress(
        self,
        plan_id: str,
        *,
        action_count: int,
        legacy_state: str,
        legacy_next_action_index: int,
        legacy_error_code: str | None,
    ) -> tuple[EngineActionProgress, ...]:
        rows = self._project._assert_writer().execute(  # noqa: SLF001
            """
            SELECT action_index, state, attempt_count, error_code
            FROM engine_agent_task_action_progress
            WHERE plan_id = ? ORDER BY action_index ASC
            """,
            (plan_id,),
        ).fetchall()
        if len(rows) != action_count:
            if rows:
                raise ValueError("engine Agent action progress is incomplete")
            now = _utc_now()
            seeded: list[tuple[str, int, str, int, str | None, str]] = []
            for index in range(action_count):
                if legacy_state == "succeeded" or index < legacy_next_action_index:
                    state, attempts, error = "succeeded", 1, None
                elif legacy_state == "partially_failed" and index == legacy_next_action_index:
                    state, attempts, error = "failed", 1, legacy_error_code
                else:
                    state, attempts, error = "pending", 0, None
                seeded.append((plan_id, index, state, attempts, error, now))
            self._project._assert_writer().executemany(  # noqa: SLF001
                """
                INSERT INTO engine_agent_task_action_progress (
                    plan_id, action_index, state, attempt_count, error_code, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                seeded,
            )
            return self._action_progress(
                plan_id,
                action_count=action_count,
                legacy_state=legacy_state,
                legacy_next_action_index=legacy_next_action_index,
                legacy_error_code=legacy_error_code,
            )
        return tuple(
            EngineActionProgress(
                action_index=int(row[0]),
                state=cast(EngineActionState, row[1]),
                attempt_count=int(row[2]),
                error_code=None if row[3] is None else str(row[3]),
            )
            for row in rows
        )

    def list_all(self) -> tuple[EngineTaskPlanSnapshot, ...]:
        rows = self._project._assert_writer().execute(  # noqa: SLF001
            """
            SELECT plan_id
            FROM engine_agent_task_plans
            ORDER BY created_at ASC, plan_id ASC
            """
        ).fetchall()
        return tuple(self.get(str(row[0])) for row in rows)

    def cancel(self, plan_id: str) -> EngineTaskPlanSnapshot:
        current = self.get(plan_id)
        if current.state == "cancelled":
            return current
        if current.state in {"running", "succeeded"}:
            raise ValueError("a running or succeeded plan cannot be cancelled")
        self._update(
            plan_id,
            state="cancelled",
            confirmation_state="rejected",
            next_action_index=current.next_action_index,
            project_revision=current.current_project_revision,
            error_code=None,
        )
        return self.get(plan_id)

    def confirm(self, plan_id: str) -> EngineTaskPlanSnapshot:
        current = self.get(plan_id)
        if current.confirmation_state == "not_required":
            return current
        if current.state != "needs_confirmation":
            raise ValueError("only a plan awaiting confirmation can be confirmed")
        self._update(
            plan_id,
            state="ready",
            confirmation_state="confirmed",
            next_action_index=current.next_action_index,
            project_revision=current.current_project_revision,
            error_code=None,
        )
        return self.get(plan_id)

    def update_execution(
        self,
        plan_id: str,
        *,
        state: EngineTaskPlanState,
        next_action_index: int,
        project_revision: int,
        error_code: str | None,
    ) -> EngineTaskPlanSnapshot:
        current = self.get(plan_id)
        self._update(
            plan_id,
            state=state,
            confirmation_state=current.confirmation_state,
            next_action_index=next_action_index,
            project_revision=project_revision,
            error_code=error_code,
        )
        return self.get(plan_id)

    def _update(
        self,
        plan_id: str,
        *,
        state: EngineTaskPlanState,
        confirmation_state: str,
        next_action_index: int,
        project_revision: int,
        error_code: str | None,
    ) -> None:
        cursor = self._project._assert_writer().execute(  # noqa: SLF001
            """
            UPDATE engine_agent_task_plans
            SET state = ?, confirmation_state = ?, next_action_index = ?,
                current_project_revision = ?, error_code = ?, updated_at = ?
            WHERE plan_id = ?
            """,
            (
                state,
                confirmation_state,
                next_action_index,
                project_revision,
                error_code,
                _utc_now(),
                plan_id,
            ),
        )
        if cursor.rowcount != 1:
            raise KeyError(f"engine Agent plan was not found: {plan_id}")


class PersistentEngineTaskOrchestrator:
    """Execute persisted actions with per-plot failure isolation and redrive."""

    def __init__(
        self,
        repository: EngineAgentPlanRepository,
        executor: EngineActionExecutor,
    ) -> None:
        self._repository = repository
        self._executor = executor

    def run(self, plan_id: str) -> EngineTaskPlanSnapshot:
        snapshot = self._repository.get(plan_id)
        if snapshot.state == "needs_confirmation":
            raise EngineTaskExecutionError("CONFIRMATION_REQUIRED", "The plan needs confirmation.")
        if snapshot.state == "succeeded":
            return snapshot
        if snapshot.state not in {"ready", "running", "partially_failed"}:
            raise EngineTaskExecutionError("PLAN_STATE_INVALID", "The plan cannot run.")

        snapshot = self._repository.update_execution(
            plan_id,
            state="running",
            next_action_index=snapshot.next_action_index,
            project_revision=snapshot.current_project_revision,
            error_code=None,
        )
        failed_plot_ids: set[str] = set()
        for index, action in enumerate(snapshot.bound.actions):
            progress = snapshot.action_progress[index]
            if progress.state == "succeeded":
                continue
            plot_id = _action_plot_id(action)
            if plot_id in failed_plot_ids:
                self._repository.update_action(
                    plan_id,
                    index,
                    state="blocked",
                    attempt_count=progress.attempt_count,
                    error_code="UPSTREAM_ACTION_FAILED",
                )
                snapshot = self._repository.get(plan_id)
                continue
            self._repository.update_action(
                plan_id,
                index,
                state="running",
                attempt_count=progress.attempt_count + 1,
                error_code=None,
            )
            action = snapshot.bound.actions[index]
            try:
                revision = self._executor.execute_action(
                    action,
                    expected_project_revision=snapshot.current_project_revision,
                )
            except Exception as error:
                code = getattr(error, "code", type(error).__name__)
                self._repository.update_action(
                    plan_id,
                    index,
                    state="failed",
                    attempt_count=progress.attempt_count + 1,
                    error_code=str(code),
                )
                failed_plot_ids.add(plot_id)
                snapshot = self._repository.get(plan_id)
                continue
            expected_revision = snapshot.current_project_revision + (
                0 if isinstance(action, ExportPlot) else 1
            )
            if revision != expected_revision:
                raise EngineTaskExecutionError(
                    "PROJECT_VERSION_INVALID",
                    "The engine action returned an unexpected project version.",
                )
            self._repository.update_action(
                plan_id,
                index,
                state="succeeded",
                attempt_count=progress.attempt_count + 1,
                error_code=None,
            )
            snapshot = self._repository.update_execution(
                plan_id,
                state="running",
                next_action_index=index + 1,
                project_revision=revision,
                error_code=None,
            )
        snapshot = self._repository.get(plan_id)
        unfinished = tuple(
            item for item in snapshot.action_progress if item.state != "succeeded"
        )
        first_unfinished = unfinished[0] if unfinished else None
        return self._repository.update_execution(
            plan_id,
            state="partially_failed" if unfinished else "succeeded",
            next_action_index=(
                first_unfinished.action_index
                if first_unfinished is not None
                else len(snapshot.bound.actions)
            ),
            project_revision=snapshot.current_project_revision,
            error_code=(
                next(
                    (item.error_code for item in unfinished if item.state == "failed"),
                    "UPSTREAM_ACTION_FAILED",
                )
                if unfinished
                else None
            ),
        )


def _action_plot_id(action: PlotEngineAction) -> str:
    if hasattr(action, "plot_id"):
        return cast(str, action.plot_id)
    target = action.target
    if target.startswith("plot:"):
        return target
    separator = target.find(":")
    last_dot = target.rfind(".")
    if separator <= 0 or last_dot <= separator + 1:
        raise EngineTaskExecutionError("ACTION_TARGET_INVALID", "The action target is invalid.")
    return "plot:" + target[separator + 1 : last_dot]


def encode_action(action: PlotEngineAction) -> str:
    """Stable helper used by external task/event serializers."""

    return json.dumps(action.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def decode_action(payload: str) -> PlotEngineAction:
    return _ACTION_ADAPTER.validate_json(payload)
