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

EngineTaskPlanState = Literal[
    "needs_confirmation",
    "ready",
    "running",
    "partially_failed",
    "succeeded",
]


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
class EngineTaskPlanSnapshot:
    proposal: EngineAgentPlan
    bound: BoundEnginePlan
    state: EngineTaskPlanState
    confirmation_state: Literal["pending", "confirmed", "not_required"]
    next_action_index: int
    current_project_revision: int
    error_code: str | None
    created_at: str
    updated_at: str


class EngineAgentPlanRepository:
    """Project-local plan store, separate from legacy ActionPlan rows."""

    def __init__(self, project: ProjectStore) -> None:
        self._project = project
        project._assert_writer().executescript(  # noqa: SLF001
            """
            CREATE TABLE IF NOT EXISTS engine_agent_task_plans (
                plan_id TEXT PRIMARY KEY,
                proposal_json TEXT NOT NULL,
                bound_plan_json TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN (
                    'needs_confirmation', 'ready', 'running',
                    'partially_failed', 'succeeded'
                )),
                confirmation_state TEXT NOT NULL CHECK (confirmation_state IN (
                    'pending', 'confirmed', 'not_required'
                )),
                next_action_index INTEGER NOT NULL CHECK (next_action_index >= 0),
                current_project_revision INTEGER NOT NULL CHECK (current_project_revision >= 0),
                error_code TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

    def create(self, proposal: EngineAgentPlan, bound: BoundEnginePlan) -> EngineTaskPlanSnapshot:
        if proposal.plan_id != bound.plan_id:
            raise ValueError("bound engine plan does not match its provider proposal")
        needs_confirmation = proposal.confirmation == "required"
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
                "needs_confirmation" if needs_confirmation else "ready",
                "pending" if needs_confirmation else "not_required",
                bound.expected_project_revision,
                now,
                now,
            ),
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
        return EngineTaskPlanSnapshot(
            proposal=EngineAgentPlan.model_validate_json(str(row[0])),
            bound=BoundEnginePlan.model_validate_json(str(row[1])),
            state=cast(EngineTaskPlanState, row[2]),
            confirmation_state=cast(
                Literal["pending", "confirmed", "not_required"], row[3]
            ),
            next_action_index=int(row[4]),
            current_project_revision=int(row[5]),
            error_code=None if row[6] is None else str(row[6]),
            created_at=str(row[7]),
            updated_at=str(row[8]),
        )

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
    """Execute only persisted, locally bound actions and resume at failure."""

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
        for index in range(snapshot.next_action_index, len(snapshot.bound.actions)):
            action = snapshot.bound.actions[index]
            try:
                revision = self._executor.execute_action(
                    action,
                    expected_project_revision=snapshot.current_project_revision,
                )
            except Exception as error:
                code = getattr(error, "code", type(error).__name__)
                return self._repository.update_execution(
                    plan_id,
                    state="partially_failed",
                    next_action_index=index,
                    project_revision=snapshot.current_project_revision,
                    error_code=str(code),
                )
            expected_revision = snapshot.current_project_revision + (
                0 if isinstance(action, ExportPlot) else 1
            )
            if revision != expected_revision:
                raise EngineTaskExecutionError(
                    "PROJECT_VERSION_INVALID",
                    "The engine action returned an unexpected project version.",
                )
            snapshot = self._repository.update_execution(
                plan_id,
                state="running",
                next_action_index=index + 1,
                project_revision=revision,
                error_code=None,
            )
        return self._repository.update_execution(
            plan_id,
            state="succeeded",
            next_action_index=len(snapshot.bound.actions),
            project_revision=snapshot.current_project_revision,
            error_code=None,
        )


def encode_action(action: PlotEngineAction) -> str:
    """Stable helper used by external task/event serializers."""

    return json.dumps(action.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def decode_action(payload: str) -> PlotEngineAction:
    return _ACTION_ADAPTER.validate_json(payload)
