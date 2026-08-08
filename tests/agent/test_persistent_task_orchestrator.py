from __future__ import annotations

from dataclasses import dataclass, field

from plotagent.agent.project_context import ProjectContextService
from plotagent.agent.task_orchestrator import (
    PersistentTaskOrchestrator,
    TaskExecutionError,
)
from plotagent.agent.task_plans import TaskPlanCompiler
from plotagent.contracts.agent_context import ContextObjectRef, ConversationStateProjection
from plotagent.contracts.decisions import ActionPlan, PatchPlotAction, PlotTitleIntent
from plotagent.contracts.task_runtime import TaskItemSnapshot, TaskOutputRef, TaskPlanSnapshot
from plotagent.storage import AgentRuntimeRepository, ProjectStore


def _ref(version: int = 1) -> ContextObjectRef:
    return ContextObjectRef(
        object_alias="active_target",
        object_id="plot:one",
        object_version=version,
        object_type="plot",
        content_hash=("a" if version == 1 else "b") * 64,
    )


class Authority:
    def __init__(self, current: ContextObjectRef | None) -> None:
        self.value = current

    def current(self, expected: ContextObjectRef) -> ContextObjectRef | None:
        return expected if self.value is None else self.value


@dataclass
class Executor:
    fail_once: set[str] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)

    def execute(self, plan: TaskPlanSnapshot, item: TaskItemSnapshot) -> tuple[TaskOutputRef, ...]:
        del plan
        action_id = item.action.action_id
        self.calls.append(action_id)
        if action_id in self.fail_once:
            self.fail_once.remove(action_id)
            raise TaskExecutionError("ORIGIN_BUSY", "Origin is busy.", retryable=True)
        return (
            TaskOutputRef(
                output_slot=item.output_slots[0],
                output_kind="result",
                summary=action_id,
            ),
        )


def _create_runtime(
    repository: AgentRuntimeRepository,
    *,
    action_ids: tuple[str, ...],
) -> TaskPlanSnapshot:
    state = ConversationStateProjection(state_version=1, current_target=_ref())
    repository.save_conversation_state("conversation:main", state, expected_state_version=None)
    context = ProjectContextService().build_snapshot(
        project_id=repository.project.project_id,
        project_revision=0,
        conversation_id="conversation:main",
        conversation_state=state,
        known_objects=(
            _ref(),
            _ref().model_copy(
                update={
                    "object_alias": "other_target",
                    "object_id": "plot:other",
                    "content_hash": "c" * 64,
                }
            ),
        ),
    )
    repository.save_context_snapshot(context)
    plan = ActionPlan(
        plan_id="plan:runtime",
        target_alias="active_target",
        actions=tuple(
            PatchPlotAction(
                action_id=action_id,
                target_alias=("other_target" if action_id == "action:third" else "active_target"),
                patches=(PlotTitleIntent(target_alias="active_target", title=action_id),),
            )
            for action_id in action_ids
        ),
    )
    runtime = TaskPlanCompiler().compile(plan, context)
    repository.create_plan(runtime)
    return runtime


def test_partial_success_resumes_only_retryable_unfinished_items(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with ProjectStore.create(tmp_path / "project") as project:
        repository = AgentRuntimeRepository(project)
        runtime = _create_runtime(
            repository,
            action_ids=("action:first", "action:second", "action:third"),
        )
        executor = Executor(fail_once={"action:second"})
        orchestrator = PersistentTaskOrchestrator(repository, Authority(None))

        partial = orchestrator.run(runtime.plan_id, executor)

        assert partial.state == "partial_success"
        assert [item.state for item in partial.items] == [
            "succeeded",
            "failed",
            "succeeded",
        ]
        assert executor.calls == ["action:first", "action:third", "action:second"]

        completed = orchestrator.run(runtime.plan_id, executor, resume=True)

        assert completed.state == "succeeded"
        assert executor.calls == [
            "action:first",
            "action:third",
            "action:second",
            "action:second",
        ]
        assert [item.attempt_count for item in completed.items] == [1, 2, 1]


def test_stale_object_version_stops_before_executor_side_effect(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with ProjectStore.create(tmp_path / "project") as project:
        repository = AgentRuntimeRepository(project)
        runtime = _create_runtime(repository, action_ids=("action:only",))
        executor = Executor()
        orchestrator = PersistentTaskOrchestrator(repository, Authority(_ref(version=2)))

        stale = orchestrator.run(runtime.plan_id, executor)

        assert stale.state == "stale"
        assert stale.items[0].state == "stale"
        assert executor.calls == []
