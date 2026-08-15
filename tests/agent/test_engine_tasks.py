from __future__ import annotations

from pathlib import Path

import pytest

from plotagent.agent.engine_client import (
    AgentCreatePlot,
    AgentFieldBinding,
    AgentSetLegend,
    AgentSetTitle,
    BoundEnginePlan,
    EngineAgentPlan,
)
from plotagent.agent.engine_tasks import (
    EngineAgentPlanRepository,
    EngineTaskExecutionError,
    PersistentEngineTaskOrchestrator,
    decode_action,
    encode_action,
)
from plotagent.engine import (
    CreatePlot,
    EngineDataRef,
    FieldBinding,
    PlotEngineAction,
    SetLegend,
    SetTitle,
)
from plotagent.storage.project import ProjectStore


class FakeExecutor:
    def __init__(self, *, fail_once: str | None = None) -> None:
        self.fail_once = fail_once
        self.calls: list[str] = []

    def execute_action(
        self,
        action: PlotEngineAction,
        *,
        expected_project_revision: int,
    ) -> int:
        self.calls.append(action.action_id)
        if self.fail_once == action.action_id:
            self.fail_once = None
            raise RuntimeError("synthetic failure")
        return expected_project_revision + 1


def _plans() -> tuple[EngineAgentPlan, BoundEnginePlan]:
    proposal = EngineAgentPlan(
        plan_id="plan:persistent",
        target_alias="active_data",
        actions=(
            AgentCreatePlot(
                action_id="action:create",
                plot_alias="result",
                profile_id="K01",
                source_alias="active_data",
                bindings=(
                    AgentFieldBinding(role="x", field_alias="x"),
                    AgentFieldBinding(role="y", field_alias="y"),
                ),
            ),
            AgentSetTitle(
                action_id="action:title",
                plot_alias="result",
                text="Persistent title",
            ),
        ),
    )
    create = CreatePlot(
        action_id="action:create",
        plot_id="plot:agent.persistent.1",
        profile_id="K01",
        data=EngineDataRef(
            kind="source",
            dataset_id="source:demo",
            version=1,
            content_hash="5" * 64,
        ),
        bindings=(
            FieldBinding(role="x", field_id="field:x"),
            FieldBinding(role="y", field_id="field:y"),
        ),
    )
    bound = BoundEnginePlan(
        plan_id=proposal.plan_id,
        expected_project_revision=10,
        actions=(
            create,
            SetTitle(
                action_id="action:title",
                target=create.plot_id,
                expected_plot_version=1,
                text="Persistent title",
            ),
        ),
    )
    return proposal, bound


def test_plan_requires_confirmation_and_resumes_only_the_failed_action(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    proposal, bound = _plans()
    with ProjectStore.create(workspace, project_id="project:tasks") as project:
        repository = EngineAgentPlanRepository(project)
        repository.create(proposal, bound)
        first_executor = FakeExecutor(fail_once="action:title")
        orchestrator = PersistentEngineTaskOrchestrator(repository, first_executor)

        with pytest.raises(EngineTaskExecutionError, match="needs confirmation"):
            orchestrator.run(proposal.plan_id)
        repository.confirm(proposal.plan_id)
        partial = orchestrator.run(proposal.plan_id)

        assert partial.state == "partially_failed"
        assert partial.next_action_index == 1
        assert partial.current_project_revision == 11
        assert first_executor.calls == ["action:create", "action:title"]

    with ProjectStore.open(workspace) as project:
        repository = EngineAgentPlanRepository(project)
        resumed_executor = FakeExecutor()
        orchestrator = PersistentEngineTaskOrchestrator(repository, resumed_executor)
        completed = orchestrator.run(proposal.plan_id)

        assert completed.state == "succeeded"
        assert completed.next_action_index == 2
        assert completed.current_project_revision == 12
        assert resumed_executor.calls == ["action:title"]
        assert orchestrator.run(proposal.plan_id) == completed
        assert resumed_executor.calls == ["action:title"]


def test_bound_action_serialization_remains_the_public_engine_contract() -> None:
    _proposal, bound = _plans()
    restored = decode_action(encode_action(bound.actions[1]))
    assert restored == bound.actions[1]
    assert "PlotSpec" not in encode_action(restored)


def test_independent_plot_items_continue_and_redrive_only_failed_work(tmp_path: Path) -> None:
    proposal, bound = _plans()
    first_create = bound.actions[0]
    assert isinstance(first_create, CreatePlot)
    second_create = first_create.model_copy(
        update={"action_id": "action:create-b", "plot_id": "plot:agent.persistent.2"}
    )
    expanded_proposal = proposal.model_copy(
        update={
            "actions": (
                proposal.actions[0],
                proposal.actions[1],
                AgentSetLegend(
                    action_id="action:legend-a",
                    plot_alias="result",
                    visible=True,
                ),
                proposal.actions[0].model_copy(
                    update={"action_id": "action:create-b", "plot_alias": "result_b"}
                ),
                proposal.actions[1].model_copy(
                    update={"action_id": "action:title-b", "plot_alias": "result_b"}
                ),
            )
        }
    )
    expanded_bound = bound.model_copy(
        update={
            "actions": (
                first_create,
                bound.actions[1],
                SetLegend(
                    action_id="action:legend-a",
                    target="legend:agent.persistent.1.main",
                    expected_plot_version=1,
                    visible=True,
                ),
                second_create,
                SetTitle(
                    action_id="action:title-b",
                    target=second_create.plot_id,
                    expected_plot_version=1,
                    text="Second title",
                ),
            )
        }
    )
    workspace = tmp_path / "isolated"
    with ProjectStore.create(workspace, project_id="project:isolated") as project:
        repository = EngineAgentPlanRepository(project)
        repository.create(expanded_proposal, expanded_bound)
        repository.confirm(expanded_proposal.plan_id)
        first_executor = FakeExecutor(fail_once="action:title")
        partial = PersistentEngineTaskOrchestrator(repository, first_executor).run(
            expanded_proposal.plan_id
        )

        assert partial.state == "partially_failed"
        assert partial.current_project_revision == 13
        assert tuple(item.state for item in partial.action_progress) == (
            "succeeded",
            "failed",
            "blocked",
            "succeeded",
            "succeeded",
        )
        assert first_executor.calls == [
            "action:create",
            "action:title",
            "action:create-b",
            "action:title-b",
        ]

        resumed_executor = FakeExecutor()
        completed = PersistentEngineTaskOrchestrator(repository, resumed_executor).run(
            expanded_proposal.plan_id
        )
        assert completed.state == "succeeded"
        assert completed.current_project_revision == 15
        assert resumed_executor.calls == ["action:title", "action:legend-a"]
        assert tuple(item.attempt_count for item in completed.action_progress) == (1, 2, 1, 1, 1)


def test_pending_plans_can_be_listed_and_explicitly_cancelled(tmp_path: Path) -> None:
    proposal, bound = _plans()
    with ProjectStore.create(tmp_path / "project", project_id="project:tasks") as project:
        repository = EngineAgentPlanRepository(project)
        repository.create(proposal, bound)

        assert tuple(item.proposal.plan_id for item in repository.list_all()) == (
            proposal.plan_id,
        )
        cancelled = repository.cancel(proposal.plan_id)
        assert cancelled.state == "cancelled"
        assert cancelled.confirmation_state == "rejected"
        assert repository.list_all() == (cancelled,)
