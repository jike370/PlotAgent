import ast
from pathlib import Path

import plotagent.origin


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
    allowed = {"-l 2", "-vg 70"}
    commands: list[str] = []
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
                if not isinstance(argument, ast.Constant) or not isinstance(
                    argument.value, str
                ):
                    violations.append(f"{source.name}:{node.lineno}:dynamic")
                    continue
                commands.append(argument.value)
                if argument.value not in allowed:
                    violations.append(
                        f"{source.name}:{node.lineno}:unexpected:{argument.value}"
                    )
    assert violations == []
    assert set(commands) == allowed
