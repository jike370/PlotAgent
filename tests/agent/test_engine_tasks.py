from __future__ import annotations

from pathlib import Path

import pytest

from plotagent.agent.engine_client import (
    AgentCreatePlot,
    AgentFieldBinding,
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
from plotagent.engine import CreatePlot, EngineDataRef, FieldBinding, PlotEngineAction, SetTitle
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
