"""X02 official DROPLINE template binder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plotagent.engine.contracts import PlotEngineAction
from plotagent.engine.ports import EngineReadback

from .messages import OriginWorkerRequest
from .profile import X02_ORIGIN_PROFILE
from .xy import OriginXYDefinition, OriginXYProject

_DEFINITION = OriginXYDefinition(
    template=X02_ORIGIN_PROFILE,
    plot_type="?",
    object_kind="drop_line_series",
    supports_line=True,
    supports_symbol=True,
)


class X02OriginProject(OriginXYProject):
    def __init__(self, op: Any) -> None:
        super().__init__(op, _DEFINITION)


def execute_x02_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = X02OriginProject(op)
    if request.previous_opju is None:
        project.create(install_dir, request.document, request.data)
        pending: tuple[PlotEngineAction, ...] = request.actions
    else:
        project.open(Path(request.previous_opju))
        pending = request.actions[-1:]
    for action in pending:
        project.apply(request.document, action, request.data)
    project.save(output)

    reopened = X02OriginProject(op)
    reopened.open(output)
    return reopened.verify(request.document, request.actions, request.data)
