"""K20 official Heat_Map template binder with native matrix readback."""

from __future__ import annotations

import math
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
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import K20Grid, k20_grid
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K20_ORIGIN_PROFILE, resolve_official_template

_TITLE_NAME = "_ENGINE_TITLE"


@dataclass(frozen=True, slots=True)
class _K20State:
    title: str
    x_label: str
    y_label: str
    x_reverse: bool = False
    y_reverse: bool = False


def _origin_tick_string(labels: tuple[str, ...]) -> str:
    return " ".join(
        f'"{label.replace(chr(34), chr(92) + chr(34)).replace(chr(10), " ")}"'
        for label in labels
    )


class K20OriginProject:
    """Bind one PlotDocument to a native Origin matrixbook and heat-map page."""

    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.plot: Any = None
        self.sheet: Any = None

    def create(
        self,
        install_dir: Path,
        document: PlotDocument,
        data: EngineDataView,
    ) -> None:
        template = resolve_official_template(install_dir, K20_ORIGIN_PROFILE)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("m", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the K20 matrixbook")
        self.sheet = book[0]
        grid = self._write_matrix(document, data)
        argument = template.with_suffix(template.suffix.lower())
        self.graph = self.op.new_graph(f"G{token}", template=str(argument), hidden=True)
        if self.graph is None:
            raise RuntimeError("Origin could not create a graph from Heat_Map.otpu")
        self.layer = self.graph[0]
        self.plot = self.layer.add_mplot(self.sheet, 0, type=105)
        if self.plot is None:
            raise RuntimeError("Origin Heat_Map.otpu rejected the native matrix plot")
        self.layer.rescale()
        self._configure_axes(grid, _K20State("", grid.column_field_name, grid.row_field_name))

    def open(self, project_path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=False, asksave=False):
            raise RuntimeError(f"Origin could not open the previous K20 project: {project_path}")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("m"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("K20 Origin project must contain one graph and one matrixbook")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        plots = self.layer.plot_list()
        if len(plots) != 1:
            raise RuntimeError("K20 Origin project must contain one native matrix plot")
        self.plot = plots[0]
        self.sheet = books[0][0]

    def apply(
        self,
        document: PlotDocument,
        action: PlotEngineAction,
        data: EngineDataView,
    ) -> None:
        token = document.plot_id.removeprefix("plot:")
        if isinstance(action, CreatePlot):
            return
        if isinstance(action, BindFields):
            self._write_matrix(document, data)
            self.layer.rescale()
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError("K20 title target does not belong to this plot")
            self._set_title(action.text)
            return
        if isinstance(action, SetAxis):
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
            if axis_name is None:
                raise ValueError("K20 axis target does not belong to this plot")
            if action.scale not in {None, "categorical"}:
                raise ValueError("Origin K20 axes support only categorical scale")
            if action.minimum is not None or action.maximum is not None:
                raise ValueError("Origin K20 public axes do not expose numeric bounds")
            if action.label is not None:
                self._set_axis_label(axis_name, action.label)
            return
        raise ValueError(f"Origin K20 binder cannot apply {action.operation}")

    def reconcile(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> None:
        grid = k20_grid(document, data)
        state = self._state(document, actions, grid)
        self._set_title(state.title)
        self._configure_axes(grid, state)

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output_path))
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError("Origin did not save a non-empty K20 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        grid = k20_grid(document, data)
        expected = np.asarray(grid.values, dtype=float)
        actual = np.asarray(self.sheet.to_np2d(), dtype=float)
        if actual.shape != expected.shape or not np.allclose(
            actual,
            expected,
            rtol=0,
            atol=1e-12,
            equal_nan=True,
        ):
            raise RuntimeError("Origin K20 matrix values differ after reopen")
        expected_map = (1.0, float(len(grid.column_labels)), 1.0, float(len(grid.row_labels)))
        if any(
            not math.isclose(float(observed), wanted, rel_tol=0, abs_tol=1e-12)
            for observed, wanted in zip(self.sheet.xymap, expected_map, strict=True)
        ):
            raise RuntimeError("Origin K20 matrix coordinate map differs after reopen")

        state = self._state(document, actions, grid)
        self._assert_state(grid, state)
        token = document.plot_id.removeprefix("plot:")
        objects = (
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
                semantic_id=f"series:{token}.primary",
                backend="origin",
                object_kind="heatmap_series",
                native_ref=f"graph:{self.graph.name}.layer:1.matrix_plot:1",
            ),
        )
        return EngineReadback(
            document=document_ref(document),
            backend="origin",
            objects=objects,
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(cast(JsonValue, asdict(state))),
        )

    def _write_matrix(self, document: PlotDocument, data: EngineDataView) -> K20Grid:
        grid = k20_grid(document, data)
        self.sheet.from_np(np.asarray(grid.values, dtype=float))
        self.sheet.xymap = (
            1.0,
            float(len(grid.column_labels)),
            1.0,
            float(len(grid.row_labels)),
        )
        return grid

    def _configure_axes(self, grid: K20Grid, state: _K20State) -> None:
        x_begin, x_end = 0.5, len(grid.column_labels) + 0.5
        y_begin, y_end = len(grid.row_labels) + 0.5, 0.5
        if state.x_reverse:
            x_begin, x_end = x_end, x_begin
        if state.y_reverse:
            y_begin, y_end = y_end, y_begin
        self.layer.axis("x").set_limits(x_begin, x_end, 1.0)
        self.layer.axis("y").set_limits(y_begin, y_end, 1.0)
        self.layer.set_int("x.label.type", 10)
        self.layer.set_int("y.label.type", 10)
        self.layer.set_str("x.label.string", _origin_tick_string(grid.column_labels))
        self.layer.set_str("y.label.string", _origin_tick_string(grid.row_labels))
        self._set_axis_label("x", state.x_label)
        self._set_axis_label("y", state.y_label)

    def _set_title(self, text: str) -> None:
        title = self.layer.label(_TITLE_NAME)
        if title is None and text:
            title = self.layer.add_label(text, 40, 2)
            if title is None:
                raise RuntimeError("Origin could not create the K20 title")
            title.name = _TITLE_NAME
        if title is not None:
            title.text = text
            title.set_int("show", int(bool(text)))

    def _set_axis_label(self, axis_name: str, text: str) -> None:
        label = self.layer.label("xb" if axis_name == "x" else "yl")
        if label is None:
            label = self.layer.add_label(text)
        if label is None:
            raise RuntimeError("Origin K20 template has no writable axis label")
        label.text = text
        label.set_int("show", 1)

    def _assert_state(self, grid: K20Grid, state: _K20State) -> None:
        title = self.layer.label(_TITLE_NAME)
        if state.title:
            if title is None or title.text != state.title or not title.get_int("show"):
                raise RuntimeError("Origin K20 title did not survive readback")
        elif title is not None and title.get_int("show"):
            raise RuntimeError("Origin K20 empty title is unexpectedly visible")
        for axis_name, axis_label, labels, reverse in (
            ("x", state.x_label, grid.column_labels, state.x_reverse),
            ("y", state.y_label, grid.row_labels, state.y_reverse),
        ):
            if self.layer.get_int(f"{axis_name}.label.type") != 10:
                raise RuntimeError("Origin K20 categorical tick mode did not survive readback")
            if self.layer.get_str(f"{axis_name}.label.string") != _origin_tick_string(labels):
                raise RuntimeError("Origin K20 category labels did not survive readback")
            label = self.layer.label("xb" if axis_name == "x" else "yl")
            if label is None or label.text != axis_label:
                raise RuntimeError("Origin K20 axis label did not survive readback")
            begin, end, _step = (float(value) for value in self.layer.axis(axis_name).limits)
            expected_descending = (axis_name == "y") != reverse
            if (begin > end) != expected_descending:
                raise RuntimeError("Origin K20 axis direction did not survive readback")

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        grid: K20Grid,
    ) -> _K20State:
        token = document.plot_id.removeprefix("plot:")
        state = _K20State("", grid.column_field_name, grid.row_field_name)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("K20 title target does not belong to this plot")
                state = replace(state, title=action.text)
                continue
            if isinstance(action, SetAxis):
                axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(
                    action.target
                )
                if axis_name is None:
                    raise ValueError("K20 axis target does not belong to this plot")
                if action.scale not in {None, "categorical"}:
                    raise ValueError("Origin K20 axes support only categorical scale")
                if action.minimum is not None or action.maximum is not None:
                    raise ValueError("Origin K20 public axes do not expose numeric bounds")
                if axis_name == "x":
                    state = replace(
                        state,
                        x_label=state.x_label if action.label is None else action.label,
                        x_reverse=(
                            state.x_reverse if action.reverse is None else action.reverse
                        ),
                    )
                else:
                    state = replace(
                        state,
                        y_label=state.y_label if action.label is None else action.label,
                        y_reverse=(
                            state.y_reverse if action.reverse is None else action.reverse
                        ),
                    )
                continue
            raise ValueError(f"Origin K20 binder cannot apply {action.operation}")
        return state


def execute_k20_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = K20OriginProject(op)
    if request.previous_opju is None:
        project.create(install_dir, request.document, request.data)
        pending = request.actions
    else:
        project.open(Path(request.previous_opju))
        pending = request.actions[-1:]
    for action in pending:
        project.apply(request.document, action, request.data)
    project.reconcile(request.document, request.actions, request.data)
    project.save(output)

    op.new(asksave=False)
    if not op.open(str(output), readonly=True, asksave=False):
        raise RuntimeError("fresh Origin session could not reopen the staged K20 project")
    reopened = K20OriginProject(op)
    graphs = list(op.pages("g"))
    books = list(op.pages("m"))
    if len(graphs) != 1 or len(books) != 1:
        raise RuntimeError("fresh K20 project has unexpected graph or matrixbook count")
    reopened.graph = graphs[0]
    reopened.layer = reopened.graph[0]
    plots = reopened.layer.plot_list()
    if len(plots) != 1:
        raise RuntimeError("fresh K20 project has an unexpected native plot count")
    reopened.plot = plots[0]
    reopened.sheet = books[0][0]
    return reopened.verify(request.document, request.actions, request.data)
