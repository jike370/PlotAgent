from __future__ import annotations

import inspect
from pathlib import Path

from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
    PlotDocumentRepository,
    PlotEngineRuntime,
    PlotEngineService,
    SetAxis,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.backends.matplotlib import K08ColumnRenderer, MatplotlibBackend
from plotagent.engine.profiles import K08_COLUMN_PROFILE
from plotagent.engine.service import EngineCatalog
from plotagent.storage.project import ProjectStore

HASH = "8" * 64


class Provider:
    def materialize(self, data, field_ids):
        columns = {
            "field:category": EngineColumn(
                field=EngineField(
                    field_id="field:category",
                    name="Condition",
                    logical_type="categorical",
                ),
                values=("Control", "Low", "High"),
            ),
            "field:value": EngineColumn(
                field=EngineField(
                    field_id="field:value",
                    name="Response",
                    logical_type="numeric",
                    unit_label="a.u.",
                ),
                values=(2.0, 4.5, 7.0),
            ),
        }
        return EngineDataView(
            data=data,
            row_ids=("row:1", "row:2", "row:3"),
            columns=tuple(columns[field_id] for field_id in field_ids),
        )


def _create() -> CreatePlot:
    return CreatePlot(
        action_id="action:create-column",
        plot_id="plot:column-demo",
        profile_id="K08",
        data=EngineDataRef(
            kind="source",
            dataset_id="dataset.column",
            version=1,
            content_hash=HASH,
        ),
        bindings=(
            FieldBinding(role="category", field_id="field:category"),
            FieldBinding(role="value", field_id="field:value"),
        ),
    )


def test_k08_renders_and_replays_only_declared_actions(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project") as project:
        backend = MatplotlibBackend(tmp_path / "artifacts", (K08ColumnRenderer(),))
        runtime = PlotEngineRuntime(
            PlotEngineService(
                EngineCatalog((K08_COLUMN_PROFILE,)),
                PlotDocumentRepository(project),
            ),
            Provider(),
            (backend,),
        )
        runtime.execute(_create())
        runtime.execute(SetTitle(action_id="action:title", target="plot:column-demo", text="Dose"))
        runtime.execute(
            SetAxis(
                action_id="action:y-axis",
                target="axis:column-demo.y",
                label="Response (a.u.)",
                minimum=0,
                maximum=8,
            )
        )
        runtime.execute(
            SetSeriesStyle(
                action_id="action:style",
                target="series:column-demo.primary",
                color="#CC5500",
                line_width_pt=1.2,
            )
        )
        result = runtime.execute(
            SetLegend(
                action_id="action:legend",
                target="legend:column-demo.main",
                visible=True,
            )
        )

        directory = tmp_path / "artifacts" / "column-demo" / "v5"
        assert (directory / "preview.png").stat().st_size > 1_000
        assert (directory / "preview.svg").stat().st_size > 1_000
        assert {item.object_kind for item in backend.readback(result.document).objects} >= {
            "column_series",
            "axis",
            "legend",
        }


def test_k08_renderer_is_independent_of_the_legacy_resolver() -> None:
    source = inspect.getsource(__import__(K08ColumnRenderer.__module__, fromlist=["*"]))
    assert "plotagent.rendering" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source
