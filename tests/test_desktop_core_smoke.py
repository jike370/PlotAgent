import json
from pathlib import Path


def test_packaging_entry_uses_the_real_desktop_core_runtime() -> None:
    source = Path("packaging/windows/desktop_core_entry.py").read_text(encoding="utf-8")
    boundary = json.loads(
        Path("packaging/windows/core-boundary.json").read_text(encoding="utf-8")
    )

    assert "plotagent.desktop_core.__main__ import main" in source
    assert "transport_smoke_stub" not in source
    assert boundary["implementation"] == "bounded_rpc_runtime"
    assert boundary["domain_capabilities"] == [
        "projects",
        "datasets",
        "plots",
        "batch",
        "figures",
        "agent",
        "exports",
        "task-control",
    ]
