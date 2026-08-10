from __future__ import annotations

from pathlib import Path

import pytest

from plotagent.engine import (
    CreatePlot,
    EngineDataRef,
    FieldBinding,
    PlotDocument,
    PlotDocumentRepository,
    SetTitle,
)
from plotagent.storage.project import ProjectStore

HASH = "b" * 64


def _create_action() -> CreatePlot:
    return CreatePlot(
        action_id="action:create",
        plot_id="plot:demo",
        profile_id="profile.line",
        data=EngineDataRef(
            kind="source",
            dataset_id="dataset.demo",
            version=1,
            content_hash=HASH,
        ),
        bindings=(
            FieldBinding(role="x", field_id="field:x"),
            FieldBinding(role="y", field_id="field:y"),
        ),
    )


def _document(action: CreatePlot) -> PlotDocument:
    return PlotDocument(
        plot_id=action.plot_id,
        plot_version=1,
        profile_id=action.profile_id,
        data=action.data,
        bindings=action.bindings,
        applied_action_ids=(action.action_id,),
    )


def test_repository_persists_new_plot_documents_without_legacy_plot_specs(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:engine") as project:
        repository = PlotDocumentRepository(project)
        create = _create_action()
        applied = repository.commit(_document(create), create)

        stored = repository.get("plot:demo")
        assert stored.document.schema_version == "2.0"
        assert stored.content_hash == applied.document_after.content_hash
        table_names = {
            str(row[0])
            for row in project._assert_writer()  # noqa: SLF001
            .execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "engine_plot_document_versions" in table_names
        assert "engine_plot_action_journal" in table_names


def test_repository_appends_explicit_actions_and_reopens(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    with ProjectStore.create(workspace, project_id="project:engine") as project:
        repository = PlotDocumentRepository(project)
        create = _create_action()
        version_one = _document(create)
        repository.commit(version_one, create)
        title = SetTitle(
            action_id="action:title",
            target="plot:demo",
            text="Temperature response",
        )
        version_two = version_one.model_copy(
            update={
                "plot_version": 2,
                "parent_version": 1,
                "applied_action_ids": ("action:create", "action:title"),
            }
        )
        repository.commit(version_two, title)

    with ProjectStore.open(workspace) as project:
        repository = PlotDocumentRepository(project)
        assert repository.get("plot:demo").document.plot_version == 2
        actions = repository.actions("plot:demo")
        assert [item.action.operation for item in actions] == ["create_plot", "set_title"]
        assert len(repository.list_latest()) == 1


def test_repository_rejects_stale_versions_and_history_mismatch(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:engine") as project:
        repository = PlotDocumentRepository(project)
        create = _create_action()
        version_one = _document(create)
        repository.commit(version_one, create)
        title = SetTitle(action_id="action:title", target="plot:demo", text="Title")

        with pytest.raises(ValueError, match="stale or non-linear"):
            repository.commit(version_one, title)
        with pytest.raises(ValueError, match="action history"):
            repository.commit(
                version_one.model_copy(update={"plot_version": 2, "parent_version": 1}),
                title,
            )

