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
