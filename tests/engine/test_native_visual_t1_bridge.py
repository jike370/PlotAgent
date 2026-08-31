from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import plotagent.engine.backends.origin.native_visual_t1 as bridge


class _Origin:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.strings: dict[str, str] = {}
        self.floats = {
            "__PAT1LOAD": 0.0,
            "__PAT1STATUS": 0.0,
            "__PAT1VALUE": 1.5,
            "__PAT1CSTITLESHOW": 1.0,
            "__PAT1AXISSHOW": 1.0,
            "__PAT1AXISTICKSIZE": 9.0,
            "__PAT1CSARRANGEMENT": 2.0,
            "__PAT1CSATTACH": 1.0,
            "__PAT1CSLEFT": 100.0,
            "__PAT1CSTOP": 900.0,
            "__PAT1CSWIDTH": 600.0,
            "__PAT1CSHEIGHT": 200.0,
            "__PAT1LAYERLEFT": 80.0,
            "__PAT1LAYERTOP": 100.0,
            "__PAT1LAYERRIGHT": 880.0,
            "__PAT1LAYERBOTTOM": 780.0,
            "__PAT1CSTICKAUTO": 0.0,
            "__PAT1CSTICKTYPE": 0.0,
            "__PAT1CSTICKNUM": 4.0,
            "__PAT1CSTITLEFONTSIZE": 9.0,
            "__PAT1CSTICKFONTSIZE": 8.0,
            "__PAT1K22LINECOUNT": 12.0,
            "__PAT1K22LINESHOW": 0.0,
            "__PAT1K22ABOVELINE": 0.0,
            "__PAT1K09ISTABLE": 1.0,
            "__PAT1K09TABLEDESIGN": 0.0,
            "__PAT1K09LEVEL1HIDDEN": 1.0,
            "__PAT1K07FILLTRANS1": 65.0,
            "__PAT1K07FILLTRANS2": 65.0,
            "__PAT1K07LINECOLOR1": 17388468.0,
            "__PAT1K07LINECOLOR2": 17388468.0,
            "__PAT1K07LINEWIDTH1": 1.5,
            "__PAT1K07LINEWIDTH2": 1.5,
            "__PAT1K14FILLCOLOR": 0x1676D2,
            "__PAT1K14FILLTRANS": 25.0,
            "__PAT1K14FILLONLY": 1.0,
            "__PAT1K14FOLLOWLINE": 0.0,
            "__PAT1K14LINECOLOR": 0x1A1A1A,
            "__PAT1K14LINEWIDTH": 1.5,
            "__PAT1K14LINESTYLE": 1.0,
            "__PAT1CALLATTACH": 2.0,
            "__PAT1CALLX0": 1.25,
            "__PAT1CALLY0": 8.5,
            "__PAT1CALLX1": 4.75,
            "__PAT1CALLY1": 3.25,
            "__PAT1CALLBEGIN": 0.0,
            "__PAT1CALLEND": 1.0,
            "__PAT1X09GROUPCOUNT": 3.0,
            "__PAT1X40GROUPCOUNT": 2.0,
            "__PAT1X40SUBGROUPSIZE": 2.0,
            "__PAT1X40STRETCHCOLOR": 1.0,
            "__PAT1X40STRETCHSHAPE": 1.0,
            "__PAT1X40STRETCHSIZE": 1.0,
            "__PAT1X40STRETCHINTERIOR": 1.0,
            "__PAT1X40BASESHAPE": 2.0,
            "__PAT1X40BASESIZE": 6.0,
            "__PAT1X40BASEINTERIOR": 0.0,
            "__PAT1X40BASEEDGE": 0x777777,
            "__PAT1X40BASEFILL": 0x777777,
            "__PAT1X40SHAPE1": 1.0,
            "__PAT1X40SHAPE2": 2.0,
            "__PAT1X40INTERIOR1": 0.0,
            "__PAT1X40INTERIOR2": 1.0,
            "__PAT1X40EDGE1": 0x777777,
            "__PAT1X40EDGE2": 0xFF0000,
            "__PAT1X40FILL1": 0x777777,
            "__PAT1X40FILL2": 0xFFFFFF,
            "__PAT1X40CONNECTSHOW": 1.0,
            "__PAT1X40CONNECTSTYLE": 0.0,
            "__PAT1X40CONNECTWIDTH": 1.0,
            "__PAT1X40CONNECTCOLOR": 0.0,
            "__PAT1X40CONNECTSUBGROUP": 1.0,
        }

    def set_lt_str(self, name: str, value: str) -> bool:
        self.strings[name] = value
        return True

    def lt_exec(self, command: str) -> bool:
        self.commands.append(command)
        return True

    def lt_float(self, name: str) -> float:
        return self.floats[name]

    def get_lt_str(self, name: str) -> str:
        return self.strings[name]


def test_native_visual_bridge_sets_and_reads_color_scale_title() -> None:
    origin = _Origin()
    origin.strings["__PAT1CSTITLEOBS"] = "Expression"

    bridge.set_color_scale_title(origin, "Graph_1", 2, "Expression")
    title = bridge.read_color_scale_title(origin, "Graph_1", 2)
    shown = bridge.read_color_scale_title_show(origin, "Graph_1", 2)

    assert title == "Expression"
    assert shown == 1
    assert origin.strings["__PAT1CSTITLE"] == "Expression"
    assert any(
        'plotagent_set_color_scale_title("Graph_1",2,__PAT1CSTITLE$)' in command
        for command in origin.commands
    )
    assert sum("plotagent_read_color_scale_title" in command for command in origin.commands) == 2
    assert Path(origin.strings["__PAT1SOURCE"]).name == "native_visual_t1.c"
    assert any("run.LoadOC(__PAT1SOURCE$,16)" in command for command in origin.commands)
    assert any("__PAT1BRIDGEVERSION" in command for command in origin.commands)


def test_native_visual_bridge_sets_and_reads_axis_line_visibility() -> None:
    origin = _Origin()

    bridge.set_axis_line_show(origin, "Graph_1", 2, 3, False)
    shown = bridge.read_axis_line_show(origin, "Graph_1", 2, 3)

    assert shown == 1
    assert any(
        'plotagent_set_axis_line_show("Graph_1",2,3,0)' in command for command in origin.commands
    )
    assert any(
        'plotagent_read_axis_line_show("Graph_1",2,3)' in command for command in origin.commands
    )


def test_native_visual_bridge_sets_and_reads_axis_tick_font_size() -> None:
    origin = _Origin()

    bridge.set_axis_tick_font_size(origin, "Graph_1", 2, 3, 9.5)
    size = bridge.read_axis_tick_font_size(origin, "Graph_1", 2, 3)

    assert size == 9.0
    assert any(
        'plotagent_set_axis_tick_font_size("Graph_1",2,3,9.5)' in command
        for command in origin.commands
    )
    assert any(
        'plotagent_read_axis_tick_font_size("Graph_1",2,3)' in command
        for command in origin.commands
    )


def test_native_visual_bridge_configures_and_reads_k09_axis_labels() -> None:
    origin = _Origin()

    bridge.configure_k09_axis_labels(origin, "Graph_1", 1)
    observed = bridge.read_k09_axis_labels(origin, "Graph_1", 1)

    assert observed == bridge.K09AxisLabelState(1, 0, 1)
    assert any(
        'plotagent_configure_k09_axis_labels("Graph_1",1)' in command for command in origin.commands
    )
    assert any(
        'plotagent_read_k09_axis_labels("Graph_1",1)' in command for command in origin.commands
    )


def test_native_visual_bridge_sets_and_reads_color_scale_anchor() -> None:
    origin = _Origin()

    bridge.set_color_scale_anchor(origin, "Graph_1", 2, "bottom")
    observed = bridge.read_color_scale_anchor(origin, "Graph_1", 2)

    assert observed == bridge.ColorScaleAnchorState(
        arrangement=2,
        attach=1,
        left=100.0,
        top=900.0,
        width=600.0,
        height=200.0,
        layer_left=80.0,
        layer_top=100.0,
        layer_right=880.0,
        layer_bottom=780.0,
    )
    assert any(
        'plotagent_set_color_scale_anchor("Graph_1",2,1)' in command for command in origin.commands
    )
    assert any(
        'plotagent_read_color_scale_anchor("Graph_1",2)' in command for command in origin.commands
    )


def test_native_visual_bridge_sets_and_reads_color_scale_tick_format() -> None:
    origin = _Origin()
    origin.strings["__PAT1CSTICKCUSTOM"] = ""

    bridge.set_color_scale_tick_format(origin, "Graph_1", 2, "scientific")
    observed = bridge.read_color_scale_tick_format(origin, "Graph_1", 2)

    assert observed == bridge.ColorScaleTickFormatState(0, 0, 4, "")
    assert any(
        'plotagent_set_color_scale_tick_format("Graph_1",2,2)' in command
        for command in origin.commands
    )
    assert any(
        'plotagent_read_color_scale_tick_format("Graph_1",2)' in command
        for command in origin.commands
    )


def test_native_visual_bridge_sets_and_reads_color_scale_typography() -> None:
    origin = _Origin()

    bridge.set_color_scale_typography(
        origin,
        "Graph_1",
        2,
        title_font_size_pt=9.0,
        tick_font_size_pt=8.0,
    )
    observed = bridge.read_color_scale_typography(origin, "Graph_1", 2)

    assert observed == bridge.ColorScaleTypographyState(9.0, 8.0)
    assert any(
        'plotagent_set_color_scale_typography("Graph_1",2,9,8)' in command
        for command in origin.commands
    )
    assert any(
        'plotagent_read_color_scale_typography("Graph_1",2)' in command
        for command in origin.commands
    )


def test_native_visual_bridge_sets_and_reads_k22_contour_line_visibility() -> None:
    origin = _Origin()

    bridge.set_k22_contour_lines_visible(origin, "Graph_1", 1, 1, False)
    observed = bridge.read_k22_contour_lines(origin, "Graph_1", 1, 1)

    assert observed == bridge.K22ContourLineState(12, 0, 0)
    assert any(
        'plotagent_set_k22_contour_lines_visible("Graph_1",1,1,0)' in command
        for command in origin.commands
    )
    assert any(
        'plotagent_read_k22_contour_lines("Graph_1",1,1)' in command
        for command in origin.commands
    )


def test_native_visual_bridge_sets_reads_and_removes_scale_arrow() -> None:
    origin = _Origin()

    bridge.set_scale_arrow(
        origin,
        "Graph_1",
        2,
        "pac_0123456789abcdef_a",
        x0=1.25,
        y0=8.5,
        x1=4.75,
        y1=3.25,
    )
    observed = bridge.read_scale_arrow(
        origin,
        "Graph_1",
        2,
        "pac_0123456789abcdef_a",
    )
    bridge.remove_graph_object(origin, "Graph_1", 2, "pac_0123456789abcdef_a")
    bridge.set_scale_arrow_head(origin, "Graph_1", 2, "pac_0123456789abcdef_a", 1)

    assert observed == bridge.ScaleArrowState(2, 1.25, 8.5, 4.75, 3.25, 0, 1)
    assert origin.strings["__PAT1ARROW"] == "pac_0123456789abcdef_a"
    assert origin.strings["__PAT1OBJ"] == "pac_0123456789abcdef_a"
    assert any(
        'plotagent_set_scale_arrow("Graph_1",2,__PAT1ARROW$,1.25,8.5,4.75,3.25)' in command
        for command in origin.commands
    )
    assert any("plotagent_read_scale_arrow" in command for command in origin.commands)
    assert any("plotagent_remove_graph_object" in command for command in origin.commands)
    assert any("plotagent_set_scale_arrow_head" in command for command in origin.commands)


def test_native_visual_bridge_sets_and_reads_x09_group_fill_colors() -> None:
    origin = _Origin()
    origin.strings["__PAT1X09GROUPCOLORS"] = "5021401 5021401 5021401"

    bridge.set_x09_group_fill_color(origin, "Graph_1", 1, 5021401)
    observed = bridge.read_x09_group_fill_colors(origin, "Graph_1", 1)

    assert observed == (5021401, 5021401, 5021401)
    assert any(
        'plotagent_set_x09_group_fill_color("Graph_1",1,5021401)' in command
        for command in origin.commands
    )
    assert any(
        'plotagent_read_x09_group_fill_colors("Graph_1",1)' in command
        for command in origin.commands
    )

    bridge.set_x09_group_fill_colors(origin, "Graph_1", 1, (11, 22, 33))
    assert any(
        'plotagent_set_x09_group_fill_colors("Graph_1",1,11,22,33)' in command
        for command in origin.commands
    )


def test_native_visual_bridge_sets_and_reads_k07_error_band_style() -> None:
    origin = _Origin()

    bridge.set_k07_error_band_fill_transparency(
        origin,
        "Graph_1",
        1,
        fill_transparency=65.0,
    )
    observed = bridge.read_k07_error_band_style(origin, "Graph_1", 1)

    assert observed == bridge.K07ErrorBandStyleState(
        fill_transparencies=(65.0, 65.0),
        line_colors=(17388468, 17388468),
        line_widths=(1.5, 1.5),
    )
    assert any(
        'plotagent_set_k07_error_band_fill_transparency("Graph_1",1,65)'
        in command
        for command in origin.commands
    )
    assert any(
        'plotagent_read_k07_error_band_style("Graph_1",1)' in command
        for command in origin.commands
    )


def test_native_visual_bridge_sets_and_reads_visible_k14_violin_style() -> None:
    origin = _Origin()

    bridge.set_k14_violin_style(
        origin,
        "Graph_1",
        1,
        2,
        fill_color=0x1676D2,
        fill_transparency=25.0,
        outline_color=0x1A1A1A,
        outline_width=1.5,
        outline_style=1,
    )
    observed = bridge.read_k14_violin_style(origin, "Graph_1", 1, 2)

    assert observed == bridge.K14ViolinStyleState(
        fill_color=0x1676D2,
        fill_transparency=25.0,
        fill_only=1,
        follow_line_transparency=0,
        outline_color=0x1A1A1A,
        outline_width=1.5,
        outline_style=1,
    )
    assert any(
        'plotagent_set_k14_violin_style("Graph_1",1,2,1472210,25,1710618,1.5,1)'
        in command
        for command in origin.commands
    )
    assert any(
        'plotagent_read_k14_violin_style("Graph_1",1,2)' in command
        for command in origin.commands
    )
    source = Path(inspect.getfile(bridge)).with_name("native_visual_t1.c").read_text(
        encoding="utf-8"
    )
    assert "Patterns.Below" in source
    assert "FollowLineTransparency" in source


def test_native_visual_bridge_sets_and_reads_x40_native_group_style() -> None:
    origin = _Origin()
    origin.strings["__PAT1X40SIZES"] = "6 7"

    bridge.set_x40_group_style(
        origin,
        "Graph_1",
        1,
        marker_shapes=(1, 2),
        marker_sizes=(6.0, 7.0),
        marker_interiors=(0, 1),
        marker_edge_colors=(0x777777, 0xFF0000),
        marker_fill_colors=(0x777777, 0xFFFFFF),
        connector_visible=True,
        connector_style=0,
        connector_width=1.0,
        connector_color=0,
    )
    observed = bridge.read_x40_group_style(origin, "Graph_1", 1)

    assert observed == bridge.X40GroupStyleState(
        group_count=2,
        subgroup_size=2,
        marker_shapes=(1, 2),
        marker_sizes=(6.0, 7.0),
        marker_interiors=(0, 1),
        marker_edge_colors=(0x777777, 0xFF0000),
        marker_fill_colors=(0x777777, 0xFFFFFF),
        connector_visible=True,
        connector_style=0,
        connector_width=1.0,
        connector_color=0,
        connector_by_subgroup=1,
    )
    assert any(
        'plotagent_set_x40_group_style("Graph_1",1,1,2,6,7,0,1,7829367,16711680,'
        "7829367,16777215,1,0,1,0)" in command
        for command in origin.commands
    )
    assert any(
        'plotagent_read_x40_group_style("Graph_1",1)' in command for command in origin.commands
    )


def test_native_visual_bridge_is_pinned_to_origin_theme_ids_and_packaged() -> None:
    source = Path(bridge.__file__).with_name("native_visual_t1.c").read_text(encoding="utf-8")

    assert "Spectrums.All.DimAxes.DimAxis2.NewAxes.All.Title" in source
    assert 'GraphObjects("SPECTRUM1")' in source
    assert "SPECTRUM_Arrangement_Horizontal" in source
    assert "LabelsDisplayAuto" in source
    assert "NewAxes.All.Labels.All" in source
    assert "plotagent_set_color_scale_typography" in source
    assert "plotagent_read_color_scale_typography" in source
    assert "plotagent_set_k22_contour_lines_visible" in source
    assert "plotagent_read_k22_contour_lines" in source
    assert 'custom.strVal = "*6"' in source
    assert "PA_OTID_AXIS_LABEL_TABLE_DESIGN" in source
    assert "plotagent_configure_k09_axis_labels" in source
    assert "plotagent_set_axis_tick_font_size" in source
    assert "plotagent_read_axis_tick_font_size" in source
    assert "plotagent_set_scale_arrow" in source
    assert "plotagent_read_scale_arrow" in source
    assert "plotagent_remove_graph_object" in source
    assert "plotagent_set_scale_arrow_head" in source
    assert "plotagent_set_x09_group_fill_color" in source
    assert "plotagent_set_x09_group_fill_colors" in source
    assert "plotagent_read_x09_group_fill_colors" in source
    assert "plotagent_set_k07_error_band_fill_transparency" in source
    assert "plotagent_read_k07_error_band_style" in source
    assert "format.Root.Pattern.Transparency.dVal" in source
    assert "format.Root.ErrorBar2D.ConnectLineColor.nVal" in source
    assert "group.Increment.BackgroundColor.nVals = colors" in source
    assert "plotagent_set_x40_group_style" in source
    assert "plotagent_read_x40_group_style" in source
    assert "GroupPlot group = layer.Groups(0)" in source
    assert "format.Root.Increment.Shape.nVals" in source
    assert "format.Root.BoxChart.ConnectLine.DataPointsColor" in source
    assert "format.Root.Dimension.Units.nVal = 5" in source
    assert "format.Root.Data.X.dVals = x_values" in source
    assert "format.Root.Data.Y.dVals = y_values" in source
    assert "BottomLabels.Font.Size" not in source
    assert "label.Font.Size.dVal" in source
    assert "LABELS_NUM_SCI_1E3" in source
    assert "get_layer_rect_page_units" in source
    assert "LT_set_str" in source
    assert "LT_set_var" in source
    assert "layer.ApplyFormat(format, true, false)" in source
    assert "GetTheme" not in inspect.getsource(bridge)

    visual_source = Path(bridge.__file__).with_name("visual_t1.py").read_text(encoding="utf-8")
    assert ".label.pt" not in visual_source

    project_root = Path(__file__).resolve().parents[2]
    spec = (project_root / "packaging" / "windows" / "plotagent-core.spec").read_text(
        encoding="utf-8"
    )
    compile(spec, "plotagent-core.spec", "exec")
    assert '"native_visual_t1.c"' in spec


def test_native_visual_bridge_rejects_untrusted_graph_names() -> None:
    origin = _Origin()

    with pytest.raises(RuntimeError, match="unsafe"):
        bridge.set_color_scale_title(origin, "Graph;type x", 1, "Expression")

    with pytest.raises(RuntimeError, match="unsafe"):
        bridge.set_scale_arrow(
            origin,
            "Graph_1",
            1,
            "bad;name",
            x0=0,
            y0=0,
            x1=1,
            y1=1,
        )
