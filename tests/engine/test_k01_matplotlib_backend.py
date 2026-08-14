from __future__ import annotations

import inspect
import warnings
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
from plotagent.engine.backends.matplotlib import K01LineRenderer, MatplotlibBackend
from plotagent.engine.profiles import K01_LINE_PROFILE
from plotagent.engine.service import EngineCatalog
from plotagent.storage.project import ProjectStore

HASH = "f" * 64


class Provider:
    def materialize(self, data, field_ids):
        columns = {
            "field:time": EngineColumn(
                field=EngineField(
                    field_id="field:time",
                    name="Time",
                    logical_type="numeric",
                    unit_label="s",
                ),
                values=(1.0, 2.0, 3.0),
            ),
            "field:signal": EngineColumn(
                field=EngineField(
                    field_id="field:signal",
                    name="Signal",
                    logical_type="numeric",
                    unit_label="a.u.",
                ),
                values=(2.0, 4.0, 8.0),
            ),
        }
        return EngineDataView(
            data=data,
            row_ids=("row:1", "row:2", "row:3"),
            columns=tuple(columns[field_id] for field_id in field_ids),
        )


def _create() -> CreatePlot:
    return CreatePlot(
        action_id="action:create",
        plot_id="plot:line-demo",
        profile_id="K01",
        data=EngineDataRef(
            kind="source",
            dataset_id="dataset.demo",
            version=1,
            content_hash=HASH,
        ),
        bindings=(
            FieldBinding(role="x", field_id="field:time"),
            FieldBinding(role="y", field_id="field:signal"),
        ),
    )


def test_k01_renders_and_replays_public_actions_without_legacy_resolver(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:k01") as project:
        backend = MatplotlibBackend(tmp_path / "artifacts", (K01LineRenderer(),))
        runtime = PlotEngineRuntime(
            PlotEngineService(
                EngineCatalog((K01_LINE_PROFILE,)),
                PlotDocumentRepository(project),
            ),
            Provider(),
            (backend,),
        )
        runtime.execute(_create())
        runtime.execute(
            SetTitle(
                action_id="action:title",
                target="plot:line-demo",
                expected_plot_version=1,
                text="Temperature response",
            )
        )
        runtime.execute(
            SetAxis(
                action_id="action:y-log",
                target="axis:line-demo.y",
                expected_plot_version=2,
                scale="log10",
            )
        )
        runtime.execute(
            SetSeriesStyle(
                action_id="action:style",
                target="series:line-demo.primary",
                expected_plot_version=3,
                color="#AA2200",
                line_width_pt=2.0,
            )
        )
        result = runtime.execute(
            SetLegend(
                action_id="action:legend",
                target="legend:line-demo.main",
                expected_plot_version=4,
                visible=True,
            )
        )

        version_dir = tmp_path / "artifacts" / "line-demo" / "v5"
        assert (version_dir / "preview.png").stat().st_size > 1_000
        assert (version_dir / "preview.svg").stat().st_size > 1_000
        readback = backend.readback(result.document)
        assert readback.document.plot_version == 5
        assert {item.semantic_id for item in readback.objects} >= {
            "axis:line-demo.y",
            "series:line-demo.primary",
            "legend:line-demo.main",
        }
        exported = backend.export(result.document, tmp_path / "out.png", "png")
        assert exported.artifact_size == (tmp_path / "out.png").stat().st_size


def test_k01_backend_source_does_not_import_legacy_rendering() -> None:
    source = inspect.getsource(__import__(K01LineRenderer.__module__, fromlist=["*"]))
    assert "plotagent.rendering" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source


def test_k01_backend_uses_a_cjk_capable_font_for_title_and_field_names(
    tmp_path: Path,
) -> None:
    class ChineseProvider:
        def materialize(self, data, field_ids):
            columns = {
                "field:time": EngineColumn(
                    field=EngineField(
                        field_id="field:time",
                        name="时间",
                        logical_type="numeric",
                        unit_label="秒",
                    ),
                    values=(1.0, 2.0, 3.0),
                ),
                "field:signal": EngineColumn(
                    field=EngineField(
                        field_id="field:signal",
                        name="响应",
                        logical_type="numeric",
                        unit_label="毫伏",
                    ),
                    values=(2.0, 4.0, 8.0),
                ),
            }
            return EngineDataView(
                data=data,
                row_ids=("row:1", "row:2", "row:3"),
                columns=tuple(columns[field_id] for field_id in field_ids),
            )

    with ProjectStore.create(tmp_path / "project", project_id="project:k01-cjk") as project:
        backend = MatplotlibBackend(tmp_path / "artifacts", (K01LineRenderer(),))
        runtime = PlotEngineRuntime(
            PlotEngineService(
                EngineCatalog((K01_LINE_PROFILE,)),
                PlotDocumentRepository(project),
            ),
            ChineseProvider(),
            (backend,),
        )
        runtime.execute(_create())
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = runtime.execute(
                SetTitle(
                    action_id="action:title-cjk",
                    target="plot:line-demo",
                    expected_plot_version=1,
                    text="中文标题：温度响应",
                )
            )

        assert not [warning for warning in caught if "missing from font" in str(warning.message)]
        version_dir = tmp_path / "artifacts" / "line-demo" / "v2"
        assert (version_dir / "preview.png").stat().st_size > 1_000
        svg = (version_dir / "preview.svg").read_text(encoding="utf-8")
        assert "<!-- 中文标题：温度响应 -->" in svg
        assert backend.readback(result.document).document.plot_version == 2
