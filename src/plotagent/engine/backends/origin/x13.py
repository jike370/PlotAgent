"""X13 official PopulationPyramid template binder."""

from __future__ import annotations

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
from plotagent.engine.profile_data import PopulationPyramidData, x13_population_pyramid
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import X13_ORIGIN_PROFILE, resolve_official_template

_HORIZONTAL_BAR = 215
_TITLE_NAME = "_ENGINE_TITLE"


def _safe_label(value: str) -> str:
    return "".join(
        f"\\x({ord(character):04X})" if character in {"\\", "%", "$"} else character
        for character in value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    ).strip()


class X13OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layers: tuple[Any, Any] | None = None
        self.plots: tuple[Any, Any] | None = None
        self.sheet: Any = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, X13_ORIGIN_PROFILE)
        pyramid = x13_population_pyramid(document, data)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the X13 data workbook")
        self.sheet = book[0]
        self._write_data(pyramid)
        self.graph = self.op.new_graph(
            f"G{token}",
            template=str(template.with_suffix(template.suffix.lower())),
            hidden=True,
        )
        if self.graph is None:
            raise RuntimeError("Origin could not create a graph from PopulationPyramid.otpu")
        native_layers = list(self.graph)
        if len(native_layers) != 2:
            raise RuntimeError("Origin PopulationPyramid.otpu must provide exactly two layers")
        self.layers = (native_layers[0], native_layers[1])
        left = self.layers[0].add_plot(self.sheet, coly=1, colx=0, type=_HORIZONTAL_BAR)
        right = self.layers[1].add_plot(self.sheet, coly=2, colx=0, type=_HORIZONTAL_BAR)
        if left is None or right is None:
            raise RuntimeError("Origin population template rejected one native bar series")
        self.plots = (left, right)
        for layer in self.layers:
            layer.rescale()

    def reopen(self, project_path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=True, asksave=False):
            raise RuntimeError("fresh Origin session could not reopen the staged X13 project")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("fresh X13 project has unexpected graph or workbook count")
        self.graph = graphs[0]
        native_layers = list(self.graph)
        if len(native_layers) != 2:
            raise RuntimeError("fresh X13 project lost one official template layer")
        self.layers = (native_layers[0], native_layers[1])
        plots = tuple(tuple(layer.plot_list()) for layer in self.layers)
        if any(len(layer_plots) != 1 for layer_plots in plots):
            raise RuntimeError("fresh X13 project has an invalid native series count")
        self.plots = (plots[0][0], plots[1][0])
        self.sheet = books[0][0]

    def apply(self, document: PlotDocument, action: PlotEngineAction, data: EngineDataView) -> None:
        if self.layers is None or self.plots is None:
            raise RuntimeError("X13 project is not initialized")
        pyramid = x13_population_pyramid(document, data)
        token = document.plot_id.removeprefix("plot:")
        if isinstance(action, (CreatePlot, BindFields)):
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError("X13 title target does not belong to this plot")
            label = self.layers[0].label(_TITLE_NAME)
            if label is None:
                label = self.layers[0].add_label(action.text, 40, 2)
                if label is None:
                    raise RuntimeError("Origin could not create the X13 title")
                label.name = _TITLE_NAME
            label.text = action.text
            label.set_int("show", 1)
            return
        if isinstance(action, SetAxis):
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
            if axis_name is None:
                raise ValueError("X13 axis target does not belong to this plot")
            expected_scale = "linear" if axis_name == "x" else "categorical"
            if action.scale is not None and action.scale != expected_scale:
                raise ValueError("Origin X13 axes are fixed by the official template")
            axes = tuple(layer.axis(axis_name) for layer in self.layers)
            if action.minimum is not None and action.maximum is not None:
                if axis_name == "x":
                    bound = max(abs(action.minimum), abs(action.maximum))
                    axes[0].set_limits(bound, 0.0)
                    axes[1].set_limits(0.0, bound)
                else:
                    for axis in axes:
                        axis.set_limits(action.minimum, action.maximum)
            if action.reverse is not None:
                for axis in axes:
                    begin, end, step = (float(value) for value in axis.limits)
                    should_reverse = begin < end if action.reverse else begin > end
                    if should_reverse:
                        axis.set_limits(end, begin, abs(step))
            if action.label is not None:
                target_layers = self.layers if axis_name == "x" else self.layers[:1]
                for layer in target_layers:
                    label = layer.label("xb" if axis_name == "x" else "yl")
                    if label is None:
                        label = layer.add_label(action.label)
                    if label is None:
                        raise RuntimeError("Origin X13 template has no writable axis label")
                    label.text = action.label
                    label.set_int("show", 1)
            return
        if isinstance(action, SetSeriesStyle):
            ordinal = {
                f"series:{token}.left": 0,
                f"series:{token}.right": 1,
            }.get(action.target)
            if ordinal is None:
                raise ValueError("X13 series target does not belong to this plot")
            if any(
                value is not None
                for value in (action.line_style, action.symbol, action.symbol_size_pt)
            ):
                raise ValueError("Origin X13 exposes bar fill color and edge width only")
            plot = self.plots[ordinal]
            if action.color is not None:
                plot.color = action.color
            if action.line_width_pt is not None:
                plot.set_float("line.width", action.line_width_pt)
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main" or action.anchor is not None:
                raise ValueError("X13 legend target or anchor is not supported")
            legend = self.layers[0].label("legend")
            if action.visible and legend is None:
                self.layers[0].activate()
                if not self.layers[0].obj.LT_execute("legend"):
                    raise RuntimeError("Origin could not create the X13 legend")
                legend = self.layers[0].label("legend")
            if legend is not None and action.visible is not None:
                legend.text = (
                    f"\\l(1) {_safe_label(pyramid.left_field_name)}\n"
                    f"\\l(2.1) {_safe_label(pyramid.right_field_name)}"
                )
                legend.set_int("link", 1)
                legend.set_int("show", int(action.visible))
            return
        raise ValueError(f"Origin X13 binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output_path))
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError("Origin did not save a non-empty X13 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        if self.layers is None or self.plots is None:
            raise RuntimeError("X13 project is not initialized")
        pyramid = x13_population_pyramid(document, data)
        expected = (pyramid.categories, pyramid.left_values, pyramid.right_values)
        for index, values in enumerate(expected):
            actual = tuple(self.sheet.to_list(index))
            if len(actual) != len(values) or any(
                str(found) != str(wanted)
                if isinstance(wanted, str)
                else abs(float(cast(Any, found)) - float(cast(Any, wanted))) > 1e-12
                for found, wanted in zip(actual, values, strict=True)
            ):
                raise RuntimeError(f"Origin X13 data column {index} differs after reopen")
        token = document.plot_id.removeprefix("plot:")
        snapshot: dict[str, object] = {"layers": 2, "categories": pyramid.categories}
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layers[0].label(_TITLE_NAME)
                if title is None or title.text != action.text or not title.get_int("show"):
                    raise RuntimeError("Origin X13 title did not survive readback")
            elif isinstance(action, SetSeriesStyle) and action.color is not None:
                ordinal = 0 if action.target == f"series:{token}.left" else 1
                expected_color = tuple(
                    int(action.color[index : index + 2], 16) for index in (1, 3, 5)
                )
                if tuple(self.plots[ordinal].color) != expected_color:
                    raise RuntimeError("Origin X13 series color did not survive readback")
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layers[0].label("legend")
                if legend is None or bool(legend.get_int("show")) != action.visible:
                    raise RuntimeError("Origin X13 legend visibility did not survive readback")
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
                    native_ref=f"graph:{self.graph.name}.layers:1-2.axis:x",
                ),
                EngineObjectRef(
                    semantic_id=f"axis:{token}.y",
                    backend="origin",
                    object_kind="axis",
                    native_ref=f"graph:{self.graph.name}.layer:1.axis:y",
                ),
                EngineObjectRef(
                    semantic_id=f"series:{token}.left",
                    backend="origin",
                    object_kind="native_population_bar",
                    native_ref=f"graph:{self.graph.name}.layer:1.plot:1",
                ),
                EngineObjectRef(
                    semantic_id=f"series:{token}.right",
                    backend="origin",
                    object_kind="native_population_bar",
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
            style_hash=canonical_hash(cast(JsonValue, snapshot)),
        )

    def _write_data(self, pyramid: PopulationPyramidData) -> None:
        columns: tuple[tuple[str, tuple[object, ...], str], ...] = (
            (pyramid.category_field_name, pyramid.categories, "X"),
            (pyramid.left_field_name, pyramid.left_values, "Y"),
            (pyramid.right_field_name, pyramid.right_values, "Y"),
        )
        for index, (label, values, axis) in enumerate(columns):
            self.sheet.from_list(index, list(values), lname=label, axis=axis)


def execute_x13_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    project = X13OriginProject(op)
    project.create(install_dir, request.document, request.data)
    for action in request.actions:
        project.apply(request.document, action, request.data)
    project.save(output)
    reopened = X13OriginProject(op)
    reopened.reopen(output)
    return reopened.verify(request.document, request.actions, request.data)
