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
            "__PAT1K09ISTABLE": 1.0,
            "__PAT1K09TABLEDESIGN": 0.0,
            "__PAT1K09LEVEL1HIDDEN": 1.0,
            "__PAT1CALLATTACH": 2.0,
            "__PAT1CALLX0": 1.25,
            "__PAT1CALLY0": 8.5,
            "__PAT1CALLX1": 4.75,
            "__PAT1CALLY1": 3.25,
            "__PAT1CALLBEGIN": 0.0,
            "__PAT1CALLEND": 1.0,
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
        'plotagent_set_axis_line_show("Graph_1",2,3,0)' in command
        for command in origin.commands
    )
    assert any(
        'plotagent_read_axis_line_show("Graph_1",2,3)' in command
        for command in origin.commands
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
        'plotagent_configure_k09_axis_labels("Graph_1",1)' in command
        for command in origin.commands
    )
    assert any(
        'plotagent_read_k09_axis_labels("Graph_1",1)' in command
        for command in origin.commands
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
        'plotagent_set_color_scale_anchor("Graph_1",2,1)' in command
        for command in origin.commands
    )
    assert any(
        'plotagent_read_color_scale_anchor("Graph_1",2)' in command
        for command in origin.commands
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
        'plotagent_set_scale_arrow("Graph_1",2,__PAT1ARROW$,1.25,8.5,4.75,3.25)'
        in command
        for command in origin.commands
    )
    assert any("plotagent_read_scale_arrow" in command for command in origin.commands)
    assert any("plotagent_remove_graph_object" in command for command in origin.commands)
    assert any("plotagent_set_scale_arrow_head" in command for command in origin.commands)


def test_native_visual_bridge_is_pinned_to_origin_theme_ids_and_packaged() -> None:
    source = Path(bridge.__file__).with_name("native_visual_t1.c").read_text(encoding="utf-8")

    assert "Spectrums.All.DimAxes.DimAxis2.NewAxes.All.Title" in source
    assert 'GraphObjects("SPECTRUM1")' in source
    assert "SPECTRUM_Arrangement_Horizontal" in source
    assert "LabelsDisplayAuto" in source
    assert "NewAxes.All.Labels.All" in source
    assert "PA_OTID_AXIS_LABEL_TABLE_DESIGN" in source
    assert "plotagent_configure_k09_axis_labels" in source
    assert "plotagent_set_axis_tick_font_size" in source
    assert "plotagent_read_axis_tick_font_size" in source
    assert "plotagent_set_scale_arrow" in source
    assert "plotagent_read_scale_arrow" in source
    assert "plotagent_remove_graph_object" in source
    assert "plotagent_set_scale_arrow_head" in source
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

    visual_source = Path(bridge.__file__).with_name("visual_t1.py").read_text(
        encoding="utf-8"
    )
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
