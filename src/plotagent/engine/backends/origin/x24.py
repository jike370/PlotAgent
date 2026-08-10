"""X24 official Pareto template binder with one cumulative authority."""

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
    SetChartParameter,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import ParetoData, x24_pareto
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import X24_ORIGIN_PROFILE, resolve_official_template

_TITLE_NAME = "_ENGINE_TITLE"
_COLUMN = 203


@dataclass(frozen=True, slots=True)
class _State:
    title: str = ""
    x_label: str = ""
    left_label: str = ""
    right_label: str = "Cumulative (%)"
    bar_color: str | None = None
    bar_line_width_pt: float | None = None
    bar_line_style: str | None = None
    line_color: str | None = None
    line_width_pt: float | None = None
    line_style: str | None = None
    legend_visible: bool = True
    reference_percent: float = 80.0


class X24OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layers: tuple[Any, Any] | None = None
        self.plots: tuple[Any, Any] | None = None
        self.sheet: Any = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, X24_ORIGIN_PROFILE)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the X24 workbook")
        self.sheet = book[0]
        pareto = x24_pareto(document, data)
        self._write(pareto)
        self.graph = self.op.new_graph(
            f"G{token}", template=str(template.with_suffix(template.suffix.lower())), hidden=True
        )
        if self.graph is None:
            raise RuntimeError("Origin could not create X24 from ParetoRaw.otpu")
        layers = list(self.graph)
        if len(layers) != 2:
            raise RuntimeError("Origin ParetoRaw.otpu must provide exactly two layers")
        self.layers = (layers[0], layers[1])
        for layer in self.layers:
            for plot in layer.plot_list():
                plot.set_int("show", 0)
        bars = self.layers[0].add_plot(self.sheet, coly=1, colx=0, type=_COLUMN)
        cumulative = self.layers[1].add_plot(self.sheet, coly=2, colx=0, type="?")
        if bars is None or cumulative is None:
            raise RuntimeError("Origin Pareto template rejected a native plot")
        self.plots = (bars, cumulative)
        for layer in self.layers:
            layer.rescale()

    def open(self, path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(path), readonly=False, asksave=False):
            raise RuntimeError("Origin could not reopen the X24 project")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("X24 project must contain one graph and workbook")
        self.graph = graphs[0]
        layers = list(self.graph)
        if len(layers) != 2:
            raise RuntimeError("X24 project lost one official layer")
        self.layers = (layers[0], layers[1])
        visible = tuple(
            tuple(plot for plot in layer.plot_list() if plot.get_int("show") != 0)
            for layer in self.layers
        )
        if tuple(len(items) for items in visible) != (1, 1):
            raise RuntimeError("X24 project must retain one visible plot per layer")
        self.plots = (visible[0][0], visible[1][0])
        self.sheet = books[0][0]

    def reconcile(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> None:
        pareto = x24_pareto(document, data)
        self._write(pareto)
        state = self._state(document, actions, pareto)
        title = self._layers()[0].label(_TITLE_NAME)
        if title is None and state.title:
            title = self._layers()[0].add_label(state.title, 40, 2)
            if title is None:
                raise RuntimeError("Origin could not create the X24 title")
            title.name = _TITLE_NAME
        if title is not None:
            title.text = state.title
            title.set_int("show", int(bool(state.title)))
        for layer in self._layers():
            layer.set_int("x.label.type", 10)
            layer.set_str("x.label.string", " ".join(f'"{label}"' for label in pareto.categories))
        self._axis_label(self._layers()[0], "xb", state.x_label)
        self._axis_label(self._layers()[0], "yl", state.left_label)
        self._axis_label(self._layers()[1], "yr", state.right_label)
        self._layers()[1].axis("y").set_limits(0.0, 100.0, 20.0)
        self._layers()[1].set_int("y.reflines.count", 1)
        self._layers()[1].set_float("y.refline1.value", state.reference_percent)
        self._layers()[1].set_int("y.refline1.lineshow", 1)
        if state.bar_color is not None:
            self._plots()[0].color = state.bar_color
        if state.bar_line_width_pt is not None:
            self._plots()[0].set_float("line.width", state.bar_line_width_pt)
        if state.bar_line_style is not None:
            style_code = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}[state.bar_line_style]
            self._plots()[0].set_int("line.style", style_code)
        if state.line_color is not None:
            self._plots()[1].color = state.line_color
        if state.line_width_pt is not None:
            self._plots()[1].set_float("line.width", state.line_width_pt)
        if state.line_style is not None:
            if state.line_style == "none":
                raise ValueError("X24 cumulative curve cannot be hidden through line style")
            self._plots()[1].set_int(
                "line.style",
                {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}[state.line_style],
            )
        self._set_legend(pareto, state.legend_visible)
        for layer in self._layers():
            layer.rescale()

    def save(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output))
        if not output.is_file() or output.stat().st_size <= 0:
            raise RuntimeError("Origin did not save a non-empty X24 project")

    def verify(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> EngineReadback:
        pareto = x24_pareto(document, data)
        state = self._state(document, actions, pareto)
        for index, expected in enumerate(
            (pareto.categories, pareto.values, pareto.cumulative_percent)
        ):
            self._assert_values(self.sheet.to_list(index), expected, f"column {index + 1}")
        if (
            abs(self._layers()[1].get_float("y.refline1.value") - state.reference_percent) > 1e-9
            or self._layers()[1].get_int("y.refline1.lineshow") != 1
        ):
            raise RuntimeError("Origin X24 reference line did not survive readback")
        legend = self._layers()[0].label("legend")
        if legend is None or bool(legend.get_int("show")) != state.legend_visible:
            raise RuntimeError("Origin X24 legend did not survive readback")
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
                semantic_id=f"series:{token}.bars",
                backend="origin",
                object_kind="pareto_bar_series",
                native_ref=f"graph:{self.graph.name}.layer:1.plot:1",
            ),
            EngineObjectRef(
                semantic_id=f"series:{token}.cumulative",
                backend="origin",
                object_kind="pareto_cumulative_series",
                native_ref=f"graph:{self.graph.name}.layer:2.plot:1",
            ),
            EngineObjectRef(
                semantic_id=f"annotation:{token}.pareto_reference_line",
                backend="origin",
                object_kind="pareto_reference_line",
                native_ref=f"graph:{self.graph.name}.layer:2.y.refline1",
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
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: ParetoData
    ) -> _State:
        token = document.plot_id.removeprefix("plot:")
        state = _State(x_label=data.category_field_name, left_label=data.value_field_name)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                key = {
                    f"axis:{token}.x": "x_label",
                    f"axis:{token}.y_left": "left_label",
                    f"axis:{token}.y_right": "right_label",
                }[action.target]
                if (
                    action.scale not in {None, "categorical" if key == "x_label" else "linear"}
                    or action.minimum is not None
                    or action.reverse is not None
                ):
                    raise ValueError("X24 exposes axis labels but fixed template scales")
                label = getattr(state, key) if action.label is None else action.label
                if key == "x_label":
                    state = replace(state, x_label=label)
                elif key == "left_label":
                    state = replace(state, left_label=label)
                else:
                    state = replace(state, right_label=label)
            elif isinstance(action, SetSeriesStyle):
                if action.target == f"series:{token}.bars":
                    if action.symbol is not None or action.symbol_size_pt is not None:
                        raise ValueError("X24 bars do not expose symbols")
                    state = replace(
                        state,
                        bar_color=state.bar_color if action.color is None else action.color,
                        bar_line_width_pt=(
                            state.bar_line_width_pt
                            if action.line_width_pt is None
                            else action.line_width_pt
                        ),
                        bar_line_style=state.bar_line_style
                        if action.line_style is None
                        else action.line_style,
                    )
                elif action.target == f"series:{token}.cumulative":
                    state = replace(
                        state,
                        line_color=state.line_color if action.color is None else action.color,
                        line_width_pt=state.line_width_pt
                        if action.line_width_pt is None
                        else action.line_width_pt,
                        line_style=state.line_style
                        if action.line_style is None
                        else action.line_style,
                    )
                else:
                    raise ValueError("X24 series target does not belong to this plot")
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main" or action.anchor is not None:
                    raise ValueError("X24 exposes only legend visibility")
                state = replace(
                    state,
                    legend_visible=state.legend_visible
                    if action.visible is None
                    else action.visible,
                )
            elif isinstance(action, SetChartParameter):
                if (
                    action.target != document.plot_id
                    or action.parameter != "pareto_reference_percent"
                    or not isinstance(action.value, (int, float))
                    or isinstance(action.value, bool)
                    or not 0 < float(action.value) <= 100
                ):
                    raise ValueError("X24 pareto_reference_percent must satisfy 0 < value <= 100")
                state = replace(state, reference_percent=float(action.value))
            else:
                raise ValueError(f"Origin X24 binder cannot apply {action.operation}")
        return state

    def _write(self, pareto: ParetoData) -> None:
        self.sheet.from_list(0, list(pareto.categories), lname=pareto.category_field_name, axis="X")
        self.sheet.from_list(1, list(pareto.values), lname=pareto.value_field_name, axis="Y")
        self.sheet.from_list(2, list(pareto.cumulative_percent), lname="Cumulative (%)", axis="Y")

    def _set_legend(self, pareto: ParetoData, visible: bool) -> None:
        layer = self._layers()[0]
        legend = layer.label("legend")
        if legend is None:
            layer.activate()
            layer.obj.LT_execute("legend")
            legend = layer.label("legend")
        if legend is None:
            raise RuntimeError("Origin X24 has no writable legend")
        legend.text = f"\\l(1, style:b) {pareto.value_field_name}\n\\l(2.1, style:l) Cumulative (%)"
        legend.set_int("link", 1)
        legend.set_int("show", int(visible))

    @staticmethod
    def _axis_label(layer: Any, name: str, text: str) -> None:
        label = (
            layer.label(name)
            or (layer.label("yl") if name == "yr" else None)
            or layer.add_label(text)
        )
        if label is None:
            raise RuntimeError("Origin X24 has no writable axis label")
        label.text = text
        label.set_int("show", 1)

    def _layers(self) -> tuple[Any, Any]:
        if self.layers is None:
            raise RuntimeError("X24 layers are not initialized")
        return self.layers

    def _plots(self) -> tuple[Any, Any]:
        if self.plots is None:
            raise RuntimeError("X24 plots are not initialized")
        return self.plots

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[object, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin X24 {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
                if abs(float(cast(Any, observed)) - float(wanted)) <= 1e-8:
                    continue
            elif observed == wanted:
                continue
            raise RuntimeError(f"Origin X24 {role} values differ after reopen")


def execute_x24_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    project = X24OriginProject(op)
    project.create(install_dir, request.document, request.data)
    project.reconcile(request.document, request.actions, request.data)
    project.save(output)
    reopened = X24OriginProject(op)
    reopened.open(output)
    return reopened.verify(request.document, request.actions, request.data)
