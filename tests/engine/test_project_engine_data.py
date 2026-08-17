from __future__ import annotations

from pathlib import Path

import pytest

from plotagent.engine import (
    CreatePlot,
    EngineDataError,
    EngineDataRef,
    FieldBinding,
    PlotDocumentRepository,
    PlotEngineRuntime,
    PlotEngineService,
    ProjectEngineDataProvider,
)
from plotagent.engine.backends.matplotlib import K01LineRenderer, MatplotlibBackend
from plotagent.engine.profiles import K01_LINE_PROFILE
from plotagent.engine.service import EngineCatalog
from plotagent.storage import ImportResource, ProjectImportService, ProjectStore

FILES_ROOT = Path(__file__).parents[1] / "fixtures" / "import" / "files"


def _import_basic(project: ProjectStore):
    result = ProjectImportService(project).import_resource(
        ImportResource(resource_id="resource:engine-data", path=FILES_ROOT / "csv_basic.csv")
    )
    assert result.kind == "committed"
    return result.datasets[0].source_dataset


def _data_ref(source, **updates: object) -> EngineDataRef:
    values = {
        "kind": "source",
        "dataset_id": source.source_dataset_id,
        "version": source.source_version,
        "content_hash": source.content_hash,
    }
    values.update(updates)
    return EngineDataRef.model_validate(values)


def test_project_source_materializes_exact_ordered_engine_view(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project") as project:
        source = _import_basic(project)
        time_field, signal_field = source.field_schema

        view = ProjectEngineDataProvider(project).materialize(
            _data_ref(source),
            (signal_field.field_id, time_field.field_id),
        )

        assert view.data == _data_ref(source)
        assert [column.field.field_id for column in view.columns] == [
            signal_field.field_id,
            time_field.field_id,
        ]
        assert [column.field.name for column in view.columns] == ["signal", "time"]
        assert [column.field.logical_type for column in view.columns] == ["numeric", "numeric"]
        assert view.columns[0].values == (1.5, 2.5)
        assert view.columns[1].values == (0, 1)
        assert len(view.row_ids) == 2
        assert all(row_id.startswith("row:") for row_id in view.row_ids)


def test_project_source_rejects_drift_unknown_fields_and_duplicates(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project") as project:
        source = _import_basic(project)
        field_id = source.field_schema[0].field_id
        provider = ProjectEngineDataProvider(project)

        with pytest.raises(EngineDataError, match="content hash"):
            provider.materialize(_data_ref(source, content_hash="0" * 64), (field_id,))
        with pytest.raises(EngineDataError, match="does not contain"):
            provider.materialize(_data_ref(source), ("field:missing",))
        with pytest.raises(EngineDataError, match="must be unique"):
            provider.materialize(_data_ref(source), (field_id, field_id))


def test_non_source_data_requires_a_dedicated_adapter(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project") as project:
        provider = ProjectEngineDataProvider(project)
        data = EngineDataRef(
            kind="prepared",
            dataset_id="prepared:test",
            version=1,
            content_hash="0" * 64,
        )

        with pytest.raises(EngineDataError, match="explicit adapter"):
            provider.materialize(data, ("field:x",))


def test_imported_project_data_drives_the_independent_k01_renderer(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project") as project:
        source = _import_basic(project)
        time_field, signal_field = source.field_schema
        backend = MatplotlibBackend(tmp_path / "artifacts", (K01LineRenderer(),))
        runtime = PlotEngineRuntime(
            PlotEngineService(
                EngineCatalog((K01_LINE_PROFILE,)),
                PlotDocumentRepository(project),
            ),
            ProjectEngineDataProvider(project),
            (backend,),
        )

        result = runtime.execute(
            CreatePlot(
                action_id="action:project-data-create",
                plot_id="plot:project-data-line",
                profile_id="K01",
                data=_data_ref(source),
                bindings=(
                    FieldBinding(role="x", field_id=time_field.field_id),
                    FieldBinding(role="y", field_id=signal_field.field_id),
                ),
            )
        )

        preview = tmp_path / "artifacts" / "project-data-line" / "v1" / "preview.png"
        assert preview.stat().st_size > 1_000
        assert backend.readback(result.document).data_hash == result.readbacks[0].data_hash
