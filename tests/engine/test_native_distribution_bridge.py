from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import plotagent.engine.backends.origin.native_distribution as bridge


class _Origin:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.strings: dict[str, str] = {}
        self.floats: dict[str, float] = {
            "__PADISTLOAD": 0.0,
            "__PADISTSTATUS": 0.0,
            "__PADISTVALUE": 1.5,
        }

    def set_lt_str(self, name: str, value: str) -> bool:
        self.strings[name] = value
        return True

    def lt_exec(self, command: str) -> bool:
        self.commands.append(command)
        return True

    def lt_float(self, name: str) -> float:
        return self.floats[name]


def test_native_distribution_bridge_uses_reviewed_origin_c_entry_points() -> None:
    origin = _Origin()

    bridge.configure_native_distribution(origin, "Graph_1", 2, 13)
    bridge.configure_native_distribution(origin, "Graph_1", 3, 14, bandwidth=0.625)
    value = bridge.read_native_distribution_value(
        origin,
        "Graph_1",
        2,
        bridge.WHISKER_COEFF,
        numeric_type="double",
    )

    assert value == pytest.approx(1.5)
    assert Path(origin.strings["__PADISTSOURCE"]).name == "native_distribution.c"
    assert any("run.LoadOC(__PADISTSOURCE$,16)" in command for command in origin.commands)
    assert any(
        'plotagent_configure_distribution("Graph_1",2,13,0)' in command
        for command in origin.commands
    )
    assert any(
        'plotagent_configure_distribution("Graph_1",3,14,0.625)' in command
        for command in origin.commands
    )
    assert any(
        f'plotagent_distribution_value("Graph_1",2,{bridge.WHISKER_COEFF},1)'
        in command
        for command in origin.commands
    )


def test_native_distribution_bridge_rejects_untrusted_names_and_bandwidths() -> None:
    origin = _Origin()

    with pytest.raises(RuntimeError, match="unsafe"):
        bridge.configure_native_distribution(origin, "Graph;type x", 1, 13)
    with pytest.raises(ValueError, match="positive and finite"):
        bridge.configure_native_distribution(origin, "Graph1", 1, 14, bandwidth=0.0)


def test_origin_c_bridge_uses_getformat_applyformat_and_pinned_theme_ids() -> None:
    source = Path(bridge.__file__).with_name("native_distribution.c").read_text(
        encoding="utf-8"
    )

    assert "plot.GetTheme(" not in source
    assert "layer.GetFormat(FPB_ALL, FOB_ALL, true, true)" in source
    assert "layer.ApplyFormat(format, true, true)" in source
    assert "octree_get_node_by_id" in source
    for symbolic_id in (
        "OTID_BOXCHART_INFO_BOX_TYPE",
        "OTID_BOXCHART_INFO_BOX_RANGE",
        "OTID_BOXCHART_INFO_BOX_WHISKER_RANGE",
        "OTID_BOXCHART_INFO_BOX_WHISKER_COEFF",
        "OTID_BOXCHART_INFO_BOX_HAS_OUTLIERS",
        "OTID_BOXCHART_INFO_DIST_CURVE_TYPE",
        "OTID_BOXCHART_INFO_DIST_CURVE_SCALE",
        "OTID_BOXCHART_INFO_DIST_SCALE_TYPE",
        "OTID_BOXCHART_INFO_DIST_KERNEL_SMOOTH_BANDWIDTH",
        "OTID_BOXCHART_INFO_DIST_KERNEL_SMOOTH_BANDWIDTH_FACTOR",
        "OTID_BOXCHART_INFO_DIST_KERNEL_SMOOTH_EXTEND",
        "OTID_BOXCHART_INFO_DATA_HEIGHT_TYPE",
    ):
        assert symbolic_id in source

    python_source = inspect.getsource(bridge)
    assert "GetTheme" not in python_source


def test_windows_bundle_includes_the_reviewed_origin_c_bridge() -> None:
    project_root = Path(__file__).resolve().parents[2]
    spec = (project_root / "packaging" / "windows" / "plotagent-core.spec").read_text(
        encoding="utf-8"
    )

    compile(spec, "plotagent-core.spec", "exec")
    assert '"native_distribution.c"' in spec
    assert '"plotagent/engine/backends/origin"' in spec
