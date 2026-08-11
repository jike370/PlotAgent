"""Official-template Origin binders for K24 facets and S01 survival plots."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import isnan
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
from plotagent.engine.profile_data import (
    SurvivalData,
    TrellisData,
    k24_trellis_data,
    s01_survival,
)
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K24_ORIGIN_PROFILE, S01_ORIGIN_PROFILE, resolve_official_template
from .trace import origin_trace_step, record_origin_trace

_TITLE = "_ENGINE_TITLE"
_COLORS = ("#2A6FDB", "#D94B4B", "#2A9D6F", "#8A5CC2", "#D88700")


@dataclass(frozen=True, slots=True)
class _Style:
    color: str | None = None
    line_width_pt: float = 1.5
    line_style: str = "solid"


@dataclass(frozen=True, slots=True)
class _State:
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    x_minimum: float | None = None
    x_maximum: float | None = None
    y_minimum: float | None = None
    y_maximum: float | None = None
    x_reverse: bool = False
    y_reverse: bool = False
    legend_visible: bool = False
    show_risk_table: bool = True


def _style(current: _Style, action: SetSeriesStyle) -> _Style:
    if action.symbol is not None or action.symbol_size_pt is not None:
        raise ValueError("structural T2 line series do not expose symbols")
    return replace(
        current,
        color=current.color if action.color is None else action.color,
        line_width_pt=current.line_width_pt
        if action.line_width_pt is None
        else action.line_width_pt,
        line_style=current.line_style if action.line_style is None else action.line_style,
    )


def _line_style(value: str) -> int:
    if value == "none":
        raise ValueError("structural T2 series cannot hide its native line")
    return {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}[value]


def _ensure_layers(graph: Any, count: int) -> tuple[Any, ...]:
    while len(list(graph)) < count:
        graph.add_layer(0)
    return tuple(list(graph))


def _axis_label(layer: Any, axis: str, text: str) -> None:
    label = layer.label("xb" if axis == "x" else "yl") or layer.add_label(text)
    if label is None:
        raise RuntimeError("Origin structural template has no writable axis label")
    label.text = text
    label.set_int("show", 1)


def _title(layer: Any, text: str) -> None:
    label = layer.label(_TITLE)
    if label is None and text:
        label = layer.add_label(text, 40, 2)
        if label is None:
            raise RuntimeError("Origin could not create the structural title")
        label.name = _TITLE
    if label is not None:
        label.text = text
        label.set_int("show", int(bool(text)))


def _apply_axis_state(layer: Any, state: _State) -> None:
    for axis in ("x", "y"):
        minimum = getattr(state, f"{axis}_minimum")
        maximum = getattr(state, f"{axis}_maximum")
        reverse = getattr(state, f"{axis}_reverse")
        native = layer.axis(axis)
        if minimum is not None and maximum is not None:
            begin, end = float(minimum), float(maximum)
            if reverse:
                begin, end = end, begin
            native.set_limits(begin, end)
        elif reverse:
            limits = getattr(native, "limits", (0.0, 1.0, 0.1))
            native.set_limits(float(limits[1]), float(limits[0]))
    _axis_label(layer, "x", state.x_label)
    _axis_label(layer, "y", state.y_label)


class K24OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.sheet: Any = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={"template_filename": K24_ORIGIN_PROFILE.filename},
        ):
            template = resolve_official_template(install_dir, K24_ORIGIN_PROFILE)
        trellis = k24_trellis_data(document, data)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            book = self.op.new_book("w", f"D{token}", hidden=True)
            if book is None:
                raise RuntimeError("Origin could not create K24 workbook")
            for residue in tuple(self.op.pages("w")):
                if residue.name == "Book1" and residue.name != book.name:
                    residue.destroy()
            self.sheet = book[0]
        with origin_trace_step(
            "source_data_write",
            details={"column_count": 3, "row_count": len(trellis.x_values)},
        ):
            self._write(trellis)
        with origin_trace_step(
            "official_plot_group_execute",
            details={
                "plot_type": "linesymb",
                "horizontal_group_role": "facet",
                "color_group_role": "facet",
                "template_filename": template.name,
            },
        ):
            self.sheet.activate()
            source = self.sheet.lt_range(False)
            self.op.lt_exec(
                f"plot_group iy:={source}!(A,B) type:=linesymb dyaxes:=0 "
                f"horz:={source}!(C) color:={source}!(C) template:={template.stem};"
            )
        with origin_trace_step("native_structure_readback"):
            graphs = list(self.op.pages("g"))
            if len(graphs) != 1:
                raise RuntimeError("Origin plot_group must create exactly one K24 graph")
            self.graph = graphs[0]
            self.graph.lname = f"K24 Trellis / {document.plot_id}"
            layers = tuple(self.graph)
            if len(layers) != 1:
                raise RuntimeError("Origin K24 Trellis must remain one native layer")
            self.layer = layers[0]
            self._assert_native_plot()
            self.layer.rescale()
        record_origin_trace(
            "native_structure_confirmed",
            "completed",
            details={"graph_count": 1, "layer_count": 1, "native_plot_id": 202},
        )

    def open(self, output: Path) -> None:
        with origin_trace_step("saved_project_reopen", details={"readonly": False}):
            self.op.new(asksave=False)
            if not self.op.open(str(output), readonly=False, asksave=False):
                raise RuntimeError("Origin could not reopen K24")
        graphs, books = list(self.op.pages("g")), list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("K24 must contain one graph and workbook")
        self.graph, self.sheet = graphs[0], books[0][0]
        layers = tuple(self.graph)
        if len(layers) != 1:
            raise RuntimeError("K24 Trellis changed from its one-layer native structure")
        self.layer = layers[0]
        self._assert_native_plot()

    def reconcile(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> None:
        trellis = k24_trellis_data(document, data)
        with origin_trace_step(
            "agent_actions_apply", details={"action_count": len(actions)}
        ):
            self._write(trellis)
            state, styles = self._state(document, actions, trellis)
            self.layer.rescale()
            _apply_axis_state(self.layer, state)
            self._set_title(state.title)
            self._apply_facet_colors(styles)

    def save(self, output: Path) -> None:
        with origin_trace_step("opju_save", details={"filename": output.name}):
            output.parent.mkdir(parents=True, exist_ok=True)
            self.op.save(str(output))
            if not output.is_file() or output.stat().st_size <= 0:
                raise RuntimeError("Origin did not save a non-empty K24 project")

    def verify(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> EngineReadback:
        trellis = k24_trellis_data(document, data)
        state, styles = self._state(document, actions, trellis)
        with origin_trace_step("reopened_native_structure_verify"):
            self._assert_native_plot()
        with origin_trace_step(
            "reopened_source_data_verify",
            details={"column_count": 3, "row_count": len(trellis.x_values)},
        ):
            self._assert_values(self.sheet.to_list(0), trellis.x_values, "X")
            self._assert_values(self.sheet.to_list(1), trellis.y_values, "Y")
            self._assert_values(self.sheet.to_list(2), trellis.facet_values, "facet")
        with origin_trace_step("reopened_agent_edits_verify"):
            self._assert_labels(state)
            self._assert_axis_limits(state)
            self._assert_facet_colors(styles)
        token = document.plot_id.removeprefix("plot:")
        objects: list[EngineObjectRef] = [
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
        ]
        for index in range(len(trellis.facet_labels)):
            objects.extend(
                (
                    EngineObjectRef(
                        semantic_id=f"panel:{token}.facet_{index + 1}",
                        backend="origin",
                        object_kind="facet_panel",
                        native_ref=f"graph:{self.graph.name}.layer:1.plot:1.panel:{index + 1}",
                    ),
                    EngineObjectRef(
                        semantic_id=f"series:{token}.facet_{index + 1}",
                        backend="origin",
                        object_kind="facet_series",
                        native_ref=f"graph:{self.graph.name}.layer:1.plot:1.subset:{index + 1}",
                    ),
                )
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
                        "state": asdict(state),
                        "styles": [asdict(style) for style in styles],
                        "native_plot_id": 202,
                        "template": K24_ORIGIN_PROFILE.filename,
                    },
                )
            ),
        )

    def _write(self, trellis: TrellisData) -> None:
        self.sheet.cols = 3
        self.sheet.from_list(0, list(trellis.x_values), lname=trellis.x_field_name, axis="X")
        self.sheet.from_list(1, list(trellis.y_values), lname=trellis.y_field_name, axis="Y")
        self.sheet.from_list(
            2,
            list(trellis.facet_values),
            lname=trellis.facet_field_name,
            axis="N",
        )

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        trellis: TrellisData,
    ) -> tuple[_State, tuple[_Style, ...]]:
        token = document.plot_id.removeprefix("plot:")
        state = _State(x_label=trellis.x_field_name, y_label=trellis.y_field_name)
        styles = tuple(_Style() for _label in trellis.facet_labels)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("K24 title target does not belong")
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                state = _axis_state(state, action, token, allow_scale=True)
            elif isinstance(action, SetSeriesStyle):
                prefix = f"series:{token}.facet_"
                if not action.target.startswith(prefix):
                    raise ValueError("K24 series target does not belong")
                index = int(action.target.removeprefix(prefix)) - 1
                if not 0 <= index < len(styles):
                    raise ValueError("K24 facet series target is out of range")
                if (
                    action.color is None
                    or action.line_width_pt is not None
                    or action.line_style is not None
                    or action.symbol is not None
                    or action.symbol_size_pt is not None
                ):
                    raise ValueError("K24 exposes only per-facet color")
                mutable = list(styles)
                mutable[index] = replace(mutable[index], color=action.color)
                styles = tuple(mutable)
            elif isinstance(action, (SetLegend, SetChartParameter)):
                raise ValueError(
                    "K24 native Trellis exposes neither a standalone legend nor manual panel layout"
                )
            else:
                raise ValueError(f"Origin K24 cannot apply {action.operation}")
        return state, styles

    def _assert_native_plot(self) -> None:
        self.graph.activate()
        plot_id = float(self.op.lt_float("layer.plot1.pid"))
        if isnan(plot_id) or int(plot_id) != 202:
            raise RuntimeError("Origin K24 did not retain its native Line+Symbol Trellis DataPlot")

    def _set_title(self, text: str) -> None:
        title = self.layer.label(_TITLE)
        if title is None and text:
            self.layer.activate()
            if not self.layer.obj.LT_execute(
                f"label -b 4 -j 1 -n {_TITLE} PlotAgentTitlePlaceholder;"
            ):
                raise RuntimeError("Origin could not create the K24 title")
            title = self.layer.label(_TITLE)
        if title is not None:
            title.text = text
            title.set_int("attach", 1)
            title.set_float("x1", 0.5)
            title.set_float("y1", 0.06)
            title.set_int("show", int(bool(text)))

    def _apply_facet_colors(self, styles: tuple[_Style, ...]) -> None:
        if not any(style.color is not None for style in styles):
            return
        native = self._read_color_list("-cu", len(styles), "__K24DEFAULT")
        values: list[str] = []
        for index, style in enumerate(styles):
            if style.color is not None:
                values.append(f'color("{style.color}")')
            elif index < len(native) and not isnan(native[index]):
                values.append(str(int(native[index])))
            else:
                values.append(f'color("{_COLORS[index % len(_COLORS)]}")')
        expression = ",".join(values)
        self.graph.activate()
        self.op.lt_exec(
            f"dataset __K24COLORS={{{expression}}}; "
            "set %C -cue 1; set %C -cu __K24COLORS; "
            "set %C -cus __K24COLORS; set %C -cusf __K24COLORS;"
        )

    def _assert_facet_colors(self, styles: tuple[_Style, ...]) -> None:
        edited = tuple(
            (index, style.color)
            for index, style in enumerate(styles, start=1)
            if style.color
        )
        if not edited:
            return
        self.graph.activate()
        self.op.lt_exec("get %C -cue __K24ENABLED;")
        if int(self.op.lt_float("__K24ENABLED")) != 1:
            raise RuntimeError("Origin K24 facet color list was disabled after reopen")
        for option, variable in (
            ("-cu", "__K24LINE"),
            ("-cus", "__K24SYMBOL"),
            ("-cusf", "__K24FILL"),
        ):
            values = self._read_color_list(option, len(styles), variable)
            for ordinal, color in edited:
                expected = int(self.op.lt_float(f'color("{color}")'))
                if ordinal > len(values) or int(values[ordinal - 1]) != expected:
                    raise RuntimeError(
                        f"Origin K24 {option} facet color did not survive readback"
                    )

    def _read_color_list(self, option: str, count: int, variable: str) -> tuple[float, ...]:
        self.graph.activate()
        self.op.lt_exec(f"dataset {variable}; get %C {option} {variable};")
        return tuple(
            float(self.op.lt_float(f"{variable}[{index}]"))
            for index in range(1, count + 1)
        )

    def _assert_labels(self, state: _State) -> None:
        x_label = self.layer.label("xb")
        y_label = self.layer.label("yl")
        if x_label is None or x_label.text != state.x_label:
            raise RuntimeError("Origin K24 X-axis label did not survive readback")
        if y_label is None or y_label.text != state.y_label:
            raise RuntimeError("Origin K24 Y-axis label did not survive readback")
        title = self.layer.label(_TITLE)
        if state.title and (
            title is None or title.text != state.title or title.get_int("show") == 0
        ):
            raise RuntimeError("Origin K24 title did not survive readback")

    def _assert_axis_limits(self, state: _State) -> None:
        for axis_name in ("x", "y"):
            minimum = getattr(state, f"{axis_name}_minimum")
            maximum = getattr(state, f"{axis_name}_maximum")
            if minimum is None or maximum is None:
                continue
            observed = tuple(float(value) for value in self.layer.axis(axis_name).limits[:2])
            expected = (float(minimum), float(maximum))
            if getattr(state, f"{axis_name}_reverse"):
                expected = expected[::-1]
            differs = any(
                abs(left - right) > 1e-8
                for left, right in zip(observed, expected, strict=True)
            )
            if differs:
                raise RuntimeError(f"Origin K24 {axis_name.upper()} limits changed after reopen")

    @staticmethod
    def _assert_values(actual: list[Any], expected: tuple[Any, ...], label: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin K24 {label} row count changed after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if isinstance(wanted, float) and isnan(wanted):
                if not isinstance(observed, float) or not isnan(observed):
                    raise RuntimeError(f"Origin K24 {label} missing value changed after reopen")
            elif observed != wanted:
                raise RuntimeError(f"Origin K24 {label} values changed after reopen")


class S01OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layers: tuple[Any, Any] | None = None
        self.sheet: Any = None
        self.plots: tuple[Any, ...] = ()

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, S01_ORIGIN_PROFILE)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create S01 workbook")
        self.sheet = book[0]
        survival = s01_survival(document, data)
        self._write(survival)
        self.graph = self.op.new_graph(
            f"G{token}", template=str(template.with_suffix(template.suffix.lower())), hidden=True
        )
        if self.graph is None:
            raise RuntimeError("Origin could not create S01 from SurvivalPlot.otp")
        layers = _ensure_layers(self.graph, 2)
        self.layers = (layers[0], layers[1])
        for layer in self.layers:
            for plot in layer.plot_list():
                plot.set_int("show", 0)
        plots: list[Any] = []
        for index, _group in enumerate(survival.groups):
            for offset in (1, 2, 3):
                plot = self.layers[0].add_plot(
                    self.sheet, coly=index * 10 + offset, colx=index * 10, type=200
                )
                if plot is None:
                    raise RuntimeError("Origin S01 template rejected a survival plot")
                plots.append(plot)
        self.plots = tuple(plots)

    def open(self, output: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(output), readonly=False, asksave=False):
            raise RuntimeError("Origin could not reopen S01")
        graphs, books = list(self.op.pages("g")), list(self.op.pages("w"))
        self.graph, self.sheet = graphs[0], books[0][0]
        layers = tuple(self.graph)
        self.layers = (layers[0], layers[1])
        self.plots = tuple(plot for plot in self.layers[0].plot_list() if plot.get_int("show") != 0)

    def reconcile(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> None:
        survival = s01_survival(document, data)
        self._write(survival)
        state, styles = self._state(document, actions, survival)
        main, risk = self._layers()
        for index, (group, style) in enumerate(zip(survival.groups, styles, strict=True)):
            lower, upper, step = self.plots[index * 3 : index * 3 + 3]
            color = style.color or _COLORS[index % len(_COLORS)]
            for plot in (lower, upper, step):
                plot.color = color
                plot.set_int("line.style", _line_style(style.line_style))
                plot.set_int("show", 1)
            lower.set_float("line.width", 0.5)
            upper.set_float("line.width", 0.5)
            step.set_float("line.width", style.line_width_pt)
            if group.lower is not None:
                lower.set_fill_area(above=color, type=9)
        group_count = len(survival.groups)
        risk_height = 12.0 + 5.0 * group_count
        main.lt_exec(f"layer.left=13;layer.top=7;layer.width=79;layer.height={76.0 - risk_height};")
        risk.lt_exec(
            f"layer.left=13;layer.top={70.0 - risk_height / 2};"
            f"layer.width=79;layer.height={risk_height};"
        )
        main.rescale()
        _apply_axis_state(main, state)
        main.axis("y").set_limits(
            1.05 if state.y_reverse else 0.0,
            0.0 if state.y_reverse else 1.05,
            0.2,
        )
        _axis_label(main, "x", "")
        _title(main, state.title)
        legend = main.label("legend")
        if legend is None:
            main.activate()
            main.obj.LT_execute("legend")
            legend = main.label("legend")
        if legend is not None:
            legend.text = "\n".join(
                f"\\l({index * 3 + 3}) {group.label}" for index, group in enumerate(survival.groups)
            )
            legend.set_int("show", int(state.legend_visible))
        self._risk_labels(risk, survival, state.show_risk_table)

    def save(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output))

    def verify(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> EngineReadback:
        survival = s01_survival(document, data)
        state, styles = self._state(document, actions, survival)
        if len(self.plots) != len(survival.groups) * 3:
            raise RuntimeError("Origin S01 native plot count differs after reopen")
        for group_index, group in enumerate(survival.groups):
            raw_time = self.sheet.to_list(group_index * 10 + 5)
            raw_survival = self.sheet.to_list(group_index * 10 + 6)
            if (
                tuple(float(value) for value in raw_time) != group.time
                or tuple(float(value) for value in raw_survival) != group.survival
            ):
                raise RuntimeError("Origin S01 raw precomputed data differ after reopen")
        token = document.plot_id.removeprefix("plot:")
        objects: list[EngineObjectRef] = [
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
                semantic_id=f"panel:{token}.risk",
                backend="origin",
                object_kind="risk_table_panel",
                native_ref=f"graph:{self.graph.name}.layer:2",
            ),
            EngineObjectRef(
                semantic_id=f"legend:{token}.main",
                backend="origin",
                object_kind="legend",
                native_ref=f"graph:{self.graph.name}.layer:1.label:legend",
            ),
        ]
        objects.extend(
            EngineObjectRef(
                semantic_id=f"series:{token}.group_{index + 1}",
                backend="origin",
                object_kind="survival_step_series",
                native_ref=f"graph:{self.graph.name}.layer:1.plot:{index * 3 + 3}",
            )
            for index in range(len(survival.groups))
        )
        return EngineReadback(
            document=document_ref(document),
            backend="origin",
            objects=tuple(objects),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(
                cast(
                    JsonValue,
                    {"state": asdict(state), "styles": [asdict(style) for style in styles]},
                )
            ),
        )

    def _write(self, survival: SurvivalData) -> None:
        for index, group in enumerate(survival.groups):
            step_time = tuple(value for value in group.time for _copy in range(2))[1:]
            step_survival = tuple(value for value in group.survival for _copy in range(2))[:-1]
            lower = tuple(value for value in (group.lower or group.survival) for _copy in range(2))[
                :-1
            ]
            upper = tuple(value for value in (group.upper or group.survival) for _copy in range(2))[
                :-1
            ]
            base = index * 10
            self.sheet.from_list(base, list(step_time), lname=survival.time_field_name, axis="X")
            self.sheet.from_list(base + 1, list(lower), lname=f"{group.label} lower", axis="Y")
            self.sheet.from_list(base + 2, list(upper), lname=f"{group.label} upper", axis="Y")
            self.sheet.from_list(base + 3, list(step_survival), lname=group.label, axis="Y")
            self.sheet.from_list(base + 5, list(group.time), lname="Raw time", axis="N")
            self.sheet.from_list(base + 6, list(group.survival), lname="Raw survival", axis="N")
            self.sheet.from_list(base + 7, list(group.lower or ()), lname="Raw lower", axis="N")
            self.sheet.from_list(base + 8, list(group.upper or ()), lname="Raw upper", axis="N")
            self.sheet.from_list(
                base + 9, list(group.risk_count or ()), lname="Risk count", axis="N"
            )

    def _risk_labels(self, layer: Any, survival: SurvivalData, visible: bool) -> None:
        layer.axis("x").set_limits(
            min(group.time[0] for group in survival.groups),
            max(group.time[-1] for group in survival.groups),
        )
        layer.axis("y").set_limits(0.5, len(survival.groups) + 0.5, 1.0)
        _axis_label(layer, "x", survival.time_field_name)
        _axis_label(layer, "y", "At risk")
        for group_index, group in enumerate(survival.groups):
            row = float(len(survival.groups) - group_index)
            group_label = layer.label(f"_ENGINE_RISK_GROUP_{group_index}") or layer.add_label(
                group.label, group.time[0], row
            )
            if group_label is not None:
                group_label.name = f"_ENGINE_RISK_GROUP_{group_index}"
                group_label.text = group.label
                group_label.set_int("show", int(visible and group.risk_count is not None))
            if group.risk_count is None:
                continue
            for value_index, (time, count) in enumerate(
                zip(group.time, group.risk_count, strict=True)
            ):
                name = f"_ENGINE_RISK_{group_index}_{value_index}"
                label = layer.label(name) or layer.add_label(str(count), time, row)
                if label is None:
                    raise RuntimeError("Origin could not create S01 risk count label")
                label.name = name
                label.text = str(count)
                label.set_int("show", int(visible))
                label.set_int("attach", 2)
                label.set_float("x1", time)
                label.set_float("y1", row)

    def _layers(self) -> tuple[Any, Any]:
        if self.layers is None:
            raise RuntimeError("S01 layers are not initialized")
        return self.layers

    @staticmethod
    def _state(
        document: PlotDocument, actions: tuple[PlotEngineAction, ...], survival: SurvivalData
    ) -> tuple[_State, tuple[_Style, ...]]:
        token = document.plot_id.removeprefix("plot:")
        state = _State(
            x_label=survival.time_field_name,
            y_label=survival.survival_field_name,
            legend_visible=len(survival.groups) > 1,
        )
        styles = tuple(_Style() for _group in survival.groups)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                state = _axis_state(state, action, token, allow_scale=False)
            elif isinstance(action, SetSeriesStyle):
                prefix = f"series:{token}.group_"
                if not action.target.startswith(prefix):
                    raise ValueError("S01 series target does not belong")
                index = int(action.target.removeprefix(prefix)) - 1
                mutable = list(styles)
                mutable[index] = _style(mutable[index], action)
                styles = tuple(mutable)
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main" or action.anchor is not None:
                    raise ValueError("S01 exposes only legend visibility")
                state = replace(
                    state,
                    legend_visible=state.legend_visible
                    if action.visible is None
                    else action.visible,
                )
            elif isinstance(action, SetChartParameter):
                if action.parameter != "show_risk_table" or not isinstance(action.value, bool):
                    raise ValueError("S01 show_risk_table must be boolean")
                state = replace(state, show_risk_table=action.value)
            else:
                raise ValueError(f"Origin S01 cannot apply {action.operation}")
        return state, styles


def _axis_state(state: _State, action: SetAxis, token: str, *, allow_scale: bool) -> _State:
    axis = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
    if axis is None or (action.scale is not None and (not allow_scale or action.scale != "linear")):
        raise ValueError("structural T2 axis edit is invalid")
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


def execute_k24_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(K24OriginProject(op), request, install_dir, output)


def execute_s01_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(S01OriginProject(op), request, install_dir, output)
