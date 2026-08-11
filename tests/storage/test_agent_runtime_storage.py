from __future__ import annotations

import pytest

from plotagent.agent.project_context import ProjectContextService
from plotagent.contracts.agent_context import ContextObjectRef, ConversationStateProjection
from plotagent.storage import AgentRuntimeRepository, ProjectStore
from plotagent.storage.errors import StorageErrorCode, StorageProblem


def _ref(*, version: int = 1) -> ContextObjectRef:
    return ContextObjectRef(
        object_alias="active_plot",
        object_id="plot:one",
        object_version=version,
        object_type="plot",
        content_hash=("a" if version == 1 else "b") * 64,
    )


def _state(version: int = 1) -> ConversationStateProjection:
    return ConversationStateProjection(state_version=version, current_target=_ref())


def test_conversation_and_project_context_are_persistent_and_optimistic(storage_root) -> None:
    workspace = storage_root / "project"
    with ProjectStore.create(workspace, project_id="project:test") as project:
        repository = AgentRuntimeRepository(project)
        state = _state()
        repository.save_conversation_state(
            "conversation:main", state, expected_state_version=None
        )
        context = ProjectContextService().build_snapshot(
            project_id=project.project_id,
            project_revision=0,
            conversation_id="conversation:main",
            conversation_state=state,
            known_objects=(_ref(),),
        )
        repository.save_context_snapshot(context)

    with ProjectStore.open(workspace) as project:
        repository = AgentRuntimeRepository(project)
        assert repository.get_conversation_state("conversation:main") == state
        assert repository.get_context_snapshot(context.snapshot_id) == context
        assert repository.latest_context_snapshot("conversation:main") == context

        repository.save_conversation_state(
            "conversation:main",
            _state(2),
            expected_state_version=1,
            context_hash=context.snapshot_hash,
        )
        with pytest.raises(StorageProblem) as captured:
            repository.save_conversation_state(
                "conversation:main",
                _state(3),
                expected_state_version=1,
            )
        assert captured.value.code == StorageErrorCode.VERSION_CONFLICT


def test_missing_context_snapshot_is_reported(storage_root) -> None:
    with ProjectStore.create(storage_root / "project") as project:
        repository = AgentRuntimeRepository(project)
        with pytest.raises(StorageProblem) as captured:
            repository.get_context_snapshot("context:missing")
        assert captured.value.code == StorageErrorCode.OBJECT_NOT_FOUND
