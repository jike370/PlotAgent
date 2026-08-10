"""Official two-layer binders for X35 dual-column and X36 column-line."""

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
from plotagent.engine.profile_data import X23SeriesData, x35_series, x36_series
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import (
    X35_ORIGIN_PROFILE,
    X36_ORIGIN_PROFILE,
    OriginTemplateProfile,
    resolve_official_template,
)

_COLUMN = 203
_LINE_STYLE = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}
_SYMBOL = {"circle": 1, "square": 0, "diamond": 3, "triangle": 2, "triangle_up": 2}
_TITLE_NAME = "_ENGINE_TITLE"


@dataclass(frozen=True, slots=True)
class _AxisState:
    label: str
    scale: Literal["linear", "log10", "datetime", "categorical"]
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool = False


@dataclass(frozen=True, slots=True)
class _SeriesState:
    color: str | None = None
    line_width_pt: float | None = None
    line_style: str | None = None
    symbol: str | None = None
    symbol_size_pt: float | None = None


@dataclass(frozen=True, slots=True)
class _State:
    title: str
    x_axis: _AxisState
    left_axis: _AxisState
    right_axis: _AxisState
    left_series: _SeriesState = _SeriesState()
    right_series: _SeriesState = _SeriesState()
    legend_visible: bool = True


class DualYSpecialOriginProject:
    def __init__(self, op: Any, *, profile_id: Literal["X35", "X36"]) -> None:
        self.op = op
        self.profile_id = profile_id
        self.profile: OriginTemplateProfile = {
            "X35": X35_ORIGIN_PROFILE,
            "X36": X36_ORIGIN_PROFILE,
        }[profile_id]
        self.graph: Any = None
        self.layers: tuple[Any, Any] | None = None
        self.plots: tuple[Any, Any] | None = None
        self.sheet: Any = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, self.profile)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError(f"Origin could not create the {self.profile_id} workbook")
        self.sheet = book[0]
        values = self._data(document, data)
        self._write(values)
        self.graph = self.op.new_graph(
            f"G{token}", template=str(template.with_suffix(template.suffix.lower())), hidden=True
        )
        if self.graph is None:
            raise RuntimeError(
                f"Origin could not create {self.profile_id} from the official template"
            )
        layers = list(self.graph)
        if len(layers) != 2:
            raise RuntimeError(f"Origin {self.profile.filename} must provide exactly two layers")
        self.layers = (layers[0], layers[1])
        left = self.layers[0].add_plot(self.sheet, coly=1, colx=0, type=_COLUMN)
        right_type: int | str = _COLUMN if self.profile_id == "X35" else "?"
        right = self.layers[1].add_plot(self.sheet, coly=2, colx=0, type=right_type)
        if left is None or right is None:
            raise RuntimeError(f"Origin {self.profile.filename} rejected a native plot")
        self.plots = (left, right)
        for layer in self._layers():
            layer.rescale()

    def open(self, project_path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=False, asksave=False):
            raise RuntimeError(f"Origin could not open the prior {self.profile_id} project")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError(f"{self.profile_id} project must contain one graph and workbook")
        self.graph = graphs[0]
        layers = list(self.graph)
        if len(layers) != 2:
            raise RuntimeError(f"{self.profile_id} project lost one official layer")
        self.layers = (layers[0], layers[1])
        native = tuple(layer.plot_list() for layer in self.layers)
        if tuple(len(items) for items in native) != (1, 1):
            raise RuntimeError(f"{self.profile_id} project must retain one plot per layer")
        self.plots = (native[0][0], native[1][0])
        self.sheet = books[0][0]

    def apply(self, document: PlotDocument, action: PlotEngineAction, data: EngineDataView) -> None:
        token = document.plot_id.removeprefix("plot:")
        if isinstance(action, CreatePlot):
            return
        if isinstance(action, BindFields):
            self._write(self._data(document, data))
            for layer in self._layers():
                layer.rescale()
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError(f"{self.profile_id} title target does not belong to this plot")
            return
        if isinstance(action, SetAxis):
            if action.target not in {
                f"axis:{token}.x",
                f"axis:{token}.y_left",
                f"axis:{token}.y_right",
            }:
                raise ValueError(f"{self.profile_id} axis target does not belong to this plot")
            return
        if isinstance(action, SetSeriesStyle):
            if action.target not in {f"series:{token}.left", f"series:{token}.right"}:
                raise ValueError(f"{self.profile_id} series target does not belong to this plot")
            if self.profile_id == "X35" and (
                action.line_style is not None
                or action.symbol is not None
                or action.symbol_size_pt is not None
            ):
                raise ValueError("X35 columns expose only color and border width")
            if action.target.endswith(".left") and (
                action.line_style is not None
                or action.symbol is not None
                or action.symbol_size_pt is not None
            ):
                raise ValueError(f"{self.profile_id} left column exposes no line or symbol edit")
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main" or action.anchor is not None:
                raise ValueError(f"{self.profile_id} exposes only legend visibility")
            return
        raise ValueError(f"Origin {self.profile_id} binder cannot apply {action.operation}")

    def reconcile(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> None:
        values = self._data(document, data)
        state = self._state(document, actions, values)
        self._set_title(state.title)
        for layer in self._layers():
            self._configure_x(layer, values, state.x_axis)
        self._configure_y(self._layers()[0], "yl", state.left_axis)
        self._configure_y(self._layers()[1], "yr", state.right_axis)
        self._apply_style(self._plots()[0], state.left_series, allow_symbol=False)
        self._apply_style(
            self._plots()[1], state.right_series, allow_symbol=self.profile_id == "X36"
        )
        self._set_legend(values, state.legend_visible)

    def save(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output))
        if not output.is_file() or output.stat().st_size <= 0:
            raise RuntimeError(f"Origin did not save a non-empty {self.profile_id} project")

    def verify(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> EngineReadback:
        values = self._data(document, data)
        state = self._state(document, actions, values)
        self._assert_values(self.sheet.to_list(0), tuple(values.x_values), "category")
        self._assert_values(self.sheet.to_list(1), values.left_values, "left")
        self._assert_values(self.sheet.to_list(2), values.right_values, "right")
        if tuple(len(layer.plot_list()) for layer in self._layers()) != (1, 1):
            raise RuntimeError(f"Origin {self.profile_id} native plot count differs after reopen")
        title = self._layers()[0].label(_TITLE_NAME)
        if state.title and (
            title is None or title.text != state.title or not title.get_int("show")
        ):
            raise RuntimeError(f"Origin {self.profile_id} title did not survive readback")
        legend = self._layers()[0].label("legend")
        if legend is None or bool(legend.get_int("show")) != state.legend_visible:
            raise RuntimeError(f"Origin {self.profile_id} legend did not survive readback")
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
                object_kind="dual_y_column_series",
                native_ref=f"graph:{self.graph.name}.layer:1.plot:1",
            ),
            EngineObjectRef(
                semantic_id=f"series:{token}.right",
                backend="origin",
                object_kind="dual_y_column_series"
                if self.profile_id == "X35"
                else "dual_y_line_series",
                native_ref=f"graph:{self.graph.name}.layer:2.plot:1",
            ),
            EngineObjectRef(
                semantic_id=f"legend:{token}.main",
                backend="origin",
                object_kind="legend",
                native_ref=f"graph:{self.graph.name}.layer:1.label:legend",
            ),
        )
        return EngineReadback(
            document=document_ref(document),
            backend="origin",
            objects=objects,
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(cast(JsonValue, asdict(state))),
        )

    def _data(self, document: PlotDocument, data: EngineDataView) -> X23SeriesData:
        return (
            x35_series(document, data) if self.profile_id == "X35" else x36_series(document, data)
        )

    def _write(self, values: X23SeriesData) -> None:
        self.sheet.from_list(0, list(values.x_values), lname=values.x_field_name, axis="X")
        self.sheet.from_list(1, list(values.left_values), lname=values.left_field_name, axis="Y")
        self.sheet.from_list(2, list(values.right_values), lname=values.right_field_name, axis="Y")

    def _configure_x(self, layer: Any, values: X23SeriesData, state: _AxisState) -> None:
        if values.x_labels is None or state.scale != "categorical":
            raise ValueError(f"Origin {self.profile_id} requires categorical X data")
        begin, end = 0.5, len(values.x_labels) + 0.5
        if state.reverse:
            begin, end = end, begin
        layer.axis("x").set_limits(begin, end, 1.0)
        layer.set_int("x.label.type", 10)
        layer.set_str("x.label.string", " ".join(f'"{label}"' for label in values.x_labels))
        self._set_axis_label(self._layers()[0], "xb", state.label)

    def _configure_y(self, layer: Any, label_name: str, state: _AxisState) -> None:
        if state.scale not in {"linear", "log10"}:
            raise ValueError(f"Origin {self.profile_id} Y axes support linear or log10")
        axis = layer.axis("y")
        axis.scale = state.scale
        if state.minimum is not None and state.maximum is not None:
            begin, end = state.minimum, state.maximum
            if state.reverse:
                begin, end = end, begin
            axis.set_limits(begin, end)
        self._set_axis_label(layer, label_name, state.label)

    def _set_title(self, text: str) -> None:
        title = self._layers()[0].label(_TITLE_NAME)
        if title is None and text:
            title = self._layers()[0].add_label(text, 40, 2)
            if title is None:
                raise RuntimeError(f"Origin could not create the {self.profile_id} title")
            title.name = _TITLE_NAME
        if title is not None:
            title.text = text
            title.set_int("show", int(bool(text)))

    @staticmethod
    def _set_axis_label(layer: Any, name: str, text: str) -> None:
        label = (
            layer.label(name)
            or (layer.label("yl") if name == "yr" else None)
            or layer.add_label(text)
        )
        if label is None:
            raise RuntimeError("Origin dual-Y template has no writable axis label")
        label.text = text
        label.set_int("show", 1)

    def _set_legend(self, values: X23SeriesData, visible: bool) -> None:
        layer = self._layers()[0]
        legend = layer.label("legend")
        if legend is None:
            layer.activate()
            layer.obj.LT_execute("legend")
            legend = layer.label("legend")
        if legend is None:
            raise RuntimeError(f"Origin {self.profile_id} has no writable legend")
        sample = "b" if self.profile_id == "X35" else "l"
        legend.text = (
            f"\\l(1, style:b) {values.left_field_name}\n"
            f"\\l(2.1, style:{sample}) {values.right_field_name}"
        )
        legend.set_int("link", 1)
        legend.set_int("show", int(visible))

    @staticmethod
    def _apply_style(plot: Any, state: _SeriesState, *, allow_symbol: bool) -> None:
        if state.color is not None:
            plot.color = state.color
        if state.line_width_pt is not None:
            plot.set_float("line.width", state.line_width_pt)
        if state.line_style is not None:
            if state.line_style == "none":
                raise ValueError("Origin dual-Y series cannot be hidden through line style")
            plot.set_int("line.style", _LINE_STYLE[state.line_style])
        if state.symbol is not None:
            if not allow_symbol:
                raise ValueError("Origin column series has no symbol")
            plot.symbol_kind = _SYMBOL[state.symbol]
        if state.symbol_size_pt is not None:
            if not allow_symbol:
                raise ValueError("Origin column series has no symbol size")
            plot.symbol_size = state.symbol_size_pt

    def _state(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: X23SeriesData
    ) -> _State:
        token = document.plot_id.removeprefix("plot:")
        state = _State(
            title="",
            x_axis=_AxisState(data.x_field_name, "categorical"),
            left_axis=_AxisState(data.left_field_name, "linear"),
            right_axis=_AxisState(data.right_field_name, "linear"),
        )
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                key = {
                    f"axis:{token}.x": "x_axis",
                    f"axis:{token}.y_left": "left_axis",
                    f"axis:{token}.y_right": "right_axis",
                }[action.target]
                current = getattr(state, key)
                state = replace(
                    state,
                    **{
                        key: replace(
                            current,
                            label=current.label if action.label is None else action.label,
                            scale=current.scale if action.scale is None else action.scale,
                            minimum=current.minimum if action.minimum is None else action.minimum,
                            maximum=current.maximum if action.maximum is None else action.maximum,
                            reverse=current.reverse if action.reverse is None else action.reverse,
                        )
                    },
                )
            elif isinstance(action, SetSeriesStyle):
                key = {
                    f"series:{token}.left": "left_series",
                    f"series:{token}.right": "right_series",
                }[action.target]
                current = getattr(state, key)
                state = replace(
                    state,
                    **{
                        key: replace(
                            current,
                            color=current.color if action.color is None else action.color,
                            line_width_pt=current.line_width_pt
                            if action.line_width_pt is None
                            else action.line_width_pt,
                            line_style=current.line_style
                            if action.line_style is None
                            else action.line_style,
                            symbol=current.symbol if action.symbol is None else action.symbol,
                            symbol_size_pt=current.symbol_size_pt
                            if action.symbol_size_pt is None
                            else action.symbol_size_pt,
                        )
                    },
                )
            elif isinstance(action, SetLegend):
                state = replace(
                    state,
                    legend_visible=state.legend_visible
                    if action.visible is None
                    else action.visible,
                )
            else:
                raise ValueError(f"Origin {self.profile_id} binder cannot apply {action.operation}")
        return state

    def _layers(self) -> tuple[Any, Any]:
        if self.layers is None:
            raise RuntimeError(f"{self.profile_id} layers are not initialized")
        return self.layers

    def _plots(self) -> tuple[Any, Any]:
        if self.plots is None:
            raise RuntimeError(f"{self.profile_id} plots are not initialized")
        return self.plots

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[object, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
                if abs(float(cast(Any, observed)) - float(wanted)) <= 1e-9:
                    continue
            elif observed == wanted:
                continue
            raise RuntimeError(f"Origin {role} values differ after reopen")


def _execute(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
    profile_id: Literal["X35", "X36"],
) -> EngineReadback:
    project = DualYSpecialOriginProject(op, profile_id=profile_id)
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
    reopened = DualYSpecialOriginProject(op, profile_id=profile_id)
    reopened.open(output)
    return reopened.verify(request.document, request.actions, request.data)


def execute_x35_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "X35")


def execute_x36_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "X36")
