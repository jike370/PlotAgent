from __future__ import annotations

import pytest

from plotagent.agent.engine_client import (
    AgentCreatePlot,
    AgentFieldBinding,
    AgentSetAxis,
    AgentSetSeriesStyle,
    AgentSetTitle,
    BundledEngineAgentBinder,
    EngineAgentPlan,
)
from plotagent.agent.project_context import ProjectContextService
from plotagent.contracts.agent_context import ContextObjectRef, ConversationStateProjection
from plotagent.contracts.project_context import ContextFieldBinding
from plotagent.engine import CreatePlot, EngineCatalog, EngineCommandError, SetAxis, SetTitle
from plotagent.engine.profiles import ENGINE_PROFILES

HASH = "7" * 64


def _source_context(*, revision: int = 4):
    source = ContextObjectRef(
        object_alias="active_data",
        object_id="source:experiment",
        object_version=2,
        object_type="source_dataset",
        content_hash=HASH,
    )
    state = ConversationStateProjection(state_version=1, current_target=source)
    return ProjectContextService().build_snapshot(
        project_id="project:demo",
        project_revision=revision,
        conversation_id="conversation:main",
        conversation_state=state,
        known_objects=(source,),
        field_bindings=(
            ContextFieldBinding(
                field_alias="time",
                field_id="field:time",
                source_dataset_id="source:experiment",
                source_version=2,
            ),
            ContextFieldBinding(
                field_alias="signal",
                field_id="field:signal",
                source_dataset_id="source:experiment",
                source_version=2,
            ),
            ContextFieldBinding(
                field_alias="group",
                field_id="field:group",
                source_dataset_id="source:experiment",
                source_version=2,
            ),
        ),
    )


def _binder() -> BundledEngineAgentBinder:
    return BundledEngineAgentBinder(EngineCatalog(ENGINE_PROFILES))


def test_bundled_agent_binds_aliases_to_public_engine_actions_and_versions() -> None:
    plan = EngineAgentPlan(
        plan_id="plan:line-demo",
        target_alias="active_data",
        actions=(
            AgentCreatePlot(
                action_id="action:create",
                plot_alias="result",
                profile_id="K01",
                source_alias="active_data",
                bindings=(
                    AgentFieldBinding(role="x", field_alias="time"),
                    AgentFieldBinding(role="y", field_alias="signal"),
                ),
            ),
            AgentSetTitle(
                action_id="action:title",
                plot_alias="result",
                text="Temperature response",
            ),
            AgentSetAxis(
                action_id="action:y-log",
                plot_alias="result",
                axis_alias="y_axis",
                scale="log10",
            ),
            AgentSetSeriesStyle(
                action_id="action:style",
                plot_alias="result",
                series_alias="series_1",
                color="#3366CC",
            ),
        ),
    )

    bound = _binder().bind(plan, _source_context())

    assert isinstance(bound.actions[0], CreatePlot)
    assert bound.actions[0].data.dataset_id == "source:experiment"
    assert bound.actions[0].data.content_hash == HASH
    assert tuple(item.field_id for item in bound.actions[0].bindings) == (
        "field:time",
        "field:signal",
    )
    assert isinstance(bound.actions[1], SetTitle)
    assert bound.actions[1].expected_plot_version == 1
    assert isinstance(bound.actions[2], SetAxis)
    assert bound.actions[2].target == "axis:agent.line-demo.1.y"
    assert bound.actions[2].expected_plot_version == 2
    assert bound.actions[3].target == "series:agent.line-demo.1.primary"
    assert bound.actions[3].expected_plot_version == 3


def test_bundled_agent_rejects_unexposed_native_objects() -> None:
    base = EngineAgentPlan(
        plan_id="plan:base",
        target_alias="active_data",
        actions=(
            AgentCreatePlot(
                action_id="action:create",
                plot_alias="result",
                profile_id="K01",
                source_alias="active_data",
                bindings=(
                    AgentFieldBinding(role="x", field_alias="time"),
                    AgentFieldBinding(role="y", field_alias="signal"),
                ),
            ),
        ),
    )
    unsupported = base.model_copy(
        update={
            "plan_id": "plan:bad-object",
            "actions": (
                *base.actions,
                AgentSetAxis(
                    action_id="action:z-axis",
                    plot_alias="result",
                    axis_alias="z_axis",
                    scale="linear",
                ),
            ),
        }
    )
    with pytest.raises(EngineCommandError, match="does not expose axis alias"):
        _binder().bind(unsupported, _source_context())


def test_bundled_agent_cannot_style_a_profile_that_does_not_publish_series_edits() -> None:
    plan = EngineAgentPlan(
        plan_id="plan:heatmap",
        target_alias="active_data",
        actions=(
            AgentCreatePlot(
                action_id="action:create-heatmap",
                plot_alias="result",
                profile_id="K20",
                source_alias="active_data",
                bindings=(
                    AgentFieldBinding(role="row", field_alias="time"),
                    AgentFieldBinding(role="column", field_alias="signal"),
                    AgentFieldBinding(role="value", field_alias="signal"),
                ),
            ),
            AgentSetSeriesStyle(
                action_id="action:invent-style",
                plot_alias="result",
                series_alias="series_1",
                color="#FF0000",
            ),
        ),
    )
    with pytest.raises(EngineCommandError, match="does not expose series alias"):
        _binder().bind(plan, _source_context())


def test_bundled_agent_binds_repeatable_k03_series_aliases_locally() -> None:
    plan = EngineAgentPlan(
        plan_id="plan:grouped-scatter",
        target_alias="active_data",
        actions=(
            AgentCreatePlot(
                action_id="action:create-scatter",
                plot_alias="result",
                profile_id="K03",
                source_alias="active_data",
                bindings=(
                    AgentFieldBinding(role="x", field_alias="time"),
                    AgentFieldBinding(role="y", field_alias="signal"),
                    AgentFieldBinding(role="group", field_alias="group"),
                ),
            ),
            AgentSetSeriesStyle(
                action_id="action:style-second-group",
                plot_alias="result",
                series_alias="series_2",
                color="#AA3300",
                symbol="diamond",
            ),
        ),
    )

    bound = _binder().bind(plan, _source_context())

    assert bound.actions[1].target == "series:agent.grouped-scatter.1.group_2"


@pytest.mark.parametrize("alias", ("series_0", "series_two", "series_01"))
def test_bundled_agent_rejects_invalid_repeatable_series_alias(alias: str) -> None:
    plan = EngineAgentPlan(
        plan_id="plan:bad-group",
        target_alias="active_data",
        actions=(
            AgentCreatePlot(
                action_id="action:create-scatter",
                plot_alias="result",
                profile_id="K03",
                source_alias="active_data",
                bindings=(
                    AgentFieldBinding(role="x", field_alias="time"),
                    AgentFieldBinding(role="y", field_alias="signal"),
                ),
            ),
            AgentSetSeriesStyle(
                action_id="action:bad-style",
                plot_alias="result",
                series_alias=alias,
                color="#AA3300",
            ),
        ),
    )

    with pytest.raises(EngineCommandError, match="does not expose series alias"):
        _binder().bind(plan, _source_context())
