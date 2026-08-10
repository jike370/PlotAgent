import ast
from pathlib import Path

import pytest

import plotagent.origin
from plotagent.origin._origin_backend import (
    NativeOriginError,
    _area_fill_command,
    _band_fill_command,
    _bar_edge_color_command,
    _bar_edge_width_command,
    _bar_gap_command,
)


def test_origin_adapter_has_no_attach_or_script_execution_calls() -> None:
    package = Path(plotagent.origin.__file__).parent
    forbidden_calls = {
        "attach",
        "lt_exec",
        "set_formula",
        "DoMethod",
        "DoStrMethod",
    }
    violations: list[str] = []
    for source in package.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            call_name = function.attr if isinstance(function, ast.Attribute) else None
            if isinstance(function, ast.Name):
                call_name = function.id
            if call_name in forbidden_calls:
                violations.append(f"{source.name}:{node.lineno}:{call_name}")
    assert violations == []


def test_origin_labtalk_surface_is_one_fixed_native_legend_command() -> None:
    package = Path(plotagent.origin.__file__).parent
    calls: list[tuple[str, int, str | None]] = []
    for source in package.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "LT_execute"
            ):
                continue
            argument = node.args[0] if len(node.args) == 1 else None
            literal = argument.value if isinstance(argument, ast.Constant) else None
            calls.append((source.name, node.lineno, literal))
    assert [(name, literal) for name, _line, literal in calls] == [
        ("_origin_backend.py", "legend")
    ]


def test_origin_set_commands_are_fixed_literals_from_the_small_allowlist() -> None:
    package = Path(plotagent.origin.__file__).parent
    allowed = {"-l 2", "-pd 1", "-paaf 100", "-pf 1", "-pfv 8", "-paaf 1", "-pf 0"}
    commands: list[str] = []
    validated_helpers: dict[str, int] = {}
    violations: list[str] = []
    for source in package.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "set_cmd"
            ):
                continue
            for argument in node.args:
                if (
                    isinstance(argument, ast.Call)
                    and isinstance(argument.func, ast.Name)
                    and argument.func.id
                    in {
                        "_area_fill_command",
                        "_band_fill_command",
                        "_bar_gap_command",
                        "_bar_edge_color_command",
                        "_bar_edge_width_command",
                    }
                ):
                    validated_helpers[argument.func.id] = (
                        validated_helpers.get(argument.func.id, 0) + 1
                    )
                    continue
                if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
                    violations.append(f"{source.name}:{node.lineno}:dynamic")
                    continue
                commands.append(argument.value)
                if argument.value not in allowed:
                    violations.append(f"{source.name}:{node.lineno}:unexpected:{argument.value}")
    assert violations == []
    assert set(commands) == allowed
    assert validated_helpers == {
        "_area_fill_command": 1,
        "_band_fill_command": 1,
        "_bar_edge_color_command": 1,
        "_bar_edge_width_command": 1,
        "_bar_gap_command": 1,
    }


def test_dynamic_area_fill_option_accepts_only_typed_hex_color() -> None:
    assert _area_fill_command("#2A6FDB") == '-cf color("#2A6FDB")'
    for invalid in ("red", "#fff", '#000000"; system("rm")'):
        with pytest.raises(NativeOriginError):
            _area_fill_command(invalid)


def test_dynamic_band_fill_option_accepts_only_typed_hex_color() -> None:
    assert _band_fill_command("#2A6FDB") == '-pfb color("#2A6FDB")'
    for invalid in ("red", "#fff", '#000000"; system("rm")'):
        with pytest.raises(NativeOriginError):
            _band_fill_command(invalid)


def test_dynamic_bar_options_accept_only_typed_bounded_values() -> None:
    assert _bar_gap_command(0.8) == "-vg 20"
    assert _bar_edge_color_command("#2A6FDB") == '-pbcr color("#2A6FDB")'
    assert _bar_edge_width_command(0.5) == "-pbw 0.5"
    for invalid in (True, 0.0, -0.1, 1.1, float("nan"), float("inf")):
        with pytest.raises(NativeOriginError):
            _bar_gap_command(invalid)
    for invalid in ("red", "#fff", '#000000"; system("rm")'):
        with pytest.raises(NativeOriginError):
            _bar_edge_color_command(invalid)
    for invalid in (True, 0.0, -0.1, 20.1, float("nan"), float("inf")):
        with pytest.raises(NativeOriginError):
            _bar_edge_width_command(invalid)
