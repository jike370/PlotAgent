from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib import colors as mcolors
from matplotlib.colors import BoundaryNorm
from matplotlib.ticker import FuncFormatter, LogLocator

import plotagent.engine.backends.origin.visual_t1 as origin_visual_t1
from plotagent.engine.backends.matplotlib.visual_t1 import (
    apply_visual_actions,
    apply_visuals_before_save,
)
from plotagent.engine.backends.origin.native_visual_t1 import ScaleArrowState
from plotagent.engine.backends.origin.visual_t1 import (
    _ORIGIN_FOUR_SIDED_FRAME_PROFILES,
    _apply_action,
    _apply_callouts,
    _apply_k09_subset_fill_colors,
    _apply_origin_product_frame,
    _apply_origin_product_typography,
    _apply_reference_lines,
    _apply_series,
    _capture_origin_template_frame,
    _centered_levels,
    _color_scale_for_action,
    _fixed_axis_bounds_mode_is_valid,
    _k09_legend_column_count,
    _k09_requested_x_tick_font_size,
    _legend_column_count,
    _origin_legend_anchor,
    _series_numeric_tolerance,
    _updated_tick_bits,
    _verify_actions,
    _verify_k09_subset_fill_color,
    _verify_origin_product_frame,
    _verify_origin_product_opposite_axes,
    _verify_origin_product_typography,
)
from plotagent.engine.contracts import (
    AddAnnotation,
    AddCallout,
    AddReferenceLine,
    BindFields,
    CreatePlot,
    EngineDataRef,
    FieldBinding,
    PlotDocument,
    PointMarkerMapEntry,
    SetAxis,
    SetCanvas,
    SetChartParameter,
    SetColorMap,
    SetDataLabels,
    SetErrorStyle,
    SetLegend,
    SetPointMarkerMap,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineReadback
from plotagent.engine.profiles import ENGINE_PROFILES
from plotagent.engine.repository import document_ref
from plotagent.engine.visual_t1 import (
    effective_visual_actions,
    split_visual_actions,
    visual_style_hash,
)

_VISUAL_ACTION_NAMES = (
    "SetTitle",
    "SetAxis",
    "SetSeriesStyle",
    "SetLegend",
    "SetColorMap",
    "SetErrorStyle",
    "SetDataLabels",
    "SetCanvas",
    "AddAnnotation",
    "AddReferenceLine",
    "AddCallout",
)


class _OriginFrameLayer:
    def __init__(self, zero_based_index: int) -> None:
        self._index = zero_based_index
        self.properties = {
            "x.showLabels": 3,
            "y.showLabels": 3,
            "x2.ticks": 10,
            "y2.ticks": 10,
        }

    def index(self) -> int:
        return self._index

    def get_int(self, name: str) -> int:
        return self.properties[name]

    def set_int(self, name: str, value: int) -> None:
        self.properties[name] = value


class _OriginFrameGraph(list[_OriginFrameLayer]):
    name = "Graph_1"


class _OriginTypographyLabel:
    def __init__(self, size: float = 20) -> None:
        self.values = {"fsize": size}

    def set_float(self, name: str, value: float) -> None:
        self.values[name] = value

    def get_float(self, name: str) -> float:
        return float(self.values[name])


class _OriginTypographyLayer:
    def __init__(self, zero_based_index: int, labels: tuple[str, ...]) -> None:
        self._index = zero_based_index
        self.labels = {name: _OriginTypographyLabel() for name in labels}

    def index(self) -> int:
        return self._index

    def label(self, name: str) -> _OriginTypographyLabel | None:
        return self.labels.get(name)


class _OriginTypographyGraph(list[_OriginTypographyLayer]):
    name = "Graph_1"


class _OriginDualAxisLayer:
    def __init__(self, zero_based_index: int) -> None:
        self._index = zero_based_index
        self.properties: dict[str, int] = {}
        self._axis = object()

    def index(self) -> int:
        return self._index

    def axis(self, name: str) -> object:
        assert name == "y"
        return self._axis

    def set_int(self, name: str, value: int) -> None:
        self.properties[name] = value


class _OriginDualAxisGraph(list[_OriginDualAxisLayer]):
    name = "Graph_1"


class _OriginColorOp:
    def lt_float(self, expression: str) -> float:
        assert expression.startswith('color("#')
        return float(int(expression.split('"', 2)[1][1:], 16))


class _OriginSeriesLayer:
    def index(self) -> int:
        return 0


class _OriginSeriesGraph(list[_OriginSeriesLayer]):
    name = "Graph_1"


class _OriginSeriesOp:
    def __init__(self, *, plot_pid: int = 200) -> None:
        self.commands: list[str] = []
        self.plot_pid = plot_pid

    def lt_exec(self, command: str) -> bool:
        self.commands.append(command)
        return True

    def lt_float(self, expression: str) -> float:
        if expression == "__PAT1COUNT":
            return 2
        if expression == "__PAT1VALUE":
            return float(self.plot_pid)
        raise AssertionError(f"unexpected LabTalk expression {expression}")


class _OriginReferenceObject:
    def __init__(
        self,
        layer: _OriginReferenceLayer,
        *,
        name: str = "",
        text: str = "",
    ) -> None:
        self.layer = layer
        self._name = ""
        self.name = name
        self.text = text
        self.values: dict[str, float | int] = {}

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        if getattr(self, "_name", ""):
            self.layer.objects.pop(self._name, None)
        self._name = value
        if value:
            self.layer.objects[value] = self

    def set_int(self, name: str, value: int) -> None:
        self.values[name] = value

    def get_int(self, name: str) -> int:
        return int(self.values.get(name, 0))

    def set_float(self, name: str, value: float) -> None:
        self.values[name] = value

    def get_float(self, name: str) -> float:
        return float(self.values.get(name, 0))


class _OriginReferenceAxis:
    def __init__(self, limits: tuple[float, float]) -> None:
        self.limits = (*limits, 0.0)
        self.scale = "linear"


class _OriginReferenceLayer:
    def __init__(self) -> None:
        self.objects: dict[str, _OriginReferenceObject] = {}
        self.properties: dict[str, float | int | str] = {}
        self.axes = {
            "x": _OriginReferenceAxis((0, 10)),
            "y": _OriginReferenceAxis((0, 100)),
        }

    def index(self) -> int:
        return 0

    def activate(self) -> int:
        return 0

    def axis(self, name: str) -> _OriginReferenceAxis:
        return self.axes[name]

    def label(self, name: str) -> _OriginReferenceObject | None:
        return self.objects.get(name)

    def add_label(self, text: str) -> _OriginReferenceObject:
        return _OriginReferenceObject(self, text=text)

    def set_int(self, name: str, value: int) -> None:
        self.properties[name] = value

    def get_int(self, name: str) -> int:
        return int(self.properties.get(name, 0))

    def set_float(self, name: str, value: float) -> None:
        self.properties[name] = value

    def get_float(self, name: str) -> float:
        return float(self.properties.get(name, 0))

    def set_str(self, name: str, value: str) -> None:
        self.properties[name] = value

    def get_str(self, name: str) -> str:
        return str(self.properties.get(name, ""))


class _OriginReferenceGraph(list[_OriginReferenceLayer]):
    name = "Graph_1"


class _OriginReferenceOp:
    def __init__(self, layer: _OriginReferenceLayer) -> None:
        self.layer = layer
        self.commands: list[str] = []

    def lt_float(self, expression: str) -> float:
        assert expression.startswith('color("#')
        return float(int(expression.split('"', 2)[1][1:], 16))

    def lt_exec(self, command: str) -> bool:
        self.commands.append(command)
        if not command.startswith("addline "):
            return True
        values = {
            key: value.rstrip(";")
            for key, value in (
                token.split(":=", 1)
                for token in command.split()
                if ":=" in token
            )
        }
        line = _OriginReferenceObject(self.layer, name=values["name"])
        line.set_int("attach", 2)
        line.set_int("color", int(values["color"]))
        line.set_int("linetype", int(values["style"]))
        line.set_float("linewidth", 1)
        coordinate = "x" if int(values["type"]) == 0 else "y"
        line.set_float(coordinate, float(values["value"]))
        return True


class _K09SubsetLayer:
    def index(self) -> int:
        return 0

    def label(self, name: str):
        assert name == "legend"
        return type("Legend", (), {"text": "\\l(1.1) A\n\\l(1.2) B\n\\l(1.3) C"})()


class _K09SubsetGraph(list[_K09SubsetLayer]):
    name = "Graph_1"


class _K09SubsetOrigin:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.enabled = False
        self.start = 2
        self.datasets: dict[str, list[int]] = {}

    def lt_exec(self, command: str) -> bool:
        self.commands.append(command)
        if command.startswith("dataset __PAT1K09COLORS={"):
            payload = command.split("{", 1)[1].split("}", 1)[0]
            self.datasets["__PAT1K09COLORS"] = [int(value) for value in payload.split(",")]
            self.enabled = True
        elif command.startswith("dataset ") and "; get __PAT1P -cuf " in command:
            variable = command.split("dataset ", 1)[1].split(";", 1)[0]
            self.datasets[variable] = list(self.datasets["__PAT1K09COLORS"])
        return True

    def lt_float(self, expression: str) -> float:
        if expression == "__PAT1COUNT":
            return 1.0
        if expression == "__PAT1K09ENABLED":
            return float(self.enabled)
        if expression == "__PAT1K09START":
            return float(self.start)
        if expression.startswith("color(\""):
            return float(int(expression.split('"', 2)[1][1:], 16))
        if "[" in expression and expression.endswith("]"):
            variable, ordinal = expression[:-1].split("[", 1)
            return float(self.datasets[variable][int(ordinal) - 1])
        raise AssertionError(f"unexpected LabTalk expression {expression}")


def _data_ref() -> EngineDataRef:
    return EngineDataRef(
        kind="source",
        dataset_id="dataset:t1",
        version=1,
        content_hash="1" * 64,
    )


def _document() -> PlotDocument:
    return PlotDocument(
        plot_id="plot:t1",
        plot_version=1,
        profile_id="K01",
        data=_data_ref(),
        bindings=(
            FieldBinding(role="x", field_id="field:x"),
            FieldBinding(role="y", field_id="field:y"),
        ),
    )


def _create() -> CreatePlot:
    document = _document()
    return CreatePlot(
        action_id="action:create",
        plot_id=document.plot_id,
        profile_id=document.profile_id,
        data=document.data,
        bindings=document.bindings,
    )


def test_visual_actions_are_split_from_structural_actions_and_hashed() -> None:
    title = SetTitle(
        action_id="action:title",
        target="plot:t1",
        expected_plot_version=1,
        text="处理组",
    )

    structural, visual = split_visual_actions((_create(), title))
    readback = EngineReadback(
        document=document_ref(_document()),
        backend="matplotlib",
        objects=(),
        data_hash="2" * 64,
        style_hash="3" * 64,
    )

    assert structural == (_create(),)
    assert visual == (title,)
    assert visual_style_hash(readback, visual) == visual_style_hash(readback, visual)
    assert visual_style_hash(readback, ()) != visual_style_hash(readback, visual)


def test_rebinding_discards_only_data_derived_visual_edits() -> None:
    title = SetTitle(
        action_id="action:title-before-rebind",
        target="plot:t1",
        expected_plot_version=1,
        text="Persistent title",
    )
    style = SetSeriesStyle(
        action_id="action:style-before-rebind",
        target="series:t1.series_2",
        expected_plot_version=2,
        marker_shape="diamond",
    )
    rebind = BindFields(
        action_id="action:rebind",
        target="plot:t1",
        expected_plot_version=3,
        data=_data_ref(),
        bindings=_document().bindings,
    )

    structural, visual = split_visual_actions((_create(), title, style, rebind))

    assert structural == (_create(), rebind)
    assert visual == (title,)


def test_point_marker_map_and_uniform_marker_shape_follow_action_order() -> None:
    point_map = SetPointMarkerMap(
        action_id="action:point-map",
        target="series:t1.series_2",
        expected_plot_version=2,
        field_id="field:group",
        entries=(
            PointMarkerMapEntry(value=True, marker_shape="circle"),
            PointMarkerMapEntry(value=False, marker_shape="triangle_down"),
        ),
    )
    style = SetSeriesStyle(
        action_id="action:uniform-marker",
        target="series:t1.series_2",
        expected_plot_version=1,
        marker_shape="diamond",
        line_width_pt=2,
    )

    structural, visual = split_visual_actions((_create(), style, point_map))

    assert structural == (_create(), point_map)
    assert len(visual) == 1
    assert isinstance(visual[0], SetSeriesStyle)
    assert visual[0].marker_shape is None
    assert visual[0].line_width_pt == 2

    structural, visual = split_visual_actions((_create(), point_map, style))

    assert structural == (_create(),)
    assert visual == (style,)

    rebind = BindFields(
        action_id="action:point-map-rebind",
        target="plot:t1",
        expected_plot_version=3,
        data=_data_ref(),
        bindings=_document().bindings,
    )
    structural, _visual = split_visual_actions((_create(), point_map, rebind))
    assert structural == (_create(), rebind)


def test_later_chart_parameter_supersedes_only_earlier_colorbar_visibility() -> None:
    colormap = SetColorMap(
        action_id="action:colormap-before-chart-parameter",
        target="series:t1.primary",
        expected_plot_version=1,
        palette="viridis",
        colorbar_visible=True,
    )
    chart_parameter = SetChartParameter(
        action_id="action:chart-parameter-after-colormap",
        target="plot:t1",
        expected_plot_version=2,
        parameter="color_scale_visible",
        value=False,
    )

    structural, visual = split_visual_actions((_create(), colormap, chart_parameter))

    assert structural == (_create(), chart_parameter)
    assert len(visual) == 1
    normalized = visual[0]
    assert isinstance(normalized, SetColorMap)
    assert normalized.palette == "viridis"
    assert normalized.colorbar_visible is False


def test_later_chart_parameter_normalizes_visibility_only_colormap_action() -> None:
    colormap = SetColorMap(
        action_id="action:visibility-only-before-chart-parameter",
        target="series:t1.primary",
        expected_plot_version=1,
        colorbar_visible=True,
    )
    chart_parameter = SetChartParameter(
        action_id="action:chart-parameter-after-visibility-only",
        target="plot:t1",
        expected_plot_version=2,
        parameter="color_scale_visible",
        value=False,
    )

    _structural, visual = split_visual_actions((_create(), colormap, chart_parameter))

    assert len(visual) == 1
    normalized = visual[0]
    assert isinstance(normalized, SetColorMap)
    assert normalized.colorbar_visible is False


def test_later_colormap_visibility_is_not_removed_by_earlier_chart_parameter() -> None:
    chart_parameter = SetChartParameter(
        action_id="action:chart-parameter-before-colormap",
        target="plot:t1",
        expected_plot_version=1,
        parameter="color_scale_visible",
        value=False,
    )
    colormap = SetColorMap(
        action_id="action:colormap-after-chart-parameter",
        target="series:t1.primary",
        expected_plot_version=2,
        colorbar_visible=True,
    )

    structural, visual = split_visual_actions((_create(), chart_parameter, colormap))

    assert structural == (_create(), chart_parameter)
    assert visual == (colormap,)


def test_cross_operation_precedence_uses_the_complete_dotted_plot_id() -> None:
    matching = SetColorMap(
        action_id="action:dotted-plot-matching-colormap",
        target="series:sample.v1.primary",
        expected_plot_version=1,
        colorbar_visible=True,
    )
    other = matching.model_copy(
        update={
            "action_id": "action:dotted-plot-other-colormap",
            "target": "series:sample.other.primary",
        }
    )
    chart_parameter = SetChartParameter(
        action_id="action:dotted-plot-chart-parameter",
        target="plot:sample.v1",
        expected_plot_version=2,
        parameter="color_scale_visible",
        value=False,
    )

    _structural, visual = split_visual_actions((matching, other, chart_parameter))

    assert len(visual) == 2
    normalized, untouched = visual
    assert isinstance(normalized, SetColorMap)
    assert normalized.target == matching.target
    assert normalized.colorbar_visible is False
    assert untouched == other


def test_origin_final_state_verification_coalesces_repeated_visual_edits() -> None:
    first = SetTitle(
        action_id="action:title-1",
        target="plot:t1",
        expected_plot_version=1,
        text="Initial title",
        font_size_pt=14,
    )
    second = SetTitle(
        action_id="action:title-2",
        target="plot:t1",
        expected_plot_version=2,
        text="Final title",
    )
    x_axis = SetAxis(
        action_id="action:x-1",
        target="axis:t1.x",
        expected_plot_version=3,
        label="Time",
    )
    x_axis_update = SetAxis(
        action_id="action:x-2",
        target="axis:t1.x",
        expected_plot_version=4,
        scale="log10",
    )

    effective = effective_visual_actions((first, second, x_axis, x_axis_update))

    assert len(effective) == 2
    title, axis = effective
    assert isinstance(title, SetTitle)
    assert title.action_id == "action:title-2"
    assert title.text == "Final title"
    assert title.font_size_pt == 14
    assert isinstance(axis, SetAxis)
    assert axis.label == "Time"
    assert axis.scale == "log10"


def test_axis_bounds_can_transition_between_fixed_and_automatic() -> None:
    fixed = SetAxis(
        action_id="action:axis-fixed",
        target="axis:t1.x",
        expected_plot_version=1,
        minimum=10,
        maximum=20,
    )
    automatic = SetAxis(
        action_id="action:axis-automatic",
        target="axis:t1.x",
        expected_plot_version=2,
        bounds_mode="automatic",
    )
    effective = effective_visual_actions((fixed, automatic))
    assert len(effective) == 1
    reset = effective[0]
    assert isinstance(reset, SetAxis)
    assert reset.bounds_mode == "automatic"
    assert reset.minimum is None
    assert reset.maximum is None

    fixed_again = fixed.model_copy(
        update={"action_id": "action:axis-fixed-again", "expected_plot_version": 3}
    )
    effective = effective_visual_actions((fixed, automatic, fixed_again))
    restored = effective[0]
    assert isinstance(restored, SetAxis)
    assert restored.bounds_mode == "fixed"
    assert (restored.minimum, restored.maximum) == (10, 20)


@pytest.mark.parametrize("native_mode", [0, 1, 8])
def test_origin_fixed_axis_accepts_equivalent_native_rescale_modes(native_mode: int) -> None:
    assert _fixed_axis_bounds_mode_is_valid(native_mode)


@pytest.mark.parametrize("native_mode", [2, 3, 4, 5, 7])
def test_origin_fixed_axis_rejects_non_fixed_native_rescale_modes(native_mode: int) -> None:
    assert not _fixed_axis_bounds_mode_is_valid(native_mode)


def test_origin_template_frame_reads_every_side_without_normalizing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _OriginFrameGraph((_OriginFrameLayer(0), _OriginFrameLayer(1)))
    monkeypatch.setattr(
        origin_visual_t1,
        "read_axis_line_show",
        lambda _op, _graph_name, layer_index, axis_code: int(
            axis_code in ({0, 1} if layer_index == 1 else {0, 1, 2, 3})
        ),
    )

    snapshot = _capture_origin_template_frame(object(), graph)

    assert snapshot[(1, 0)] is True
    assert snapshot[(1, 2)] is False
    assert snapshot[(1, 3)] is False
    assert snapshot[(2, 2)] is True
    assert len(snapshot) == 8


def test_origin_product_typography_uses_pt_defaults_and_explicit_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _OriginTypographyGraph(
        (
            _OriginTypographyLayer(0, ("xb", "yl", "legend", "_ENGINE_TITLE")),
            _OriginTypographyLayer(1, ("yr",)),
        )
    )
    ticks: dict[tuple[int, int], float] = {}
    monkeypatch.setattr(
        origin_visual_t1,
        "set_axis_tick_font_size",
        lambda _op, _graph, layer, axis, size: ticks.__setitem__((layer, axis), size),
    )
    monkeypatch.setattr(
        origin_visual_t1,
        "read_axis_tick_font_size",
        lambda _op, _graph, layer, axis: ticks[(layer, axis)],
    )

    _apply_origin_product_typography(object(), graph)

    assert ticks == {
        (1, 0): 8,
        (1, 1): 8,
        (2, 0): 8,
        (2, 1): 8,
        (2, 3): 8,
    }
    assert graph[0].labels["_ENGINE_TITLE"].get_float("fsize") == 10
    assert graph[0].labels["xb"].get_float("fsize") == 9
    assert graph[0].labels["legend"].get_float("fsize") == 8
    assert graph[1].labels["yr"].get_float("fsize") == 9

    ticks[(2, 3)] = 7
    graph[0].labels["_ENGINE_TITLE"].set_float("fsize", 11)
    graph[0].labels["legend"].set_float("fsize", 7.5)
    graph[1].labels["yr"].set_float("fsize", 8.5)
    actions = (
        SetTitle(
            action_id="action:product-title",
            target="plot:t1",
            expected_plot_version=1,
            font_size_pt=11,
        ),
        SetAxis(
            action_id="action:product-right-axis",
            target="axis:t1.y_right",
            expected_plot_version=2,
            title_font_size_pt=8.5,
            tick_font_size_pt=7,
        ),
        SetLegend(
            action_id="action:product-legend",
            target="legend:t1.main",
            expected_plot_version=3,
            font_size_pt=7.5,
        ),
    )

    snapshot = _verify_origin_product_typography(object(), graph, actions)

    assert snapshot["title.font_pt"] == 11
    assert snapshot["layer:2.right.tick_font_pt"] == 7
    assert snapshot["layer:2.yr.font_pt"] == 8.5
    assert snapshot["layer:1.legend.font_pt"] == 7.5


def test_origin_product_frame_boxes_only_eligible_cartesian_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _OriginFrameGraph((_OriginFrameLayer(0),))
    template_frame = {
        (1, axis_code): axis_code in {0, 1}
        for axis_code in (0, 1, 2, 3)
    }
    writes: list[tuple[int, int, bool]] = []
    monkeypatch.setattr(
        origin_visual_t1,
        "set_axis_line_show",
        lambda _op, _graph_name, layer_index, axis_code, visible: writes.append(
            (layer_index, axis_code, visible)
        ),
    )

    product_frame = _apply_origin_product_frame(
        object(), graph, "K03", template_frame
    )

    assert all(product_frame.values())
    assert writes == [(1, 2, True), (1, 3, True)]
    assert graph[0].properties == {
        "x.showLabels": 1,
        "y.showLabels": 1,
        "x2.ticks": 0,
        "y2.ticks": 0,
    }


def test_origin_product_frame_verifies_clean_top_and_right_sides() -> None:
    graph = _OriginFrameGraph((_OriginFrameLayer(0),))
    graph[0].properties.update(
        {
            "x.showLabels": 1,
            "y.showLabels": 1,
            "x2.ticks": 0,
            "y2.ticks": 0,
        }
    )

    snapshot = _verify_origin_product_opposite_axes(graph, "K03")

    assert snapshot == {
        "top.ticks": 0,
        "top.labels": False,
        "right.ticks": 0,
        "right.labels": False,
    }


@pytest.mark.parametrize(
    ("property_name", "value", "side"),
    (
        ("x2.ticks", 2, "top"),
        ("y2.ticks", 2, "right"),
        ("x.showLabels", 3, "top"),
        ("y.showLabels", 3, "right"),
    ),
)
def test_origin_product_frame_rejects_opposite_ticks_or_labels(
    property_name: str,
    value: int,
    side: str,
) -> None:
    graph = _OriginFrameGraph((_OriginFrameLayer(0),))
    graph[0].properties.update(
        {
            "x.showLabels": 1,
            "y.showLabels": 1,
            "x2.ticks": 0,
            "y2.ticks": 0,
            property_name: value,
        }
    )

    with pytest.raises(RuntimeError, match=f"side={side}"):
        _verify_origin_product_opposite_axes(graph, "K03")


def test_origin_product_frame_rejects_layer_drift_for_boxed_profiles() -> None:
    graph = _OriginFrameGraph((_OriginFrameLayer(0), _OriginFrameLayer(1)))
    template_frame = {
        (layer_index, axis_code): axis_code in {0, 1}
        for layer_index in (1, 2)
        for axis_code in (0, 1, 2, 3)
    }

    with pytest.raises(RuntimeError, match="exactly one native graph layer"):
        _apply_origin_product_frame(object(), graph, "K03", template_frame)


def test_origin_product_frame_policy_partitions_the_34_profile_catalog() -> None:
    preserved = {
        "K20",
        "K21",
        "K22",
        "K24",
        "S61",
        "X13",
        "X23",
        "X24",
        "X35",
        "X36",
    }
    catalog = {profile.profile_id for profile in ENGINE_PROFILES}

    assert len(_ORIGIN_FOUR_SIDED_FRAME_PROFILES) == 24
    assert len(preserved) == 10
    assert _ORIGIN_FOUR_SIDED_FRAME_PROFILES.isdisjoint(preserved)
    assert _ORIGIN_FOUR_SIDED_FRAME_PROFILES | preserved == catalog


@pytest.mark.parametrize(
    "profile_id",
    ("K20", "K21", "K22", "K24", "S61", "X13", "X23", "X24", "X35", "X36"),
)
def test_origin_product_frame_preserves_special_template_topology(
    monkeypatch: pytest.MonkeyPatch,
    profile_id: str,
) -> None:
    graph = _OriginFrameGraph((_OriginFrameLayer(0), _OriginFrameLayer(1)))
    template_frame = {
        (layer_index, axis_code): axis_code in {0, 1}
        for layer_index in (1, 2)
        for axis_code in (0, 1, 2, 3)
    }
    monkeypatch.setattr(
        origin_visual_t1,
        "set_axis_line_show",
        lambda *_args: pytest.fail("special templates must not be normalized"),
    )

    product_frame = _apply_origin_product_frame(
        object(), graph, profile_id, template_frame
    )

    assert product_frame == template_frame


def test_origin_product_frame_fresh_readback_respects_explicit_axis_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _OriginFrameGraph((_OriginFrameLayer(0), _OriginFrameLayer(1)))
    action = SetAxis(
        action_id="action:show-right-axis-line",
        target="axis:t1.y_right",
        expected_plot_version=1,
        axis_line_visible=True,
    )
    monkeypatch.setattr(
        origin_visual_t1,
        "read_axis_line_show",
        lambda _op, _graph_name, layer_index, axis_code: int(
            axis_code in {0, 1} or (layer_index == 2 and axis_code == 3)
        ),
    )

    product_frame = {
        (layer_index, axis_code): axis_code in {0, 1}
        for layer_index in (1, 2)
        for axis_code in (0, 1, 2, 3)
    }
    snapshot = _verify_origin_product_frame(
        object(), graph, (action,), product_frame
    )

    assert snapshot["layer:1.bottom"] is True
    assert snapshot["layer:1.top"] is False
    assert snapshot["layer:2.right"] is True


def test_origin_dual_y_axis_colors_target_distinct_official_layers() -> None:
    graph = _OriginDualAxisGraph(
        (_OriginDualAxisLayer(0), _OriginDualAxisLayer(1))
    )
    document = _document().model_copy(update={"profile_id": "X35"})
    left = SetAxis(
        action_id="action:x35-left-axis-color",
        target="axis:t1.y_left",
        expected_plot_version=1,
        axis_line_color="#1676D2",
    )
    right = SetAxis(
        action_id="action:x35-right-axis-color",
        target="axis:t1.y_right",
        expected_plot_version=2,
        axis_line_color="#E07A00",
    )

    _apply_action(_OriginColorOp(), graph, document, left)
    assert graph[0].properties == {"y.color": int("1676D2", 16)}
    assert graph[1].properties == {}

    _apply_action(_OriginColorOp(), graph, document, right)
    assert graph[0].properties == {"y.color": int("1676D2", 16)}
    assert graph[1].properties == {"y.color": int("E07A00", 16)}


def test_origin_product_frame_fails_when_an_unedited_side_does_not_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _OriginFrameGraph((_OriginFrameLayer(0),))
    monkeypatch.setattr(
        origin_visual_t1,
        "read_axis_line_show",
        lambda _op, _graph_name, _layer_index, axis_code: int(axis_code != 2),
    )

    product_frame = {
        (1, axis_code): True for axis_code in (0, 1, 2, 3)
    }
    with pytest.raises(RuntimeError, match="side=top"):
        _verify_origin_product_frame(object(), graph, (), product_frame)


def test_origin_series_edit_ungroups_multi_plot_layer_before_visible_style() -> None:
    graph = _OriginSeriesGraph((_OriginSeriesLayer(),))
    origin = _OriginSeriesOp()

    _apply_series(
        origin,
        graph,
        SetSeriesStyle(
            action_id="action:group-2-red",
            target="series:t1.group_2",
            expected_plot_version=1,
            line_stroke_color="#FF0000",
            line_width_pt=2,
        ),
    )

    ungroup = origin.commands.index("layer -gu;")
    color = next(
        index
        for index, command in enumerate(origin.commands)
        if 'set __PAT1P -cl color("#FF0000")' in command
    )
    width = next(
        index
        for index, command in enumerate(origin.commands)
        if "set __PAT1P -wp 2" in command
    )
    assert ungroup < color < width
    assert any("range __PAT1P=[Graph_1]1!2" in command for command in origin.commands)


@pytest.mark.parametrize("interior", ("open", "hollow"))
def test_origin_non_solid_marker_interior_overrides_requested_fill(interior: str) -> None:
    graph = _OriginSeriesGraph((_OriginSeriesLayer(),))
    origin = _OriginSeriesOp()

    _apply_series(
        origin,
        graph,
        SetSeriesStyle(
            action_id=f"action:{interior}-black",
            target="series:t1.group_2",
            expected_plot_version=1,
            marker_interior=interior,
            marker_fill_color="#000000",
            marker_stroke_color="#000000",
        ),
    )

    assert any("set __PAT1P -kf 1" in command for command in origin.commands)
    assert any(
        'set __PAT1P -csf color("#FFFFFF")' in command for command in origin.commands
    )
    assert not any(
        'set __PAT1P -csf color("#000000")' in command for command in origin.commands
    )


def test_origin_line_symbol_color_cascades_to_unoverridden_marker_colors() -> None:
    graph = _OriginSeriesGraph((_OriginSeriesLayer(),))
    origin = _OriginSeriesOp(plot_pid=202)

    _apply_series(
        origin,
        graph,
        SetSeriesStyle(
            action_id="action:x36-blue-line",
            target="series:t1.right",
            expected_plot_version=1,
            line_stroke_color="#1676D2",
        ),
    )

    assert any('set __PAT1P -cl color("#1676D2")' in item for item in origin.commands)
    assert any('set __PAT1P -csf color("#1676D2")' in item for item in origin.commands)
    assert any('set __PAT1P -cse color("#1676D2")' in item for item in origin.commands)


def test_origin_k09_subset_fill_edit_preserves_unedited_native_subsets() -> None:
    graph = _K09SubsetGraph((_K09SubsetLayer(),))
    origin = _K09SubsetOrigin()
    document = _document().model_copy(update={"profile_id": "K09"})
    action = SetSeriesStyle(
        action_id="action:k09-group-2-red",
        target="series:t1.group_2",
        expected_plot_version=1,
        fill_color="#FF0000",
    )

    handled = _apply_k09_subset_fill_colors(origin, graph, document, (action,))

    assert handled == frozenset({action.action_id})
    assert origin.datasets["__PAT1K09COLORS"] == [2, 0xFF0000, 4]
    assert _verify_k09_subset_fill_color(origin, graph, action) == {
        "subset": 2,
        "fill_color": 0xFF0000,
        "custom_increment_list": True,
    }
    assert not any("[Graph_1]1!2" in command for command in origin.commands)


def test_origin_k09_rejects_unverified_per_subset_border_edit() -> None:
    graph = _K09SubsetGraph((_K09SubsetLayer(),))
    document = _document().model_copy(update={"profile_id": "K09"})
    action = SetSeriesStyle(
        action_id="action:k09-group-2-border",
        target="series:t1.group_2",
        expected_plot_version=1,
        fill_stroke_color="#FF0000",
    )

    with pytest.raises(ValueError, match="only independent fill_color"):
        _apply_k09_subset_fill_colors(_K09SubsetOrigin(), graph, document, (action,))


def test_origin_k09_reads_horizontal_legend_columns_from_native_subset_samples() -> None:
    text = (
        "\\l(1,m1,2) Absorption energy"
        "\\l(1,m2,2) Defect formation energy"
        "\\l(1,m3,2) Energy barrier"
    )

    assert _k09_legend_column_count(text) == 3
    assert _k09_legend_column_count(text.replace("\\l(1,m2,2)", "\n\\l(1,m2,2)").replace(
        "\\l(1,m3,2)", "\n\\l(1,m3,2)"
    )) == 1

    custom_blocks = (
        "\\L(1, PatternFill:#5B7DB6 BorderColor:#5B7DB6 Width:40 Height:50)\\sc A"
        "\\L(1, PatternFill:#0BA4A0 BorderColor:#0BA4A0 Width:40 Height:50)\\sc B"
        "\\L(1, PatternFill:#FF5757 BorderColor:#FF5757 Width:40 Height:50)\\sc C"
    )
    assert _k09_legend_column_count(custom_blocks) == 3


def test_origin_k09_presentation_keeps_explicit_category_tick_size() -> None:
    actions = (
        SetAxis(
            action_id="action:k09-x-12",
            target="axis:t1.x",
            expected_plot_version=1,
            tick_font_size_pt=12,
        ),
        SetAxis(
            action_id="action:k09-x-9",
            target="axis:t1.x",
            expected_plot_version=2,
            tick_font_size_pt=9,
        ),
        SetAxis(
            action_id="action:k09-y-8",
            target="axis:t1.y",
            expected_plot_version=3,
            tick_font_size_pt=8,
        ),
    )

    assert _k09_requested_x_tick_font_size(actions) == 9
    assert _k09_requested_x_tick_font_size((actions[-1],)) is None


def test_matplotlib_automatic_bounds_restore_data_driven_limits() -> None:
    figure, axis = plt.subplots()
    axis.plot((0, 1, 2), (1, 4, 9))
    apply_visual_actions(
        figure,
        _document(),
        (
            SetAxis(
                action_id="action:fixed-before-reset",
                target="axis:t1.x",
                expected_plot_version=1,
                minimum=10,
                maximum=20,
            ),
            SetAxis(
                action_id="action:reset-to-auto",
                target="axis:t1.x",
                expected_plot_version=2,
                bounds_mode="automatic",
            ),
        ),
    )
    left, right = axis.get_xlim()
    plt.close(figure)
    assert left < 0
    assert right > 2


def test_effective_visual_actions_keep_latest_cross_type_precedence() -> None:
    marker_first = SetSeriesStyle(
        action_id="action:marker-first",
        target="series:t1.primary",
        expected_plot_version=1,
        marker_shape="circle",
    )
    colormap = SetColorMap(
        action_id="action:colormap-middle",
        target="series:t1.primary",
        expected_plot_version=2,
        palette="viridis",
    )
    marker_last = SetSeriesStyle(
        action_id="action:marker-last",
        target="series:t1.primary",
        expected_plot_version=3,
        marker_fill_color="#D1495B",
    )

    effective = effective_visual_actions((marker_first, colormap, marker_last))

    assert [type(action) for action in effective] == [SetColorMap, SetSeriesStyle]
    merged_marker = effective[-1]
    assert isinstance(merged_marker, SetSeriesStyle)
    assert merged_marker.marker_shape == "circle"
    assert merged_marker.marker_fill_color == "#D1495B"
    assert merged_marker.action_id == "action:marker-last"


def test_profile_renderers_cannot_reclaim_shared_visual_actions() -> None:
    backend_root = Path(__file__).parents[2] / "src" / "plotagent" / "engine" / "backends"
    shared_adapters = {
        backend_root / "matplotlib" / "visual_t1.py",
        backend_root / "origin" / "visual_t1.py",
    }

    violations: list[str] = []
    for source in backend_root.rglob("*.py"):
        if source in shared_adapters:
            continue
        text = source.read_text(encoding="utf-8")
        claimed = [name for name in _VISUAL_ACTION_NAMES if name in text]
        if claimed:
            violations.append(f"{source.relative_to(backend_root)}: {', '.join(claimed)}")

    assert violations == []


def test_centered_origin_levels_are_strict_and_pin_the_midpoint() -> None:
    levels = _centered_levels(-3.0, 0.0, 9.0, 8)

    assert len(levels) == 8
    assert levels[0] == -3.0
    assert levels[4] == 0.0
    assert levels[-1] == 9.0
    assert all(left < right for left, right in pairwise(levels))


def test_origin_tick_bitfield_preserves_visibility_and_sets_direction() -> None:
    hide_minor = SetAxis(
        action_id="action:hide-minor",
        target="axis:t1.x",
        expected_plot_version=1,
        minor_ticks_visible=False,
    )
    inward = SetAxis(
        action_id="action:inward",
        target="axis:t1.x",
        expected_plot_version=1,
        tick_direction="in",
    )
    show_both = SetAxis(
        action_id="action:show-both",
        target="axis:t1.x",
        expected_plot_version=1,
        major_ticks_visible=True,
        minor_ticks_visible=True,
        tick_direction="inout",
    )

    assert _updated_tick_bits(10, hide_minor) == 2
    assert _updated_tick_bits(10, inward) == 5
    assert _updated_tick_bits(0, show_both) == 15


def test_origin_series_width_tolerance_matches_native_storage_resolution() -> None:
    assert _series_numeric_tolerance("line_width") == 0.051
    assert _series_numeric_tolerance("fill_stroke_width") == 0.051
    assert _series_numeric_tolerance("marker_size") == 1e-7


def test_origin_automatic_vertical_legend_normalizes_to_one_column() -> None:
    assert _legend_column_count(0) == 1
    assert _legend_column_count(1) == 1
    assert _legend_column_count(2) == 2


@pytest.mark.parametrize(
    ("anchor", "expected"),
    (
        ("inside", (0, 2136.0, 828.0)),
        ("inside_top_left", (0, 624.0, 828.0)),
        ("inside_top_right", (0, 2136.0, 828.0)),
        ("inside_bottom_left", (0, 624.0, 2112.0)),
        ("inside_bottom_right", (0, 2136.0, 2112.0)),
        ("right", (0, 2952.0, 1470.0)),
        ("bottom", (0, 1380.0, 2574.0)),
    ),
)
def test_origin_legend_anchor_respects_layer_relative_inside_positions(
    anchor: str,
    expected: tuple[object, object, object],
) -> None:
    graph = _OriginCanvasGraph(width=8, height=6)
    layer = type(
        "LegendLayer",
        (),
        {
            "get_float": lambda _self, name: {
                "left": 10.0,
                "top": 20.0,
                "width": 50.0,
                "height": 50.0,
            }[name],
            "get_int": lambda _self, name: {"unit": 1}[name],
        },
    )()
    legend = type(
        "LegendLabel",
        (),
        {
            "get_float": lambda _self, name: {"width": 600.0, "height": 300.0}[name]
        },
    )()

    observed = _origin_legend_anchor(graph, layer, legend, anchor)

    assert observed == expected


class _NativeColorScale:
    def IsValid(self) -> bool:
        return True


class _NativeColorScaleCollection:
    def __init__(self) -> None:
        self.added: list[int] = []

    def Add(self, object_type: int) -> _NativeColorScale:
        self.added.append(object_type)
        return _NativeColorScale()


class _NativeColorScaleLayer:
    def __init__(self) -> None:
        self.obj = type(
            "LayerObject",
            (),
            {"GraphObjects": _NativeColorScaleCollection()},
        )()
        self.label_value = None
        self.activated = False

    def label(self, name: str):
        assert name == "SPECTRUM1"
        return self.label_value

    def activate(self) -> None:
        self.activated = True


class _NativeColorScaleOrigin:
    def Label(self, native, layer_obj):
        del native, layer_obj
        return type("ColorScaleLabel", (), {"name": ""})()


def test_origin_colorbar_visibility_creates_a_missing_native_scale() -> None:
    layer = _NativeColorScaleLayer()
    action = SetColorMap(
        action_id="action:create-color-scale",
        target="series:t1.primary",
        expected_plot_version=1,
        colorbar_visible=True,
    )

    spectrum = _color_scale_for_action(_NativeColorScaleOrigin(), layer, action)

    assert spectrum is not None
    assert spectrum.name == "SPECTRUM1"
    assert layer.activated is True
    assert layer.obj.GraphObjects.added == [13]


def test_origin_rejects_styling_an_absent_color_scale() -> None:
    layer = _NativeColorScaleLayer()
    action = SetColorMap(
        action_id="action:style-missing-color-scale",
        target="series:t1.primary",
        expected_plot_version=1,
        colorbar_title="Intensity",
    )

    with pytest.raises(RuntimeError, match="color scale that is absent"):
        _color_scale_for_action(_NativeColorScaleOrigin(), layer, action)


def test_origin_keeps_hidden_color_scale_style_latent_when_scale_is_absent() -> None:
    layer = _NativeColorScaleLayer()
    action = SetColorMap(
        action_id="action:hidden-missing-color-scale",
        target="series:t1.primary",
        expected_plot_version=1,
        colorbar_visible=False,
        colorbar_title="Intensity",
    )

    assert _color_scale_for_action(_NativeColorScaleOrigin(), layer, action) is None
    assert layer.obj.GraphObjects.added == []


def test_matplotlib_shared_visual_language_edits_native_artists() -> None:
    figure, axis = plt.subplots()
    (line,) = axis.plot([1, 2, 3], [2, 4, 3], label="Response")
    axis.legend()
    actions = (
        SetTitle(
            action_id="action:title",
            target="plot:t1",
            expected_plot_version=1,
            text="温度响应",
            font_family="Microsoft YaHei",
            font_size_pt=16,
            font_weight="bold",
            color="#222222",
        ),
        SetAxis(
            action_id="action:axis",
            target="axis:t1.y",
            expected_plot_version=1,
            label="响应值",
            minimum=0,
            maximum=6,
            major_tick_step=2,
            minor_tick_count=1,
            tick_format="decimal",
            tick_rotation_deg=15,
            tick_color="#333333",
            axis_line_color="#444444",
            axis_line_width_pt=1.25,
            major_grid_visible=True,
            grid_color="#CCCCCC",
            grid_line_width_pt=0.75,
            grid_line_style="dot",
        ),
        SetSeriesStyle(
            action_id="action:series",
            target="series:t1.primary",
            expected_plot_version=1,
            line_stroke_color="#A52A2A",
            line_width_pt=2.5,
            line_style="dash_dot",
            line_opacity=0.8,
            marker_shape="diamond",
            marker_size_pt=9,
            marker_interior="open",
            marker_stroke_color="#A52A2A",
            marker_stroke_width_pt=1.5,
        ),
        SetLegend(
            action_id="action:legend",
            target="legend:t1.main",
            expected_plot_version=1,
            visible=True,
            anchor="right",
            columns=1,
            title="实验条件",
            font_size_pt=10,
            font_color="#222222",
            frame_visible=True,
            frame_color="#777777",
            frame_width_pt=1,
        ),
        SetDataLabels(
            action_id="action:labels",
            target="series:t1.primary",
            expected_plot_version=1,
            visible=True,
            value_format="decimal",
            prefix="v=",
            position="above",
            font_size_pt=8,
            font_color="#333333",
        ),
        AddAnnotation(
            action_id="action:annotation",
            target="plot:t1",
            annotation_id="annotation:t1.note",
            expected_plot_version=1,
            text="阈值",
            x=0.6,
            y=0.8,
            coordinate_system="axes",
            font_size_pt=9,
            color="#555555",
        ),
    )

    apply_visual_actions(figure, _document(), actions)

    assert axis.get_title() == "温度响应"
    assert axis.get_ylabel() == "响应值"
    assert axis.get_ylim() == (0.0, 6.0)
    assert line.get_color() == "#A52A2A"
    assert line.get_linewidth() == 2.5
    assert line.get_marker() == "D"
    assert line.get_markersize() == 9
    assert line.get_markerfacecolor() == "none"
    assert axis.get_legend() is not None
    assert axis.get_legend().get_title().get_text() == "实验条件"
    assert sum(text.get_gid() == "plotagent-label:series:t1.primary" for text in axis.texts) == 3
    assert any(text.get_gid() == "annotation:t1.note" for text in axis.texts)
    plt.close(figure)


def test_matplotlib_canvas_action_changes_the_output_page_not_data_axes() -> None:
    figure, axis = plt.subplots(figsize=(6.4, 4.8))
    axis.plot([0, 1], [2, 3])
    limits_before = (axis.get_xlim(), axis.get_ylim())

    apply_visual_actions(
        figure,
        _document(),
        (
            SetCanvas(
                action_id="action:wide-canvas",
                target="plot:t1",
                expected_plot_version=1,
                aspect_ratio=2.5,
            ),
        ),
    )

    assert tuple(float(value) for value in figure.get_size_inches()) == pytest.approx(
        (12.0, 4.8)
    )
    assert (axis.get_xlim(), axis.get_ylim()) == limits_before
    plt.close(figure)


def test_matplotlib_reference_lines_use_target_axis_data_coordinates() -> None:
    figure, left = plt.subplots()
    right = left.twinx()
    left.plot([0, 1, 2], [2, 4, 6])
    right.plot([0, 1, 2], [20, 40, 60])
    actions = (
        AddReferenceLine(
            action_id="action:x-threshold",
            target="axis:t1.x",
            expected_plot_version=1,
            reference_line_id="reference_line:t1.x_threshold",
            value=1.25,
            label="X threshold",
            line_color="#B42318",
            line_width_pt=1.5,
            line_style="dash",
        ),
        AddReferenceLine(
            action_id="action:right-mean",
            target="axis:t1.y_right",
            expected_plot_version=2,
            reference_line_id="reference_line:t1.right_mean",
            value=35,
            label="Mean",
            line_color="#175CD3",
            line_width_pt=2,
            line_style="dot",
        ),
    )

    apply_visual_actions(figure, _document(), actions)

    x_line = next(line for line in left.lines if line.get_gid() == actions[0].reference_line_id)
    right_line = next(
        line for line in right.lines if line.get_gid() == actions[1].reference_line_id
    )
    assert tuple(x_line.get_xdata()) == pytest.approx((1.25, 1.25))
    assert tuple(x_line.get_ydata()) == pytest.approx((0, 1))
    assert tuple(right_line.get_xdata()) == pytest.approx((0, 1))
    assert tuple(right_line.get_ydata()) == pytest.approx((35, 35))
    assert x_line.get_linestyle() == "--"
    assert right_line.get_linestyle() == ":"
    assert any(text.get_gid() == actions[0].reference_line_id + ".label" for text in left.texts)
    assert any(
        text.get_gid() == actions[1].reference_line_id + ".label" for text in right.texts
    )
    plt.close(figure)


def test_latest_reference_line_with_same_semantic_id_supersedes_earlier_state() -> None:
    first = AddReferenceLine(
        action_id="action:reference-first",
        target="axis:t1.y",
        expected_plot_version=1,
        reference_line_id="reference_line:t1.threshold",
        value=2,
        line_color="#B42318",
    )
    latest = first.model_copy(
        update={
            "action_id": "action:reference-latest",
            "expected_plot_version": 2,
            "value": 3,
            "line_color": "#175CD3",
        }
    )

    assert effective_visual_actions((first, latest)) == (latest,)


def test_matplotlib_callout_binds_to_reference_line_without_category_slot_coordinates() -> None:
    figure, axis = plt.subplots()
    axis.bar((0, 1, 2), (10, 20, 15))
    reference = AddReferenceLine(
        action_id="action:k08-mean",
        target="axis:t1.y",
        expected_plot_version=1,
        reference_line_id="reference_line:t1.eu_mean",
        value=16.26640875,
        line_color="#D92D20",
    )
    callout = AddCallout(
        action_id="action:k08-mean-callout",
        target=reference.reference_line_id,
        expected_plot_version=2,
        callout_id="callout:t1.eu_mean_explanation",
        text="Mean total content across EU",
        anchor_fraction=0.55,
        text_x_fraction=0.52,
        text_y_fraction=0.82,
        arrow_color="#101828",
        arrow_width_pt=1.25,
        arrow_head="filled",
    )

    apply_visual_actions(figure, _document(), (callout, reference))

    annotation = next(
        text for text in axis.texts if text.get_gid() == callout.callout_id
    )
    assert annotation.get_text() == callout.text
    assert annotation.xy == pytest.approx((0.55, reference.value))
    assert annotation.get_position() == pytest.approx((0.52, 0.82))
    assert annotation.arrow_patch is not None
    assert annotation.arrow_patch.get_gid() == callout.callout_id + ".arrow"
    assert annotation.arrow_patch.get_linewidth() == pytest.approx(1.25)
    plt.close(figure)


def test_matplotlib_callout_rejects_missing_reference_line() -> None:
    figure, axis = plt.subplots()
    axis.plot((0, 1), (0, 1))
    callout = AddCallout(
        action_id="action:missing-callout-target",
        target="reference_line:t1.missing",
        expected_plot_version=1,
        callout_id="callout:t1.missing",
        text="Missing",
        text_x_fraction=0.5,
        text_y_fraction=0.5,
    )

    with pytest.raises(ValueError, match="not an effective reference line"):
        apply_visual_actions(figure, _document(), (callout,))
    plt.close(figure)


def test_latest_callout_with_same_semantic_id_supersedes_earlier_state() -> None:
    first = AddCallout(
        action_id="action:callout-first",
        target="reference_line:t1.mean",
        expected_plot_version=1,
        callout_id="callout:t1.mean",
        text="Mean",
        text_x_fraction=0.4,
        text_y_fraction=0.8,
    )
    latest = first.model_copy(
        update={
            "action_id": "action:callout-latest",
            "expected_plot_version": 2,
            "text": "EU mean",
        }
    )

    assert effective_visual_actions((first, latest)) == (latest,)


def test_origin_reference_line_is_native_axis_scale_object_with_fresh_readback() -> None:
    layer = _OriginReferenceLayer()
    graph = _OriginReferenceGraph((layer,))
    op = _OriginReferenceOp(layer)
    action = AddReferenceLine(
        action_id="action:origin-reference",
        target="axis:t1.y",
        expected_plot_version=1,
        reference_line_id="reference_line:t1.mean",
        value=42.5,
        label="Mean",
        line_color="#B42318",
        line_width_pt=1.5,
        line_style="dash",
    )

    _apply_action(op, graph, _document(), action)
    snapshot = _verify_actions(op, graph, _document(), (action,))

    assert layer.properties["y.reflines.count"] == 1
    assert layer.properties["y.refline1.value"] == pytest.approx(42.5)
    assert layer.properties["y.refline1.labeltext"] == "Mean"
    assert op.commands == []
    assert snapshot[action.action_id]["axis"] == "y"
    assert snapshot[action.action_id]["native_index"] == 1
    assert snapshot[action.action_id]["value"] == pytest.approx(42.5)
    assert snapshot[action.action_id]["line_width_pt"] == pytest.approx(1.5)
    assert snapshot[action.action_id]["label"] == "Mean"


def test_origin_reference_line_rebuild_clears_touched_old_axis_and_indexes_per_axis() -> None:
    layer = _OriginReferenceLayer()
    graph = _OriginReferenceGraph((layer,))
    op = _OriginReferenceOp(layer)
    old_y = AddReferenceLine(
        action_id="action:old-y",
        target="axis:t1.y",
        expected_plot_version=1,
        reference_line_id="reference_line:t1.moved",
        value=2,
    )
    x_one = AddReferenceLine(
        action_id="action:x-one",
        target="axis:t1.x",
        expected_plot_version=2,
        reference_line_id="reference_line:t1.moved",
        value=3,
    )
    x_two = AddReferenceLine(
        action_id="action:x-two",
        target="axis:t1.x",
        expected_plot_version=3,
        reference_line_id="reference_line:t1.other",
        value=4,
    )

    _apply_reference_lines(
        op,
        graph,
        (x_one, x_two),
        touched_actions=(old_y, x_one, x_two),
    )

    assert layer.properties["y.reflines.count"] == 0
    assert layer.properties["x.reflines.count"] == 2
    assert layer.properties["x.refline1.value"] == pytest.approx(3)
    assert layer.properties["x.refline2.value"] == pytest.approx(4)


def test_origin_callout_uses_native_scale_geometry_bound_to_reference_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layer = _OriginReferenceLayer()
    graph = _OriginReferenceGraph((layer,))
    op = _OriginReferenceOp(layer)
    reference = AddReferenceLine(
        action_id="action:origin-callout-reference",
        target="axis:t1.y",
        expected_plot_version=1,
        reference_line_id="reference_line:t1.eu_mean",
        value=16.5,
        label="EU mean",
    )
    callout = AddCallout(
        action_id="action:origin-callout",
        target=reference.reference_line_id,
        expected_plot_version=2,
        callout_id="callout:t1.eu_mean_explanation",
        text="Average across EU countries",
        anchor_fraction=0.5,
        text_x_fraction=0.2,
        text_y_fraction=0.8,
        arrow_color="#B42318",
        arrow_width_pt=1.5,
        arrow_head="open",
        font_size_pt=9,
        font_weight="bold",
        italic=True,
        text_color="#175CD3",
    )
    arrow_states: dict[str, ScaleArrowState] = {}

    def remove_object(
        _op: object,
        _graph_name: str,
        _layer_index: int,
        object_name: str,
    ) -> None:
        layer.objects.pop(object_name, None)

    def set_arrow(
        _op: object,
        _graph_name: str,
        _layer_index: int,
        arrow_name: str,
        *,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
    ) -> None:
        arrow_states[arrow_name] = ScaleArrowState(2, x0, y0, x1, y1, 0, 2)
        _OriginReferenceObject(layer, name=arrow_name)

    def read_arrow(
        _op: object,
        _graph_name: str,
        _layer_index: int,
        arrow_name: str,
    ) -> ScaleArrowState:
        return arrow_states[arrow_name]

    monkeypatch.setattr(origin_visual_t1, "remove_graph_object", remove_object)
    monkeypatch.setattr(origin_visual_t1, "set_scale_arrow", set_arrow)
    monkeypatch.setattr(origin_visual_t1, "read_scale_arrow", read_arrow)
    monkeypatch.setattr(origin_visual_t1, "set_scale_arrow_head", lambda *_args: None)

    _apply_reference_lines(op, graph, (reference,))
    _apply_callouts(
        op,
        graph,
        (callout,),
        reference_lines=(reference,),
    )
    snapshot = _verify_actions(op, graph, _document(), (callout, reference))

    observed = snapshot[callout.action_id]
    assert observed["reference_line_id"] == reference.reference_line_id
    assert observed["arrow"] == {
        "attach": 2,
        "x0": pytest.approx(2),
        "y0": pytest.approx(80),
        "x1": pytest.approx(5),
        "y1": pytest.approx(16.5),
        "begin_style": 0,
        "end_style": 2,
    }
    assert observed["arrow_head"] == "open"
    assert observed["text"] == "Average across EU countries"
    assert observed["text_x"] == pytest.approx(2)
    assert observed["text_y"] == pytest.approx(80)


def test_origin_callout_rejects_missing_effective_reference_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layer = _OriginReferenceLayer()
    graph = _OriginReferenceGraph((layer,))
    op = _OriginReferenceOp(layer)
    callout = AddCallout(
        action_id="action:origin-missing-callout",
        target="reference_line:t1.missing",
        expected_plot_version=1,
        callout_id="callout:t1.missing",
        text="Missing",
        text_x_fraction=0.2,
        text_y_fraction=0.8,
    )
    monkeypatch.setattr(origin_visual_t1, "remove_graph_object", lambda *_args: None)

    with pytest.raises(ValueError, match="not an effective reference line"):
        _apply_callouts(
            op,
            graph,
            (callout,),
            reference_lines=(),
        )


def test_latest_canvas_action_is_the_only_effective_page_state() -> None:
    first = SetCanvas(
        action_id="action:first-canvas",
        target="plot:t1",
        expected_plot_version=1,
        width_mm=180,
        height_mm=120,
    )
    latest = SetCanvas(
        action_id="action:latest-canvas",
        target="plot:t1",
        expected_plot_version=2,
        aspect_ratio=3,
    )

    effective = effective_visual_actions((first, latest))

    assert effective == (latest,)


class _OriginCanvasGraph:
    def __init__(self, width: float = 8, height: float = 6) -> None:
        self.obj = self
        self.properties = {"width": width, "height": height}
        self.keep_aspect_ratio = True

    def GetWidth(self) -> float:
        return self.properties["width"]

    def GetHeight(self) -> float:
        return self.properties["height"]

    def LT_execute(self, command: str) -> bool:
        if command == "gfitp margin:=5 aspect:=0;":
            return True
        assignments = {
            token.split("=", 1)[0]: float(token.split("=", 1)[1])
            for token in command.replace(";", "").split()
        }
        self.properties["width"] = assignments["page.width"] / 600
        self.properties["height"] = assignments["page.height"] / 600
        return True

    def SetNumProp(self, name: str, value: int) -> int:
        assert name == "KAR"
        self.keep_aspect_ratio = bool(value)
        return 1

    def get_float(self, name: str) -> float:
        if name in {"resx", "resy"}:
            return 600.0
        raise AssertionError(f"canvas must not read the theme-tree property {name}")

    def set_float(self, name: str, value: float) -> None:
        raise AssertionError(f"canvas must not write the theme-tree property {name}={value}")


def test_origin_canvas_action_uses_inches_and_has_fresh_readback_evidence() -> None:
    graph = _OriginCanvasGraph()
    action = SetCanvas(
        action_id="action:origin-canvas",
        target="plot:t1",
        expected_plot_version=1,
        width_mm=254,
        height_mm=127,
    )

    _apply_action(object(), graph, _document(), action)
    snapshot = _verify_actions(object(), graph, _document(), (action,))

    assert graph.properties == {"width": 10.0, "height": 5.0}
    assert graph.keep_aspect_ratio is False
    assert snapshot[action.action_id] == {
        "width_mm": 254.0,
        "height_mm": 127.0,
        "aspect_ratio": 2.0,
    }


def test_matplotlib_cjk_edit_replaces_a_profile_local_latin_font() -> None:
    figure, axis = plt.subplots()
    axis.set_title("Nyquist Plot", fontfamily="DejaVu Sans")
    action = SetTitle(
        action_id="action:cjk-title",
        target="plot:t1",
        expected_plot_version=1,
        text="最终黑盒 S34",
    )

    apply_visual_actions(
        figure,
        _document(),
        (action,),
        resolved_font_family="Microsoft YaHei",
    )

    assert axis.get_title() == "最终黑盒 S34"
    assert axis.title.get_fontfamily() == ["Microsoft YaHei"]
    plt.close(figure)


def test_matplotlib_legend_columns_have_native_property_evidence() -> None:
    figure, axis = plt.subplots()
    right = axis.twinx()
    axis.plot([1, 2], [2, 3], label="Control")
    right.plot([1, 2], [30, 50], label="Treatment")

    apply_visual_actions(
        figure,
        _document(),
        (
            SetLegend(
                action_id="action:legend-columns",
                target="legend:t1.main",
                expected_plot_version=1,
                visible=True,
                columns=2,
            ),
        ),
    )

    legend = axis.get_legend()
    assert legend is not None
    assert legend._ncols == 2
    assert [text.get_text() for text in legend.get_texts()] == ["Control", "Treatment"]
    assert right.get_legend() is None
    plt.close(figure)


def test_matplotlib_colormap_missing_color_has_native_property_evidence() -> None:
    figure, axis = plt.subplots()
    image = axis.imshow(np.asarray([[1.0, np.nan], [2.0, 3.0]]))

    apply_visual_actions(
        figure,
        _document(),
        (
            SetColorMap(
                action_id="action:missing-color",
                target="series:t1.matrix",
                expected_plot_version=1,
                missing_color="#A23B72",
            ),
        ),
    )

    np.testing.assert_allclose(
        image.cmap.get_bad(),
        mcolors.to_rgba("#A23B72"),
    )
    plt.close(figure)


def test_matplotlib_explicit_marker_color_overrides_and_can_restore_scalar_mapping() -> None:
    figure, axis = plt.subplots()
    collection = axis.scatter([1, 2, 3], [2, 4, 3], c=[0.1, 0.5, 0.9])
    marker_action = SetSeriesStyle(
        action_id="action:explicit-marker-fill",
        target="series:t1.primary",
        expected_plot_version=1,
        marker_fill_color="#D1495B",
    )

    apply_visual_actions(figure, _document(), (marker_action,))
    figure.canvas.draw()
    assert collection.get_array() is None
    np.testing.assert_allclose(
        collection.get_facecolors()[0],
        mcolors.to_rgba("#D1495B"),
    )

    apply_visual_actions(
        figure,
        _document(),
        (
            marker_action,
            SetColorMap(
                action_id="action:restore-colormap",
                target="series:t1.primary",
                expected_plot_version=2,
                palette="viridis",
            ),
        ),
    )
    assert collection.get_array() is not None
    np.testing.assert_allclose(collection.get_array(), [0.1, 0.5, 0.9])
    plt.close(figure)


def test_matplotlib_shape_edge_and_fill_opacity_are_independent() -> None:
    figure, axis = plt.subplots()
    collection = axis.fill_between(
        [1, 2, 3],
        [1, 2, 1],
        [3, 4, 3],
        alpha=0.35,
        edgecolor="#1D3557",
        label="Band",
    )

    apply_visual_actions(
        figure,
        _document(),
        (
            SetSeriesStyle(
                action_id="action:independent-alpha",
                target="series:t1.primary",
                expected_plot_version=1,
                line_opacity=0.8,
                fill_opacity=0.25,
            ),
        ),
    )

    assert collection.get_alpha() is None
    assert collection.get_edgecolors()[0, 3] == pytest.approx(0.8)
    assert collection.get_facecolors()[0, 3] == pytest.approx(0.25)
    plt.close(figure)


def test_matplotlib_visibility_and_tick_direction_edit_native_objects() -> None:
    figure, axis = plt.subplots()
    axis.set_xlabel("Time")
    (line,) = axis.plot([1, 2, 3], [2, 4, 3])
    band = axis.fill_between([1, 2, 3], [1, 3, 2], [3, 5, 4])
    actions = (
        SetAxis(
            action_id="action:axis-visibility",
            target="axis:t1.x",
            expected_plot_version=1,
            tick_labels_visible=False,
            major_ticks_visible=False,
            minor_ticks_visible=False,
            tick_direction="inout",
            axis_line_visible=False,
            axis_title_visible=False,
        ),
        SetSeriesStyle(
            action_id="action:series-visibility",
            target="series:t1.primary",
            expected_plot_version=1,
            visible=False,
        ),
    )

    apply_visual_actions(figure, _document(), actions)
    figure.canvas.draw()

    assert axis.xaxis.label.get_visible() is False
    assert axis.spines["bottom"].get_visible() is False
    assert all(not label.get_visible() for label in axis.get_xticklabels())
    assert all(not tick.tick1line.get_visible() for tick in axis.xaxis.get_major_ticks())
    assert all(not tick.tick1line.get_visible() for tick in axis.xaxis.get_minor_ticks())
    assert all(tick._tickdir == "inout" for tick in axis.xaxis.get_major_ticks())
    assert line.get_visible() is False
    assert band.get_visible() is False
    plt.close(figure)


def test_matplotlib_grid_visibility_does_not_require_style_parameters() -> None:
    figure, axis = plt.subplots()
    axis.plot([1, 2, 3], [2, 4, 3])

    apply_visual_actions(
        figure,
        _document(),
        (
            SetAxis(
                action_id="action:grid-visibility-only",
                target="axis:t1.y",
                expected_plot_version=1,
                major_grid_visible=True,
                minor_grid_visible=True,
            ),
        ),
    )
    figure.canvas.draw()

    assert any(line.get_visible() for line in axis.get_ygridlines())
    plt.close(figure)


def test_matplotlib_log_axis_uses_a_logarithmic_minor_tick_locator() -> None:
    figure, axis = plt.subplots()
    axis.plot([1, 10, 100], [1, 2, 3])

    apply_visual_actions(
        figure,
        _document(),
        (
            SetAxis(
                action_id="action:log-minor-ticks",
                target="axis:t1.x",
                expected_plot_version=1,
                scale="log10",
                minor_tick_count=2,
            ),
        ),
    )

    assert isinstance(axis.xaxis.get_minor_locator(), LogLocator)
    figure.canvas.draw()
    plt.close(figure)


def test_matplotlib_data_labels_edit_matrix_cells() -> None:
    figure, axis = plt.subplots()
    axis.imshow(np.asarray([[1.25, 2.5], [3.75, 5.0]]))

    apply_visual_actions(
        figure,
        _document(),
        (
            SetDataLabels(
                action_id="action:matrix-labels",
                target="series:t1.matrix",
                expected_plot_version=1,
                visible=True,
                value_format="decimal",
                prefix="v=",
                suffix=" unit",
                position="center",
            ),
        ),
    )

    labels = [
        text
        for text in axis.texts
        if text.get_gid() == "plotagent-label:series:t1.matrix"
    ]
    assert [label.get_text() for label in labels] == [
        "v=1.25 unit",
        "v=2.5 unit",
        "v=3.75 unit",
        "v=5 unit",
    ]
    plt.close(figure)


def test_matplotlib_colormap_error_band_and_save_hook(tmp_path: Path) -> None:
    figure, axis = plt.subplots()
    image = axis.imshow(np.asarray([[0.0, 1.0], [2.0, np.nan]]), label="Matrix")
    axis.errorbar([0, 1], [1, 2], yerr=[0.2, 0.3], capsize=4)
    band = axis.fill_between([0, 1], [0.8, 1.7], [1.2, 2.3])
    actions = (
        SetColorMap(
            action_id="action:cmap",
            target="series:t1.matrix",
            expected_plot_version=1,
            palette="blue_orange",
            reverse=True,
            minimum=0,
            maximum=2,
            mode="discrete",
            levels=4,
            missing_color="#999999",
            colorbar_visible=True,
            colorbar_anchor="bottom",
            colorbar_title="Intensity",
            colorbar_tick_format="scientific",
        ),
        SetErrorStyle(
            action_id="action:error",
            target="series:t1.primary",
            expected_plot_version=1,
            bar_color="#B03030",
            bar_width_pt=1.75,
            cap_size_pt=7,
            bar_opacity=0.7,
            band_fill_color="#BFD7EA",
            band_fill_opacity=0.35,
            band_stroke_color="#5B7FA3",
            band_stroke_width_pt=1.25,
        ),
    )
    output = tmp_path / "t1.png"

    with apply_visuals_before_save(_document(), actions):
        figure.savefig(output)

    assert output.is_file()
    assert isinstance(image.norm, BoundaryNorm)
    assert image.get_clim() == (0.0, 2.0)
    assert len(figure.axes) == 2
    assert figure.axes[-1].get_xlabel() == "Intensity"
    assert isinstance(figure.axes[-1]._colorbar.formatter, FuncFormatter)
    assert band.get_alpha() == 0.35
    plt.close(figure)


def test_repeated_colormap_actions_preserve_prior_properties_when_shown_later() -> None:
    figure, axis = plt.subplots()
    axis.imshow(np.asarray([[0.0, 1.0], [2.0, 3.0]]))
    hidden_with_title = SetColorMap(
        action_id="action:hidden-colorbar-title",
        target="series:t1.matrix",
        expected_plot_version=1,
        colorbar_visible=False,
        colorbar_title="Intensity",
    )
    shown_later = SetColorMap(
        action_id="action:show-colorbar-later",
        target="series:t1.matrix",
        expected_plot_version=2,
        colorbar_visible=True,
    )

    effective = effective_visual_actions((hidden_with_title, shown_later))
    apply_visual_actions(figure, _document(), (hidden_with_title, shown_later))

    assert len(effective) == 1
    merged = effective[0]
    assert isinstance(merged, SetColorMap)
    assert merged.colorbar_visible is True
    assert merged.colorbar_title == "Intensity"
    assert len(figure.axes) == 2
    assert figure.axes[-1].get_ylabel() == "Intensity"
    plt.close(figure)


def test_matplotlib_keeps_hidden_colorbar_style_latent_when_bar_is_absent() -> None:
    figure, axis = plt.subplots()
    axis.imshow(np.asarray([[0.0, 1.0], [2.0, 3.0]]))

    apply_visual_actions(
        figure,
        _document(),
        (
            SetColorMap(
                action_id="action:hidden-absent-colorbar",
                target="series:t1.matrix",
                expected_plot_version=1,
                colorbar_visible=False,
                colorbar_title="Intensity",
            ),
        ),
    )

    assert len(figure.axes) == 1
    plt.close(figure)


def test_matplotlib_rejects_styling_an_absent_colorbar() -> None:
    figure, axis = plt.subplots()
    axis.imshow(np.asarray([[0.0, 1.0], [2.0, 3.0]]))
    action = SetColorMap(
        action_id="action:style-absent-colorbar",
        target="series:t1.matrix",
        expected_plot_version=1,
        colorbar_title="Intensity",
    )

    with pytest.raises(RuntimeError, match="colorbar that is absent"):
        apply_visual_actions(figure, _document(), (action,))
    plt.close(figure)
