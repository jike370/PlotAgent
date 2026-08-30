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
from plotagent.engine.backends.matplotlib import K09GroupedColumnRenderer, MatplotlibBackend
from plotagent.engine.profile_data import category_series_grid

HASH = "9" * 64
CATEGORIES = ("FAPbI3", "MAPbI3", "3AMP", "3AMPY", "3AP", "BA", "PEA")
SERIES = (
    ("Absorption energy", (0.0, 0.0, 2.784, 2.988, 3.135, 2.968, 2.498)),
    ("Defect formation energy", (1.422, 1.075, 3.574, 3.791, 3.812, 3.716, 3.584)),
    ("Energy barrier", (0.737, 0.688, 0.907, 0.966, 1.467, 1.293, 0.861)),
)


def _real_fig1c_case() -> tuple[PlotDocument, tuple[object, ...], EngineDataView]:
    rows = tuple(
        (category, series_name, series_values[category_index])
        for category_index, category in enumerate(CATEGORIES)
        for series_name, series_values in SERIES
    )
    data = EngineDataRef(
        kind="prepared",
        dataset_id="dataset.k09-fig1c",
        version=1,
        content_hash=HASH,
    )
    bindings = (
        FieldBinding(role="category", field_id="field:cations"),
        FieldBinding(role="group", field_id="field:energy-type"),
        FieldBinding(role="value", field_id="field:energy-ev"),
    )
    create = CreatePlot(
        action_id="action:create-k09-fig1c",
        plot_id="plot:k09-fig1c",
        profile_id="K09",
        data=data,
        bindings=bindings,
    )
    visual_actions = (
        SetAxis(
            action_id="action:k09-fig1c-x-axis",
            target="axis:k09-fig1c.x",
            expected_plot_version=1,
            label="Cations",
            title_font_size_pt=10,
            tick_font_size_pt=9,
            major_grid_visible=False,
            minor_grid_visible=False,
        ),
        SetAxis(
            action_id="action:k09-fig1c-y-axis",
            target="axis:k09-fig1c.y",
            expected_plot_version=2,
            label="Energy (eV)",
            bounds_mode="fixed",
            minimum=0,
            maximum=4.4,
            major_tick_step=1,
            title_font_size_pt=10,
            tick_font_size_pt=9,
            major_grid_visible=False,
            minor_grid_visible=False,
        ),
        *tuple(
            SetSeriesStyle(
                action_id=f"action:k09-fig1c-series-{index}",
                target=f"series:k09-fig1c.group_{index}",
                expected_plot_version=index + 2,
                fill_color=color,
            )
            for index, color in enumerate(("#5B7DB6", "#0BA4A0", "#FF5757"), start=1)
        ),
        SetLegend(
            action_id="action:k09-fig1c-legend",
            target="legend:k09-fig1c.main",
            expected_plot_version=6,
            visible=True,
            anchor="inside_top_left",
            columns=3,
            font_size_pt=8,
            frame_visible=False,
        ),
        SetCanvas(
            action_id="action:k09-fig1c-canvas",
            target="plot:k09-fig1c",
            expected_plot_version=7,
            width_mm=180,
            height_mm=100,
        ),
    )
    actions = (create, *visual_actions)
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=len(actions),
        parent_version=len(actions) - 1,
        profile_id="K09",
        data=data,
        bindings=bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:{index}" for index in range(len(rows))),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:cations",
                    name="Cations",
                    logical_type="categorical",
                ),
                values=tuple(row[0] for row in rows),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:energy-type",
                    name="Energy type",
                    logical_type="categorical",
                ),
                values=tuple(row[1] for row in rows),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:energy-ev",
                    name="Energy (eV)",
                    logical_type="numeric",
                ),
                values=tuple(row[2] for row in rows),
            ),
        ),
    )
    return document, actions, view


def test_k09_real_fig1c_preserves_order_zeros_and_all_values() -> None:
    document, _, view = _real_fig1c_case()
    grid = category_series_grid(document, view, profile_id="K09")

    assert grid.category_labels == CATEGORIES
    assert grid.series_labels == tuple(item[0] for item in SERIES)
    assert grid.values[0] == pytest.approx((0.0, 1.422, 0.737))
    assert grid.values[1] == pytest.approx((0.0, 1.075, 0.688))
    assert len(grid.values) == 7
    assert all(len(row) == 3 for row in grid.values)


def test_k09_real_fig1c_shared_visuals_render_expected_svg(tmp_path: Path) -> None:
    document, actions, view = _real_fig1c_case()
    backend = MatplotlibBackend(tmp_path, (K09GroupedColumnRenderer(),))

    change = backend.stage(document, actions, EngineRenderSource(data=view))
    change.publish()

    output_dir = tmp_path / "k09-fig1c" / f"v{document.plot_version}"
    svg_path = output_dir / "preview.svg"
    svg = svg_path.read_text(encoding="utf-8")
    root = ElementTree.parse(svg_path).getroot()

    assert (output_dir / "preview.png").stat().st_size > 10_000
    assert root.attrib["width"].endswith("pt")
    assert root.attrib["height"].endswith("pt")
    assert float(root.attrib["width"].removesuffix("pt")) == pytest.approx(
        180 / 25.4 * 72,
        abs=0.02,
    )
    assert float(root.attrib["height"].removesuffix("pt")) == pytest.approx(
        100 / 25.4 * 72,
        abs=0.02,
    )
    for text in (*CATEGORIES, *(item[0] for item in SERIES), "Energy (eV)", "Cations"):
        assert text in svg
    for color in ("#5b7db6", "#0ba4a0", "#ff5757"):
        assert color in svg.lower()
