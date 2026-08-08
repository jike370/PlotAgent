"""Compile provider-authored ActionPlan proposals into local runtime plans."""

from __future__ import annotations

import hashlib

from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.decisions import ActionPlan
from plotagent.contracts.project_context import ProjectContextSnapshot
from plotagent.contracts.task_runtime import TaskItemSnapshot, TaskPlanSnapshot

_OUTPUT_SLOTS: dict[str, tuple[str, ...]] = {
    "create_plot": ("primary",),
    "patch_plot": ("primary", "change_set"),
    "create_batch": ("batch",),
    "patch_batch": ("batch", "change_set"),
    "create_figure": ("figure",),
    "patch_figure": ("figure", "change_set"),
    "export_artifact": ("artifact",),
}


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


class TaskPlanCompiler:
    """Bind aliases, versions, dependencies and idempotency locally."""

    def compile(
        self,
        source_plan: ActionPlan,
        context: ProjectContextSnapshot,
    ) -> TaskPlanSnapshot:
        known = {
            item.object_alias: item
            for item in (
                context.known_objects
                + context.recent_result_objects
                + (context.conversation_state.current_target,)
            )
        }
        item_ids = {
            action.action_id: (
                f"taskitem:{_short_hash(source_plan.plan_id + ':' + action.action_id)}"
            )
            for action in source_plan.actions
        }
        needs_confirmation = source_plan.confirmation == "required"
        items: list[TaskItemSnapshot] = []
        for action in source_plan.actions:
            expected = tuple(
                dict.fromkeys(
                    item
                    for alias in (source_plan.target_alias, action.target_alias)
                    if (item := known.get(alias)) is not None
                )
            )
            dependencies = tuple(item_ids[action_id] for action_id in action.depends_on)
            items.append(
                TaskItemSnapshot(
                    task_item_id=item_ids[action.action_id],
                    action=action,
                    state=(
                        "pending"
                        if needs_confirmation or dependencies
                        else "ready"
                    ),
                    depends_on=dependencies,
                    expected_objects=expected,
                    idempotency_key=(
                        "agentplan."
                        + _short_hash(source_plan.plan_id)
                        + "."
                        + _short_hash(action.action_id)
                    ),
                    output_slots=_OUTPUT_SLOTS[action.action_type],
                )
            )
        return TaskPlanSnapshot(
            plan_id=source_plan.plan_id,
            conversation_id=context.conversation_id,
            context_snapshot_id=context.snapshot_id,
            context_hash=context.snapshot_hash,
            project_revision=context.project_revision,
            source_plan=source_plan,
            source_plan_hash=canonical_hash(source_plan),
            state="needs_confirmation" if needs_confirmation else "ready",
            confirmation_state="pending" if needs_confirmation else "not_required",
            items=tuple(items),
        )
