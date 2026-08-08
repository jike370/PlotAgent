from __future__ import annotations

import pytest
from pydantic import ValidationError

from plotagent.contracts.agent_context import ContextObjectRef, ConversationStateProjection
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.decisions import ActionPlan, CreatePlotAction, SemanticFieldSelection
from plotagent.contracts.project_context import ProjectContextSnapshot, TargetResolution
from plotagent.contracts.task_runtime import TaskItemSnapshot, TaskPlanSnapshot


def _ref(alias: str, object_id: str, object_type: str = "plot") -> ContextObjectRef:
    return ContextObjectRef.model_validate(
        {
            "object_alias": alias,
            "object_id": object_id,
            "object_version": 1,
            "object_type": object_type,
            "content_hash": "a" * 64,
        }
    )


def _plan() -> ActionPlan:
    return ActionPlan(
        plan_id="plan:create",
        target_alias="active_target",
        actions=(
            CreatePlotAction(
                action_id="action:create",
                target_alias="active_target",
                chart_type_id="K01",
                field_selections=(
                    SemanticFieldSelection(role="x", context_field_alias="selected_x"),
                    SemanticFieldSelection(role="y", context_field_alias="selected_y"),
                ),
            ),
        ),
    )


def test_project_context_keeps_authoritative_ids_local_and_versioned() -> None:
    project = _ref("active_target", "project:demo", "project")
    plot = _ref("selected_plot", "plot:one")
    state = ConversationStateProjection(
        state_version=2,
        current_target=project,
        selected_objects=(plot,),
    )

    snapshot = ProjectContextSnapshot(
        snapshot_id="context:demo.2",
        snapshot_hash="b" * 64,
        project_id="project:demo",
        project_revision=4,
        conversation_id="conversation:main",
        conversation_state=state,
        known_objects=(plot,),
    )

    assert snapshot.project_revision == 4
    with pytest.raises(ValidationError, match="selected objects"):
        ProjectContextSnapshot(
            snapshot_id="context:demo.2",
            snapshot_hash="b" * 64,
            project_id="project:demo",
            project_revision=4,
            conversation_id="conversation:main",
            conversation_state=state,
            known_objects=(_ref("selected_plot", "plot:other"),),
        )


def test_target_resolution_requires_one_minimal_question_for_ambiguity() -> None:
    first = _ref("first_plot", "plot:first")
    second = _ref("second_plot", "plot:second")
    resolution = TargetResolution(
        status="ambiguous",
        precedence="explicit_turn_reference",
        candidates=(first, second),
        question="你要修改哪一张图？",
    )
    assert len(resolution.candidates) == 2
    with pytest.raises(ValidationError, match="candidates and one question"):
        TargetResolution(
            status="ambiguous",
            precedence="explicit_turn_reference",
            candidates=(first,),
            question="你要修改哪一张图？",
        )


def test_task_plan_is_one_item_per_action_and_preserves_confirmation() -> None:
    source = _plan()
    action = source.actions[0]
    item = TaskItemSnapshot(
        task_item_id="taskitem:create.1",
        action=action,
        state="ready",
        idempotency_key="plan.create.action.create",
        output_slots=("primary",),
    )

    runtime = TaskPlanSnapshot(
        plan_id=source.plan_id,
        conversation_id="conversation:main",
        context_snapshot_id="context:demo.2",
        context_hash="c" * 64,
        project_revision=4,
        source_plan=source,
        source_plan_hash=canonical_hash(source),
        state="ready",
        confirmation_state="not_required",
        items=(item,),
    )

    assert runtime.items[0].action.action_id == "action:create"
    with pytest.raises(ValidationError, match="one item per source action"):
        TaskPlanSnapshot(
            **{
                **runtime.model_dump(),
                "items": (
                    item,
                    item.model_copy(update={"task_item_id": "taskitem:create.2"}),
                ),
            },
        )


def test_failed_task_item_requires_typed_failure() -> None:
    with pytest.raises(ValidationError, match="requires a failure"):
        TaskItemSnapshot(
            task_item_id="taskitem:create.1",
            action=_plan().actions[0],
            state="failed",
            idempotency_key="plan.create.action.create",
            output_slots=("primary",),
        )
