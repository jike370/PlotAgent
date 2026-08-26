from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from plotagent.contracts.agent_data import RenameFieldOperation, SelectFieldsOperation
from plotagent.engine.contracts import EngineColumn, EngineDataRef, EngineDataView, EngineField
from plotagent.storage.project import ProjectStore
from plotagent.tooling.data_workspace import StagedDataWorkspace
from plotagent.tooling.data_workspace_ops import DataWorkspaceError

HASH_A = "a" * 64


class Provider:
    def __init__(self, source_view: EngineDataView) -> None:
        self.source_view = source_view

    def materialize(
        self,
        data: EngineDataRef,
        field_ids: tuple[str, ...],
    ) -> EngineDataView:
        assert data == self.source_view.data
        by_id = {column.field.field_id: column for column in self.source_view.columns}
        return self.source_view.model_copy(
            update={"columns": tuple(by_id[field_id] for field_id in field_ids)}
        )


class WrongIdentityProvider(Provider):
    def materialize(
        self,
        data: EngineDataRef,
        field_ids: tuple[str, ...],
    ) -> EngineDataView:
        return (
            super()
            .materialize(data, field_ids)
            .model_copy(update={"data": data.model_copy(update={"content_hash": "b" * 64})})
        )


def source_view() -> EngineDataView:
    return EngineDataView(
        data=EngineDataRef(
            kind="source",
            dataset_id="source:test",
            version=1,
            content_hash=HASH_A,
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
                values=(4.0, 5.0, 6.0),
            ),
        ),
    )


def test_staged_handles_are_immutable_chained_task_scoped_and_restart_safe(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 8, 18, 10, 0, tzinfo=UTC)]
    project_path = tmp_path / "project"
    original = source_view()
    provider = Provider(original)
    with ProjectStore.create(  # noqa: SIM117 - project must outlive its staging index
        project_path, project_id="project:test"
    ) as project:
        with StagedDataWorkspace(
            project,
            clock=lambda: now[0],
            ttl_seconds=3_600,
        ) as workspace:
            source_handle = workspace.stage_source(
                task_id="task:test",
                task_version=1,
                item_id=None,
                source=original.data,
                field_ids=("field:x", "field:y"),
                provider=provider,
            )
            assert (project.tmp_root / "agent-data-v2" / "index.sqlite3").is_file()
            assert source_handle.operation_kind == "source"
            assert source_handle.data == original.data
            assert len(source_handle.lineage) == 1
            assert (
                workspace.stage_source(
                    task_id="task:test",
                    task_version=1,
                    item_id=None,
                    source=original.data,
                    field_ids=("field:x", "field:y"),
                    provider=provider,
                )
                == source_handle
            )

            renamed = workspace.apply(
                task_id="task:test",
                task_version=1,
                item_id=None,
                operation=RenameFieldOperation(
                    input_handle_id=source_handle.handle_id,
                    field_id="field:y",
                    output_name="Signal",
                ),
            )
            selected = workspace.apply(
                task_id="task:test",
                task_version=1,
                item_id=None,
                operation=SelectFieldsOperation(
                    input_handle_id=renamed.handle_id,
                    field_ids=("field:x", "field:y"),
                ),
            )
            assert selected.parent_handle_ids == (renamed.handle_id,)
            assert selected.data.kind == "prepared"
            assert selected.data.content_hash == selected.data_hash
            assert tuple(field.name for field in selected.fields) == ("Time", "Signal")
            assert len(selected.lineage) == 3
            preview = workspace.preview(
                selected.handle_id,
                task_id="task:test",
                task_version=1,
                item_id=None,
                field_ids=("field:y",),
                offset=1,
                limit=1,
            )
            assert preview.rows == ((5.0,),)
            assert preview.has_more is True
            with pytest.raises(DataWorkspaceError) as crossed:
                workspace.get(
                    selected.handle_id,
                    task_id="task:other",
                    task_version=1,
                    item_id=None,
                )
            assert crossed.value.code == "DATA_HANDLE_NOT_FOUND"
            with pytest.raises(DataWorkspaceError) as crossed_item:
                workspace.get(
                    selected.handle_id,
                    task_id="task:test",
                    task_version=1,
                    item_id="item:other",
                )
            assert crossed_item.value.code == "DATA_HANDLE_NOT_FOUND"
            assert original.columns[1].field.name == "Response"

    with (
        ProjectStore.open(project_path) as reopened_project,
        StagedDataWorkspace(
            reopened_project,
            clock=lambda: now[0],
            ttl_seconds=3_600,
        ) as reopened_workspace,
    ):
        restored, restored_view = reopened_workspace.get(
            selected.handle_id,
            task_id="task:test",
            task_version=1,
            item_id=None,
        )
        assert restored == selected
        assert restored_view.columns[1].field.name == "Signal"
        now[0] += timedelta(hours=2)
        with pytest.raises(DataWorkspaceError) as expired:
            reopened_workspace.get(
                selected.handle_id,
                task_id="task:test",
                task_version=1,
                item_id=None,
            )
        assert expired.value.code == "DATA_HANDLE_EXPIRED"
        assert reopened_workspace.cleanup_expired() == 3
        with pytest.raises(DataWorkspaceError) as missing:
            reopened_workspace.get(
                selected.handle_id,
                task_id="task:test",
                task_version=1,
                item_id=None,
            )
        assert missing.value.code == "DATA_HANDLE_NOT_FOUND"


def test_staged_artifact_corruption_fails_closed(tmp_path: Path) -> None:
    now = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
    original = source_view()
    with ProjectStore.create(  # noqa: SIM117 - project must outlive its staging index
        tmp_path / "project", project_id="project:test"
    ) as project:
        with StagedDataWorkspace(project, clock=lambda: now) as workspace:
            handle = workspace.stage_source(
                task_id="task:test",
                task_version=1,
                item_id=None,
                source=original.data,
                field_ids=("field:x",),
                provider=Provider(original),
            )
            path = workspace._artifact_path(handle)  # noqa: SLF001
            path.write_bytes(b"corrupt")
            with pytest.raises(DataWorkspaceError) as caught:
                workspace.get(
                    handle.handle_id,
                    task_id="task:test",
                    task_version=1,
                    item_id=None,
                )
            assert caught.value.code == "DATA_HANDLE_CORRUPT"


def test_source_materialization_must_preserve_authorized_identity(tmp_path: Path) -> None:
    original = source_view()
    with (
        ProjectStore.create(tmp_path / "project", project_id="project:test") as project,
        StagedDataWorkspace(project) as workspace,
        pytest.raises(DataWorkspaceError) as caught,
    ):
        workspace.stage_source(
            task_id="task:test",
            task_version=1,
            item_id=None,
            source=original.data,
            field_ids=("field:x",),
            provider=WrongIdentityProvider(original),
        )
    assert caught.value.code == "DATA_SOURCE_IDENTITY_MISMATCH"
