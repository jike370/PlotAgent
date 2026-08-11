"""Official-template Origin binder for K22 contour matrices."""

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
from plotagent.engine.profile_data import RegularGridData, k22_regular_grid
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K22_ORIGIN_PROFILE, OriginTemplateProfile, resolve_official_template

_TITLE_NAME = "_ENGINE_TITLE"


@dataclass(frozen=True, slots=True)
class _MatrixState:
    title: str
    x_label: str
    y_label: str
    x_reverse: bool = False
    y_reverse: bool = False
    levels: int = 12
    x_minimum: float | None = None
    x_maximum: float | None = None
    y_minimum: float | None = None
    y_maximum: float | None = None


@dataclass(frozen=True, slots=True)
class _Definition:
    profile_id: str
    template: OriginTemplateProfile
    plot_type: int
    object_kind: str


_K22 = _Definition("K22", K22_ORIGIN_PROFILE, 226, "filled_contour")


class AdvancedMatrixOriginProject:
    def __init__(self, op: Any, definition: _Definition) -> None:
        self.op = op
        self.definition = definition
        self.graph: Any = None
        self.layer: Any = None
        self.plot: Any = None
        self.sheet: Any = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, self.definition.template)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("m", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError(
                f"Origin could not create the {self.definition.profile_id} matrixbook"
            )
        self.sheet = book[0]
        self._write_default(document, data)
        self.graph = self.op.new_graph(
            f"G{token}", template=str(template.with_suffix(template.suffix.lower())), hidden=True
        )
        if self.graph is None:
            raise RuntimeError(
                f"Origin could not create {self.definition.profile_id} from the official template"
            )
        self.layer = self.graph[0]
        self.plot = self.layer.add_mplot(self.sheet, 0, type=self.definition.plot_type)
        if self.plot is None:
            raise RuntimeError(f"Origin template rejected the {self.definition.profile_id} matrix")
        self.layer.rescale()

    def open(self, project_path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=False, asksave=False):
            raise RuntimeError(
                f"Origin could not open the previous {self.definition.profile_id} project"
            )
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("m"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError(
                f"{self.definition.profile_id} project must contain one graph and one matrixbook"
            )
        self.graph = graphs[0]
        self.layer = self.graph[0]
        plots = self.layer.plot_list()
        if len(plots) != 1:
            raise RuntimeError(f"{self.definition.profile_id} must contain one native matrix plot")
        self.plot = plots[0]
        self.sheet = books[0][0]

    def apply(self, document: PlotDocument, action: PlotEngineAction, data: EngineDataView) -> None:
        token = document.plot_id.removeprefix("plot:")
        if isinstance(action, (CreatePlot, BindFields, SetChartParameter)):
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError(f"{self.definition.profile_id} title target does not belong")
            self._set_title(action.text)
            return
        if isinstance(action, SetAxis):
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
            if axis_name is None:
                raise ValueError(f"{self.definition.profile_id} axis target does not belong")
            if action.scale not in {None, "linear"}:
                raise ValueError(
                    f"Origin {self.definition.profile_id} {axis_name} axis "
                    "requires linear"
                )
            if action.label is not None:
                self._set_axis_label(axis_name, action.label)
            return
        raise ValueError(
            f"Origin {self.definition.profile_id} binder cannot apply {action.operation}"
        )

    def reconcile(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> None:
        grid22 = k22_regular_grid(document, data)
        state = self._state(document, actions, grid22.x_field_name, grid22.y_field_name)
        self.sheet.from_np(np.asarray(grid22.z_values, dtype=float))
        self.sheet.xymap = (
            grid22.x_values[0],
            grid22.x_values[-1],
            grid22.y_values[0],
            grid22.y_values[-1],
        )
        self._configure_k22(grid22, state)
        self._set_title(state.title)

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output_path))
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError(
                f"Origin did not save a non-empty {self.definition.profile_id} project"
            )

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        grid22 = k22_regular_grid(document, data)
        state = self._state(document, actions, grid22.x_field_name, grid22.y_field_name)
        expected = np.asarray(grid22.z_values, dtype=float)
        levels = tuple(float(value) for value in self.plot.zlevels["levels"])
        if len(levels) != state.levels + 1:
            raise RuntimeError("Origin K22 contour levels differ after reopen")
        actual = np.asarray(self.sheet.to_np2d(), dtype=float)
        if actual.shape != expected.shape or not np.allclose(
            actual, expected, rtol=0, atol=1e-12, equal_nan=True
        ):
            raise RuntimeError(f"Origin {self.definition.profile_id} matrix differs after reopen")
        self._assert_state(state)
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
                    object_kind=self.definition.object_kind,
                    native_ref=f"graph:{self.graph.name}.layer:1.matrix_plot:1",
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(cast(JsonValue, asdict(state))),
        )

    def _write_default(self, document: PlotDocument, data: EngineDataView) -> None:
        grid22 = k22_regular_grid(document, data)
        self.sheet.from_np(np.asarray(grid22.z_values, dtype=float))
        self.sheet.xymap = (
            grid22.x_values[0],
            grid22.x_values[-1],
            grid22.y_values[0],
            grid22.y_values[-1],
        )

    def _configure_k22(self, grid: RegularGridData, state: _MatrixState) -> None:
        x_begin = grid.x_values[0] if state.x_minimum is None else state.x_minimum
        x_end = grid.x_values[-1] if state.x_maximum is None else state.x_maximum
        y_begin = grid.y_values[0] if state.y_minimum is None else state.y_minimum
        y_end = grid.y_values[-1] if state.y_maximum is None else state.y_maximum
        if state.x_reverse:
            x_begin, x_end = x_end, x_begin
        if state.y_reverse:
            y_begin, y_end = y_end, y_begin
        self.layer.axis("x").set_limits(x_begin, x_end)
        self.layer.axis("y").set_limits(y_begin, y_end)
        self._set_axis_label("x", state.x_label)
        self._set_axis_label("y", state.y_label)
        z_min = min(value for row in grid.z_values for value in row)
        z_max = max(value for row in grid.z_values for value in row)
        self.plot.zlevels = {
            "minors": 0,
            "levels": np.linspace(z_min, z_max, state.levels + 1).tolist(),
        }

    def _set_title(self, text: str) -> None:
        title = self.layer.label(_TITLE_NAME)
        if title is None and text:
            title = self.layer.add_label(text, 40, 2)
            if title is None:
                raise RuntimeError("Origin could not create the matrix title")
            title.name = _TITLE_NAME
        if title is not None:
            title.text = text
            title.set_int("show", int(bool(text)))

    def _set_axis_label(self, axis_name: str, text: str) -> None:
        label = self.layer.label("xb" if axis_name == "x" else "yl")
        if label is None:
            label = self.layer.add_label(text)
        if label is None:
            raise RuntimeError("Origin matrix template has no writable axis label")
        label.text = text
        label.set_int("show", 1)

    def _assert_state(self, state: _MatrixState) -> None:
        title = self.layer.label(_TITLE_NAME)
        if state.title and (
            title is None or title.text != state.title or not title.get_int("show")
        ):
            raise RuntimeError("Origin matrix title did not survive readback")
        for axis_name, expected in (("x", state.x_label), ("y", state.y_label)):
            label = self.layer.label("xb" if axis_name == "x" else "yl")
            if label is None or label.text != expected:
                raise RuntimeError("Origin matrix axis label did not survive readback")

    def _state(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        x_name: str,
        y_name: str,
    ) -> _MatrixState:
        token = document.plot_id.removeprefix("plot:")
        state = _MatrixState(title="", x_label=x_name, y_label=y_name)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("matrix title target does not belong to this plot")
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
                if axis_name is None:
                    raise ValueError("matrix axis target does not belong to this plot")
                if action.scale not in {None, "linear"}:
                    raise ValueError(f"matrix {axis_name} axis requires linear")
                if axis_name == "x":
                    state = replace(
                        state,
                        x_label=state.x_label if action.label is None else action.label,
                        x_reverse=(
                            state.x_reverse if action.reverse is None else action.reverse
                        ),
                        x_minimum=action.minimum,
                        x_maximum=action.maximum,
                    )
                else:
                    state = replace(
                        state,
                        y_label=state.y_label if action.label is None else action.label,
                        y_reverse=(
                            state.y_reverse if action.reverse is None else action.reverse
                        ),
                        y_minimum=action.minimum,
                        y_maximum=action.maximum,
                    )
            elif isinstance(action, SetChartParameter):
                if action.target != document.plot_id:
                    raise ValueError("matrix parameter target does not belong to this plot")
                if (
                    action.parameter != "levels"
                    or isinstance(action.value, bool)
                    or not isinstance(action.value, int)
                    or not 2 <= action.value <= 64
                ):
                    raise ValueError("K22 levels must be an integer from 2 to 64")
                state = replace(state, levels=action.value)
            else:
                raise ValueError(
                    f"Origin {self.definition.profile_id} binder cannot apply {action.operation}"
                )
        return state


class K22OriginProject(AdvancedMatrixOriginProject):
    def __init__(self, op: Any) -> None:
        super().__init__(op, _K22)


def _execute(
    project: AdvancedMatrixOriginProject,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
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
    project.open(output)
    return project.verify(request.document, request.actions, request.data)


def execute_k22_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(K22OriginProject(op), request, install_dir, output)
