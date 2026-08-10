from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
    PlotDocument,
    PlotDocumentRepository,
    PlotEngineRuntime,
    PlotEngineService,
    SetAxis,
    SetTitle,
)
from plotagent.engine.backends.matplotlib import K20HeatmapRenderer, MatplotlibBackend
from plotagent.engine.profile_data import k20_grid
from plotagent.engine.profiles import K20_HEATMAP_PROFILE
from plotagent.engine.service import EngineCatalog
from plotagent.storage.project import ProjectStore

HASH = "2" * 64


class Provider:
    def materialize(self, data, field_ids):
        columns = {
            "field:row": EngineColumn(
                field=EngineField(
                    field_id="field:row",
                    name="Protein",
                    logical_type="categorical",
                ),
                values=("P2", "P1", "P2", "P1"),
            ),
            "field:column": EngineColumn(
                field=EngineField(
                    field_id="field:column",
                    name="Condition",
                    logical_type="categorical",
                ),
                values=("Control", "Control", "Drug", "Drug"),
            ),
            "field:value": EngineColumn(
                field=EngineField(
                    field_id="field:value",
                    name="Expression",
                    logical_type="numeric",
                    unit_label="a.u.",
                ),
                values=(2.0, 1.0, 4.0, 3.0),
            ),
        }
        return EngineDataView(
            data=data,
            row_ids=("row:1", "row:2", "row:3", "row:4"),
            columns=tuple(columns[field_id] for field_id in field_ids),
        )


def _create() -> CreatePlot:
    return CreatePlot(
        action_id="action:create-heatmap",
        plot_id="plot:heatmap-demo",
        profile_id="K20",
        data=EngineDataRef(
            kind="source",
            dataset_id="dataset.heatmap",
            version=1,
            content_hash=HASH,
        ),
        bindings=(
            FieldBinding(role="row", field_id="field:row"),
            FieldBinding(role="column", field_id="field:column"),
            FieldBinding(role="value", field_id="field:value"),
        ),
    )


def test_k20_renders_ordered_long_table_and_replays_declared_actions(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project") as project:
        backend = MatplotlibBackend(tmp_path / "artifacts", (K20HeatmapRenderer(),))
        runtime = PlotEngineRuntime(
            PlotEngineService(
                EngineCatalog((K20_HEATMAP_PROFILE,)),
                PlotDocumentRepository(project),
            ),
            Provider(),
            (backend,),
        )
        runtime.execute(_create())
        runtime.execute(
            SetTitle(
                action_id="action:title",
                target="plot:heatmap-demo",
                expected_plot_version=1,
                text="Expression map",
            )
        )
        result = runtime.execute(
            SetAxis(
                action_id="action:y-axis",
                target="axis:heatmap-demo.y",
                expected_plot_version=2,
                label="Protein ID",
                reverse=True,
            )
        )

        directory = tmp_path / "artifacts" / "heatmap-demo" / "v3"
        assert (directory / "preview.png").stat().st_size > 1_000
        assert (directory / "preview.svg").stat().st_size > 1_000
        assert {item.object_kind for item in backend.readback(result.document).objects} >= {
            "heatmap_series",
            "axis",
            "colorbar",
        }


def test_k20_grid_preserves_first_seen_order_and_missing_cells() -> None:
    create = _create()
    data = Provider().materialize(create.data, tuple(item.field_id for item in create.bindings))
    grid = k20_grid(
        PlotDocument(
            plot_id=create.plot_id,
            plot_version=1,
            profile_id=create.profile_id,
            data=create.data,
            bindings=create.bindings,
            applied_action_ids=(create.action_id,),
        ),
        data,
    )
    assert grid.row_labels == ("P2", "P1")
    assert grid.column_labels == ("Control", "Drug")
    assert grid.values == ((2.0, 4.0), (1.0, 3.0))


def test_k20_grid_rejects_duplicate_cells_instead_of_averaging() -> None:
    create = _create()
    view = Provider().materialize(create.data, tuple(item.field_id for item in create.bindings))
    columns = list(view.columns)
    columns[0] = columns[0].model_copy(update={"values": ("P2", "P2", "P2", "P1")})
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=1,
        profile_id=create.profile_id,
        data=create.data,
        bindings=create.bindings,
        applied_action_ids=(create.action_id,),
    )
    with pytest.raises(ValueError, match="duplicate matrix cell"):
        k20_grid(document, view.model_copy(update={"columns": tuple(columns)}))


def test_k20_renderer_is_independent_of_the_legacy_resolver() -> None:
    source = inspect.getsource(__import__(K20HeatmapRenderer.__module__, fromlist=["*"]))
    assert "plotagent.rendering" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source
