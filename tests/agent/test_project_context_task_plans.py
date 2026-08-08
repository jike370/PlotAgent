from __future__ import annotations

from plotagent.agent.project_context import ProjectContextService, TargetResolver
from plotagent.agent.task_plans import TaskPlanCompiler
from plotagent.contracts.agent_context import ContextObjectRef, ConversationStateProjection
from plotagent.contracts.decisions import (
    ActionPlan,
    CreatePlotAction,
    PatchPlotAction,
    PlotTitleIntent,
    SemanticFieldSelection,
)


def _ref(alias: str, object_id: str, object_type: str) -> ContextObjectRef:
    return ContextObjectRef(
        object_alias=alias,
        object_id=object_id,
        object_version=1,
        object_type=object_type,
        content_hash="a" * 64,
    )


def _snapshot():  # type: ignore[no-untyped-def]
    project = _ref("active_target", "project:demo", "project")
    plot = _ref("selected_plot", "plot:one", "plot")
    state = ConversationStateProjection(
        state_version=1,
        current_target=project,
        selected_objects=(plot,),
    )
    return ProjectContextService().build_snapshot(
        project_id="project:demo",
        project_revision=2,
        conversation_id="conversation:main",
        conversation_state=state,
        known_objects=(plot,),
    )


def test_context_snapshot_is_deterministic_and_target_precedence_is_local() -> None:
    first = _snapshot()
    second = _snapshot()

    assert first == second
    explicit = TargetResolver().resolve(
        first,
        explicit_turn_aliases=("selected_plot",),
        allowed_object_types=frozenset({"plot"}),
    )
    assert explicit.status == "resolved"
    assert explicit.precedence == "explicit_turn_reference"
    assert explicit.target is not None
    assert explicit.target.object_id == "plot:one"


def test_target_resolver_asks_once_instead_of_guessing_between_candidates() -> None:
    snapshot = _snapshot()
    other = _ref("other_plot", "plot:two", "plot")
    snapshot = ProjectContextService().build_snapshot(
        project_id=snapshot.project_id,
        project_revision=snapshot.project_revision,
        conversation_id=snapshot.conversation_id,
        conversation_state=snapshot.conversation_state,
        known_objects=(*snapshot.known_objects, other),
    )

    result = TargetResolver().resolve(
        snapshot,
        explicit_turn_aliases=("selected_plot", "other_plot"),
        allowed_object_types=frozenset({"plot"}),
    )

    assert result.status == "ambiguous"
    assert result.question == "请选择要操作的对象：selected_plot、other_plot"


def test_compiler_binds_versions_dependencies_and_confirmation_without_tool_loop() -> None:
    create = CreatePlotAction(
        action_id="action:create",
        target_alias="active_target",
        chart_type_id="K01",
        field_selections=(
            SemanticFieldSelection(role="x", context_field_alias="selected_x"),
            SemanticFieldSelection(role="y", context_field_alias="selected_y"),
        ),
    )
    patch = PatchPlotAction(
        action_id="action:title",
        target_alias="active_target",
        depends_on=(create.action_id,),
        patches=(
            PlotTitleIntent(
                target_alias="active_target",
                title="Result",
            ),
        ),
    )
    source = ActionPlan(
        plan_id="plan:two-step",
        target_alias="active_target",
        actions=(create, patch),
        confirmation="required",
    )

    runtime = TaskPlanCompiler().compile(source, _snapshot())

    assert runtime.state == "needs_confirmation"
    assert runtime.confirmation_state == "pending"
    assert [item.state for item in runtime.items] == ["pending", "pending"]
    assert runtime.items[1].depends_on == (runtime.items[0].task_item_id,)
    assert runtime.items[0].expected_objects[0].object_version == 1
    assert runtime.items[0].output_slots == ("primary",)

