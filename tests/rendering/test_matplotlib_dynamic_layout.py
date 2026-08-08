from __future__ import annotations

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.legend import Legend

from plotagent.contracts.base import PhysicalLength
from plotagent.contracts.plots import SafeRichText, SafeTextNode
from plotagent.rendering import ResolvedPlot
from plotagent.rendering.matplotlib.adapter import MatplotlibRenderer
from tests.rendering.fixture_factory import resolve_chart


def _text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


def test_bubble_size_key_is_derived_from_resolved_size_encoding() -> None:
    figure = MatplotlibRenderer().build_figure(resolve_chart("K04"))
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()

    size_legend = next(
        item
        for item in figure.findobj(match=Legend)
        if item.get_title().get_text() == "Size"
    )
    labels = tuple(float(item.get_text()) for item in size_legend.get_texts())
    marker_sizes = tuple(float(item.get_markersize()) for item in size_legend.legend_handles)

    assert labels == tuple(sorted(labels))
    assert len(labels) >= 2
    assert marker_sizes == tuple(sorted(marker_sizes))
    assert size_legend.get_window_extent(renderer).x1 <= figure.bbox.x1 - 7.5


def test_point_colliding_legend_moves_outside_without_covering_observations() -> None:
    figure = MatplotlibRenderer().build_figure(resolve_chart("K12"))
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    axis = figure.axes[0]
    legend = axis.get_legend()

    assert legend is not None
    legend_box = legend.get_window_extent(renderer)
    assert legend_box.x0 >= axis.get_window_extent(renderer).x1
    assert legend_box.x1 <= figure.bbox.x1 - 7.5
    for collection in axis.collections:
        offsets = np.asarray(collection.get_offsets())
        display = collection.get_offset_transform().transform(offsets)
        assert not np.any(
            (display[:, 0] >= legend_box.x0)
            & (display[:, 0] <= legend_box.x1)
            & (display[:, 1] >= legend_box.y0)
            & (display[:, 1] <= legend_box.y1)
        )


def test_line_colliding_legend_moves_outside_without_covering_curves() -> None:
    figure = MatplotlibRenderer().build_figure(resolve_chart("X38"))
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    axis = figure.axes[0]
    legend = axis.get_legend()

    assert legend is not None
    legend_box = legend.get_window_extent(renderer)
    assert legend_box.x0 >= axis.get_window_extent(renderer).x1
    assert legend_box.x1 <= figure.bbox.x1 - 7.5
    for line in axis.lines:
        display = line.get_transform().transform(line.get_path().vertices)
        assert not np.any(
            (display[:, 0] >= legend_box.x0)
            & (display[:, 0] <= legend_box.x1)
            & (display[:, 1] >= legend_box.y0)
            & (display[:, 1] <= legend_box.y1)
        )


def test_twin_y_inside_legend_does_not_trigger_destructive_auto_outside_layout() -> None:
    figure = MatplotlibRenderer().build_figure(resolve_chart("X36"))
    figure.canvas.draw()
    axes = figure.axes[:2]
    legend = next(axis.get_legend() for axis in axes if axis.get_legend() is not None)

    assert getattr(legend, "_plotagent_outside_right", False) is False
    assert axes[0].get_position().width > 0.65


def test_long_categorical_tick_labels_are_fitted_inside_fixed_canvas() -> None:
    resolved = resolve_chart("K12")
    replacements = (
        "Ground beef and veal products",
        "Processed ham and pork products",
    )
    axes = tuple(
        axis.model_copy(
            update={
                "ticks": tuple(
                    tick.model_copy(update={"label": _text(label)})
                    for tick, label in zip(axis.ticks, replacements, strict=True)
                )
            }
        )
        if axis.orientation == "x"
        else axis
        for axis in resolved.plan.axes
    )
    long_labels = ResolvedPlot.create(
        resolved.plan.model_copy(update={"axes": axes}),
        resolved.tables,
    )

    figure = MatplotlibRenderer().build_figure(long_labels)
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    axis = figure.axes[0]
    bounded_text = (*axis.get_xticklabels(), axis.xaxis.label)

    assert all(item.get_rotation() == pytest.approx(30.0) for item in axis.get_xticklabels())
    assert min(item.get_window_extent(renderer).y0 for item in bounded_text) >= 7.5
    assert (figure.bbox.width, figure.bbox.height) == pytest.approx((1051.0, 709.0))


def test_colorbar_tick_labels_are_fitted_inside_fixed_canvas() -> None:
    figure = MatplotlibRenderer().build_figure(resolve_chart("K22"))
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    colorbar_axis = figure.axes[1]

    rightmost = max(
        item.get_window_extent(renderer).x1 for item in colorbar_axis.get_yticklabels()
    )
    assert rightmost <= figure.bbox.x1 - 7.5
    assert (figure.bbox.width, figure.bbox.height) == pytest.approx((1051.0, 709.0))


def test_long_y_ticks_and_colorbar_remain_inside_and_do_not_overlap_data_axis() -> None:
    resolved = resolve_chart("K20")
    replacements = (
        "Long scientific row label OTU1091",
        "Long scientific row label OTU434",
    )
    axes = tuple(
        axis.model_copy(
            update={
                "ticks": tuple(
                    tick.model_copy(update={"label": _text(label)})
                    for tick, label in zip(axis.ticks, replacements, strict=True)
                )
            }
        )
        if axis.orientation == "y"
        else axis
        for axis in resolved.plan.axes
    )
    fonts = tuple(
        font.model_copy(update={"size": PhysicalLength(value=9.5, unit="pt")})
        for font in resolved.plan.fonts
    )
    long_labels = ResolvedPlot.create(
        resolved.plan.model_copy(
            update={
                "title": _text("Visual qualification · matrix with long row labels"),
                "axes": axes,
                "fonts": fonts,
                "colorbar": resolved.plan.colorbar.model_copy(
                    update={"title": _text("Value")}
                ),
            }
        ),
        resolved.tables,
    )

    figure = MatplotlibRenderer().build_figure(long_labels)
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    data_axis, colorbar_axis = figure.axes
    left_artists = (*data_axis.get_yticklabels(), data_axis.yaxis.label)
    right_artists = (*colorbar_axis.get_yticklabels(), colorbar_axis.yaxis.label)
    title_bounds = data_axis.title.get_window_extent(renderer)

    assert min(item.get_window_extent(renderer).x0 for item in left_artists) >= 7.5
    assert max(item.get_window_extent(renderer).x1 for item in right_artists) <= (
        figure.bbox.x1 - 7.5
    )
    assert data_axis.get_window_extent(renderer).x1 <= (
        colorbar_axis.get_window_extent(renderer).x0 - 7.5
    )
    assert title_bounds.x0 >= 7.5
    assert title_bounds.x1 <= figure.bbox.x1 - 7.5
    assert title_bounds.y1 <= figure.bbox.y1 - 7.5
    pixels = np.asarray(figure.canvas.buffer_rgba())[:, :, :3]
    nonwhite_y, nonwhite_x = np.nonzero(np.any(pixels < 250, axis=2))
    assert int(nonwhite_x.min()) >= 7
    assert int(nonwhite_x.max()) <= int(figure.bbox.x1) - 8
    assert int(nonwhite_y.min()) >= 7
    assert int(nonwhite_y.max()) <= int(figure.bbox.y1) - 8


def test_long_plot_title_is_fitted_inside_fixed_canvas_without_losing_text() -> None:
    resolved = resolve_chart("K06")
    title = "Visual qualification · K06 · Point estimate with error bars"
    with_long_title = ResolvedPlot.create(
        resolved.plan.model_copy(update={"title": _text(title)}),
        resolved.tables,
    )

    figure = MatplotlibRenderer().build_figure(with_long_title)
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    rendered_title = figure.axes[0].title
    bounds = rendered_title.get_window_extent(renderer)

    assert rendered_title.get_text().replace("\n", " ") == title
    assert bounds.x0 >= 7.5
    assert bounds.x1 <= figure.bbox.x1 - 7.5
    assert bounds.y1 <= figure.bbox.y1 - 7.5
    assert rendered_title.get_fontsize() <= resolved.plan.fonts[0].size.value


def test_resolved_annotation_color_is_consumed_by_matplotlib() -> None:
    figure = MatplotlibRenderer().build_figure(resolve_chart("S61"))
    rendered = {
        item.get_text(): (item.get_color(), item.get_horizontalalignment())
        for item in figure.axes[0].texts
    }

    assert rendered == {
        "12": ("#000000", "center"),
        "2": ("#FFFFFF", "center"),
        "1": ("#FFFFFF", "center"),
        "10": ("#000000", "center"),
    }


def test_survival_risk_group_label_does_not_touch_the_first_count() -> None:
    base_layer = resolve_chart("S01").plan.layers[0]
    risk_layer = base_layer.model_copy(
        update={
            "geometry": "special.risk_table",
            "label": _text("Treatment"),
            "z_order": 2,
        }
    )
    figure = Figure(figsize=(6, 2))
    FigureCanvasAgg(figure)
    axis = figure.subplots()

    MatplotlibRenderer()._draw_special(
        axis,
        risk_layer,
        {"time": (0.0, 3.0, 6.0), "risk_count": (89, 80, 71)},
    )
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    group_label = next(item for item in axis.texts if item.get_text() == "Treatment")
    first_count = next(item for item in axis.texts if item.get_text() == "89")

    assert group_label.get_position()[0] < 0
    assert group_label.get_window_extent(renderer).x1 < first_count.get_window_extent(renderer).x0
