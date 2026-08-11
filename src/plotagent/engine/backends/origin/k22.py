"""K22 official CONTOUR binder with native matrix and level readback."""

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
    SetChartParameter,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import RegularGridData, k22_regular_grid
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K22_ORIGIN_PROFILE, resolve_official_template
from .trace import origin_trace_step, record_origin_trace

_TITLE_NAME = "_ENGINE_TITLE"


@dataclass(frozen=True, slots=True)
class _K22State:
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


class K22OriginProject:
    """Bind one K22 PlotDocument to an editable native matrix contour."""

    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.plot: Any = None
        self.sheet: Any = None
        self.last_native_structure: dict[str, object] | None = None

    def create(
        self,
        install_dir: Path,
        document: PlotDocument,
        data: EngineDataView,
    ) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={"template_filename": K22_ORIGIN_PROFILE.filename},
        ):
            template = resolve_official_template(install_dir, K22_ORIGIN_PROFILE)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("matrixbook_create"):
            book = self.op.new_book("m", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the K22 matrixbook")
        self.sheet = book[0]
        grid = k22_regular_grid(document, data)
        with origin_trace_step(
            "source_matrix_write",
            details={
                "row_count": len(grid.y_values),
                "column_count": len(grid.x_values),
                "x_field": grid.x_field_name,
                "y_field": grid.y_field_name,
                "z_field": grid.z_field_name,
                "source_values_preserved": True,
            },
        ):
            self._write_grid(grid)
        argument = template.with_suffix(template.suffix.lower())
        with origin_trace_step(
            "official_color_fill_contour_create",
            details={
                "route": "matrixbook + CONTOUR.otpu + add_mplot",
                "template_filename": template.name,
                "native_plot_type": 226,
                "triangulation_used": False,
            },
        ):
            self.graph = self.op.new_graph(
                f"G{token}", template=str(argument), hidden=True
            )
        if self.graph is None:
            raise RuntimeError("Origin could not create a graph from CONTOUR.otpu")
        self.graph.lname = f"K22 Filled Contour / {document.plot_id}"
        self.layer = self.graph[0]
        self.plot = self.layer.add_mplot(self.sheet, 0, type=226)
        if self.plot is None:
            raise RuntimeError("Origin CONTOUR.otpu rejected the native matrix plot")
        self.layer.rescale()
        state = _K22State("", grid.x_field_name, grid.y_field_name)
        self._configure_axes(grid, state)
        self._configure_levels(grid, state)
        self._configure_color_scale(grid)
        native = self._native_structure(grid, state)
        self.last_native_structure = native
        record_origin_trace("native_matrix_contour_confirmed", "completed", details=native)

    def open(self, project_path: Path, *, readonly: bool = False) -> None:
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        with origin_trace_step(
            "opju_open", details={"filename": project_path.name, "readonly": readonly}
        ):
            if not self.op.open(str(project_path), readonly=readonly, asksave=False):
                raise RuntimeError(f"Origin could not open the K22 project: {project_path}")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("m"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("K22 project must contain one graph and one matrixbook")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        plots = list(self.layer.plot_list() or [])
        if len(plots) != 1:
            raise RuntimeError("K22 project must contain one native matrix plot")
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
            self._write_grid(k22_regular_grid(document, data))
            self.layer.rescale()
            return
        if isinstance(action, SetChartParameter):
            if (
                action.target != document.plot_id
                or action.parameter != "levels"
                or isinstance(action.value, bool)
                or not isinstance(action.value, int)
                or not 2 <= action.value <= 64
            ):
                raise ValueError("K22 levels must be an integer from 2 to 64")
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError("K22 title target does not belong to this plot")
            self._set_title(action.text)
            return
        if isinstance(action, SetAxis):
            axis_name = {
                f"axis:{token}.x": "x",
                f"axis:{token}.y": "y",
            }.get(action.target)
            if axis_name is None:
                raise ValueError("K22 axis target does not belong to this plot")
            if action.scale not in {None, "linear"}:
                raise ValueError("Origin K22 axes require linear scale")
            if action.label is not None:
                self._set_axis_label(axis_name, action.label)
            return
        raise ValueError(f"Origin K22 binder cannot apply {action.operation}")

    def reconcile(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> None:
        grid = k22_regular_grid(document, data)
        state = self._state(document, actions, grid)
        self._write_grid(grid)
        self.layer.rescale()
        self._set_title(state.title)
        self._configure_axes(grid, state)
        self._configure_levels(grid, state)
        self._configure_color_scale(grid)

    def save(self, output_path: Path) -> None:
        with origin_trace_step("opju_save", details={"filename": output_path.name}):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.exists():
                raise FileExistsError(
                    f"Origin refuses to overwrite existing K22 artifact: {output_path}"
                )
            self.op.save(str(output_path))
            if not output_path.is_file() or output_path.stat().st_size <= 0:
                raise RuntimeError("Origin did not save a non-empty K22 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        grid = k22_regular_grid(document, data)
        expected = np.asarray(grid.z_values, dtype=float)
        actual = np.asarray(self.sheet.to_np2d(), dtype=float)
        if actual.shape != expected.shape or not np.allclose(
            actual, expected, rtol=0, atol=1e-12, equal_nan=True
        ):
            raise RuntimeError("Origin K22 source matrix differs after reopen")
        expected_map = (
            grid.x_values[0],
            grid.x_values[-1],
            grid.y_values[0],
            grid.y_values[-1],
        )
        if any(
            not math.isclose(float(observed), wanted, rel_tol=0, abs_tol=1e-12)
            for observed, wanted in zip(self.sheet.xymap, expected_map, strict=True)
        ):
            raise RuntimeError("Origin K22 matrix coordinate map differs after reopen")

        state = self._state(document, actions, grid)
        self._assert_state(grid, state)
        native = self._native_structure(grid, state)
        self.last_native_structure = native
        token = document.plot_id.removeprefix("plot:")
        color_scale_name = cast(str, native["color_scale_name"])
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
                    object_kind="filled_contour",
                    native_ref=f"graph:{self.graph.name}.layer:1.matrix_plot:1",
                ),
                EngineObjectRef(
                    semantic_id=f"legend:{token}.colorbar",
                    backend="origin",
                    object_kind="colorbar",
                    native_ref=(
                        f"graph:{self.graph.name}.layer:1.graph_object:{color_scale_name}"
                    ),
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(
                cast(JsonValue, {"state": asdict(state), "native_structure": native})
            ),
        )

    def _write_grid(self, grid: RegularGridData) -> None:
        self.sheet.from_np(np.asarray(grid.z_values, dtype=float))
        self.sheet.xymap = (
            grid.x_values[0],
            grid.x_values[-1],
            grid.y_values[0],
            grid.y_values[-1],
        )

    def _configure_levels(self, grid: RegularGridData, state: _K22State) -> None:
        z_min = min(value for row in grid.z_values for value in row)
        z_max = max(value for row in grid.z_values for value in row)
        self.plot.zlevels = {
            "minors": 0,
            "levels": np.linspace(z_min, z_max, state.levels + 1).tolist(),
        }

    def _configure_color_scale(self, grid: RegularGridData) -> None:
        label = (
            grid.z_field_name
            if grid.z_unit is None
            else f"{grid.z_field_name} ({grid.z_unit})"
        )
        self.graph.activate()
        if not self.op.set_lt_str("__K22CSTITLE", label):
            raise RuntimeError("Origin could not stage the K22 color-scale title")
        if not self.op.lt_exec(
            "page.active=1; Spectrum1.title=1; Spectrum1.title$=__K22CSTITLE$;"
        ):
            raise RuntimeError("Origin could not set the K22 color-scale title")

    def _native_structure(
        self, grid: RegularGridData, state: _K22State
    ) -> dict[str, object]:
        self.graph.activate()
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe K22 graph name for native readback: {graph_name!r}")
        if not self.op.lt_exec(
            "page.active=1; layer -c; __K22COUNT=count; "
            f"range __K22P=[{graph_name}]1!1; get __K22P -pt __K22PID;"
        ):
            raise RuntimeError("Origin could not read the native K22 structure")
        plot_count = int(self.op.lt_float("__K22COUNT"))
        plot_type = int(self.op.lt_float("__K22PID"))
        plots = list(self.layer.plot_list() or [])
        if len(self.graph) != 1 or plot_count != 1 or len(plots) != 1 or plot_type != 226:
            raise RuntimeError("Origin K22 must retain one native PID 226 matrix contour")
        matrix_dataset = str(self.sheet.obj[0].DatasetName)
        plot_dataset = str(plots[0].obj.DatasetName)
        if not matrix_dataset or plot_dataset != matrix_dataset:
            raise RuntimeError("Origin K22 lost its native matrix source binding")

        observed_levels = tuple(float(value) for value in self.plot.zlevels["levels"])
        z_min = min(value for row in grid.z_values for value in row)
        z_max = max(value for row in grid.z_values for value in row)
        expected_levels = tuple(
            float(value) for value in np.linspace(z_min, z_max, state.levels + 1)
        )
        if len(observed_levels) != len(expected_levels) or not np.allclose(
            observed_levels, expected_levels, rtol=0, atol=1e-12
        ):
            raise RuntimeError("Origin K22 contour levels differ after readback")

        color_scales = [
            graph_object
            for graph_object in self.layer.obj.GraphObjects
            if int(graph_object.GetObjectType()) == 13
        ]
        if len(color_scales) != 1:
            raise RuntimeError("Origin K22 must retain one native color scale object")
        return {
            "layer_count": len(self.graph),
            "plot_count": plot_count,
            "native_plot_type": plot_type,
            "matrix_dataset": matrix_dataset,
            "plot_dataset": plot_dataset,
            "matrix_shape": [len(grid.y_values), len(grid.x_values)],
            "matrix_xymap": [
                grid.x_values[0],
                grid.x_values[-1],
                grid.y_values[0],
                grid.y_values[-1],
            ],
            "contour_interval_count": state.levels,
            "contour_boundary_count": len(observed_levels),
            "contour_minimum": observed_levels[0],
            "contour_maximum": observed_levels[-1],
            "color_scale_name": str(color_scales[0].Name),
            "color_scale_object_type": 13,
            "triangulation_used": False,
        }

    def _configure_axes(self, grid: RegularGridData, state: _K22State) -> None:
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

    def _set_title(self, text: str) -> None:
        title = self.layer.label(_TITLE_NAME)
        if title is None and text:
            self.layer.activate()
            if not self.layer.obj.LT_execute(
                f"label -j 1 -n {_TITLE_NAME} PlotAgentTitlePlaceholder;"
            ):
                raise RuntimeError("Origin could not create the K22 title")
            title = self.layer.label(_TITLE_NAME)
            if title is None:
                raise RuntimeError("Origin could not create the K22 title")
        if title is not None:
            title.text = text
            title.set_int("attach", 1)
            title.set_float("x1", 0.5)
            title.set_float("y1", 0.012)
            title.set_int("fsize", 14)
            title.set_int("fstyle", 0)
            title.set_int("background", 0)
            title.set_int("show", int(bool(text)))

    def _set_axis_label(self, axis_name: str, text: str) -> None:
        label = self.layer.label("xb" if axis_name == "x" else "yl")
        if label is None:
            label = self.layer.add_label(text)
        if label is None:
            raise RuntimeError("Origin K22 template has no writable axis label")
        label.text = text
        label.set_int("show", 1)

    def _assert_state(self, grid: RegularGridData, state: _K22State) -> None:
        title = self.layer.label(_TITLE_NAME)
        if state.title:
            if title is None or title.text != state.title or not title.get_int("show"):
                raise RuntimeError("Origin K22 title did not survive readback")
        elif title is not None and title.get_int("show"):
            raise RuntimeError("Origin K22 empty title is unexpectedly visible")
        for axis_name, axis_label, default_min, default_max, fixed_min, fixed_max, reverse in (
            (
                "x",
                state.x_label,
                grid.x_values[0],
                grid.x_values[-1],
                state.x_minimum,
                state.x_maximum,
                state.x_reverse,
            ),
            (
                "y",
                state.y_label,
                grid.y_values[0],
                grid.y_values[-1],
                state.y_minimum,
                state.y_maximum,
                state.y_reverse,
            ),
        ):
            label = self.layer.label("xb" if axis_name == "x" else "yl")
            if label is None or label.text != axis_label:
                raise RuntimeError("Origin K22 axis label did not survive readback")
            expected_begin = default_min if fixed_min is None else fixed_min
            expected_end = default_max if fixed_max is None else fixed_max
            if reverse:
                expected_begin, expected_end = expected_end, expected_begin
            begin, end = (
                float(value) for value in self.layer.axis(axis_name).limits[:2]
            )
            if not math.isclose(begin, expected_begin, rel_tol=0, abs_tol=1e-10):
                raise RuntimeError("Origin K22 axis beginning differs after readback")
            if not math.isclose(end, expected_end, rel_tol=0, abs_tol=1e-10):
                raise RuntimeError("Origin K22 axis ending differs after readback")

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        grid: RegularGridData,
    ) -> _K22State:
        token = document.plot_id.removeprefix("plot:")
        state = _K22State("", grid.x_field_name, grid.y_field_name)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("K22 title target does not belong to this plot")
                state = replace(state, title=action.text)
                continue
            if isinstance(action, SetAxis):
                axis_name = {
                    f"axis:{token}.x": "x",
                    f"axis:{token}.y": "y",
                }.get(action.target)
                if axis_name is None:
                    raise ValueError("K22 axis target does not belong to this plot")
                if action.scale not in {None, "linear"}:
                    raise ValueError("Origin K22 axes require linear scale")
                if axis_name == "x":
                    state = replace(
                        state,
                        x_label=state.x_label if action.label is None else action.label,
                        x_minimum=action.minimum,
                        x_maximum=action.maximum,
                        x_reverse=(
                            state.x_reverse if action.reverse is None else action.reverse
                        ),
                    )
                else:
                    state = replace(
                        state,
                        y_label=state.y_label if action.label is None else action.label,
                        y_minimum=action.minimum,
                        y_maximum=action.maximum,
                        y_reverse=(
                            state.y_reverse if action.reverse is None else action.reverse
                        ),
                    )
                continue
            if isinstance(action, SetChartParameter):
                if (
                    action.target != document.plot_id
                    or action.parameter != "levels"
                    or isinstance(action.value, bool)
                    or not isinstance(action.value, int)
                    or not 2 <= action.value <= 64
                ):
                    raise ValueError("K22 levels must be an integer from 2 to 64")
                state = replace(state, levels=action.value)
                continue
            raise ValueError(f"Origin K22 binder cannot apply {action.operation}")
        return state


def execute_k22_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = K22OriginProject(op)
    if request.previous_opju is None:
        project.create(install_dir, request.document, request.data)
        pending = request.actions
    else:
        project.open(Path(request.previous_opju))
        pending = request.actions[-1:]
    with origin_trace_step(
        "agent_actions_apply", details={"action_count": len(pending)}
    ):
        for action in pending:
            with origin_trace_step(
                "agent_action_apply",
                details=cast(dict[str, object], action.model_dump(exclude_none=True)),
            ):
                project.apply(request.document, action, request.data)
        project.reconcile(request.document, request.actions, request.data)
    project.save(output)
    reopened = K22OriginProject(op)
    reopened.open(output, readonly=True)
    with origin_trace_step("reopened_native_structure_verify"):
        return reopened.verify(request.document, request.actions, request.data)
