from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from plotagent.contracts.rendering import OriginDataObject, OriginExportPlan, OriginGraphObject
from plotagent.origin._origin_backend import (
    NativeOriginError,
    _apply_right_y_axis_style,
    _legend_text,
    _read_template_y_axis_style,
)
from plotagent.origin.native import (
    PROJECT_FOLDERS,
    build_native_project,
    inspect_native_project,
    native_primitives,
)
from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from plotagent.origin.validation import expected_validation_report, origin_canonical_hash
from tests.rendering.fixture_factory import resolve_chart


def _plan(chart_id: str) -> OriginExportPlan:
    resolved = resolve_chart(chart_id)
    return compile_origin_plan((resolved,), build_origin_export_spec((resolved,)))


def test_s07_uses_only_fixed_native_legend_sample_tokens() -> None:
    assert _legend_text("graph.S07.0", ["Down", "Not significant", "Up"]) == (
        r"\l(1) Down" "\n" r"\l(2) Not significant" "\n" r"\l(3) Up"
    )
    with pytest.raises(NativeOriginError, match="fixed legend vocabulary"):
        _legend_text("graph.S07.0", ["Down", "user label", "Up"])


def test_nonfixed_legend_labels_do_not_receive_generated_origin_tokens() -> None:
    assert _legend_text("graph.K01.0", ["Series 1", "Series 2"]) == "Series 1\nSeries 2"


@dataclass
class _RecordingBackend:
    plan: OriginExportPlan
    calls: list[tuple[str, str]] = field(default_factory=list)

    def set_plan(self, plan: OriginExportPlan) -> None:
        self.calls.append(("plan", plan.origin_plan_id))

    def ensure_blank(self) -> None:
        self.calls.append(("blank", ""))

    def create_folder(self, name: str) -> None:
        self.calls.append(("folder", name))

    def write_data_object(self, data: OriginDataObject) -> None:
        self.calls.append(("data", data.object_id))

    def write_graph_object(self, graph: OriginGraphObject) -> None:
        self.calls.append(("graph", graph.graph_id))

    def write_manifest(self, plan: OriginExportPlan) -> None:
        self.calls.append(("manifest", plan.origin_plan_id))

    def inspect(self, plan: OriginExportPlan) -> dict[str, object]:
        self.calls.append(("inspect", plan.origin_plan_id))
        return expected_validation_report(plan)

    def save(self, path: str) -> None:
        self.calls.append(("save", path))


@pytest.mark.parametrize(
    "chart_id",
    [
        *(f"K{index:02d}" for index in range(1, 23)),
        "K24",
        "K25",
        "S01",
        "S05",
        "S21",
        "S25",
        "S31",
        "S34",
        "S61",
        "X01",
        "X02",
        "X03",
        "X05",
        "X07",
        "X09",
        "X11",
        "X12",
        "X13",
        "X15",
        "X16",
        "X17",
        "X18",
        "X19",
        "X23",
        "X24",
        "X35",
        "X36",
        "X37",
        "X38",
        "S07",
    ],
)
def test_all_52_plans_normalize_to_fixed_native_primitives(chart_id: str) -> None:
    plan = _plan(chart_id)
    primitives = [
        primitive
        for graph in plan.graph_objects
        for layer in graph.layers
        for plot in layer.plots
        for primitive in native_primitives(plot)
    ]

    assert primitives
    assert {item.plot_type for item in primitives} <= {
        "line",
        "line_symbol",
        "scatter",
        "column",
        "bar",
        "area",
        "fill_area",
        "floating_column",
        "bubble",
        "bubble_color",
        "heatmap",
        "contour",
    }


def test_origin_hash_escapes_unicode_before_cross_process_validation() -> None:
    assert origin_canonical_hash({"title": "温度 Δ–β"}) == (
        "fcf83f29b36c6c84c691a00250cf86abb46840ea47627dd03fac5ac67a427e52"
    )


def test_closed_executor_orders_native_objects_before_validation_and_save() -> None:
    plan = _plan("K25")
    backend = _RecordingBackend(plan)

    report = build_native_project(backend, plan, "temporary.opju")

    assert report == expected_validation_report(plan)
    assert backend.calls[:6] == [
        ("plan", plan.origin_plan_id),
        ("blank", ""),
        *(("folder", folder) for folder in PROJECT_FOLDERS),
    ]
    assert backend.calls[-2:] == [
        ("inspect", plan.origin_plan_id),
        ("save", "temporary.opju"),
    ]


def test_fresh_inspection_rejects_report_drift() -> None:
    plan = _plan("K20")
    backend = _RecordingBackend(plan)
    expected = expected_validation_report(plan)
    expected["raster_objects"] = True
    backend.inspect = lambda unused: expected  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="fresh native Origin report differs"):
        inspect_native_project(backend, plan)


@pytest.mark.parametrize(
    ("chart_id", "transforms", "plot_count"),
    [
        ("K06", {"interval_connector", "direct"}, 4),
        ("K07", {"direct", "band"}, 2),
        ("K13", {"box_outline", "direct"}, 2),
        ("K14", {"violin_polygon"}, 1),
        ("S21", {"forest_interval"}, 1),
    ],
)
def test_interval_distribution_and_band_geometry_is_not_collapsed(
    chart_id: str,
    transforms: set[str],
    plot_count: int,
) -> None:
    plan = _plan(chart_id)
    primitives = [
        primitive
        for graph in plan.graph_objects
        for layer in graph.layers
        for plot in layer.plots
        for primitive in native_primitives(plot)
    ]

    assert {item.transform for item in primitives} == transforms
    assert len(primitives) == plot_count
    if chart_id == "K07":
        assert any(item.plot_type == "fill_area" for item in primitives)


def test_bubble_uses_scatter_with_native_column_modifiers() -> None:
    plan = _plan("K04")
    primitive = native_primitives(plan.graph_objects[0].layers[0].plots[0])[0]

    assert primitive.plot_type == "scatter"
    assert primitive.size_role == "size"
    assert primitive.color_role == "color"


def test_forest_symbol_is_one_weight_sized_scatter_primitive() -> None:
    plan = _plan("S21")
    interval = plan.graph_objects[0].layers[0].plots[0]
    symbol = interval.model_copy(update={"native_kind": "forest_symbol"})

    primitives = native_primitives(symbol)

    assert len(primitives) == 1
    assert primitives[0].plot_type == "scatter"
    assert primitives[0].x_role == "effect"
    assert primitives[0].y_role == "label"
    assert primitives[0].size_role == "weight"
    assert primitives[0].transform == "forest_symbol"


def test_lollipop_uses_one_native_symbol_plot_with_frame_drop_lines() -> None:
    plan = _plan("X02")
    plot = plan.graph_objects[0].layers[0].plots[0]
    primitive = native_primitives(plot)[0]

    assert plot.native_kind == "lollipop"
    assert primitive.plot_type == "scatter"
    assert primitive.x_role == "x"
    assert primitive.y_role == "y"
    assert primitive.transform == "lollipop_drop"


def test_right_y_axis_weight_is_copied_from_qualified_template_left_axis() -> None:
    class FakeLabel:
        def __init__(self, bold: float) -> None:
            self.values = {"font.bold": bold}

        def get_float(self, key: str) -> float:
            return self.values[key]

        def set_int(self, key: str, value: int) -> None:
            self.values[key] = float(value)

    class FakeLayer:
        def __init__(self) -> None:
            self.values = {
                "y.thickness": 0.49,
                "y.tickthickness": float("nan"),
                "y.mtickthickness": float("nan"),
                "y.label.bold": 0.0,
                "tickW": 0.49,
            }
            self.labels = {"yl": FakeLabel(1.0), "yr": FakeLabel(0.0)}

        def get_float(self, key: str) -> float:
            return self.values[key]

        def set_float(self, key: str, value: float) -> None:
            self.values[key] = value

        def set_int(self, key: str, value: int) -> None:
            self.values[key] = float(value)

        def label(self, key: str) -> FakeLabel:
            return self.labels[key]

    layer = FakeLayer()
    style = _read_template_y_axis_style(layer)
    _apply_right_y_axis_style(layer, style)

    assert layer.values["y2.thickness"] == 0.49
    assert layer.values["y2.tickthickness"] == 0.49
    assert layer.values["y2.mtickthickness"] == 0.49
    assert layer.values["y2.label.bold"] == 0.0
    assert layer.labels["yr"].values["font.bold"] == 1.0


@pytest.mark.parametrize("chart_id", ["K08", "K09", "K15"])
def test_non_stacked_bars_use_visible_native_columns(chart_id: str) -> None:
    plan = _plan(chart_id)
    primitives = [
        primitive
        for layer in plan.graph_objects[0].layers
        for plot in layer.plots
        for primitive in native_primitives(plot)
    ]

    assert primitives[0].plot_type == "column"
    assert primitives[0].y_role == "height"
    assert primitives[0].y2_role is None


@pytest.mark.parametrize("chart_id", ["X09", "X35"])
def test_floating_columns_use_native_xyy_rectangles(
    chart_id: str,
) -> None:
    plan = _plan(chart_id)
    layer = plan.graph_objects[0].layers[0]
    plot = layer.plots[0]
    primitive = native_primitives(plot)[0]
    assert primitive.plot_type == "floating_column"
    assert primitive.transform == "direct"
    assert primitive.y_role == "bottom"
    assert primitive.y2_role == "top"
    assert primitive.bar_width_role == "width"
