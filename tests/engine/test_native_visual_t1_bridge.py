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
def test_native_visual_bridge_is_pinned_to_origin_theme_ids_and_packaged() -> None:
    source = Path(bridge.__file__).with_name("native_visual_t1.c").read_text(encoding="utf-8")

    assert "Spectrums.All.DimAxes.DimAxis2.NewAxes.All.Title" in source
    assert 'GraphObjects("SPECTRUM1")' in source
    assert "SPECTRUM_Arrangement_Horizontal" in source
    assert "LabelsDisplayAuto" in source
    assert "NewAxes.All.Labels.All" in source
    assert "LABELS_NUM_SCI_1E3" in source
    assert "get_layer_rect_page_units" in source
    assert "LT_set_str" in source
    assert "LT_set_var" in source
    assert "layer.ApplyFormat(format, true, false)" in source
    assert "GetTheme" not in inspect.getsource(bridge)

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
