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


def test_native_visual_bridge_sets_and_reads_point_symbol_edge_width() -> None:
    origin = _Origin()

    bridge.set_symbol_edge_width(origin, "Graph_1", 2, 3, 1.5)
    value = bridge.read_native_visual_value(
        origin,
        "Graph_1",
        2,
        3,
        bridge.SYMBOL_EDGE_WIDTH,
        numeric_type="double",
    )

    assert value == pytest.approx(1.5)
    assert Path(origin.strings["__PAT1SOURCE"]).name == "native_visual_t1.c"
    assert any("run.LoadOC(__PAT1SOURCE$,16)" in command for command in origin.commands)
    assert any(
        'plotagent_set_symbol_edge_width("Graph_1",2,3,1.5)' in command
        for command in origin.commands
    )


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


def test_native_visual_bridge_is_pinned_to_origin_theme_ids_and_packaged() -> None:
    source = Path(bridge.__file__).with_name("native_visual_t1.c").read_text(encoding="utf-8")

    assert "format.Root.Symbol.EdgeWidthVal.dVal = width_points" in source
    assert "plot.UpdateThemeIDs(format.Root)" in source
    assert "plot.ApplyFormat(format, true, true)" in source
    assert "OTID_CURVE_SYMBOL_EDGE_WIDTH" in source
    assert "octree_get_node_by_id" in source
    assert "Spectrums.All.DimAxes.DimAxis2.NewAxes.All.Title" in source
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


def test_native_visual_bridge_rejects_untrusted_arguments() -> None:
    origin = _Origin()

    with pytest.raises(RuntimeError, match="unsafe"):
        bridge.set_symbol_edge_width(origin, "Graph;type x", 1, 1, 1.0)
    with pytest.raises(ValueError, match="one-based"):
        bridge.set_symbol_edge_width(origin, "Graph1", 0, 1, 1.0)
    with pytest.raises(ValueError, match="non-negative"):
        bridge.set_symbol_edge_width(origin, "Graph1", 1, 1, -1.0)
