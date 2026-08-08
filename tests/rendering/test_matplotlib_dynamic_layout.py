from __future__ import annotations

import numpy as np
import pytest
from matplotlib.legend import Legend

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
