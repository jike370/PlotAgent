"""Official-template Origin binders for S21, S34 and S61."""

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
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import ForestData, NyquistData, s21_forest, s34_nyquist
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import (
    S21_ORIGIN_PROFILE,
    S34_ORIGIN_PROFILE,
    resolve_official_template,
)

_TITLE = "_ENGINE_TITLE"


@dataclass(frozen=True, slots=True)
class _AxesState:
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    x_minimum: float | None = None
    x_maximum: float | None = None
    y_minimum: float | None = None
    y_maximum: float | None = None
    x_reverse: bool = False
    y_reverse: bool = False


@dataclass(frozen=True, slots=True)
class _Style:
    color: str | None = None
    line_width_pt: float = 1.5
    line_style: str = "solid"
    symbol: str = "circle"
    symbol_size_pt: float = 6.0


def _style(current: _Style, action: SetSeriesStyle) -> _Style:
    return replace(
        current,
        color=current.color if action.color is None else action.color,
        line_width_pt=current.line_width_pt
        if action.line_width_pt is None
        else action.line_width_pt,
        line_style=current.line_style if action.line_style is None else action.line_style,
        symbol=current.symbol if action.symbol is None else action.symbol,
        symbol_size_pt=(
            current.symbol_size_pt if action.symbol_size_pt is None else action.symbol_size_pt
        ),
    )


def _line_style(value: str) -> int:
    if value == "none":
        raise ValueError("Origin scientific series cannot hide its native line")
    return {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}[value]


def _symbol(value: str) -> int:
    try:
        return {"circle": 1, "square": 2, "diamond": 3, "triangle": 4, "plus": 5}[value]
    except KeyError as error:
        raise ValueError(f"Origin does not expose symbol {value!r}") from error


def _tick_string(labels: tuple[str, ...]) -> str:
    return " ".join(f'"{label.replace(chr(34), chr(92) + chr(34))}"' for label in labels)


def _set_title(layer: Any, text: str) -> None:
    label = layer.label(_TITLE)
    if label is None and text:
        label = layer.add_label(text, 40, 2)
        if label is None:
            raise RuntimeError("Origin could not create the title")
        label.name = _TITLE
    if label is not None:
        label.text = text
        label.set_int("show", int(bool(text)))


def _set_axis_label(layer: Any, axis: str, text: str) -> None:
    label = layer.label("xb" if axis == "x" else "yl") or layer.add_label(text)
    if label is None:
        raise RuntimeError("Origin template has no writable axis label")
    label.text = text
    label.set_int("show", 1)


def _set_axis(layer: Any, axis: str, state: _AxesState) -> None:
    minimum = getattr(state, f"{axis}_minimum")
    maximum = getattr(state, f"{axis}_maximum")
    reverse = getattr(state, f"{axis}_reverse")
    if minimum is not None and maximum is not None:
        begin, end = float(minimum), float(maximum)
    else:
        native = layer.axis(axis)
        limits = getattr(native, "limits", None)
        if isinstance(limits, tuple) and len(limits) >= 2:
            begin, end = float(limits[0]), float(limits[1])
        else:
            begin, end = 0.0, 1.0
    if reverse:
        begin, end = end, begin
    if minimum is not None or reverse:
        layer.axis(axis).set_limits(begin, end)
    _set_axis_label(layer, axis, getattr(state, f"{axis}_label"))


def _edit_axes(state: _AxesState, action: SetAxis, token: str) -> _AxesState:
    axis = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
    if axis is None:
        raise ValueError("axis target does not belong to this plot")
    if axis == "x":
        return replace(
            state,
            x_label=state.x_label if action.label is None else action.label,
            x_minimum=state.x_minimum if action.minimum is None else action.minimum,
            x_maximum=state.x_maximum if action.maximum is None else action.maximum,
            x_reverse=state.x_reverse if action.reverse is None else action.reverse,
        )
    return replace(
        state,
        y_label=state.y_label if action.label is None else action.label,
        y_minimum=state.y_minimum if action.minimum is None else action.minimum,
        y_maximum=state.y_maximum if action.maximum is None else action.maximum,
        y_reverse=state.y_reverse if action.reverse is None else action.reverse,
    )


class S21OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.sheet: Any = None
        self.plots: tuple[Any, ...] = ()

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, S21_ORIGIN_PROFILE)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the S21 workbook")
        self.sheet = book[0]
        forest = s21_forest(document, data)
        self._write(forest)
        self.graph = self.op.new_graph(
            f"G{token}", template=str(template.with_suffix(template.suffix.lower())), hidden=True
        )
        if self.graph is None:
            raise RuntimeError("Origin could not create S21 from SCATTERINTERVAL.otp")
        self.layer = self.graph[0]
        for plot in self.layer.plot_list():
            plot.set_int("show", 0)
        plots: list[Any] = []
        for colx, coly, plot_type in ((0, 1, 200), (2, 3, 200)):
            plot = self.layer.add_plot(self.sheet, coly=coly, colx=colx, type=plot_type)
            if plot is None:
                raise RuntimeError("Origin S21 template rejected a native line")
            plots.append(plot)
        for index in range(len(forest.labels)):
            plot = self.layer.add_plot(
                self.sheet,
                coly=5 + index * 2,
                colx=4 + index * 2,
                type=201,
            )
            if plot is None:
                raise RuntimeError("Origin S21 template rejected a weighted point")
            plots.append(plot)
        self.plots = tuple(plots)
        self.layer.rescale()

    def open(self, output: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(output), readonly=False, asksave=False):
            raise RuntimeError("Origin could not reopen S21")
        graphs, books = list(self.op.pages("g")), list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("S21 must contain one graph and workbook")
        self.graph, self.sheet = graphs[0], books[0][0]
        self.layer = self.graph[0]
        self.plots = tuple(plot for plot in self.layer.plot_list() if plot.get_int("show") != 0)

    def reconcile(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> None:
        forest = s21_forest(document, data)
        self._write(forest)
        axes, interval, point, null_effect = self._state(document, actions, forest)
        self.plots[0].color = interval.color or "#2A6FDB"
        self.plots[0].set_float("line.width", interval.line_width_pt)
        self.plots[0].set_int("line.style", _line_style(interval.line_style))
        self.plots[1].color = "#6B7280"
        weights = np.asarray(forest.weight, dtype=float)
        for plot, weight in zip(self.plots[2:], weights, strict=True):
            plot.color = point.color or interval.color or "#2A6FDB"
            plot.symbol_kind = _symbol(point.symbol)
            plot.symbol_size = point.symbol_size_pt * (0.65 + 0.75 * weight / weights.max())
            plot.set_int("line.connect", 0)
            plot.set_int("show", 1)
        self.plots[0].set_int("show", 1)
        self.plots[1].set_int("show", 1)
        self.sheet.from_list(2, [null_effect, null_effect], lname="Null effect", axis="X")
        self.layer.set_int("y.label.type", 10)
        self.layer.set_str("y.label.string", _tick_string(forest.labels))
        self.layer.axis("y").set_limits(0.5, len(forest.labels) + 0.5, 1.0)
        _set_title(self.layer, axes.title)
        _set_axis(self.layer, "x", axes)
        _set_axis_label(self.layer, "y", axes.y_label)
        legend = self.layer.label("legend")
        if legend is not None:
            legend.set_int("show", 0)
        self.layer.rescale()

    def save(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output))

    def verify(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> EngineReadback:
        forest = s21_forest(document, data)
        axes, interval, point, null_effect = self._state(document, actions, forest)
        if len(self.plots) != len(forest.labels) + 2:
            raise RuntimeError("Origin S21 native plot count differs after reopen")
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
                    semantic_id=f"series:{token}.interval",
                    backend="origin",
                    object_kind="forest_intervals",
                    native_ref=f"graph:{self.graph.name}.layer:1.plot:1",
                ),
                EngineObjectRef(
                    semantic_id=f"series:{token}.points",
                    backend="origin",
                    object_kind="forest_weighted_points",
                    native_ref=f"graph:{self.graph.name}.layer:1.plot:3..{len(self.plots)}",
                ),
                EngineObjectRef(
                    semantic_id=f"annotation:{token}.null_effect",
                    backend="origin",
                    object_kind="reference_line",
                    native_ref=f"graph:{self.graph.name}.layer:1.plot:2",
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(
                cast(
                    JsonValue,
                    {
                        "axes": asdict(axes),
                        "interval": asdict(interval),
                        "point": asdict(point),
                        "null_effect": null_effect,
                    },
                )
            ),
        )

    def _write(self, forest: ForestData) -> None:
        interval_x: list[float] = []
        interval_y: list[float] = []
        for position, lower, upper in zip(
            range(1, len(forest.labels) + 1), forest.lower, forest.upper, strict=True
        ):
            interval_x.extend((lower, upper, float("nan")))
            interval_y.extend((float(position), float(position), float("nan")))
        self.sheet.from_list(0, interval_x, lname="Interval X", axis="X")
        self.sheet.from_list(1, interval_y, lname="Interval Y", axis="Y")
        self.sheet.from_list(2, [0.0, 0.0], lname="Null effect", axis="X")
        self.sheet.from_list(3, [0.5, len(forest.labels) + 0.5], lname="Null Y", axis="Y")
        for index, (effect, position) in enumerate(
            zip(forest.effect, range(1, len(forest.labels) + 1), strict=True)
        ):
            self.sheet.from_list(4 + index * 2, [effect], lname=forest.labels[index], axis="X")
            self.sheet.from_list(5 + index * 2, [float(position)], lname="Study", axis="Y")

    @staticmethod
    def _state(
        document: PlotDocument, actions: tuple[PlotEngineAction, ...], forest: ForestData
    ) -> tuple[_AxesState, _Style, _Style, float]:
        token = document.plot_id.removeprefix("plot:")
        axes = _AxesState(x_label=forest.effect_field_name, y_label=forest.label_field_name)
        interval, point, null_effect = _Style(), _Style(line_style="none"), 0.0
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                axes = replace(axes, title=action.text)
            elif isinstance(action, SetAxis):
                axis = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
                if axis is None:
                    raise ValueError("S21 axis target does not belong")
                if axis == "y" and action.scale not in {None, "categorical"}:
                    raise ValueError("S21 y axis requires categorical scale")
                axes = _edit_axes(axes, action, token)
            elif isinstance(action, SetSeriesStyle):
                if action.target == f"series:{token}.interval":
                    interval = _style(interval, action)
                elif action.target == f"series:{token}.points":
                    point = _style(point, action)
                else:
                    raise ValueError("S21 series target does not belong")
            elif isinstance(action, SetChartParameter):
                if (
                    action.parameter != "null_effect"
                    or isinstance(action.value, bool)
                    or not isinstance(action.value, (int, float))
                ):
                    raise ValueError("S21 null_effect must be numeric")
                null_effect = float(action.value)
            else:
                raise ValueError(f"Origin S21 cannot apply {action.operation}")
        return axes, interval, point, null_effect


class S34OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.sheet: Any = None
        self.plots: tuple[Any, ...] = ()

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, S34_ORIGIN_PROFILE)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create S34 workbook")
        self.sheet = book[0]
        nyquist = s34_nyquist(document, data)
        self._write(nyquist)
        self.graph = self.op.new_graph(
            f"G{token}", template=str(template.with_suffix(template.suffix.lower())), hidden=True
        )
        if self.graph is None:
            raise RuntimeError("Origin could not create S34 from LINESYMB.otpu")
        self.layer = self.graph[0]
        for plot in self.layer.plot_list():
            plot.set_int("show", 0)
        plots = []
        for index in range(len(nyquist.series)):
            plot = self.layer.add_plot(self.sheet, coly=index * 3 + 1, colx=index * 3, type=202)
            if plot is None:
                raise RuntimeError("Origin S34 template rejected a line-symbol plot")
            plots.append(plot)
        self.plots = tuple(plots)

    def open(self, output: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(output), readonly=False, asksave=False):
            raise RuntimeError("Origin could not reopen S34")
        graphs, books = list(self.op.pages("g")), list(self.op.pages("w"))
        self.graph, self.sheet = graphs[0], books[0][0]
        self.layer = self.graph[0]
        self.plots = tuple(plot for plot in self.layer.plot_list() if plot.get_int("show") != 0)

    def reconcile(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> None:
        nyquist = s34_nyquist(document, data)
        self._write(nyquist)
        axes, styles, legend_visible, equal_axes = self._state(document, actions, nyquist)
        for index, (plot, style) in enumerate(zip(self.plots, styles, strict=True)):
            plot.color = (
                style.color or ("#2A6FDB", "#D94B4B", "#2A9D6F", "#8A5CC2", "#D88700")[index % 5]
            )
            plot.set_float("line.width", style.line_width_pt)
            plot.set_int("line.style", _line_style(style.line_style))
            plot.symbol_kind = _symbol(style.symbol)
            plot.symbol_size = style.symbol_size_pt
            plot.set_int("show", 1)
        self.layer.rescale()
        if equal_axes and axes.x_minimum is None and axes.y_minimum is None:
            upper = (
                max(
                    max(value for series in nyquist.series for value in series.z_real),
                    max(value for series in nyquist.series for value in series.z_imaginary),
                )
                * 1.08
            )
            self.layer.axis("x").set_limits(0.0, upper)
            self.layer.axis("y").set_limits(0.0, upper)
        _set_title(self.layer, axes.title)
        _set_axis(self.layer, "x", axes)
        _set_axis(self.layer, "y", axes)
        legend = self.layer.label("legend")
        if legend is None:
            self.layer.activate()
            self.layer.obj.LT_execute("legend")
            legend = self.layer.label("legend")
        if legend is None:
            raise RuntimeError("S34 template has no writable legend")
        legend.text = "\n".join(
            f"\\l({index + 1}) {series.label}" for index, series in enumerate(nyquist.series)
        )
        legend.set_int("show", int(legend_visible))
        legend.set_int("link", 0)

    def save(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output))

    def verify(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> EngineReadback:
        nyquist = s34_nyquist(document, data)
        axes, styles, legend_visible, equal_axes = self._state(document, actions, nyquist)
        if len(self.plots) != len(nyquist.series):
            raise RuntimeError("Origin S34 series count differs after reopen")
        token = document.plot_id.removeprefix("plot:")
        objects = list(_origin_base_objects(document, self.graph.name))
        objects.append(
            EngineObjectRef(
                semantic_id=f"legend:{token}.main",
                backend="origin",
                object_kind="legend",
                native_ref=f"graph:{self.graph.name}.layer:1.label:legend",
            )
        )
        objects.extend(
            EngineObjectRef(
                semantic_id=f"series:{token}.group_{index + 1}",
                backend="origin",
                object_kind="nyquist_series",
                native_ref=f"graph:{self.graph.name}.layer:1.plot:{index + 1}",
            )
            for index in range(len(self.plots))
        )
        return EngineReadback(
            document=document_ref(document),
            backend="origin",
            objects=tuple(objects),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(
                cast(
                    JsonValue,
                    {
                        "axes": asdict(axes),
                        "styles": [asdict(style) for style in styles],
                        "legend": legend_visible,
                        "equal_axes": equal_axes,
                    },
                )
            ),
        )

    def _write(self, nyquist: NyquistData) -> None:
        for index, series in enumerate(nyquist.series):
            self.sheet.from_list(
                index * 3, list(series.z_real), lname=nyquist.z_real_field_name, axis="X"
            )
            self.sheet.from_list(
                index * 3 + 1, list(series.z_imaginary), lname=series.label, axis="Y"
            )
            self.sheet.from_list(
                index * 3 + 2, list(series.frequency or ()), lname="Frequency", axis="N"
            )

    @staticmethod
    def _state(
        document: PlotDocument, actions: tuple[PlotEngineAction, ...], nyquist: NyquistData
    ) -> tuple[_AxesState, tuple[_Style, ...], bool, bool]:
        token = document.plot_id.removeprefix("plot:")
        axes = _AxesState(x_label=nyquist.z_real_field_name, y_label=nyquist.z_imaginary_field_name)
        styles = tuple(_Style() for _series in nyquist.series)
        legend_visible, equal_axes = len(nyquist.series) > 1, True
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                axes = replace(axes, title=action.text)
            elif isinstance(action, SetAxis):
                axis = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
                if axis is None or action.scale not in {None, "linear"}:
                    raise ValueError("S34 axis edit is invalid")
                axes = _edit_axes(axes, action, token)
            elif isinstance(action, SetSeriesStyle):
                prefix = f"series:{token}.group_"
                if not action.target.startswith(prefix):
                    raise ValueError("S34 series target does not belong")
                index = int(action.target.removeprefix(prefix)) - 1
                mutable = list(styles)
                mutable[index] = _style(mutable[index], action)
                styles = tuple(mutable)
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main" or action.anchor is not None:
                    raise ValueError("S34 exposes only legend visibility")
                legend_visible = legend_visible if action.visible is None else action.visible
            elif isinstance(action, SetChartParameter):
                if action.parameter != "equal_axes" or not isinstance(action.value, bool):
                    raise ValueError("S34 equal_axes must be boolean")
                equal_axes = action.value
            else:
                raise ValueError(f"Origin S34 cannot apply {action.operation}")
        return axes, styles, legend_visible, equal_axes


def _origin_base_objects(document: PlotDocument, graph_name: str) -> tuple[EngineObjectRef, ...]:
    token = document.plot_id.removeprefix("plot:")
    return (
        EngineObjectRef(
            semantic_id=document.plot_id,
            backend="origin",
            object_kind="graph",
            native_ref=f"graph:{graph_name}",
        ),
        EngineObjectRef(
            semantic_id=f"axis:{token}.x",
            backend="origin",
            object_kind="axis",
            native_ref=f"graph:{graph_name}.layer:1.axis:x",
        ),
        EngineObjectRef(
            semantic_id=f"axis:{token}.y",
            backend="origin",
            object_kind="axis",
            native_ref=f"graph:{graph_name}.layer:1.axis:y",
        ),
    )


def _execute(
    project: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    project.create(install_dir, request.document, request.data)
    project.reconcile(request.document, request.actions, request.data)
    project.save(output)
    reopened = type(project)(project.op)
    reopened.open(output)
    return cast(
        EngineReadback,
        reopened.verify(request.document, request.actions, request.data),
    )


def execute_s21_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(S21OriginProject(op), request, install_dir, output)


def execute_s34_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(S34OriginProject(op), request, install_dir, output)
