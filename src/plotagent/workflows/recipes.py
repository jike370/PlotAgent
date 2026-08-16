"""Explicitly saved, structure-bound workflow recipe replay."""

from __future__ import annotations

import re
import uuid

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.workflows import TaskDraft, WorkflowContext, WorkflowRecipe
from plotagent.engine import EngineCatalog


def structure_fingerprint(context: WorkflowContext) -> str:
    """Hash source structure without binding a recipe to content or row count."""

    fields_by_source: dict[str, list[JsonValue]] = {
        source.source_alias: [
            {
                "name": field.name.casefold().strip(),
                "logical_type": field.logical_type,
                "unit_label": (field.unit_label or "").casefold().strip(),
            }
            for field in context.fields
            if field.source_alias == source.source_alias
        ]
        for source in context.sources
    }
    sources: list[JsonValue] = [
        fields_by_source[source.source_alias] for source in context.sources
    ]
    return canonical_hash({"sources": sources})


def goal_signature(context: WorkflowContext) -> str:
    """Conservatively match a normalized goal and explicit profile selection."""

    normalized = " ".join(
        token
        for token in re.split(r"[^\w\u4e00-\u9fff]+", context.instruction.casefold())
        if token
    )
    return canonical_hash(
        {
            "instruction": normalized,
            "profiles": list(context.selected_profile_ids),
            "source_count": len(context.selected_source_aliases),
            "plot_count": len(context.selected_plot_aliases),
        }
    )


def profile_contract_hash(catalog: EngineCatalog, profile_ids: tuple[str, ...]) -> str:
    unique = tuple(dict.fromkeys(profile_ids))
    return canonical_hash(
        {
            "profiles": [
                catalog.get(profile_id).model_dump(mode="json") for profile_id in unique
            ]
        }
    )


def replay_recipe(recipe: WorkflowRecipe, context: WorkflowContext) -> TaskDraft:
    """Rebind a validated template to the current run's stable aliases."""

    token = context.workflow_run_id.removeprefix("workflow:")
    items = tuple(
        item.model_copy(
            update={
                "item_id": f"item:{token}.{position}",
                "plot_alias": f"plot_{position}",
            }
        )
        for position, item in enumerate(recipe.draft_template.items, start=1)
    )
    return recipe.draft_template.model_copy(
        update={
            "draft_id": f"draft:{token}",
            "workflow_run_id": context.workflow_run_id,
            "route": "recipe_replay",
            "items": items,
            "confidence": 1.0,
        }
    )


def build_recipe(
    *,
    context: WorkflowContext,
    draft: TaskDraft,
    catalog: EngineCatalog,
    plan_id: str,
    display_name: str,
    export_hash: str,
) -> WorkflowRecipe:
    profile_ids = tuple(item.profile_id for item in draft.items)
    contract_hash = profile_contract_hash(catalog, profile_ids)
    return WorkflowRecipe(
        recipe_id=f"recipe:{uuid.uuid4().hex}",
        recipe_version=1,
        display_name=display_name,
        structure_fingerprint=structure_fingerprint(context),
        goal_signature=goal_signature(context),
        draft_template=draft,
        engine_profile_hash=contract_hash,
        renderer_contract_hash=contract_hash,
        created_from_workflow_run_id=context.workflow_run_id,
        created_from_plan_id=plan_id,
        created_from_export_hash=export_hash,
    )
