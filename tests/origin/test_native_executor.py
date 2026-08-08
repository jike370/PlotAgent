from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import pytest

from plotagent.contracts.base import ColorValue
from plotagent.contracts.plots import BarAreaEditSpec, SpecialistEditSpec
from plotagent.contracts.rendering import (
    OriginDataObject,
    OriginExportPlan,
    OriginGraphObject,
    ResolvedAnnotation,
)
from plotagent.origin._origin_backend import (
    NativeOriginError,
    _apply_right_y_axis_style,
    _bar_width_ratio,
    _frame_page_bounds,
    _legend_labels,
    _legend_text,
    _native_layer_frame,
    _place_inside_legend,
    _place_page_color_scale,
    _place_page_title,
    _primitive_color,
    _read_template_y_axis_style,
    _style_annotation_label,
    _tick_label_rotation,
)
from plotagent.origin.native import (
    PROJECT_FOLDERS,
    build_native_project,
    inspect_native_project,
    materialize_primitive,
    native_primitives,
    physical_plot_count,
)
from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from plotagent.origin.validation import expected_validation_report, origin_canonical_hash
from plotagent.rendering import PlotResolver, RenderDataStore, RenderTable
from tests.rendering.fixture_factory import build_plot_and_store, resolve_chart


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


def test_duplicate_physical_styles_share_one_origin_legend_row() -> None:
    graph = _plan("K05").graph_objects[0]
    layer = graph.layers[0]
    base = layer.plots[0]
    graph = graph.model_copy(
        update={
            "layers": (
                layer.model_copy(
                    update={
                        "plots": (
                            base.model_copy(update={"label": "Y1"}),
                            base.model_copy(update={"label": "Y1"}),
                            base.model_copy(update={"label": "Y1 interval"}),
                        )
                    }
                ),
            )
        }
    )

    assert _legend_labels(graph) == ["Y1", "Y1 interval"]


def _grouped_bar_plan(group_count: int, width_ratio: float) -> OriginExportPlan:
    plot, unused_store = build_plot_and_store("K09")
    del unused_store
    categories: list[str] = []
    groups: list[str] = []
    values: list[float] = []
    for category in ("A", "B"):
        for group_index in range(group_count):
            categories.append(category)
            groups.append(f"G{group_index + 1}")
            values.append(float(group_index + 1))
    fields = plot.series[0].data.role_fields
    table = RenderTable.from_columns(
        dict(
            zip(
                fields,
                (tuple(categories), tuple(groups), tuple(values)),
                strict=True,
            )
        )
    )
    content_hash = hashlib.sha256(f"K09:{group_count}:{width_ratio}".encode()).hexdigest()
    calculation_ref = plot.plot_calculation_refs[0].model_copy(
        update={"content_hash": content_hash}
    )
    series_data = plot.series[0].data.model_copy(
        update={"calculation_result_ref": calculation_ref}
    )
    specialist = SpecialistEditSpec(
        bar_area=BarAreaEditSpec(width_ratio=width_ratio)
    )
    edited = plot.model_copy(
        update={
            "plot_calculation_refs": (calculation_ref,),
            "series": (plot.series[0].model_copy(update={"data": series_data}),),
            "specialist": specialist,
        }
    )
    resolved = PlotResolver().resolve(edited, RenderDataStore({content_hash: table}))
    return compile_origin_plan((resolved,), build_origin_export_spec((resolved,)))


@pytest.mark.parametrize("group_count", [1, 2, 3, 5])
@pytest.mark.parametrize("width_ratio", [0.8, 0.65])
def test_grouped_bar_uses_resolved_per_bar_width_and_offsets_without_overlap(
    group_count: int,
    width_ratio: float,
) -> None:
    plan = _grouped_bar_plan(group_count, width_ratio)
    graph_layer = plan.graph_objects[0].layers[0]
    intervals: list[tuple[float, float]] = []
    for plot in graph_layer.plots:
        primitive = native_primitives(plot)[0]
        data = next(item for item in plan.data_objects if item.object_id == plot.data_object_id)
        width = _bar_width_ratio(data, plot, primitive)
        assert width == pytest.approx(width_ratio / group_count)
        x_field_id = next(item.field_id for item in plot.role_columns if item.role == "x")
        x_column = next(item for item in data.columns if item.field_id == x_field_id)
        center = float(x_column.values[0])
        intervals.append((center - width / 2, center + width / 2))

    intervals.sort()
    assert all(
        left_interval[1] <= right_interval[0] + 1e-12
        for left_interval, right_interval in zip(intervals, intervals[1:], strict=False)
    )


def test_fill_area_uses_typed_uncertainty_color_and_band_alpha() -> None:
    plan = _plan("K07")
    band = plan.graph_objects[0].layers[0].plots[1].model_copy(
        update={
            "uncertainty_color": ColorValue(value="#7B61A8"),
            "band_alpha": 0.32,
        }
    )
    primitive = native_primitives(band)[0]

    assert primitive.plot_type == "fill_area"
    assert _primitive_color(band, primitive) == "#7B61A8"
    assert round((1 - band.band_alpha) * 100) == 68


def test_fill_area_materializes_as_two_native_lines() -> None:
    primitive = native_primitives(_plan("K07").graph_objects[0].layers[0].plots[1])[0]

    assert primitive.plot_type == "fill_area"
    assert physical_plot_count(primitive) == 2


def test_x09_origin_plan_suppresses_internal_interval_boundary_legend() -> None:
    graph = _plan("X09").graph_objects[0]

    assert graph.legend_visible is False


class _FakePageObject:
    def __init__(self, **values: float) -> None:
        self.values = dict(values)

    def get_float(self, key: str) -> float:
        return self.values[key]

    def get_int(self, key: str) -> int:
        return int(self.values[key])

    def set_float(self, key: str, value: float) -> None:
        self.values[key] = value

    def set_int(self, key: str, value: int) -> None:
        self.values[key] = float(value)


class _ScalingFakePageObject(_FakePageObject):
    def set_float(self, key: str, value: float) -> None:
        if key == "fsize" and "fsize" in self.values:
            ratio = value / self.values["fsize"]
            self.values["width"] *= ratio
            self.values["height"] *= ratio
        super().set_float(key, value)


@pytest.mark.parametrize("chart_id", ["X01", "K05", "S05", "S25", "X03"])
def test_shared_title_layout_is_page_attached_and_above_plot_frame(chart_id: str) -> None:
    graph_plan = _plan(chart_id).graph_objects[0].model_copy(
        update={"title": f"{chart_id} title"}
    )
    page = _FakePageObject(width=890.0, height=600.0)
    title = _FakePageObject(width=140.0, height=24.0)

    _place_page_title(page, graph_plan, graph_plan.layers[0], title)

    layer_top = (
        graph_plan.layers[0].top_mm / graph_plan.page_height_mm * page.get_float("height")
    )
    assert title.get_int("attach") == 1
    left = title.get_float("x1") * page.get_float("width")
    top = title.get_float("y1") * page.get_float("height")
    assert left >= 0
    assert left + title.get_float("width") <= page.get_float("width")
    assert top + title.get_float("height") <= layer_top - 1.0


def test_s05_legend_is_page_attached_and_clamped_inside_canvas() -> None:
    graph_plan = _plan("S05").graph_objects[0].model_copy(
        update={"legend_visible": True, "legend_anchor_x": 1.0, "legend_anchor_y": 1.0}
    )
    page = _FakePageObject(width=890.0, height=600.0)
    legend = _FakePageObject(width=260.0, height=90.0, fillcolor=0.0)

    _place_inside_legend(page, graph_plan, graph_plan.layers[0], legend)

    assert legend.get_int("attach") == 1
    left = legend.get_float("x1") * page.get_float("width")
    top = legend.get_float("y1") * page.get_float("height")
    assert left >= 0
    assert left + legend.get_float("width") <= page.get_float("width")
    assert top >= 0
    assert top + legend.get_float("height") <= page.get_float("height")


@pytest.mark.parametrize("chart_id", ["X05", "X23", "X35", "X36", "X38"])
def test_legend_charts_reserve_a_right_gutter_outside_the_data_frame(chart_id: str) -> None:
    graph_plan = _plan(chart_id).graph_objects[0]
    frame = _native_layer_frame(graph_plan, graph_plan.layers[0])

    assert frame.width_mm < graph_plan.layers[0].width_mm

    page = _FakePageObject(width=2102.0, height=1417.0)
    legend = _FakePageObject(width=180.0, height=143.0, fillcolor=0.0)
    _place_inside_legend(page, graph_plan, graph_plan.layers[0], legend)
    frame_left, _, frame_width, _ = _frame_page_bounds(
        page, graph_plan, graph_plan.layers[0]
    )
    legend_left = legend.get_float("x1") * page.get_float("width")
    assert legend_left > frame_left + frame_width


@pytest.mark.parametrize("chart_id", ["K04", "K20", "K22"])
def test_color_scale_charts_reserve_and_use_a_page_right_gutter(chart_id: str) -> None:
    graph_plan = _plan(chart_id).graph_objects[0]
    frame = _native_layer_frame(graph_plan, graph_plan.layers[0])
    assert frame.width_mm < graph_plan.layers[0].width_mm

    page = _FakePageObject(width=2102.0, height=1417.0)
    scale = _FakePageObject(width=420.0, height=991.0)
    _place_page_color_scale(page, graph_plan, graph_plan.layers[0], scale)
    frame_left, _, frame_width, _ = _frame_page_bounds(
        page, graph_plan, graph_plan.layers[0]
    )
    scale_left = scale.get_float("x1") * page.get_float("width")
    assert scale.get_int("attach") == 1
    assert scale_left > frame_left + frame_width
    assert scale_left + scale.get_float("width") <= page.get_float("width")


def test_dense_categorical_tick_labels_rotate_and_gain_bottom_room() -> None:
    graph_plan = _plan("X23").graph_objects[0]
    layer = graph_plan.layers[0]
    x_axis = next(axis for axis in layer.axes if axis.orientation == "x")
    labels = (
        "China",
        "India",
        "U.S.",
        "Indonesia",
        "Brazil",
        "Russia",
        "Japan",
        "Germany",
        "Australia",
    )
    ticks = tuple(
        x_axis.ticks[0].model_copy(update={"value": float(index), "label": label})
        for index, label in enumerate(labels)
    )
    dense_axis = x_axis.model_copy(
        update={"scale": "categorical", "minimum": -0.5, "maximum": 8.5, "ticks": ticks}
    )
    dense_layer = layer.model_copy(
        update={
            "axes": tuple(
                dense_axis if axis.orientation == "x" else axis for axis in layer.axes
            )
        }
    )
    dense_graph = graph_plan.model_copy(update={"layers": (dense_layer, *graph_plan.layers[1:])})

    assert _tick_label_rotation(dense_axis, graph_plan.font_size_pt, layer.width_mm) == 45
    assert _native_layer_frame(dense_graph, dense_layer).height_mm < dense_layer.height_mm


def test_long_title_is_scaled_to_the_page_top_band() -> None:
    graph_plan = _plan("X36").graph_objects[0].model_copy(
        update={"title": "Visual qualification - X36 - Dual-Y column-line plot"}
    )
    page = _FakePageObject(width=2102.0, height=1417.0)
    title = _ScalingFakePageObject(width=2500.0, height=105.0, fsize=10.5)

    _place_page_title(page, graph_plan, graph_plan.layers[0], title)

    left = title.get_float("x1") * page.get_float("width")
    top = title.get_float("y1") * page.get_float("height")
    _, layer_top, _, _ = _frame_page_bounds(page, graph_plan, graph_plan.layers[0])
    assert 4.0 <= title.get_float("fsize") < 10.5
    assert left >= 0
    assert left + title.get_float("width") <= page.get_float("width")
    assert top + title.get_float("height") < layer_top


def test_annotation_color_is_applied_only_when_resolved() -> None:
    class FakeLabel:
        def __init__(self) -> None:
            self.values: dict[str, float] = {}
            self.color = "template-default"

        def set_float(self, key: str, value: float) -> None:
            self.values[key] = value

    label = FakeLabel()
    plain = ResolvedAnnotation(annotation_id="annotation:plain", kind="text")
    colored = plain.model_copy(
        update={"annotation_id": "annotation:colored", "color": ColorValue(value="#D73027")}
    )

    _style_annotation_label(label, plain, 8.0)
    assert label.color == "template-default"
    _style_annotation_label(label, colored, 9.0)
    assert label.color == "#D73027"
    assert label.values["fsize"] == 9.0


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
        ("K06", {"point_interval", "direct"}, 2),
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


def test_error_bar_point_estimates_do_not_connect_across_observations() -> None:
    plot = _plan("K06").graph_objects[0].layers[0].plots[0]
    primitives = native_primitives(plot)

    assert [item.plot_type for item in primitives] == ["line", "scatter"]
    assert primitives[0].transform == "point_interval"
    assert primitives[0].cap_size_pt == plot.cap_size_pt
    assert primitives[1].transform == "direct"
    assert primitives[1].y_role == "center"
    assert all(
        item.y_role not in {"lower", "upper"}
        for item in primitives
        if item.plot_type == "scatter"
    )


def test_error_bar_materializes_independent_intervals_and_caps_only() -> None:
    plan = _plan("K06")
    plot = plan.graph_objects[0].layers[0].plots[0]
    data = next(item for item in plan.data_objects if item.object_id == plot.data_object_id)
    interval, center = native_primitives(plot)
    table = materialize_primitive(interval, data)

    assert table is not None
    assert materialize_primitive(center, data) is None
    row_count = data.data_ref.row_count
    assert len(table.x) == len(table.y) == row_count * 18
    for row_index in range(row_count):
        start = row_index * 18
        x_chunk = table.x[start : start + 18]
        y_chunk = table.y[start : start + 18]
        assert all(x_chunk[index] is None for index in (2, 5, 8, 11, 14, 17))
        assert all(y_chunk[index] is None for index in (2, 5, 8, 11, 14, 17))
        # Horizontal interval: two vertical caps and one horizontal connector.
        assert x_chunk[0] == x_chunk[1] == x_chunk[3]
        assert x_chunk[3] < x_chunk[4]
        assert x_chunk[6] == x_chunk[7] == x_chunk[4]
        assert y_chunk[3] == y_chunk[4]
        # Vertical interval: two horizontal caps and one vertical connector.
        assert y_chunk[9] == y_chunk[10] == y_chunk[12]
        assert y_chunk[12] < y_chunk[13]
        assert y_chunk[15] == y_chunk[16] == y_chunk[13]
        assert x_chunk[12] == x_chunk[13]


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


def test_histogram_materializes_bin_centers_without_a_phantom_width_role() -> None:
    plan = _plan("K15")
    plot = plan.graph_objects[0].layers[0].plots[0]
    primitive = native_primitives(plot)[0]
    data = next(item for item in plan.data_objects if item.object_id == plot.data_object_id)

    assert primitive.transform == "histogram"
    assert primitive.bar_width_role is None
    table = materialize_primitive(primitive, data)
    assert table is not None
    left = next(item.values for item in data.columns if item.role == "left")
    right = next(item.values for item in data.columns if item.role == "right")
    assert table.x == tuple(
        (float(low) + float(high)) / 2
        for low, high in zip(left, right, strict=True)
    )


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
