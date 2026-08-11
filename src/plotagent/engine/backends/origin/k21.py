"""K21 official Heat_Map_With_Labels binder with native matrix readback."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal, cast

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
from plotagent.engine.profile_data import K20Grid, k21_correlation_grid
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K21_ORIGIN_PROFILE, resolve_official_template
from .trace import origin_trace_step, record_origin_trace

_TITLE_NAME = "_ENGINE_TITLE"

# Verified against the shipped Origin 2024 Heat_Map_With_Labels.otpu theme.
# FillDispl and LabelDispl are distinct native Plot Details properties.
_TRIANGLE_THEME: dict[str, tuple[int, int]] = {
    "full": (1, 0),
    # Origin names these enum pairs in native bottom-up matrix coordinates.
    # K21 presents the first supplied row at the top, so the user-facing
    # lower/upper display directions intentionally use the opposite pair.
    "lower": (4, 2),
    "upper": (2, 1),
}


@dataclass(frozen=True, slots=True)
class _K21State:
    title: str
    x_label: str
    y_label: str
    x_reverse: bool = False
    y_reverse: bool = False
    triangle: Literal["full", "lower", "upper"] = "full"


def _origin_tick_string(labels: tuple[str, ...]) -> str:
    return " ".join(
        f'"{label.replace(chr(34), chr(92) + chr(34)).replace(chr(10), " ")}"'
        for label in labels
    )


def _display_labels(
    labels: tuple[str, ...], begin: float, end: float
) -> tuple[str, ...]:
    return tuple(reversed(labels)) if begin > end else labels


def _theme_child(parent: Any, name: str) -> Any:
    try:
        return next(child for child in parent.Children if str(child.Name) == name)
    except StopIteration as error:
        raise RuntimeError(f"Origin K21 theme is missing {name}") from error


class K21OriginProject:
    """Bind one K21 PlotDocument to an editable native Origin matrix plot."""

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
            details={"template_filename": K21_ORIGIN_PROFILE.filename},
        ):
            template = resolve_official_template(install_dir, K21_ORIGIN_PROFILE)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("matrixbook_create"):
            book = self.op.new_book("m", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the K21 matrixbook")
        self.sheet = book[0]
        grid = k21_correlation_grid(document, data)
        with origin_trace_step(
            "source_matrix_write",
            details={
                "row_count": len(grid.row_labels),
                "column_count": len(grid.column_labels),
                "row_field": grid.row_field_name,
                "column_field": grid.column_field_name,
                "value_field": grid.value_field_name,
                "source_values_preserved": True,
            },
        ):
            self._write_grid(grid)
        argument = template.with_suffix(template.suffix.lower())
        with origin_trace_step(
            "official_heatmap_with_labels_create",
            details={
                "route": (
                    "matrixbook + Heat_Map_With_Labels.otpu + add_mplot"
                ),
                "template_filename": template.name,
                "native_plot_type": 105,
            },
        ):
            self.graph = self.op.new_graph(
                f"G{token}", template=str(argument), hidden=True
            )
        if self.graph is None:
            raise RuntimeError(
                "Origin could not create a graph from Heat_Map_With_Labels.otpu"
            )
        self.graph.lname = f"K21 Correlation Matrix / {document.plot_id}"
        self.layer = self.graph[0]
        self.plot = self.layer.add_mplot(self.sheet, 0, type=105)
        if self.plot is None:
            raise RuntimeError(
                "Origin Heat_Map_With_Labels.otpu rejected the native matrix plot"
            )
        self.layer.rescale()
        state = _K21State("", grid.column_field_name, grid.row_field_name)
        self._configure_axes(grid, state)
        self._configure_native_display(state)
        self._configure_colormap(grid)
        native = self._native_structure(state)
        self.last_native_structure = native
        record_origin_trace("native_heatmap_labels_confirmed", "completed", details=native)

    def open(self, project_path: Path, *, readonly: bool = False) -> None:
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        with origin_trace_step(
            "opju_open", details={"filename": project_path.name, "readonly": readonly}
        ):
            if not self.op.open(str(project_path), readonly=readonly, asksave=False):
                raise RuntimeError(f"Origin could not open the K21 project: {project_path}")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("m"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("K21 project must contain one graph and one matrixbook")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        plots = list(self.layer.plot_list() or [])
        if len(plots) != 1:
            raise RuntimeError("K21 project must contain one native matrix plot")
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
            self._write_grid(k21_correlation_grid(document, data))
            self.layer.rescale()
            return
        if isinstance(action, SetChartParameter):
            if (
                action.target != document.plot_id
                or action.parameter != "triangle"
                or action.value not in _TRIANGLE_THEME
            ):
                raise ValueError("K21 exposes triangle=full|lower|upper")
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError("K21 title target does not belong to this plot")
            self._set_title(action.text)
            return
        if isinstance(action, SetAxis):
            axis_name = {
                f"axis:{token}.x": "x",
                f"axis:{token}.y": "y",
            }.get(action.target)
            if axis_name is None:
                raise ValueError("K21 axis target does not belong to this plot")
            if action.scale not in {None, "categorical"}:
                raise ValueError("Origin K21 axes support only categorical scale")
            if action.minimum is not None or action.maximum is not None:
                raise ValueError("Origin K21 public axes do not expose numeric bounds")
            if action.label is not None:
                self._set_axis_label(axis_name, action.label)
            return
        raise ValueError(f"Origin K21 binder cannot apply {action.operation}")

    def reconcile(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> None:
        grid = k21_correlation_grid(document, data)
        state = self._state(document, actions, grid)
        self._write_grid(grid)
        self.layer.rescale()
        self._set_title(state.title)
        self._configure_axes(grid, state)
        self._configure_native_display(state)
        self._configure_colormap(grid)

    def save(self, output_path: Path) -> None:
        with origin_trace_step("opju_save", details={"filename": output_path.name}):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.exists():
                raise FileExistsError(
                    f"Origin refuses to overwrite existing K21 artifact: {output_path}"
                )
            self.op.save(str(output_path))
            if not output_path.is_file() or output_path.stat().st_size <= 0:
                raise RuntimeError("Origin did not save a non-empty K21 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        grid = k21_correlation_grid(document, data)
        expected = np.asarray(grid.values, dtype=float)
        actual = np.asarray(self.sheet.to_np2d(), dtype=float)
        if actual.shape != expected.shape or not np.allclose(
            actual, expected, rtol=0, atol=1e-12, equal_nan=True
        ):
            raise RuntimeError("Origin K21 source matrix differs after reopen")
        expected_map = (
            1.0,
            float(len(grid.column_labels)),
            1.0,
            float(len(grid.row_labels)),
        )
        if any(
            not math.isclose(float(observed), wanted, rel_tol=0, abs_tol=1e-12)
            for observed, wanted in zip(self.sheet.xymap, expected_map, strict=True)
        ):
            raise RuntimeError("Origin K21 matrix coordinate map differs after reopen")

        state = self._state(document, actions, grid)
        self._assert_state(grid, state)
        native = self._native_structure(state)
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
                    object_kind="correlation_matrix",
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

    def _write_grid(self, grid: K20Grid) -> None:
        self.sheet.from_np(np.asarray(grid.values, dtype=float))
        self.sheet.xymap = (
            1.0,
            float(len(grid.column_labels)),
            1.0,
            float(len(grid.row_labels)),
        )

    def _configure_native_display(self, state: _K21State) -> None:
        fill_value, label_value = _TRIANGLE_THEME[state.triangle]
        theme = self.plot.obj.GetTheme()
        label = _theme_child(theme, "Label")
        _theme_child(label, "Enable").SetIntValue(1)
        _theme_child(theme, "FillDispl").SetIntValue(fill_value)
        _theme_child(theme, "LabelDispl").SetIntValue(label_value)
        self.plot.obj.PutTheme(theme)

    def _configure_colormap(self, grid: K20Grid) -> None:
        self.graph.activate()
        command = (
            "page.active=1; layer.cmap.type=0; layer.cmap.zmin=-1; "
            "layer.cmap.zmax=1; layer.cmap.numMajorLevels=5; "
            "layer.cmap.numMinorLevels=3; layer.cmap.SetLevels(1); "
            "layer.cmap.updateScale();"
        )
        if not self.op.lt_exec(command):
            raise RuntimeError("Origin could not set the K21 correlation color scale")
        if not self.op.set_lt_str("__K21CSTITLE", grid.value_field_name):
            raise RuntimeError("Origin could not stage the K21 color-scale title")
        if not self.op.lt_exec(
            "page.active=1; Spectrum1.title=1; Spectrum1.title$=__K21CSTITLE$;"
        ):
            raise RuntimeError("Origin could not set the K21 color-scale title")

    def _native_structure(self, state: _K21State) -> dict[str, object]:
        self.graph.activate()
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe K21 graph name for native readback: {graph_name!r}")
        command = (
            "page.active=1; layer -c; __K21COUNT=count; "
            f"range __K21P=[{graph_name}]1!1; get __K21P -pt __K21PID; "
            "__K21ZMIN=layer.cmap.zmin; __K21ZMAX=layer.cmap.zmax; "
            "__K21CMAPTYPE=layer.cmap.type;"
        )
        if not self.op.lt_exec(command):
            raise RuntimeError("Origin could not read the native K21 structure")
        plot_count = int(self.op.lt_float("__K21COUNT"))
        plot_type = int(self.op.lt_float("__K21PID"))
        plots = list(self.layer.plot_list() or [])
        if len(self.graph) != 1 or plot_count != 1 or len(plots) != 1 or plot_type != 105:
            raise RuntimeError("Origin K21 must retain one native PID 105 heatmap")
        matrix_dataset = str(self.sheet.obj[0].DatasetName)
        plot_dataset = str(plots[0].obj.DatasetName)
        if not matrix_dataset or plot_dataset != matrix_dataset:
            raise RuntimeError("Origin K21 lost its native matrix source binding")

        theme = plots[0].obj.GetTheme()
        label = _theme_child(theme, "Label")
        label_enabled = int(_theme_child(label, "Enable").GetValue())
        fill_display = int(_theme_child(theme, "FillDispl").GetValue())
        label_display = int(_theme_child(theme, "LabelDispl").GetValue())
        expected_fill, expected_label = _TRIANGLE_THEME[state.triangle]
        if label_enabled != 1:
            raise RuntimeError("Origin K21 native cell labels are disabled")
        if (fill_display, label_display) != (expected_fill, expected_label):
            raise RuntimeError("Origin K21 triangle display differs after readback")

        z_min = float(self.op.lt_float("__K21ZMIN"))
        z_max = float(self.op.lt_float("__K21ZMAX"))
        cmap_type = int(self.op.lt_float("__K21CMAPTYPE"))
        if not math.isclose(z_min, -1.0, rel_tol=0, abs_tol=1e-12):
            raise RuntimeError("Origin K21 colormap minimum must stay at -1")
        if not math.isclose(z_max, 1.0, rel_tol=0, abs_tol=1e-12):
            raise RuntimeError("Origin K21 colormap maximum must stay at 1")
        if cmap_type not in {0, 1}:
            raise RuntimeError("Origin K21 colormap must remain linear")

        color_scales = [
            graph_object
            for graph_object in self.layer.obj.GraphObjects
            if int(graph_object.GetObjectType()) == 13
        ]
        if len(color_scales) != 1:
            raise RuntimeError("Origin K21 must retain one native color scale object")
        graph_objects = list(self.layer.obj.GraphObjects)
        text_like_objects = [
            item for item in graph_objects if int(item.GetObjectType()) not in {13}
        ]
        return {
            "layer_count": len(self.graph),
            "plot_count": plot_count,
            "native_plot_type": plot_type,
            "matrix_dataset": matrix_dataset,
            "plot_dataset": plot_dataset,
            "native_z_label_contract": (
                "Heat_Map_With_Labels.otpu + matrix source + Label.Enable=1"
            ),
            "label_enabled": label_enabled,
            "triangle": state.triangle,
            "fill_display": fill_display,
            "label_display": label_display,
            "color_scale_minimum": z_min,
            "color_scale_maximum": z_max,
            "color_scale_type": cmap_type,
            "color_scale_name": str(color_scales[0].Name),
            "color_scale_object_type": 13,
            "non_color_scale_graph_object_count": len(text_like_objects),
        }

    def _configure_axes(self, grid: K20Grid, state: _K21State) -> None:
        x_begin, x_end = 0.5, len(grid.column_labels) + 0.5
        y_begin, y_end = len(grid.row_labels) + 0.5, 0.5
        if state.x_reverse:
            x_begin, x_end = x_end, x_begin
        if state.y_reverse:
            y_begin, y_end = y_end, y_begin
        self.layer.axis("x").set_limits(
            x_begin, x_end, -1.0 if x_begin > x_end else 1.0
        )
        self.layer.axis("y").set_limits(
            y_begin, y_end, -1.0 if y_begin > y_end else 1.0
        )
        self.layer.set_int("x.label.type", 10)
        self.layer.set_int("y.label.type", 10)
        self.layer.set_str(
            "x.label.string",
            _origin_tick_string(_display_labels(grid.column_labels, x_begin, x_end)),
        )
        self.layer.set_str(
            "y.label.string",
            _origin_tick_string(_display_labels(grid.row_labels, y_begin, y_end)),
        )
        self._set_axis_label("x", state.x_label)
        self._set_axis_label("y", state.y_label)

    def _set_title(self, text: str) -> None:
        title = self.layer.label(_TITLE_NAME)
        if title is None and text:
            self.layer.activate()
            if not self.layer.obj.LT_execute(
                f"label -j 1 -n {_TITLE_NAME} PlotAgentTitlePlaceholder;"
            ):
                raise RuntimeError("Origin could not create the K21 title")
            title = self.layer.label(_TITLE_NAME)
            if title is None:
                raise RuntimeError("Origin could not create the K21 title")
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
            raise RuntimeError("Origin K21 template has no writable axis label")
        label.text = text
        label.set_int("show", 1)

    def _assert_state(self, grid: K20Grid, state: _K21State) -> None:
        title = self.layer.label(_TITLE_NAME)
        if state.title:
            if title is None or title.text != state.title or not title.get_int("show"):
                raise RuntimeError("Origin K21 title did not survive readback")
        elif title is not None and title.get_int("show"):
            raise RuntimeError("Origin K21 empty title is unexpectedly visible")
        for axis_name, axis_label, labels, reverse in (
            ("x", state.x_label, grid.column_labels, state.x_reverse),
            ("y", state.y_label, grid.row_labels, state.y_reverse),
        ):
            if self.layer.get_int(f"{axis_name}.label.type") != 10:
                raise RuntimeError("Origin K21 categorical tick mode did not survive")
            label = self.layer.label("xb" if axis_name == "x" else "yl")
            if label is None or label.text != axis_label:
                raise RuntimeError("Origin K21 axis label did not survive readback")
            begin, end, step = (
                float(value) for value in self.layer.axis(axis_name).limits
            )
            expected_descending = (axis_name == "y") != reverse
            if (begin > end) != expected_descending:
                raise RuntimeError("Origin K21 axis direction did not survive readback")
            if (step < 0) != expected_descending:
                raise RuntimeError("Origin K21 tick direction did not survive readback")
            expected_labels = _origin_tick_string(_display_labels(labels, begin, end))
            if self.layer.get_str(f"{axis_name}.label.string") != expected_labels:
                raise RuntimeError("Origin K21 category labels did not survive readback")

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        grid: K20Grid,
    ) -> _K21State:
        token = document.plot_id.removeprefix("plot:")
        state = _K21State("", grid.column_field_name, grid.row_field_name)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("K21 title target does not belong to this plot")
                state = replace(state, title=action.text)
                continue
            if isinstance(action, SetAxis):
                axis_name = {
                    f"axis:{token}.x": "x",
                    f"axis:{token}.y": "y",
                }.get(action.target)
                if axis_name is None:
                    raise ValueError("K21 axis target does not belong to this plot")
                if action.scale not in {None, "categorical"}:
                    raise ValueError("Origin K21 axes support only categorical scale")
                if action.minimum is not None or action.maximum is not None:
                    raise ValueError("Origin K21 public axes do not expose numeric bounds")
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
            if isinstance(action, SetChartParameter):
                if (
                    action.target != document.plot_id
                    or action.parameter != "triangle"
                    or action.value not in _TRIANGLE_THEME
                ):
                    raise ValueError("K21 exposes triangle=full|lower|upper")
                state = replace(
                    state,
                    triangle=cast(
                        Literal["full", "lower", "upper"], action.value
                    ),
                )
                continue
            raise ValueError(f"Origin K21 binder cannot apply {action.operation}")
        return state


def execute_k21_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = K21OriginProject(op)
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
    reopened = K21OriginProject(op)
    reopened.open(output, readonly=True)
    with origin_trace_step("reopened_native_structure_verify"):
        return reopened.verify(request.document, request.actions, request.data)
