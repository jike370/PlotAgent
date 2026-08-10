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
from plotagent.engine.backends.matplotlib import MatplotlibBackend, X23DualYRenderer
from plotagent.engine.profiles import X23_DUAL_Y_LINE_PROFILE
from plotagent.engine.service import EngineCatalog
from plotagent.storage.project import ProjectStore

HASH = "4" * 64


class Provider:
    def materialize(self, data, field_ids):
        columns = {
            "field:country": EngineColumn(
                field=EngineField(
                    field_id="field:country",
                    name="Country",
                    logical_type="categorical",
                ),
                values=("A", "B", "C", "D"),
            ),
            "field:population": EngineColumn(
                field=EngineField(
                    field_id="field:population",
                    name="Population",
                    logical_type="numeric",
                    unit_label="million",
                ),
                values=(12.0, 15.0, 19.0, 24.0),
            ),
            "field:gdp": EngineColumn(
                field=EngineField(
                    field_id="field:gdp",
                    name="GDP per capita",
                    logical_type="numeric",
                    unit_label="USD",
                ),
                values=(20_000.0, 23_500.0, 22_000.0, 28_000.0),
            ),
        }
        return EngineDataView(
            data=data,
            row_ids=("row:1", "row:2", "row:3", "row:4"),
            columns=tuple(columns[field_id] for field_id in field_ids),
        )


def _create() -> CreatePlot:
    return CreatePlot(
        action_id="action:create-dual",
        plot_id="plot:dual-demo",
        profile_id="X23",
        data=EngineDataRef(
            kind="source",
            dataset_id="dataset.dual",
            version=1,
            content_hash=HASH,
        ),
        bindings=(
            FieldBinding(role="x", field_id="field:country"),
            FieldBinding(role="left", field_id="field:population"),
            FieldBinding(role="right", field_id="field:gdp"),
        ),
    )


def test_x23_renders_two_independent_axes_and_replays_actions(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project") as project:
        backend = MatplotlibBackend(tmp_path / "artifacts", (X23DualYRenderer(),))
        runtime = PlotEngineRuntime(
            PlotEngineService(
                EngineCatalog((X23_DUAL_Y_LINE_PROFILE,)),
                PlotDocumentRepository(project),
            ),
            Provider(),
            (backend,),
        )
        runtime.execute(_create())
        runtime.execute(
            SetTitle(action_id="action:title", target="plot:dual-demo", text="Country metrics")
        )
        runtime.execute(
            SetAxis(
                action_id="action:right-axis",
                target="axis:dual-demo.y_right",
                label="GDP per capita (USD)",
                minimum=15_000,
                maximum=30_000,
            )
        )
        runtime.execute(
            SetSeriesStyle(
                action_id="action:left-style",
                target="series:dual-demo.left",
                color="#0F766E",
                line_width_pt=2.0,
            )
        )
        runtime.execute(
            SetSeriesStyle(
                action_id="action:right-style",
                target="series:dual-demo.right",
                color="#BE123C",
                line_style="dash",
            )
        )
        result = runtime.execute(
            SetLegend(
                action_id="action:legend",
                target="legend:dual-demo.main",
                visible=True,
            )
        )

        directory = tmp_path / "artifacts" / "dual-demo" / "v6"
        assert (directory / "preview.png").stat().st_size > 1_000
        assert (directory / "preview.svg").stat().st_size > 1_000
        kinds = [item.object_kind for item in backend.readback(result.document).objects]
        assert kinds.count("axis") == 3
        assert kinds.count("line_series") == 2
        assert "legend" in kinds


def test_x23_renderer_is_independent_of_the_legacy_resolver() -> None:
    source = inspect.getsource(__import__(X23DualYRenderer.__module__, fromlist=["*"]))
    assert "plotagent.rendering" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source
