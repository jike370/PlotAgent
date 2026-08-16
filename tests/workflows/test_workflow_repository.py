from __future__ import annotations

from pathlib import Path

from plotagent.contracts.workflows import (
    DraftFieldBinding,
    TaskDraft,
    TaskDraftItem,
    WorkflowBudget,
    WorkflowContext,
    WorkflowField,
    WorkflowSource,
)
from plotagent.engine import EngineCatalog
from plotagent.engine.profiles import ENGINE_PROFILES
from plotagent.storage import ProjectStore
from plotagent.workflows.compiler import DraftCompiler
from plotagent.workflows.recipes import build_recipe, replay_recipe
from plotagent.workflows.repository import WorkflowRepository


def _context() -> WorkflowContext:
    return WorkflowContext(
        workflow_run_id="workflow:stored",
        project_id="project:stored",
        project_revision=0,
        instruction="画折线图",
        sources=(
            WorkflowSource(
                source_alias="data_1",
                source_dataset_id="source:stored",
                source_version=1,
                content_hash="a" * 64,
                display_name="data.csv",
                row_count=3,
            ),
        ),
        fields=(
            WorkflowField(
                field_alias="x_field",
                source_alias="data_1",
                field_id="field:x",
                name="X",
                logical_type="numeric",
            ),
            WorkflowField(
                field_alias="y_field",
                source_alias="data_1",
                field_id="field:y",
                name="Y",
                logical_type="numeric",
            ),
        ),
        selected_source_aliases=("data_1",),
        selected_profile_ids=("K01",),
        allowed_profile_ids=tuple(profile.profile_id for profile in ENGINE_PROFILES),
        budget=WorkflowBudget(),
    )


def _draft() -> TaskDraft:
    return TaskDraft(
        draft_id="draft:stored",
        workflow_run_id="workflow:stored",
        route="deterministic",
        summary="创建折线图",
        confidence=1,
        items=(
            TaskDraftItem(
                task_kind="create",
                item_id="item:stored.1",
                plot_alias="plot_1",
                profile_id="K01",
                source_aliases=("data_1",),
                bindings=(
                    DraftFieldBinding(role="x", source_alias="data_1", field_alias="x_field"),
                    DraftFieldBinding(role="y", source_alias="data_1", field_alias="y_field"),
                ),
            ),
        ),
    )


def test_repository_persists_only_workflow_contracts(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "workflow", project_id="project:stored") as project:
        repository = WorkflowRepository(project)
        context = _context()
        run = repository.create_run(context)
        assert run.state == "routing"
        assert repository.get_context(context.workflow_run_id) == context

        draft = repository.save_draft(_draft())
        plan = DraftCompiler(EngineCatalog(ENGINE_PROFILES)).compile(draft, context)
        snapshot = repository.save_plan(plan)
        assert snapshot.state == "awaiting_confirmation"
        assert all(item.state == "pending" for item in snapshot.item_progress)

        confirmed = repository.confirm(plan.plan_id)
        assert confirmed.state == "ready"

        failed = repository.set_item_state(
            plan.plan_id,
            plan.items[0].item_id,
            "failed",
            increment_attempt=True,
            error_code="LOG_SCALE_NON_POSITIVE",
            error_message="Log10 轴包含 0 或负值；任务未执行。",
            error_retryable=False,
        )
        assert failed.item_progress[0].error_message == "Log10 轴包含 0 或负值；任务未执行。"
        assert failed.item_progress[0].error_retryable is False


def test_rejected_plan_cannot_be_confirmed(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "workflow", project_id="project:stored") as project:
        repository = WorkflowRepository(project)
        context = _context()
        repository.create_run(context)
        draft = repository.save_draft(_draft())
        plan = DraftCompiler(EngineCatalog(ENGINE_PROFILES)).compile(draft, context)
        repository.save_plan(plan)

        rejected = repository.reject(plan.plan_id)
        assert rejected.state == "rejected"
        assert repository.get_run(context.workflow_run_id).state == "cancelled"


def test_successful_export_can_be_saved_and_replayed_as_an_explicit_recipe(
    tmp_path: Path,
) -> None:
    catalog = EngineCatalog(ENGINE_PROFILES)
    with ProjectStore.create(tmp_path / "workflow", project_id="project:stored") as project:
        repository = WorkflowRepository(project)
        context = _context()
        repository.create_run(context)
        draft = repository.save_draft(_draft())
        plan = DraftCompiler(catalog).compile(draft, context)
        repository.save_plan(plan)
        recipe = build_recipe(
            context=context,
            draft=draft,
            catalog=catalog,
            plan_id=plan.plan_id,
            display_name="折线图流程",
            export_hash="b" * 64,
        )
        repository.save_recipe(recipe)

        matches = repository.find_recipes(
            recipe.structure_fingerprint, recipe.goal_signature
        )
        assert matches == (recipe,)

        new_context = context.model_copy(update={"workflow_run_id": "workflow:replay"})
        replayed = replay_recipe(matches[0], new_context)
        assert replayed.route == "recipe_replay"
        assert replayed.workflow_run_id == "workflow:replay"
        assert replayed.items[0].item_id == "item:replay.1"
        assert replayed.items[0].bindings == draft.items[0].bindings
