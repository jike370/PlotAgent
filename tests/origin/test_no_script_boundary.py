import ast
from pathlib import Path

import pytest

import plotagent.origin
from plotagent.origin._origin_backend import (
    NativeOriginError,
    _area_fill_command,
    _floating_column_gap_command,
)


def test_origin_adapter_has_no_attach_or_script_execution_calls() -> None:
    package = Path(plotagent.origin.__file__).parent
    forbidden_calls = {
        "attach",
        "lt_exec",
        "LT_execute",
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


def test_origin_set_commands_are_fixed_literals_from_the_small_allowlist() -> None:
    package = Path(plotagent.origin.__file__).parent
    allowed = {"-l 2", "-vg 70", "-pd 1", "-paaf 100", "-pbw 0"}
    commands: list[str] = []
    validated_area_fills = 0
    validated_floating_gaps = 0
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
                    in {"_area_fill_command", "_floating_column_gap_command"}
                ):
                    if argument.func.id == "_area_fill_command":
                        validated_area_fills += 1
                    else:
                        validated_floating_gaps += 1
                    continue
                if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
                    violations.append(f"{source.name}:{node.lineno}:dynamic")
                    continue
                commands.append(argument.value)
                if argument.value not in allowed:
                    violations.append(f"{source.name}:{node.lineno}:unexpected:{argument.value}")
    assert violations == []
    assert set(commands) == allowed
    assert validated_area_fills == 1
    assert validated_floating_gaps == 1


def test_dynamic_area_fill_option_accepts_only_typed_hex_color() -> None:
    assert _area_fill_command("#2A6FDB") == '-cf color("#2A6FDB")'
    for invalid in ("red", "#fff", '#000000"; system("rm")'):
        with pytest.raises(NativeOriginError):
            _area_fill_command(invalid)


def test_dynamic_floating_column_gap_accepts_only_bounded_finite_width() -> None:
    assert _floating_column_gap_command(0.72) == "-vg 28"
    assert _floating_column_gap_command(0.34) == "-vg 66"
    for invalid in (True, 0.0, -0.1, 1.1, float("nan"), float("inf")):
        with pytest.raises(NativeOriginError):
            _floating_column_gap_command(invalid)
