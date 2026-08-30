from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

import pytest

from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    EngineRenderSource,
    FieldBinding,
    PlotDocument,
    SetAxis,
    SetCanvas,
    SetLegend,
    SetSeriesStyle,
)
from plotagent.engine.backends.matplotlib import K08ColumnRenderer, MatplotlibBackend

HASH = "8" * 64
SITES = tuple(range(13))
FRACTIONS = (
    0.33852964,
    0.30398383,
    0.19563125,
    0.09334103,
    0.03916474,
    0.01751347,
    0.00750577,
    0.00240570,
    0.00115473,
    0.00038491,
    0.000096228,
    0.00019246,
    0.000096228,
)


def _real_fig2f_case() -> tuple[PlotDocument, tuple[object, ...], EngineDataView]:
    data = EngineDataRef(
        kind="prepared",
        dataset_id="dataset.k08-fig2f",
        version=1,
        content_hash=HASH,
    )
    bindings = (
        FieldBinding(role="category", field_id="field:m6a-sites"),
        FieldBinding(role="value", field_id="field:fraction-transcripts"),
    )
    create = CreatePlot(
        action_id="action:create-k08-fig2f",
        plot_id="plot:k08-fig2f",
        profile_id="K08",
        data=data,
        bindings=bindings,
    )
    actions = (
        create,
        SetAxis(
            action_id="action:k08-fig2f-x-axis",
            target="axis:k08-fig2f.x",
            expected_plot_version=1,
            label="m6A sites",
            tick_rotation_deg=90,
            title_font_size_pt=10,
            tick_font_size_pt=9,
            major_grid_visible=False,
            minor_grid_visible=False,
        ),
        SetAxis(
            action_id="action:k08-fig2f-y-axis",
            target="axis:k08-fig2f.y",
            expected_plot_version=2,
            label="Fraction of transcripts",
            bounds_mode="fixed",
            minimum=0,
            maximum=0.4,
            major_tick_step=0.1,
            title_font_size_pt=10,
            tick_font_size_pt=9,
            major_grid_visible=False,
            minor_grid_visible=False,
        ),
        SetSeriesStyle(
            action_id="action:k08-fig2f-series",
            target="series:k08-fig2f.primary",
            expected_plot_version=3,
            fill_color="#8C8C8C",
            fill_stroke_color="#333333",
            fill_stroke_width_pt=0.8,
        ),
        SetLegend(
            action_id="action:k08-fig2f-legend",
            target="legend:k08-fig2f.main",
            expected_plot_version=4,
            visible=False,
        ),
        SetCanvas(
            action_id="action:k08-fig2f-canvas",
            target="plot:k08-fig2f",
            expected_plot_version=5,
            width_mm=75,
            height_mm=100,
        ),
    )
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=len(actions),
        parent_version=len(actions) - 1,
        profile_id="K08",
        data=data,
        bindings=bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:{index}" for index in SITES),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:m6a-sites",
                    name="m6A_sites",
                    logical_type="numeric",
                ),
                values=SITES,
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:fraction-transcripts",
                    name="fraction_transcripts",
                    logical_type="numeric",
                ),
                values=FRACTIONS,
            ),
        ),
    )
    return document, actions, view


def test_k08_real_fig2f_keeps_all_numeric_categories_and_published_values() -> None:
    document, _, view = _real_fig2f_case()

    assert document.bindings[0].role == "category"
    assert view.columns[0].field.logical_type == "numeric"
    assert view.columns[0].values == SITES
    assert view.columns[1].values == FRACTIONS
    assert sum(FRACTIONS) == pytest.approx(1.0, abs=2e-8)
    assert FRACTIONS[10:] == pytest.approx((0.000096228, 0.00019246, 0.000096228))


def test_k08_real_fig2f_shared_visuals_render_expected_svg(tmp_path: Path) -> None:
    document, actions, view = _real_fig2f_case()
    backend = MatplotlibBackend(tmp_path, (K08ColumnRenderer(),))

    change = backend.stage(document, actions, EngineRenderSource(data=view))
    change.publish()

    output_dir = tmp_path / "k08-fig2f" / f"v{document.plot_version}"
    svg_path = output_dir / "preview.svg"
    svg = svg_path.read_text(encoding="utf-8")
    root = ElementTree.parse(svg_path).getroot()

    assert (output_dir / "preview.png").stat().st_size > 8_000
    assert float(root.attrib["width"].removesuffix("pt")) == pytest.approx(
        75 / 25.4 * 72,
        abs=0.02,
    )
    assert float(root.attrib["height"].removesuffix("pt")) == pytest.approx(
        100 / 25.4 * 72,
        abs=0.02,
    )
    assert "m6A sites" in svg
    assert "Fraction of transcripts" in svg
    for category in SITES:
        assert f">{category}<" in svg or f"<!-- {category} -->" in svg
    assert "#8c8c8c" in svg.lower()
    assert "#333333" in svg.lower()
    assert "rotate(-90" in svg.lower() or "rotate(90" in svg.lower()
