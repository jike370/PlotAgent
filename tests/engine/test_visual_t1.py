from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm

from plotagent.engine.backends.matplotlib.visual_t1 import (
    apply_visual_actions,
    apply_visuals_before_save,
)
from plotagent.engine.backends.origin.visual_t1 import (
    _centered_levels,
    _effective_state_actions,
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
    SetColorMap,
    SetDataLabels,
    SetErrorStyle,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineReadback
from plotagent.engine.repository import document_ref
from plotagent.engine.visual_t1 import split_visual_actions, visual_style_hash

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

    effective = _effective_state_actions((first, second, x_axis, x_axis_update))

    assert len(effective) == 2
    title, axis = effective
    assert isinstance(title, SetTitle)
    assert title.action_id == "action:title-2"
    assert title.text == "Final title"
    assert title.font_size_pt == 14
    assert isinstance(axis, SetAxis)
    assert axis.label == "Time"
    assert axis.scale == "log10"


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
    assert band.get_alpha() == 0.35
    plt.close(figure)
