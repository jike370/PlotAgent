"""Deterministic local execution of persisted Agent task plans."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from plotagent.contracts.agent_context import ContextObjectRef
from plotagent.contracts.task_runtime import (
    TaskFailure,
    TaskItemSnapshot,
    TaskOutputRef,
    TaskPlanSnapshot,
)
from plotagent.storage.agent_runtime import AgentRuntimeRepository
from plotagent.storage.errors import StorageErrorCode, StorageProblem


class ObjectVersionAuthority(Protocol):
    def current(self, expected: ContextObjectRef) -> ContextObjectRef | None: ...


class TaskItemExecutor(Protocol):
    def execute(
        self, plan: TaskPlanSnapshot, item: TaskItemSnapshot
    ) -> tuple[TaskOutputRef, ...]: ...


@dataclass(frozen=True, slots=True)
class TaskExecutionError(Exception):
    code: str
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


class PersistentTaskOrchestrator:
    """Run a closed plan; never lets a provider add tools or actions mid-run."""

    def __init__(
        self,
        repository: AgentRuntimeRepository,
        authority: ObjectVersionAuthority,
    ) -> None:
        self.repository = repository
        self.authority = authority

    def run(
        self,
        plan_id: str,
        executor: TaskItemExecutor,
        *,
        resume: bool = False,
        on_progress: Callable[[TaskPlanSnapshot], None] | None = None,
    ) -> TaskPlanSnapshot:
        plan = self.repository.get_plan(plan_id)
        if plan.state == "needs_confirmation":
            raise StorageProblem(
                StorageErrorCode.VERSION_CONFLICT,
                "Task plan requires confirmation before execution.",
            )
        if plan.state in {"succeeded", "cancelled", "stale"}:
            return plan
        if plan.state in {"failed", "interrupted", "partial_success"} and not resume:
            raise StorageProblem(
                StorageErrorCode.VERSION_CONFLICT,
                "Task plan must be resumed explicitly.",
            )
        if resume:
            plan = self._prepare_resume(plan)
        if plan.state == "ready":
            plan = self.repository.transition_plan(plan_id, "running")

        while True:
            plan = self.repository.get_plan(plan_id)
            runnable = tuple(item for item in plan.items if item.state == "ready")
            if not runnable:
                break
            for item in runnable:
                if not self._versions_match(item):
                    self.repository.transition_item(item.task_item_id, "stale")
                    plan = self.repository.transition_plan(plan_id, "stale")
                    if on_progress is not None:
                        on_progress(plan)
                    return plan
                attempt = self.repository.begin_attempt(item.task_item_id)
                try:
                    outputs = executor.execute(plan, item)
                except TaskExecutionError as error:
                    plan = self.repository.finish_attempt(
                        attempt.attempt_id,
                        failure=TaskFailure(
                            code=error.code,
                            message=error.message,
                            retryable=error.retryable,
                        ),
                    )
                except Exception as error:
                    plan = self.repository.finish_attempt(
                        attempt.attempt_id,
                        failure=TaskFailure(
                            code="TASK_EXECUTION_FAILED",
                            message=str(error)[:512] or "Task execution failed.",
                            retryable=False,
                        ),
                    )
                else:
                    plan = self.repository.finish_attempt(
                        attempt.attempt_id,
                        outputs=outputs,
                    )
                if on_progress is not None:
                    on_progress(plan)
            self._block_failed_dependents(plan_id)

        self._block_failed_dependents(plan_id)
        return self.repository.refresh_plan(plan_id)

    def _prepare_resume(self, plan: TaskPlanSnapshot) -> TaskPlanSnapshot:
        for item in plan.items:
            if item.state == "interrupted" or (
                item.state == "failed" and item.failure is not None and item.failure.retryable
            ):
                self.repository.transition_item(item.task_item_id, "ready")
        refreshed = self.repository.get_plan(plan.plan_id)
        states = {item.task_item_id: item.state for item in refreshed.items}
        for item in refreshed.items:
            if item.state == "blocked" and all(
                states[dependency] in {"succeeded", "ready", "pending"}
                for dependency in item.depends_on
            ):
                self.repository.transition_item(item.task_item_id, "pending")
        return self.repository.refresh_plan(plan.plan_id)

    def _versions_match(self, item: TaskItemSnapshot) -> bool:
        for expected in item.expected_objects:
            actual = self.authority.current(expected)
            if actual is None:
                return False
            if actual.object_id != expected.object_id:
                return False
            if actual.object_version != expected.object_version:
                return False
            if expected.content_hash is not None and actual.content_hash != expected.content_hash:
                return False
        return True

    def _block_failed_dependents(self, plan_id: str) -> None:
        plan = self.repository.get_plan(plan_id)
        failed = {
            item.task_item_id
            for item in plan.items
            if item.state in {"failed", "blocked", "stale", "cancelled"}
        }
        for item in plan.items:
            if item.state == "pending" and failed.intersection(item.depends_on):
                self.repository.transition_item(item.task_item_id, "blocked")
