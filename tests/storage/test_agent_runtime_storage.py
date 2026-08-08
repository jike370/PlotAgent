from __future__ import annotations

import sqlite3

import pytest

from plotagent.agent.project_context import ProjectContextService
from plotagent.agent.task_plans import TaskPlanCompiler
from plotagent.contracts.agent_context import ContextObjectRef, ConversationStateProjection
from plotagent.contracts.decisions import ActionPlan, PatchPlotAction, PlotTitleIntent
from plotagent.contracts.task_runtime import TaskFailure, TaskOutputRef
from plotagent.storage import AgentRuntimeRepository, ProjectStore
from plotagent.storage.errors import StorageErrorCode, StorageProblem
from plotagent.storage.schema import PROJECT_SCHEMA_VERSION


def _ref() -> ContextObjectRef:
    return ContextObjectRef(
        object_alias="active_target",
        object_id="plot:one",
        object_version=1,
        object_type="plot",
        content_hash="a" * 64,
    )


def _state(version: int = 1) -> ConversationStateProjection:
    return ConversationStateProjection(state_version=version, current_target=_ref())


def _runtime(repository: AgentRuntimeRepository):  # type: ignore[no-untyped-def]
    state = _state()
    repository.save_conversation_state(
        "conversation:main", state, expected_state_version=None
    )
    context = ProjectContextService().build_snapshot(
        project_id=repository.project.project_id,
        project_revision=0,
        conversation_id="conversation:main",
        conversation_state=state,
        known_objects=(_ref(),),
    )
    repository.save_context_snapshot(context)
    plan = ActionPlan(
        plan_id="plan:patch",
        target_alias="active_target",
        actions=(
            PatchPlotAction(
                action_id="action:title",
                target_alias="active_target",
                patches=(
                    PlotTitleIntent(target_alias="active_target", title="Updated"),
                ),
            ),
        ),
    )
    runtime = TaskPlanCompiler().compile(plan, context)
    repository.create_plan(runtime)
    return runtime


def test_project_schema_v2_contains_persistent_agent_runtime(storage_root) -> None:
    with ProjectStore.create(storage_root / "project", project_id="project:test") as project:
        connection = project._assert_writer()  # noqa: SLF001
        assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == (
            PROJECT_SCHEMA_VERSION
        )
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {
            "conversations",
            "conversation_states",
            "project_context_snapshots",
            "task_plans",
            "task_items",
            "task_attempts",
            "task_checkpoints",
            "task_events",
        }.issubset(tables)


def test_open_migrates_project_v1_to_v2_without_touching_domain_rows(storage_root) -> None:
    workspace = storage_root / "project"
    with ProjectStore.create(workspace, project_id="project:test") as project:
        database = project.database_path
    with sqlite3.connect(database) as connection:
        for table in (
            "task_events",
            "task_checkpoints",
            "task_attempts",
            "task_items",
            "task_plans",
            "project_context_snapshots",
            "conversation_states",
            "conversations",
        ):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("UPDATE schema_info SET value = '1' WHERE key = 'schema_version'")
        connection.execute("PRAGMA user_version = 1")
        connection.commit()

    with ProjectStore.open(workspace) as project:
        connection = project._assert_writer()  # noqa: SLF001
        assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == 2
        assert connection.execute("SELECT project_id FROM project_meta").fetchone()[0] == (
            "project:test"
        )


def test_conversation_context_and_plan_are_idempotent_and_optimistic(storage_root) -> None:
    with ProjectStore.create(storage_root / "project") as project:
        repository = AgentRuntimeRepository(project)
        runtime = _runtime(repository)
        repository.create_plan(runtime)

        assert repository.get_plan(runtime.plan_id) == runtime
        assert repository.get_context_snapshot(runtime.context_snapshot_id).snapshot_hash == (
            runtime.context_hash
        )
        updated = _state(2)
        repository.save_conversation_state(
            "conversation:main",
            updated,
            expected_state_version=1,
            context_hash=runtime.context_hash,
        )
        with pytest.raises(StorageProblem) as captured:
            repository.save_conversation_state(
                "conversation:main",
                _state(3),
                expected_state_version=1,
            )
        assert captured.value.code == StorageErrorCode.VERSION_CONFLICT


def test_attempt_failure_is_partial_and_can_resume_without_repeating_success(storage_root) -> None:
    with ProjectStore.create(storage_root / "project") as project:
        repository = AgentRuntimeRepository(project)
        runtime = _runtime(repository)
        item = runtime.items[0]

        first = repository.begin_attempt(item.task_item_id)
        failed = repository.finish_attempt(
            first.attempt_id,
            failure=TaskFailure(code="RENDER_FAILED", message="Origin failed.", retryable=True),
        )
        assert failed.state == "failed"
        assert failed.items[0].state == "failed"
        repository.transition_item(item.task_item_id, "ready")
        second = repository.begin_attempt(item.task_item_id)
        succeeded = repository.finish_attempt(
            second.attempt_id,
            outputs=(
                TaskOutputRef(
                    output_slot="primary",
                    output_kind="object",
                    object_ref=_ref().model_copy(update={"object_version": 2}),
                ),
            ),
        )
        assert succeeded.state == "succeeded"
        assert succeeded.items[0].attempt_count == 2
        assert len(repository.list_events(runtime.plan_id)) == 6


def test_process_recovery_marks_only_active_work_interrupted(storage_root) -> None:
    workspace = storage_root / "project"
    with ProjectStore.create(workspace) as project:
        repository = AgentRuntimeRepository(project)
        runtime = _runtime(repository)
        repository.begin_attempt(runtime.items[0].task_item_id)
        assert repository.get_plan(runtime.plan_id).state == "running"
        assert repository.recover_interrupted() == (runtime.plan_id,)
        recovered = repository.get_plan(runtime.plan_id)
        assert recovered.state == "interrupted"
        assert recovered.items[0].state == "interrupted"

