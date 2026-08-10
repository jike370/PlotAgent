"""K18 official AREA template binder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plotagent.engine.contracts import PlotEngineAction
from plotagent.engine.ports import EngineReadback

from .messages import OriginWorkerRequest
from .profile import K18_ORIGIN_PROFILE
from .xy import OriginXYDefinition, OriginXYProject

_DEFINITION = OriginXYDefinition(
    template=K18_ORIGIN_PROFILE,
    plot_type="?",
    object_kind="area_series",
    supports_line=True,
    supports_symbol=False,
)


class K18OriginProject(OriginXYProject):
    def __init__(self, op: Any) -> None:
        super().__init__(op, _DEFINITION)


def execute_k18_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = K18OriginProject(op)
    if request.previous_opju is None:
        project.create(install_dir, request.document, request.data)
        pending: tuple[PlotEngineAction, ...] = request.actions
    else:
        project.open(Path(request.previous_opju))
        pending = request.actions[-1:]
    for action in pending:
        project.apply(request.document, action, request.data)
    project.save(output)

    reopened = K18OriginProject(op)
    reopened.open(output)
    return reopened.verify(request.document, request.actions, request.data)
