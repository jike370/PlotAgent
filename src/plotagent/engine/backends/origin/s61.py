"""Official Heat Map with Labels binder for the S61 confusion matrix."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, cast

import numpy as np

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetChartParameter,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import K20Grid, s61_confusion_grid
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import S61_ORIGIN_PROFILE, resolve_official_template

_TITLE = "_ENGINE_TITLE"


@dataclass(frozen=True, slots=True)
class _State:
    title: str = ""
    x_label: str = "Predicted"
    y_label: str = "Actual"
    x_reverse: bool = False
    y_reverse: bool = False
    show_counts: bool = True


def _ticks(labels: tuple[str, ...]) -> str:
    return " ".join(f'"{label.replace(chr(34), chr(92) + chr(34))}"' for label in labels)


class S61OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.plot: Any = None
        self.sheet: Any = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, S61_ORIGIN_PROFILE)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("m", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create S61 matrixbook")
        self.sheet = book[0]
        grid = s61_confusion_grid(document, data)
        self._write(grid)
        self.graph = self.op.new_graph(
            f"G{token}", template=str(template.with_suffix(template.suffix.lower())), hidden=True
        )
        if self.graph is None:
            raise RuntimeError("Origin could not create S61 from Heat_Map_With_Labels.otpu")
        self.layer = self.graph[0]
        for plot in self.layer.plot_list():
            plot.set_int("show", 0)
        self.plot = self.layer.add_mplot(self.sheet, 0, type=105)
        if self.plot is None:
            raise RuntimeError("Origin S61 template rejected the confusion matrix")
        self.layer.rescale()

    def open(self, output: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(output), readonly=False, asksave=False):
            raise RuntimeError("Origin could not reopen S61")
        graphs, books = list(self.op.pages("g")), list(self.op.pages("m"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("S61 must contain one graph and matrixbook")
        self.graph, self.sheet = graphs[0], books[0][0]
        self.layer = self.graph[0]
        visible = tuple(plot for plot in self.layer.plot_list() if plot.get_int("show") != 0)
        if len(visible) != 1:
            raise RuntimeError("S61 must retain one visible native matrix plot")
        self.plot = visible[0]

    def reconcile(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> None:
        grid = s61_confusion_grid(document, data)
        state = self._state(document, actions, grid)
        self._write(grid)
        self.plot.set_int("show", 1)
        self.plot.set_int("label.show", int(state.show_counts))
        self.plot.set_float("label.fsize", 10.0)
        x_begin, x_end = 0.5, len(grid.column_labels) + 0.5
        y_begin, y_end = 0.5, len(grid.row_labels) + 0.5
        if state.x_reverse:
            x_begin, x_end = x_end, x_begin
        if state.y_reverse:
            y_begin, y_end = y_end, y_begin
        self.layer.axis("x").set_limits(x_begin, x_end, 1.0)
        self.layer.axis("y").set_limits(y_begin, y_end, 1.0)
        self.layer.set_int("x.label.type", 10)
        self.layer.set_int("y.label.type", 10)
        self.layer.set_str("x.label.string", _ticks(grid.column_labels))
        self.layer.set_str("y.label.string", _ticks(grid.row_labels))
        self._axis_label("x", state.x_label)
        self._axis_label("y", state.y_label)
        title = self.layer.label(_TITLE)
        if title is None and state.title:
            title = self.layer.add_label(state.title, 40, 2)
            if title is None:
                raise RuntimeError("Origin could not create S61 title")
            title.name = _TITLE
        if title is not None:
            title.text = state.title
            title.set_int("show", int(bool(state.title)))
        self.layer.rescale()

    def save(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output))

    def verify(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> EngineReadback:
        grid = s61_confusion_grid(document, data)
        state = self._state(document, actions, grid)
        expected = np.asarray(grid.values, dtype=float)
        actual = np.asarray(self.sheet.to_np2d(), dtype=float)
        if actual.shape != expected.shape or not np.allclose(actual, expected, rtol=0, atol=0):
            raise RuntimeError("Origin S61 counts differ after reopen")
        if bool(self.plot.get_int("label.show")) != state.show_counts:
            raise RuntimeError("Origin S61 count labels differ after reopen")
        token = document.plot_id.removeprefix("plot:")
        return EngineReadback(
            document=document_ref(document),
            backend="origin",
            objects=(
                EngineObjectRef(
                    semantic_id=document.plot_id,
                    backend="origin",
                    object_kind="graph",
                    native_ref=f"graph:{self.graph.name}",
                ),
                EngineObjectRef(
                    semantic_id=f"axis:{token}.x",
                    backend="origin",
                    object_kind="axis",
                    native_ref=f"graph:{self.graph.name}.layer:1.axis:x",
                ),
                EngineObjectRef(
                    semantic_id=f"axis:{token}.y",
                    backend="origin",
                    object_kind="axis",
                    native_ref=f"graph:{self.graph.name}.layer:1.axis:y",
                ),
                EngineObjectRef(
                    semantic_id=f"series:{token}.matrix",
                    backend="origin",
                    object_kind="confusion_matrix",
                    native_ref=f"graph:{self.graph.name}.layer:1.matrix_plot:1",
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(cast(JsonValue, asdict(state))),
        )

    def _write(self, grid: K20Grid) -> None:
        self.sheet.from_np(np.asarray(grid.values, dtype=float))
        self.sheet.xymap = (
            1.0,
            float(len(grid.column_labels)),
            1.0,
            float(len(grid.row_labels)),
        )

    def _axis_label(self, axis: str, text: str) -> None:
        label = self.layer.label("xb" if axis == "x" else "yl") or self.layer.add_label(text)
        if label is None:
            raise RuntimeError("Origin S61 template has no writable axis label")
        label.text = text
        label.set_int("show", 1)

    @staticmethod
    def _state(
        document: PlotDocument, actions: tuple[PlotEngineAction, ...], grid: K20Grid
    ) -> _State:
        token = document.plot_id.removeprefix("plot:")
        state = _State(x_label=grid.column_field_name, y_label=grid.row_field_name)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                axis = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
                if (
                    axis is None
                    or action.scale not in {None, "categorical"}
                    or action.minimum is not None
                ):
                    raise ValueError("S61 axes expose labels and reverse only")
                if axis == "x":
                    state = replace(
                        state,
                        x_label=state.x_label if action.label is None else action.label,
                        x_reverse=state.x_reverse if action.reverse is None else action.reverse,
                    )
                else:
                    state = replace(
                        state,
                        y_label=state.y_label if action.label is None else action.label,
                        y_reverse=state.y_reverse if action.reverse is None else action.reverse,
                    )
            elif isinstance(action, SetChartParameter):
                if (
                    action.target != document.plot_id
                    or action.parameter != "show_counts"
                    or not isinstance(action.value, bool)
                ):
                    raise ValueError("S61 show_counts must be boolean")
                state = replace(state, show_counts=action.value)
            else:
                raise ValueError(f"Origin S61 cannot apply {action.operation}")
        return state


def execute_s61_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    project = S61OriginProject(op)
    project.create(install_dir, request.document, request.data)
    project.reconcile(request.document, request.actions, request.data)
    project.save(output)
    reopened = S61OriginProject(op)
    reopened.open(output)
    return reopened.verify(request.document, request.actions, request.data)
