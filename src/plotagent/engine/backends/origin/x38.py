"""X38 official OffsetStackY binder that keeps worksheet Y values raw."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, cast

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
from plotagent.engine.profile_data import OffsetStackData, x38_offset_stack
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import X38_ORIGIN_PROFILE, resolve_official_template

_LINE_STYLE = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}
_TITLE_NAME = "_ENGINE_TITLE"


@dataclass(frozen=True, slots=True)
class _SeriesState:
    color: str | None = None
    line_width_pt: float | None = None
    line_style: str | None = None


@dataclass(frozen=True, slots=True)
class _State:
    title: str
    x_label: str
    y_label: str
    x_scale: str = "linear"
    y_scale: str = "linear"
    x_reverse: bool = False
    y_reverse: bool = False
    series: tuple[_SeriesState, ...] = ()
    legend_visible: bool = True


class X38OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.sheet: Any = None
        self.plots: list[Any] = []

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, X38_ORIGIN_PROFILE)
        offset = x38_offset_stack(document, data)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the X38 workbook")
        self.sheet = book[0]
        self._write(offset)
        self.graph = self.op.new_graph(
            f"G{token}", template=str(template.with_suffix(template.suffix.lower())), hidden=True
        )
        if self.graph is None:
            raise RuntimeError("Origin could not create X38 from OffsetStackY.otp")
        self.layer = self.graph[0]
        for plot in self.layer.plot_list():
            plot.set_int("show", 0)
        for index in range(len(offset.series)):
            plot = self.layer.add_plot(self.sheet, coly=index + 1, colx=0, type="?")
            if plot is None:
                raise RuntimeError(f"Origin OffsetStackY rejected series {index + 1}")
            self.plots.append(plot)
        self.layer.rescale()

    def open(self, path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(path), readonly=False, asksave=False):
            raise RuntimeError("Origin could not reopen the X38 project")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("X38 project must contain one graph and workbook")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        self.plots = [plot for plot in self.layer.plot_list() if plot.get_int("show") != 0]
        self.sheet = books[0][0]

    def reconcile(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> None:
        offset = x38_offset_stack(document, data)
        state = self._state(document, actions, offset)
        title = self.layer.label(_TITLE_NAME)
        if title is None and state.title:
            title = self.layer.add_label(state.title, 40, 2)
            if title is None:
                raise RuntimeError("Origin could not create the X38 title")
            title.name = _TITLE_NAME
        if title is not None:
            title.text = state.title
            title.set_int("show", int(bool(state.title)))
        self._axis_label("xb", state.x_label)
        self._axis_label("yl", state.y_label)
        for name, scale, reverse in (
            ("x", state.x_scale, state.x_reverse),
            ("y", state.y_scale, state.y_reverse),
        ):
            axis = self.layer.axis(name)
            axis.scale = scale
            begin, end, step = (float(value) for value in axis.limits)
            if (begin > end) != reverse:
                axis.set_limits(end, begin, abs(step))
        for plot, style in zip(self.plots, state.series, strict=True):
            if style.color is not None:
                plot.color = style.color
            if style.line_width_pt is not None:
                plot.set_float("line.width", style.line_width_pt)
            if style.line_style is not None:
                if style.line_style == "none":
                    raise ValueError("X38 cannot hide one stacked line through line style")
                plot.set_int("line.style", _LINE_STYLE[style.line_style])
        self._set_legend(offset, state.legend_visible)

    def save(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output))
        if not output.is_file() or output.stat().st_size <= 0:
            raise RuntimeError("Origin did not save a non-empty X38 project")

    def verify(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> EngineReadback:
        offset = x38_offset_stack(document, data)
        state = self._state(document, actions, offset)
        if len(self.plots) != len(offset.series):
            raise RuntimeError("Origin X38 native series count differs after reopen")
        expected = (offset.series[0].x_values, *(series.y_values for series in offset.series))
        for index, values in enumerate(expected):
            self._assert_values(self.sheet.to_list(index), values, f"column {index + 1}")
        legend = self.layer.label("legend")
        if legend is None or bool(legend.get_int("show")) != state.legend_visible:
            raise RuntimeError("Origin X38 legend did not survive readback")
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
            *tuple(
                EngineObjectRef(
                    semantic_id=f"series:{token}.group_{index}",
                    backend="origin",
                    object_kind="offset_line_series",
                    native_ref=f"graph:{self.graph.name}.layer:1.plot:{index}",
                )
                for index in range(1, len(self.plots) + 1)
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

    def _state(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: OffsetStackData
    ) -> _State:
        token = document.plot_id.removeprefix("plot:")
        state = _State(
            title="",
            x_label=data.x_field_name,
            y_label=data.y_field_name,
            series=tuple(_SeriesState() for _ in data.series),
        )
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("X38 title target does not belong to this plot")
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                if action.minimum is not None:
                    raise ValueError("X38 official offset template keeps automatic bounds")
                if action.target == f"axis:{token}.x":
                    if action.scale not in {None, "linear", "log10"}:
                        raise ValueError("X38 X axis supports linear or log10")
                    state = replace(
                        state,
                        x_label=state.x_label if action.label is None else action.label,
                        x_scale=state.x_scale if action.scale is None else action.scale,
                        x_reverse=state.x_reverse if action.reverse is None else action.reverse,
                    )
                elif action.target == f"axis:{token}.y":
                    if action.scale not in {None, "linear", "log10"}:
                        raise ValueError("X38 Y axis supports linear or log10")
                    state = replace(
                        state,
                        y_label=state.y_label if action.label is None else action.label,
                        y_scale=state.y_scale if action.scale is None else action.scale,
                        y_reverse=state.y_reverse if action.reverse is None else action.reverse,
                    )
                else:
                    raise ValueError("X38 axis target does not belong to this plot")
            elif isinstance(action, SetSeriesStyle):
                prefix = f"series:{token}.group_"
                suffix = (
                    action.target.removeprefix(prefix) if action.target.startswith(prefix) else ""
                )
                if (
                    not suffix.isdigit()
                    or not 1 <= int(suffix) <= len(state.series)
                    or action.symbol is not None
                    or action.symbol_size_pt is not None
                ):
                    raise ValueError("X38 series target or style is unsupported")
                index = int(suffix) - 1
                current = state.series[index]
                updated = replace(
                    current,
                    color=current.color if action.color is None else action.color,
                    line_width_pt=current.line_width_pt
                    if action.line_width_pt is None
                    else action.line_width_pt,
                    line_style=current.line_style
                    if action.line_style is None
                    else action.line_style,
                )
                state = replace(
                    state, series=(*state.series[:index], updated, *state.series[index + 1 :])
                )
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main" or action.anchor is not None:
                    raise ValueError("X38 exposes only legend visibility")
                state = replace(
                    state,
                    legend_visible=state.legend_visible
                    if action.visible is None
                    else action.visible,
                )
            else:
                raise ValueError(f"Origin X38 binder cannot apply {action.operation}")
        return state

    def _write(self, data: OffsetStackData) -> None:
        self.sheet.from_list(0, list(data.series[0].x_values), lname=data.x_field_name, axis="X")
        for index, series in enumerate(data.series, start=1):
            self.sheet.from_list(index, list(series.y_values), lname=series.label, axis="Y")

    def _axis_label(self, name: str, text: str) -> None:
        label = self.layer.label(name) or self.layer.add_label(text)
        if label is None:
            raise RuntimeError("Origin X38 has no writable axis label")
        label.text = text
        label.set_int("show", 1)

    def _set_legend(self, data: OffsetStackData, visible: bool) -> None:
        legend = self.layer.label("legend")
        if legend is None:
            self.layer.activate()
            self.layer.obj.LT_execute("legend")
            legend = self.layer.label("legend")
        if legend is None:
            raise RuntimeError("Origin X38 has no writable legend")
        legend.text = "\n".join(
            f"\\l({index}, style:l) {series.label}"
            for index, series in enumerate(data.series, start=1)
        )
        legend.set_int("link", 1)
        legend.set_int("show", int(visible))

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[object, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin X38 {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
                if abs(float(cast(Any, observed)) - float(wanted)) <= 1e-9:
                    continue
            elif observed == wanted:
                continue
            raise RuntimeError(f"Origin X38 {role} values differ after reopen")


def execute_x38_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    project = X38OriginProject(op)
    project.create(install_dir, request.document, request.data)
    project.reconcile(request.document, request.actions, request.data)
    project.save(output)
    reopened = X38OriginProject(op)
    reopened.open(output)
    return reopened.verify(request.document, request.actions, request.data)
