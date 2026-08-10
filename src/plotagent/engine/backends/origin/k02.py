"""K02 official LINESYMB template binder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plotagent.engine.contracts import PlotEngineAction
from plotagent.engine.ports import EngineReadback

from .messages import OriginWorkerRequest
from .profile import K02_ORIGIN_PROFILE
from .xy import OriginXYDefinition, OriginXYProject

_DEFINITION = OriginXYDefinition(
    template=K02_ORIGIN_PROFILE,
    plot_type="y",
    object_kind="line_symbol_series",
    supports_line=True,
    supports_symbol=True,
)


class K02OriginProject(OriginXYProject):
    def __init__(self, op: Any) -> None:
        super().__init__(op, _DEFINITION)


def execute_k02_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = K02OriginProject(op)
    if request.previous_opju is None:
        project.create(install_dir, request.document, request.data)
        pending: tuple[PlotEngineAction, ...] = request.actions
    else:
        project.open(Path(request.previous_opju))
        pending = request.actions[-1:]
    for action in pending:
        project.apply(request.document, action, request.data)
    project.save(output)

    op.new(asksave=False)
    if not op.open(str(output), readonly=True, asksave=False):
        raise RuntimeError("fresh Origin session could not reopen the staged K02 project")
    reopened = K02OriginProject(op)
    graphs = list(op.pages("g"))
    books = list(op.pages("w"))
    if len(graphs) != 1 or len(books) != 1:
        raise RuntimeError("fresh K02 project has unexpected graph or workbook count")
    reopened.graph = graphs[0]
    reopened.layer = reopened.graph[0]
    plots = reopened.layer.plot_list()
    if len(plots) != 1:
        raise RuntimeError("fresh K02 project has an unexpected native plot count")
    reopened.plot = plots[0]
    reopened.sheet = books[0][0]
    return reopened.verify(request.document, request.actions, request.data)
