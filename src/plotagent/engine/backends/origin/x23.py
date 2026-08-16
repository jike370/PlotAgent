"""X23 official DOUBLEY template binder with native two-layer readback."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isclose, isnan
from pathlib import Path
from typing import Any, Literal, cast

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import X23SeriesData, x23_series
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import X23_ORIGIN_PROFILE, resolve_official_template
from .readback import axis_scale_matches

_LINE_STYLE = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}
_LINE_SYMBOL = 202
_OFFICIAL_COMMAND = "worksheet -s 1 0 3 0; run.section(plot,2Ys_Y-Y);"
_TITLE_NAME = "_ENGINE_TITLE"


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
        self.book: Any = None
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
        self.book = self.op.new_book("w", f"D{token}", hidden=True)
        if self.book is None:
            raise RuntimeError("Origin could not create the X23 data workbook")
        for residue in tuple(self.op.pages("w")):
            if residue.name == "Book1" and residue.name != self.book.name:
                residue.destroy()
        self.sheet = self.book[0]
        self._write_data(document, data)
        self.sheet.activate()
        self.op.lt_exec(_OFFICIAL_COMMAND)
        if x23_series(document, data).x_labels is not None:
            self.sheet.activate()
            self.sheet.lt_exec("wks.col1.categorical.type=2; wks.col1.categorical.sort=0;")
            self.op.lt_exec("doc -u;")
        graphs = list(self.op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError("Origin 2Ys_Y-Y menu section must create exactly one graph")
        self.graph = graphs[0]
        self.graph.name = f"G{token}"
        self.graph.lname = f"X23 {template.stem} / {document.plot_id}"
        self._bind_native_graph()
        self._assert_native_structure(verify_offsets=False)

    def open(self, project_path: Path, *, readonly: bool = False) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=readonly, asksave=False):
            raise RuntimeError(f"Origin could not open the previous X23 project: {project_path}")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("X23 Origin project must contain one graph and one workbook")
        self.graph, self.book = graphs[0], books[0]
        self.sheet = self.book[0]
        self._bind_native_graph()

    def apply(self, document: PlotDocument, action: PlotEngineAction, data: EngineDataView) -> None:
        document.plot_id.removeprefix("plot:")
        if isinstance(action, CreatePlot):
            return
        if isinstance(action, BindFields):
            self._write_data(document, data)
            for layer in self._layers():
                layer.rescale()
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
        self._apply_series(1, state.left_series)
        self._apply_series(2, state.right_series)
        self._set_legend(series, state.legend_visible)

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Native readback visits layer 2.  Persist the official DOUBLEY page
        # with its primary layer active or Origin may reopen/export only the
        # transparent linked overlay instead of the complete two-layer page.
        self.graph.activate()
        self.op.lt_exec(f"{self.graph.name}!page.active=1;")
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
        native = self._assert_native_structure(verify_offsets=True)
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
                    object_kind="dual_y_line_symbol_series",
                    native_ref=f"graph:{self.graph.name}.layer:1.plot:1",
                ),
                EngineObjectRef(
                    semantic_id=f"series:{token}.right",
                    backend="origin",
                    object_kind="dual_y_line_symbol_series",
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
            style_hash=canonical_hash(cast(JsonValue, {"state": asdict(state), **native})),
        )

    def _write_data(self, document: PlotDocument, data: EngineDataView) -> None:
        series = x23_series(document, data)
        self.sheet.from_list(0, list(series.x_values), lname=series.x_field_name, axis="X")
        self.sheet.from_list(1, list(series.left_values), lname=series.left_field_name, axis="Y")
        self.sheet.from_list(2, list(series.right_values), lname=series.right_field_name, axis="Y")
        self.sheet.cols_axis("xyy")
        if series.x_labels is not None and hasattr(self.sheet, "lt_exec"):
            self.sheet.lt_exec("wks.col1.categorical.type=2; wks.col1.categorical.sort=0;")

    def _set_title(self, text: str) -> None:
        layer = self._layers()[0]
        title = layer.label(_TITLE_NAME)
        if title is None and text:
            title = layer.add_label(text)
            if title is None:
                raise RuntimeError("Origin could not create the X23 title")
            title.name = _TITLE_NAME
        if title is not None:
            title.text = text
            title.set_int("attach", 1)
            title.set_float("x1", 0.5)
            title.set_float("y1", 0.012)
            title.set_int("fsize", 14)
            title.set_int("background", 0)
            title.set_int("show", int(bool(text)))

    def _configure_x_axis(self, data: X23SeriesData, state: _AxisState) -> None:
        for layer in self._layers():
            axis = layer.axis("x")
            if data.x_labels is not None:
                if state.scale != "categorical":
                    raise ValueError("Origin X23 categorical x data cannot use a numeric scale")
                if state.minimum is not None and state.maximum is not None:
                    begin, end = state.minimum, state.maximum
                    if state.reverse:
                        begin, end = end, begin
                    axis.set_limits(begin, end)
                elif state.reverse:
                    begin, end, step = (float(value) for value in axis.limits)
                    axis.set_limits(end, begin, abs(step))
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

    def _apply_series(self, layer_index: int, state: _SeriesEdit) -> None:
        commands: list[str] = []
        if state.color is not None:
            commands.extend(
                (
                    f'set %C -cl color("{state.color}")',
                    f'set %C -cse color("{state.color}")',
                    f'set %C -csf color("{state.color}")',
                )
            )
        if state.line_width_pt is not None:
            commands.append(f"set %C -wp {state.line_width_pt}")
        if state.line_style is not None:
            if state.line_style == "none":
                raise ValueError("Origin X23 cannot hide one of its two lines")
            commands.append(f"set %C -d {_LINE_STYLE[state.line_style]}")
        if commands:
            self.op.lt_exec(self._graph_layer_prefix(layer_index) + "; ".join(commands) + ";")

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
            f"\\l(1) {_safe_legend_label(data.left_field_name)}\n"
            f"\\l(2.1) {_safe_legend_label(data.right_field_name)}"
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
            if not axis_scale_matches(axis.scale, axis_state.scale):
                raise RuntimeError("Origin X23 y-axis scale did not survive readback")
            label = layer.label(label_name) or (layer.label("yl") if label_name == "yr" else None)
            if label is None or label.text != axis_state.label:
                raise RuntimeError("Origin X23 y-axis label did not survive readback")
            self._assert_direction(axis, axis_state.reverse)
        x_label = self._layers()[0].label("xb")
        if x_label is None or x_label.text != state.x_axis.label:
            raise RuntimeError("Origin X23 x-axis label did not survive readback")
        for layer in self._layers():
            self._assert_direction(layer.axis("x"), state.x_axis.reverse)
        for layer_index, edit in enumerate((state.left_series, state.right_series), start=1):
            self._assert_series_style(layer_index, edit)
        legend = self._layers()[0].label("legend")
        if (
            legend is None
            or legend.get_int("link") != 1
            or bool(legend.get_int("show")) != state.legend_visible
        ):
            raise RuntimeError("Origin X23 legend visibility did not survive readback")
        legend_text = str(legend.text)
        if (
            legend_text.count(r"\l(") != 2
            or r"\l(1)" not in legend_text
            or r"\l(2.1)" not in legend_text
            or _safe_legend_label(data.left_field_name) not in legend_text
            or _safe_legend_label(data.right_field_name) not in legend_text
        ):
            raise RuntimeError("Origin X23 legend lost a native cross-layer sample")

    def _bind_native_graph(self) -> None:
        native_layers = tuple(self.graph)
        if len(native_layers) != 2:
            raise RuntimeError("Origin DOUBLEY.OTP must provide exactly two native layers")
        self.layers = (native_layers[0], native_layers[1])
        native_plots = tuple(tuple(layer.plot_list()) for layer in self.layers)
        if tuple(len(items) for items in native_plots) != (1, 1):
            raise RuntimeError("Origin DOUBLEY must create one native plot in each layer")
        self.plots = (native_plots[0][0], native_plots[1][0])

    def _graph_layer_prefix(self, layer_index: int) -> str:
        return f"window -a {self.graph.name}; {self.graph.name}!page.active={layer_index}; "

    def _assert_native_structure(self, *, verify_offsets: bool) -> dict[str, object]:
        if self.book is None:
            raise RuntimeError("X23 source workbook is not initialized")
        plot_ids: list[int] = []
        symbol_kinds: list[int] = []
        symbol_sizes: list[float] = []
        x_ranges: list[str] = []
        y_ranges: list[str] = []
        for layer_index, expected_y in enumerate(("B", "C"), start=1):
            prefix = f"__X23{layer_index}"
            command = (
                self._graph_layer_prefix(layer_index)
                + f"get %C -pt {prefix}PT; get %C -k {prefix}K; get %C -z {prefix}Z; "
                + f"range -wx {prefix}X=1; range -wy {prefix}Y=1; "
                + f"string {prefix}XS$=%({prefix}X); string {prefix}YS$=%({prefix}Y);"
            )
            if verify_offsets:
                command += (
                    f" get %C -sx {prefix}SX; get %C -sxs {prefix}SXS;"
                    f" get %C -sy {prefix}SY; get %C -sys {prefix}SYS;"
                )
            self.op.lt_exec(command)
            plot_id = float(self.op.lt_float(f"{prefix}PT"))
            symbol_kind = int(self.op.lt_float(f"{prefix}K"))
            symbol_size = float(self.op.lt_float(f"{prefix}Z"))
            if isnan(plot_id) or int(plot_id) != _LINE_SYMBOL:
                raise RuntimeError(
                    f"Origin X23 layer {layer_index} must be Line+Symbol PID {_LINE_SYMBOL}"
                )
            if symbol_kind <= 0 or symbol_size <= 0:
                raise RuntimeError(
                    f"Origin X23 layer {layer_index} lost its native visible symbols"
                )
            x_range = str(self.op.get_lt_str(f"{prefix}XS"))
            y_range = str(self.op.get_lt_str(f"{prefix}YS"))
            source_prefix = f"[{self.book.name}]"
            if not x_range.startswith(source_prefix) or '!A"' not in x_range:
                raise RuntimeError(
                    f"Origin X23 layer {layer_index} lost shared X source A: {x_range!r}"
                )
            if not y_range.startswith(source_prefix) or f'!{expected_y}"' not in y_range:
                raise RuntimeError(
                    f"Origin X23 layer {layer_index} lost Y source {expected_y}: {y_range!r}"
                )
            if verify_offsets:
                values = (
                    float(self.op.lt_float(f"{prefix}SX")),
                    float(self.op.lt_float(f"{prefix}SXS")),
                    float(self.op.lt_float(f"{prefix}SY")),
                    float(self.op.lt_float(f"{prefix}SYS")),
                )
                if any(
                    not isclose(actual, expected, abs_tol=1e-8)
                    for actual, expected in zip(values, (0.0, 1.0, 0.0, 1.0), strict=True)
                ):
                    raise RuntimeError(
                        f"Origin X23 layer {layer_index} has non-native offset/scale {values}"
                    )
            plot_ids.append(int(plot_id))
            symbol_kinds.append(symbol_kind)
            symbol_sizes.append(symbol_size)
            x_ranges.append(x_range)
            y_ranges.append(y_range)
        self.op.lt_exec(
            self._graph_layer_prefix(2)
            + "__X23LINK=layer.link; __X23XLINK=layer.x.link; __X23YLINK=layer.y.link;"
        )
        link_target = int(self.op.lt_float("__X23LINK"))
        x_link = int(self.op.lt_float("__X23XLINK"))
        y_link = int(self.op.lt_float("__X23YLINK"))
        if (link_target, x_link, y_link) != (1, 1, 0):
            raise RuntimeError(
                "Origin X23 layer 2 must link to layer 1 with straight 1:1 X and "
                f"independent Y; observed {(link_target, x_link, y_link)}"
            )
        designations = [self.sheet.get_int(f"col{index}.type") for index in range(1, 4)]
        if designations != [4, 1, 1]:
            raise RuntimeError(
                f"Origin X23 source designation must remain XYY; observed {designations}"
            )
        datasets = tuple(str(plot.obj.DatasetName) for plot in self._plots())
        if not datasets[0].endswith("_B") or not datasets[1].endswith("_C"):
            raise RuntimeError(
                f"Origin X23 Origin C datasets are not the native B/C sources: {datasets}"
            )
        return {
            "official_menu_command": _OFFICIAL_COMMAND,
            "native_plot_ids": plot_ids,
            "symbol_kinds": symbol_kinds,
            "symbol_sizes": symbol_sizes,
            "source_x_ranges": x_ranges,
            "source_y_ranges": y_ranges,
            "origin_c_datasets": list(datasets),
            "layer2_link": {"target": link_target, "x": x_link, "y": y_link},
            "worksheet_designations": designations,
        }

    def _assert_series_style(self, layer_index: int, state: _SeriesEdit) -> None:
        if all(value is None for value in (state.color, state.line_width_pt, state.line_style)):
            return
        prefix = f"__X23STYLE{layer_index}"
        self.op.lt_exec(
            self._graph_layer_prefix(layer_index)
            + f"get %C -cl {prefix}C; get %C -w {prefix}W; get %C -d {prefix}D;"
        )
        if state.color is not None:
            expected = int(self.op.lt_float(f'color("{state.color}")'))
            if int(self.op.lt_float(f"{prefix}C")) != expected:
                raise RuntimeError("Origin X23 line/symbol color did not survive readback")
        if state.line_width_pt is not None and not isclose(
            float(self.op.lt_float(f"{prefix}W")) / 500.0,
            state.line_width_pt,
            abs_tol=1e-8,
        ):
            raise RuntimeError("Origin X23 line width did not survive readback")
        if (
            state.line_style is not None
            and state.line_style != "none"
            and int(self.op.lt_float(f"{prefix}D")) != _LINE_STYLE[state.line_style]
        ):
            raise RuntimeError("Origin X23 line style did not survive readback")

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
        document.plot_id.removeprefix("plot:")
        state = _X23State(
            title="",
            x_axis=_AxisState(data.x_field_name, cast(Any, data.x_scale)),
            left_axis=_AxisState(data.left_field_name, "linear"),
            right_axis=_AxisState(data.right_field_name, "linear"),
        )
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            raise ValueError(f"Origin X23 binder cannot apply {action.operation}")
        return state


def execute_x23_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    structure_output = output.with_name(f"{output.stem}.official-structure.opju")
    project = X23OriginProject(op)
    if request.previous_opju is None:
        project.create(install_dir, request.document, request.data)
        project.save(structure_output)
        editable = X23OriginProject(op)
        editable.open(structure_output)
        pending = request.actions
    else:
        editable = project
        editable.open(Path(request.previous_opju))
        pending = request.actions[-1:]
    for action in pending:
        editable.apply(request.document, action, request.data)
    editable.reconcile(request.document, request.actions, request.data)
    editable.save(output)

    reopened = X23OriginProject(op)
    reopened.open(output, readonly=True)
    readback = reopened.verify(request.document, request.actions, request.data)
    structure_output.unlink(missing_ok=True)
    return readback
