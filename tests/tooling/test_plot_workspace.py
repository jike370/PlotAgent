from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from plotagent.contracts.canonical import canonical_hash
from plotagent.engine import (
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
    SetTitle,
)
from plotagent.engine.backends.origin.messages import OriginWorkerResponse
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.repository import document_ref
from plotagent.storage.project import ProjectStore
from plotagent.tooling.data_workspace import StagedDataWorkspace
from plotagent.tooling.plot_workspace import SandboxPlotError, SandboxPlotWorkspace

NOW = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
SOURCE_HASH = "a" * 64


class Provider:
    def __init__(self, view: EngineDataView) -> None:
        self.view = view

    def materialize(
        self,
        data: EngineDataRef,
        field_ids: tuple[str, ...],
    ) -> EngineDataView:
        assert data == self.view.data
        columns = {column.field.field_id: column for column in self.view.columns}
        return self.view.model_copy(
            update={"columns": tuple(columns[field_id] for field_id in field_ids)}
        )


class FakeOriginWorker:
    def run(self, request):
        Path(request.output_opju).write_bytes(
            f"editable-origin-v{request.document.plot_version}".encode()
        )
        return OriginWorkerResponse(
            readback=EngineReadback(
                document=document_ref(request.document),
                backend="origin",
                objects=(
                    EngineObjectRef(
                        semantic_id=f"series:{request.document.plot_id.removeprefix('plot:')}.group_1",
                        backend="origin",
                        object_kind="series",
                        native_ref="Graph1.Layer1.Plot1",
                    ),
                ),
                data_hash=request.source.source_hash(),
                style_hash=canonical_hash(request.document),
            )
        )


def source_view() -> EngineDataView:
    return EngineDataView(
        data=EngineDataRef(
            kind="source",
            dataset_id="source:plot-test",
            version=1,
            content_hash=SOURCE_HASH,
        ),
        row_ids=("row:1", "row:2", "row:3"),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:x",
                    name="Time",
                    logical_type="numeric",
                    unit_label="s",
                ),
                values=(1.0, 2.0, 3.0),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:y",
                    name="Response",
                    logical_type="numeric",
                    unit_label="mV",
                ),
                values=(4.0, 5.0, 7.0),
            ),
        ),
    )


def bindings() -> tuple[FieldBinding, ...]:
    return (
        FieldBinding(role="x", field_id="field:x"),
        FieldBinding(role="y", field_id="field:y"),
    )


def test_matplotlib_preview_edit_and_restart_are_isolated_and_immutable(
    tmp_path: Path,
) -> None:
    project_path = tmp_path / "project"
    view = source_view()
    with (
        ProjectStore.create(project_path, project_id="project:test") as project,
        StagedDataWorkspace(project, clock=lambda: NOW) as data_workspace,
    ):
        data_handle = data_workspace.stage_source(
            task_id="task:plot",
            task_version=1,
            item_id="item:one",
            source=view.data,
            field_ids=("field:x", "field:y"),
            provider=Provider(view),
        )
        with SandboxPlotWorkspace(
            project,
            data_workspace,
            task_id="task:plot",
            task_version=1,
            item_id="item:one",
            clock=lambda: NOW,
        ) as workspace:
            preview = workspace.preview(
                data_view_handle_id=data_handle.handle_id,
                profile_id="K01",
                bindings=bindings(),
                backends=("matplotlib",),
            )
            assert (
                workspace.preview(
                    data_view_handle_id=data_handle.handle_id,
                    profile_id="K01",
                    bindings=bindings(),
                    backends=("matplotlib",),
                )
                == preview
            )
            assert preview.document.plot_version == 1
            assert preview.root_sources == (view.data,)
            assert tuple(item.format for item in preview.artifacts) == ("png", "svg")
            assert all(
                workspace.artifact_path(preview.handle_id, artifact.artifact_id).is_file()
                for artifact in preview.artifacts
            )
            assert "native_ref" not in preview.model_dump_json()

            edited = workspace.apply_edit(
                preview.handle_id,
                edit=SetTitle(
                    action_id="action:title",
                    target=preview.document.plot_id,
                    expected_plot_version=1,
                    text="Updated title",
                ),
                expected_backend="matplotlib",
            )
            assert (
                workspace.apply_edit(
                    preview.handle_id,
                    edit=SetTitle(
                        action_id="action:title",
                        target=preview.document.plot_id,
                        expected_plot_version=1,
                        text="Updated title",
                    ),
                    expected_backend="matplotlib",
                )
                == edited
            )
            assert edited.document.plot_version == 2
            assert edited.parent_handle_id == preview.handle_id
            assert edited.root_sources == preview.root_sources
            assert len(edited.lineage) == 2
            assert project._assert_writer().execute(  # noqa: SLF001
                "SELECT revision FROM project_meta"
            ).fetchone() == (0,)
            parent_tables = {
                str(row[0])
                for row in project._assert_writer()  # noqa: SLF001
                .execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                .fetchall()
            }
            assert "engine_plot_document_versions" not in parent_tables
            with pytest.raises(SandboxPlotError) as wrong_backend:
                workspace.apply_edit(
                    edited.handle_id,
                    edit=SetTitle(
                        action_id="action:wrong-backend",
                        target=edited.document.plot_id,
                        expected_plot_version=2,
                        text="No",
                    ),
                    expected_backend="origin",
                )
            assert wrong_backend.value.code == "SANDBOX_BACKEND_MISMATCH"

    with (
        ProjectStore.open(project_path) as project,
        StagedDataWorkspace(project, clock=lambda: NOW) as data_workspace,
        SandboxPlotWorkspace(
            project,
            data_workspace,
            task_id="task:plot",
            task_version=1,
            item_id="item:one",
            clock=lambda: NOW,
        ) as workspace,
    ):
        assert workspace.get(edited.handle_id) == edited
        with SandboxPlotWorkspace(
            project,
            data_workspace,
            task_id="task:plot",
            task_version=1,
            item_id="item:other",
            clock=lambda: NOW,
        ) as other_item:
            with pytest.raises(SandboxPlotError) as crossed:
                other_item.get(edited.handle_id)
            assert crossed.value.code == "SANDBOX_PLOT_NOT_FOUND"


def test_origin_preview_returns_editable_artifact_without_native_ref_disclosure(
    tmp_path: Path,
) -> None:
    view = source_view()
    with (
        ProjectStore.create(tmp_path / "project", project_id="project:test") as project,
        StagedDataWorkspace(project, clock=lambda: NOW) as data_workspace,
    ):
        data_handle = data_workspace.stage_source(
            task_id="task:origin",
            task_version=1,
            item_id=None,
            source=view.data,
            field_ids=("field:x", "field:y"),
            provider=Provider(view),
        )
        with SandboxPlotWorkspace(
            project,
            data_workspace,
            task_id="task:origin",
            task_version=1,
            item_id=None,
            origin_install_dir=tmp_path / "origin-install",
            origin_worker=FakeOriginWorker(),
            clock=lambda: NOW,
        ) as workspace:
            handle = workspace.preview(
                data_view_handle_id=data_handle.handle_id,
                profile_id="K01",
                bindings=bindings(),
                backends=("origin",),
            )
            assert tuple(item.format for item in handle.artifacts) == ("opju",)
            artifact = workspace.artifact_path(
                handle.handle_id,
                handle.artifacts[0].artifact_id,
            )
            assert artifact.read_bytes() == b"editable-origin-v1"
            assert handle.readbacks[0].objects[0].object_kind == "series"
            public_json = handle.model_dump_json()
            assert "native_ref" not in public_json
            assert "Graph1.Layer1.Plot1" not in public_json
