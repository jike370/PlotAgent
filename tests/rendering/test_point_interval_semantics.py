from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.container import ErrorbarContainer

from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from plotagent.rendering.matplotlib.adapter import MatplotlibRenderer
from tests.rendering.fixture_factory import resolve_chart


def test_point_interval_resolver_preserves_one_center_per_observation() -> None:
    resolved = resolve_chart("K06")
    layer = resolved.plan.layers[0]
    table = resolved.table_for(layer)
    roles = {
        binding.role: table.column(binding.field_id)
        for binding in layer.field_bindings
    }

    assert layer.geometry == "xy.error"
    assert tuple(roles) == ("x", "center", "x_lower", "x_upper", "lower", "upper")
    assert len(roles["center"]) == table.row_count
    assert all(
        float(lower) <= float(center) <= float(upper)
        for lower, center, upper in zip(
            roles["lower"], roles["center"], roles["upper"], strict=True
        )
    )
    assert all(
        float(lower) <= float(center) <= float(upper)
        for lower, center, upper in zip(
            roles["x_lower"], roles["x"], roles["x_upper"], strict=True
        )
    )
    x_axis = next(axis for axis in resolved.plan.axes if axis.orientation == "x")
    assert x_axis.scale == "linear"
    assert x_axis.minimum <= min(float(value) for value in roles["x_lower"])
    assert x_axis.maximum >= max(float(value) for value in roles["x_upper"])


def test_point_interval_matplotlib_uses_center_markers_and_independent_bars() -> None:
    resolved = resolve_chart("K06")
    row_count = resolved.plan.layers[0].displayed_row_count
    figure = MatplotlibRenderer().build_figure(resolved)
    try:
        containers = [
            item for item in figure.axes[0].containers if isinstance(item, ErrorbarContainer)
        ]
        assert len(containers) == 1
        container = containers[0]
        assert container.has_yerr is True
        assert container.has_xerr is True
        center_markers, cap_lines, interval_collections = container.lines
        assert center_markers.get_marker() not in {"", "None", "none", None}
        assert center_markers.get_linestyle() in {"None", "none", ""}
        assert len(center_markers.get_xdata()) == len(center_markers.get_ydata()) == row_count
        assert len(cap_lines) == 4
        assert all(len(item.get_ydata()) == row_count for item in cap_lines)
        assert len(interval_collections) == 2
        segment_sets = [collection.get_segments() for collection in interval_collections]
        assert all(len(segments) == row_count for segments in segment_sets)
        assert any(
            all(np.isclose(segment[0, 1], segment[1, 1]) for segment in segments)
            for segments in segment_sets
        )
        assert any(
            all(np.isclose(segment[0, 0], segment[1, 0]) for segment in segments)
            for segments in segment_sets
        )
    finally:
        plt.close(figure)


def test_point_interval_origin_plan_has_one_center_symbol_and_no_endpoint_symbols() -> None:
    resolved = resolve_chart("K06")
    export = build_origin_export_spec((resolved,), export_id="export:point-interval")
    plan = compile_origin_plan((resolved,), export)
    plot = plan.graph_objects[0].layers[0].plots[0]

    assert plot.native_kind == "error_bar"
    assert tuple(item.role for item in plot.role_columns) == (
        "x",
        "center",
        "x_lower",
        "x_upper",
        "lower",
        "upper",
    )
    data = next(item for item in plan.data_objects if item.object_id == plot.data_object_id)
    designations = {item.role: item.designation for item in data.columns}
    assert designations["x_lower"] == designations["x_upper"] == "XError"
    assert designations["lower"] == designations["upper"] == "YError"
    assert plot.symbol == resolved.plan.layers[0].symbol
