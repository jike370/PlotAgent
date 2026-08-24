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

from plotagent.engine.backends.matplotlib.visual_t1 import (
    apply_visual_actions,
    apply_visuals_before_save,
)
from plotagent.engine.backends.origin.visual_t1 import (
    _centered_levels,
    _color_scale_for_action,
    _fixed_axis_bounds_mode_is_valid,
    _legend_column_count,
    _series_numeric_tolerance,
    _updated_tick_bits,
)
from plotagent.engine.contracts import (
    AddAnnotation,
    BindFields,
    CreatePlot,
    EngineDataRef,
    FieldBinding,
    PlotDocument,
    SetAxis,
    SetChartParameter,
    SetColorMap,
    SetDataLabels,
    SetErrorStyle,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineReadback
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
    "AddAnnotation",
)


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
