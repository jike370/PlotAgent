"""Official-template Origin binder for S01 survival plots."""

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
from plotagent.engine.profile_data import (
    SurvivalData,
    s01_survival,
)
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import S01_ORIGIN_PROFILE, resolve_official_template
from .trace import origin_trace_step, record_origin_trace

_TITLE = "_ENGINE_TITLE"
_COLORS = ("#2A6FDB", "#D94B4B", "#2A9D6F", "#8A5CC2", "#D88700")
_OFFICIAL_HELP_URL = "https://docs.originlab.com/origin-help/kaplanmeier-dialog/"
_OFFICIAL_OUTPUT_TEMPLATE = "SurvivalPlot.otp"


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


def _tick_string(labels: tuple[str, ...]) -> str:
    return " ".join(f'"{label.replace(chr(34), chr(92) + chr(34))}"' for label in labels)


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


class S01OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layers: tuple[Any, Any] | None = None
        self.sheet: Any = None
        self.plots: tuple[Any, ...] = ()
        self.last_native_structure: dict[str, object] | None = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={
                "help_url": _OFFICIAL_HELP_URL,
                "template_filename": S01_ORIGIN_PROFILE.filename,
                "template_sha256": S01_ORIGIN_PROFILE.sha256,
                "product_input_contract": "supplied survival geometry",
            },
        ):
            template = resolve_official_template(install_dir, S01_ORIGIN_PROFILE)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create S01 workbook")
        self.sheet = book[0]
        survival = s01_survival(document, data)
        with origin_trace_step(
            "source_data_write",
            details={"group_count": len(survival.groups), "precomputed": True},
        ):
            self._write(survival)
        with origin_trace_step(
            "official_survival_output_template_create",
            details={
                "official_output_template": _OFFICIAL_OUTPUT_TEMPLATE,
                "kaplan_meier_estimation_executed": False,
            },
        ):
            self.graph = self.op.new_graph(
                f"G{token}",
                template=str(template.with_suffix(template.suffix.lower())),
                hidden=True,
            )
        if self.graph is None:
            raise RuntimeError("Origin could not create S01 from SurvivalPlot.otp")
        layers = _ensure_layers(self.graph, 2)
        self.layers = (layers[0], layers[1])
        for layer in self.layers:
            for plot in layer.plot_list():
                plot.set_int("show", 0)
            template_legend = layer.label("legend")
            if template_legend is not None:
                template_legend.set_int("show", 0)
            template_title = layer.label("Title")
            if template_title is not None:
                template_title.set_int("show", 0)
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
        self.last_native_structure = self._native_structure(survival)
        record_origin_trace(
            "native_survival_composition_confirmed",
            "completed",
            details=self.last_native_structure,
        )

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
        main.activate()
        for index, (group, style) in enumerate(zip(survival.groups, styles, strict=True)):
            lower, upper, step = self.plots[index * 3 : index * 3 + 3]
            color = style.color or _COLORS[index % len(_COLORS)]
            for plot in (lower, upper, step):
                plot.color = color
                plot.set_int("show", 1)
            lower.set_cmd("-wp 0")
            upper.set_cmd("-wp 0")
            step.set_cmd(
                f"-d {_line_style(style.line_style)}",
                f"-wp {style.line_width_pt}",
            )
            if group.lower is not None:
                # originpro.set_fill_area requires an Origin color index, not a CSS
                # colour string.  Passing the hex string produces a saved line pair
                # without a native confidence fill in Origin 2024.
                origin_color = int(self.op.lt_float(f'color("{color}")'))
                lower.set_fill_area(above=origin_color, type=9)
                lower.transparency = 70
        group_count = len(survival.groups)
        risk_height = 8.0 + 6.0 * group_count
        risk_top = 84.0 - risk_height
        main_height = risk_top - 14.0
        main.lt_exec(
            f"layer.left=13;layer.top=7;layer.width=79;layer.height={main_height};"
            "axis -ps X L 0;"
        )
        risk.lt_exec(
            f"layer.left=13;layer.top={risk_top};"
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
        top_x_title = main.label("xt")
        if top_x_title is not None:
            top_x_title.set_int("show", 0)
        _title(main, state.title)
        risk_template_legend = risk.label("legend")
        if risk_template_legend is not None:
            risk_template_legend.set_int("show", 0)
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
        self.last_native_structure = self._native_structure(survival)
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

    def _native_structure(self, survival: SurvivalData) -> dict[str, object]:
        layers = self._layers()
        if len(self.plots) != len(survival.groups) * 3:
            raise RuntimeError("Origin S01 must retain lower/upper/step plots per group")
        designation_codes: list[int] = []
        for group_index in range(len(survival.groups)):
            base = group_index * 10
            designation_codes.extend(
                int(self.sheet.get_int(f"col{base + offset + 1}.type"))
                for offset in (0, 1, 2, 3, 5, 6, 7, 8, 9)
            )
        expected = [4, 1, 1, 1, 2, 2, 2, 2, 2] * len(survival.groups)
        if designation_codes != expected:
            raise RuntimeError("Origin S01 supplied survival worksheet designations changed")
        return {
            "official_help_url": _OFFICIAL_HELP_URL,
            "official_output_template": _OFFICIAL_OUTPUT_TEMPLATE,
            "kaplan_meier_estimation_executed": False,
            "layer_count": len(layers),
            "native_plot_count": len(self.plots),
            "group_count": len(survival.groups),
            "source_designations": designation_codes,
            "risk_table_layer": 2,
        }

    def _risk_labels(self, layer: Any, survival: SurvivalData, visible: bool) -> None:
        layer.axis("x").set_limits(
            min(group.time[0] for group in survival.groups),
            max(group.time[-1] for group in survival.groups),
        )
        layer.axis("y").set_limits(0.5, len(survival.groups) + 0.5, 1.0)
        layer.set_int("y.label.type", 10)
        layer.set_str(
            "y.label.string",
            _tick_string(tuple(group.label for group in reversed(survival.groups))),
        )
        _axis_label(layer, "x", survival.time_field_name)
        _axis_label(layer, "y", "At risk")
        for group_index, group in enumerate(survival.groups):
            row = float(len(survival.groups) - group_index)
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


def execute_s01_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(S01OriginProject(op), request, install_dir, output)
