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


def test_native_visual_bridge_is_pinned_to_origin_theme_ids_and_packaged() -> None:
    source = Path(bridge.__file__).with_name("native_visual_t1.c").read_text(encoding="utf-8")

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


def test_native_visual_bridge_rejects_untrusted_graph_names() -> None:
    origin = _Origin()

    with pytest.raises(RuntimeError, match="unsafe"):
        bridge.set_color_scale_title(origin, "Graph;type x", 1, "Expression")
