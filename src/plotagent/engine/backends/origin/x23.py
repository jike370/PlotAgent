"""X23 official DOUBLEY template binder with native two-layer readback."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal, cast

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import X23SeriesData, x23_series
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import X23_ORIGIN_PROFILE, resolve_official_template

_LINE_STYLE = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}
_TITLE_NAME = "_ENGINE_TITLE"


def _hex_rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def _safe_legend_label(value: str) -> str:
    output: list[str] = []
    for character in value:
        codepoint = ord(character)
        if character in {"\\", "%", "$"}:
            output.append(f"\\x({codepoint:04X})")
        elif character in {"\r", "\n", "\t"} or codepoint < 0x20 or codepoint == 0x7F:
            output.append(" ")
        else:
            output.append(character)
    return "".join(output).strip()


def _origin_tick_string(labels: tuple[str, ...]) -> str:
    return " ".join(
        f'"{label.replace(chr(34), chr(92) + chr(34)).replace(chr(10), " ")}"'
        for label in labels
    )


@dataclass(frozen=True, slots=True)
class _AxisState:
    label: str
    scale: Literal["linear", "log10", "datetime", "categorical"]
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool = False


@dataclass(frozen=True, slots=True)
class _SeriesEdit:
    color: str | None = None
    line_width_pt: float | None = None
    line_style: Literal["solid", "dash", "dot", "dash_dot", "none"] | None = None


@dataclass(frozen=True, slots=True)
class _X23State:
    title: str
    x_axis: _AxisState
    left_axis: _AxisState
    right_axis: _AxisState
    left_series: _SeriesEdit = _SeriesEdit()
    right_series: _SeriesEdit = _SeriesEdit()
    legend_visible: bool = True


class X23OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layers: tuple[Any, Any] | None = None
        self.plots: tuple[Any, Any] | None = None
        self.sheet: Any = None

    def create(
        self,
        install_dir: Path,
        document: PlotDocument,
        data: EngineDataView,
    ) -> None:
        template = resolve_official_template(install_dir, X23_ORIGIN_PROFILE)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the X23 data workbook")
        self.sheet = book[0]
        self._write_data(document, data)
        argument = template.with_suffix(template.suffix.lower())
        self.graph = self.op.new_graph(f"G{token}", template=str(argument), hidden=True)
        if self.graph is None:
            raise RuntimeError("Origin could not create a graph from DOUBLEY.OTP")
        native_layers = list(self.graph)
        if len(native_layers) != 2:
            raise RuntimeError("Origin DOUBLEY.OTP must provide exactly two native layers")
        self.layers = (native_layers[0], native_layers[1])
        left_plot = self.layers[0].add_plot(self.sheet, coly=1, colx=0, type="l")
        right_plot = self.layers[1].add_plot(self.sheet, coly=2, colx=0, type="l")
        if left_plot is None or right_plot is None:
            raise RuntimeError("Origin DOUBLEY.OTP rejected one of the native line plots")
        self.plots = (left_plot, right_plot)
        for layer in self.layers:
            layer.rescale()

    def open(self, project_path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=False, asksave=False):
            raise RuntimeError(f"Origin could not open the previous X23 project: {project_path}")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("X23 Origin project must contain one graph and one workbook")
        self.graph = graphs[0]
        native_layers = list(self.graph)
        if len(native_layers) != 2:
            raise RuntimeError("X23 Origin project must retain two native layers")
        self.layers = (native_layers[0], native_layers[1])
        plot_lists = tuple(layer.plot_list() for layer in self.layers)
        if tuple(len(items) for items in plot_lists) != (1, 1):
            raise RuntimeError("X23 Origin project must retain one plot in each layer")
        self.plots = (plot_lists[0][0], plot_lists[1][0])
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
            self._write_data(document, data)
            for layer in self._layers():
                layer.rescale()
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError("X23 title target does not belong to this plot")
            return
        if isinstance(action, SetAxis):
            if action.target not in {
                f"axis:{token}.x",
                f"axis:{token}.y_left",
                f"axis:{token}.y_right",
            }:
                raise ValueError("X23 axis target does not belong to this plot")
            return
        if isinstance(action, SetSeriesStyle):
            if action.target not in {f"series:{token}.left", f"series:{token}.right"}:
                raise ValueError("X23 series target does not belong to this plot")
            if action.symbol is not None or action.symbol_size_pt is not None:
                raise ValueError("Origin X23 does not expose symbol edits")
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError("X23 legend target does not belong to this plot")
            if action.anchor is not None:
                raise ValueError("Origin X23 does not expose legend anchor edits")
            return
        raise ValueError(f"Origin X23 binder cannot apply {action.operation}")

    def reconcile(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> None:
        series = x23_series(document, data)
        state = self._state(document, actions, series)
        self._set_title(state.title)
        self._configure_x_axis(series, state.x_axis)
        self._configure_y_axis(self._layers()[0], "yl", state.left_axis)
        self._configure_y_axis(self._layers()[1], "yr", state.right_axis)
        self._apply_series(self._plots()[0], state.left_series)
        self._apply_series(self._plots()[1], state.right_series)
        self._set_legend(series, state.legend_visible)

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output_path))
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError("Origin did not save a non-empty X23 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        series = x23_series(document, data)
        self._assert_values(self.sheet.to_list(0), series.x_values, "x")
        self._assert_values(self.sheet.to_list(1), series.left_values, "left")
        self._assert_values(self.sheet.to_list(2), series.right_values, "right")
        state = self._state(document, actions, series)
        self._assert_state(series, state)
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
                    semantic_id=f"axis:{token}.y_left",
                    backend="origin",
                    object_kind="axis",
                    native_ref=f"graph:{self.graph.name}.layer:1.axis:y",
                ),
                EngineObjectRef(
                    semantic_id=f"axis:{token}.y_right",
                    backend="origin",
                    object_kind="axis",
                    native_ref=f"graph:{self.graph.name}.layer:2.axis:y",
                ),
                EngineObjectRef(
                    semantic_id=f"series:{token}.left",
                    backend="origin",
                    object_kind="line_series",
                    native_ref=f"graph:{self.graph.name}.layer:1.plot:1",
                ),
                EngineObjectRef(
                    semantic_id=f"series:{token}.right",
                    backend="origin",
                    object_kind="line_series",
                    native_ref=f"graph:{self.graph.name}.layer:2.plot:1",
                ),
                EngineObjectRef(
                    semantic_id=f"legend:{token}.main",
                    backend="origin",
                    object_kind="legend",
                    native_ref=f"graph:{self.graph.name}.layer:1.label:legend",
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(cast(JsonValue, asdict(state))),
        )

    def _write_data(self, document: PlotDocument, data: EngineDataView) -> None:
        series = x23_series(document, data)
        self.sheet.from_list(0, list(series.x_values), lname=series.x_field_name, axis="X")
        self.sheet.from_list(1, list(series.left_values), lname=series.left_field_name, axis="Y")
        self.sheet.from_list(2, list(series.right_values), lname=series.right_field_name, axis="Y")
        self.sheet.cols_axis("xyy")

    def _set_title(self, text: str) -> None:
        layer = self._layers()[0]
        title = layer.label(_TITLE_NAME)
        if title is None and text:
            title = layer.add_label(text, 40, 2)
            if title is None:
                raise RuntimeError("Origin could not create the X23 title")
            title.name = _TITLE_NAME
        if title is not None:
            title.text = text
            title.set_int("show", int(bool(text)))

    def _configure_x_axis(self, data: X23SeriesData, state: _AxisState) -> None:
        for layer in self._layers():
            axis = layer.axis("x")
            if data.x_labels is not None:
                if state.scale != "categorical":
                    raise ValueError("Origin X23 categorical x data cannot use a numeric scale")
                begin, end = 0.5, len(data.x_labels) + 0.5
                if state.reverse:
                    begin, end = end, begin
                axis.set_limits(begin, end, 1.0)
                layer.set_int("x.label.type", 10)
                layer.set_str("x.label.string", _origin_tick_string(data.x_labels))
            else:
                if state.scale not in {"linear", "log10"}:
                    raise ValueError("Origin X23 numeric x supports only linear or log10")
                axis.scale = state.scale
                self._set_limits(axis, state)
        self._set_axis_label(self._layers()[0], "xb", state.label)

    def _configure_y_axis(self, layer: Any, label_name: str, state: _AxisState) -> None:
        if state.scale not in {"linear", "log10"}:
            raise ValueError("Origin X23 y axes support only linear or log10")
        axis = layer.axis("y")
        axis.scale = state.scale
        self._set_limits(axis, state)
        self._set_axis_label(layer, label_name, state.label)

    @staticmethod
    def _set_limits(axis: Any, state: _AxisState) -> None:
        if state.minimum is not None and state.maximum is not None:
            begin, end = state.minimum, state.maximum
            if state.reverse:
                begin, end = end, begin
            axis.set_limits(begin, end)
            return
        begin, end, step = (float(value) for value in axis.limits)
        should_descend = state.reverse
        if (begin > end) != should_descend:
            axis.set_limits(end, begin, abs(step))

    @staticmethod
    def _set_axis_label(layer: Any, name: str, text: str) -> None:
        label = layer.label(name)
        if label is None and name == "yr":
            label = layer.label("yl")
        if label is None:
            label = layer.add_label(text)
        if label is None:
            raise RuntimeError("Origin DOUBLEY.OTP has no writable axis label")
        label.text = text
        label.set_int("show", 1)

    @staticmethod
    def _apply_series(plot: Any, state: _SeriesEdit) -> None:
        if state.color is not None:
            plot.color = state.color
        if state.line_width_pt is not None:
            plot.set_float("line.width", state.line_width_pt)
        if state.line_style is not None:
            if state.line_style == "none":
                raise ValueError("Origin X23 cannot hide one of its two lines")
            plot.set_int("line.style", _LINE_STYLE[state.line_style])

    def _set_legend(self, data: X23SeriesData, visible: bool) -> None:
        layer = self._layers()[0]
        legend = layer.label("legend")
        if legend is None:
            layer.activate()
            if not layer.obj.LT_execute("legend"):
                raise RuntimeError("Origin could not create the linked X23 legend")
            legend = layer.label("legend")
        if legend is None:
            raise RuntimeError("Origin DOUBLEY.OTP has no writable legend")
        legend.text = (
            f"\\l(1, style:l) {_safe_legend_label(data.left_field_name)}\n"
            f"\\l(2.1, style:l) {_safe_legend_label(data.right_field_name)}"
        )
        legend.set_int("link", 1)
        legend.set_int("show", int(visible))

    def _assert_state(self, data: X23SeriesData, state: _X23State) -> None:
        title = self._layers()[0].label(_TITLE_NAME)
        if state.title and (
            title is None or title.text != state.title or not title.get_int("show")
        ):
            raise RuntimeError("Origin X23 title did not survive readback")
        for layer, label_name, axis_state in (
            (self._layers()[0], "yl", state.left_axis),
            (self._layers()[1], "yr", state.right_axis),
        ):
            axis = layer.axis("y")
            if axis.scale != axis_state.scale:
                raise RuntimeError("Origin X23 y-axis scale did not survive readback")
            label = layer.label(label_name) or (layer.label("yl") if label_name == "yr" else None)
            if label is None or label.text != axis_state.label:
                raise RuntimeError("Origin X23 y-axis label did not survive readback")
            self._assert_direction(axis, axis_state.reverse)
        x_label = self._layers()[0].label("xb")
        if x_label is None or x_label.text != state.x_axis.label:
            raise RuntimeError("Origin X23 x-axis label did not survive readback")
        for layer in self._layers():
            if data.x_labels is not None and (
                layer.get_int("x.label.type") != 10
                or layer.get_str("x.label.string") != _origin_tick_string(data.x_labels)
            ):
                raise RuntimeError("Origin X23 category labels did not survive readback")
            self._assert_direction(layer.axis("x"), state.x_axis.reverse)
        for plot, edit in zip(self._plots(), (state.left_series, state.right_series), strict=True):
            if edit.color is not None and tuple(plot.color) != _hex_rgb(edit.color):
                raise RuntimeError("Origin X23 line color did not survive readback")
            if edit.line_width_pt is not None and abs(
                plot.get_float("line.width") - edit.line_width_pt
            ) > 0.01:
                raise RuntimeError("Origin X23 line width did not survive readback")
            if (
                edit.line_style is not None
                and edit.line_style != "none"
                and plot.get_int("line.style") != _LINE_STYLE[edit.line_style]
            ):
                raise RuntimeError("Origin X23 line style did not survive readback")
        legend = self._layers()[0].label("legend")
        if legend is None or bool(legend.get_int("show")) != state.legend_visible:
            raise RuntimeError("Origin X23 legend visibility did not survive readback")
        if "\\l(1, style:l)" not in legend.text or "\\l(2.1, style:l)" not in legend.text:
            raise RuntimeError("Origin X23 legend lost a native cross-layer sample")

    @staticmethod
    def _assert_direction(axis: Any, reverse: bool) -> None:
        begin, end, _step = (float(value) for value in axis.limits)
        if (begin > end) != reverse:
            raise RuntimeError("Origin X23 axis direction did not survive readback")

    def _layers(self) -> tuple[Any, Any]:
        if self.layers is None:
            raise RuntimeError("X23 native layers are not initialized")
        return self.layers

    def _plots(self) -> tuple[Any, Any]:
        if self.plots is None:
            raise RuntimeError("X23 native plots are not initialized")
        return self.plots

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[object, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin X23 {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
                if abs(float(cast(Any, observed)) - float(wanted)) <= 1e-12:
                    continue
            elif observed == wanted:
                continue
            raise RuntimeError(f"Origin X23 {role} values differ after reopen")

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: X23SeriesData,
    ) -> _X23State:
        token = document.plot_id.removeprefix("plot:")
        state = _X23State(
            title="",
            x_axis=_AxisState(data.x_field_name, cast(Any, data.x_scale)),
            left_axis=_AxisState(data.left_field_name, "linear"),
            right_axis=_AxisState(data.right_field_name, "linear"),
        )
        axis_targets = {
            f"axis:{token}.x": "x_axis",
            f"axis:{token}.y_left": "left_axis",
            f"axis:{token}.y_right": "right_axis",
        }
        series_targets = {
            f"series:{token}.left": "left_series",
            f"series:{token}.right": "right_series",
        }
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                state = replace(state, title=action.text)
                continue
            if isinstance(action, SetAxis):
                attribute = axis_targets[action.target]
                current = getattr(state, attribute)
                updated_axis = replace(
                    current,
                    label=current.label if action.label is None else action.label,
                    scale=current.scale if action.scale is None else action.scale,
                    minimum=current.minimum if action.minimum is None else action.minimum,
                    maximum=current.maximum if action.maximum is None else action.maximum,
                    reverse=current.reverse if action.reverse is None else action.reverse,
                )
                if attribute == "x_axis":
                    state = replace(state, x_axis=updated_axis)
                elif attribute == "left_axis":
                    state = replace(state, left_axis=updated_axis)
                else:
                    state = replace(state, right_axis=updated_axis)
                continue
            if isinstance(action, SetSeriesStyle):
                attribute = series_targets[action.target]
                current_series = getattr(state, attribute)
                updated_series = replace(
                    current_series,
                    color=current_series.color if action.color is None else action.color,
                    line_width_pt=(
                        current_series.line_width_pt
                        if action.line_width_pt is None
                        else action.line_width_pt
                    ),
                    line_style=(
                        current_series.line_style
                        if action.line_style is None
                        else action.line_style
                    ),
                )
                if attribute == "left_series":
                    state = replace(state, left_series=updated_series)
                else:
                    state = replace(state, right_series=updated_series)
                continue
            if isinstance(action, SetLegend):
                state = replace(
                    state,
                    legend_visible=(
                        state.legend_visible if action.visible is None else action.visible
                    ),
                )
                continue
            raise ValueError(f"Origin X23 binder cannot apply {action.operation}")
        return state


def execute_x23_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = X23OriginProject(op)
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
        raise RuntimeError("fresh Origin session could not reopen the staged X23 project")
    reopened = X23OriginProject(op)
    graphs = list(op.pages("g"))
    books = list(op.pages("w"))
    if len(graphs) != 1 or len(books) != 1:
        raise RuntimeError("fresh X23 project has unexpected graph or workbook count")
    reopened.graph = graphs[0]
    native_layers = list(reopened.graph)
    if len(native_layers) != 2:
        raise RuntimeError("fresh X23 project lost a native layer")
    reopened.layers = (native_layers[0], native_layers[1])
    plot_lists = tuple(layer.plot_list() for layer in reopened.layers)
    if tuple(len(items) for items in plot_lists) != (1, 1):
        raise RuntimeError("fresh X23 project has an unexpected native plot count")
    reopened.plots = (plot_lists[0][0], plot_lists[1][0])
    reopened.sheet = books[0][0]
    return reopened.verify(request.document, request.actions, request.data)
