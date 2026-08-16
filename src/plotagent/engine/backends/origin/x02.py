"""X02 native Vertical Drop Line binder using Origin's official plot command."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isclose, isnan
from pathlib import Path
from typing import Any, cast

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import XYSeriesData, xy_series
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import X02_ORIGIN_PROFILE, resolve_official_template
from .readback import axis_scale_matches
from .trace import origin_trace_step, record_origin_trace

_LINE_STYLE = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}
_SYMBOL = {"square": 1, "circle": 2, "triangle": 3, "triangle_up": 3, "diamond": 5}
_TITLE_NAME = "_ENGINE_TITLE"
_OFFICIAL_HELP_URL = "https://docs.originlab.com/origin-help/vertical-drop-line/"
_OFFICIAL_MENU = "Plot > Basic 2D > Vertical Drop Line"
_OFFICIAL_COMMAND = "worksheet -p 201 DROPLINE"


@dataclass(frozen=True, slots=True)
class _AxisEdits:
    label: str | None = None
    scale: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool | None = None


@dataclass(frozen=True, slots=True)
class _SeriesEdits:
    color: str | None = None
    line_width_pt: float | None = None
    line_style: str | None = None
    symbol: str | None = None
    symbol_size_pt: float | None = None


@dataclass(frozen=True, slots=True)
class _State:
    title: str | None = None
    x_axis: _AxisEdits = _AxisEdits()
    y_axis: _AxisEdits = _AxisEdits()
    series: _SeriesEdits = _SeriesEdits()
    legend_visible: bool | None = None


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


class X02OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.book: Any = None
        self.sheet: Any = None
        self.graph: Any = None
        self.layer: Any = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={"template_filename": X02_ORIGIN_PROFILE.filename},
        ):
            template = resolve_official_template(install_dir, X02_ORIGIN_PROFILE)
        series = xy_series(document, data, profile_id="X02")
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            self.book = self.op.new_book("w", f"D{token}", hidden=True)
            if self.book is None:
                raise RuntimeError("Origin could not create the X02 workbook")
            for residue in tuple(self.op.pages("w")):
                if residue.name == "Book1" and residue.name != self.book.name:
                    residue.destroy()
            self.sheet = self.book[0]
        with origin_trace_step(
            "source_data_write",
            details={"column_count": 2, "row_count": len(series.x_values)},
        ):
            self._write(series)
        with origin_trace_step(
            "official_plot_command_execute",
            details={
                "official_help_url": _OFFICIAL_HELP_URL,
                "official_menu": _OFFICIAL_MENU,
                "labtalk": _OFFICIAL_COMMAND,
                "template_filename": template.name,
            },
        ):
            self.sheet.activate()
            self.op.lt_exec("worksheet -s 1 0 2 0; worksheet -p 201 DROPLINE;")
        with origin_trace_step("native_structure_readback"):
            graphs = list(self.op.pages("g"))
            if len(graphs) != 1:
                raise RuntimeError("Origin DROPLINE must create exactly one graph")
            self.graph = graphs[0]
            self.graph.name = f"G{token}"
            self.graph.lname = f"X02 {template.stem} / {document.plot_id}"
            self._bind_native_objects()
            self._assert_native_structure(verify_transform=False)
        record_origin_trace(
            "native_drop_lines_confirmed",
            "completed",
            details={
                "layer_count": 1,
                "native_plot_ids": [201],
                "vertical_drop_lines": True,
                "worksheet_values": "raw",
            },
        )

    def open(self, path: Path) -> None:
        with origin_trace_step(
            "saved_project_reopen", details={"filename": path.name, "readonly": False}
        ):
            self.op.new(asksave=False)
            if not self.op.open(str(path), readonly=False, asksave=False):
                raise RuntimeError("Origin could not reopen the X02 project")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("X02 project must contain one graph and one workbook")
        self.graph, self.book = graphs[0], books[0]
        self.sheet = self.book[0]
        self._bind_native_objects()

    def reconcile(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> None:
        series = xy_series(document, data, profile_id="X02")
        state = self._state(document, actions)
        with origin_trace_step("agent_actions_apply", details={"action_count": len(actions)}):
            if state.title is not None:
                self._set_title(state.title)
            self._apply_axis("x", "xb", state.x_axis)
            self._apply_axis("y", "yl", state.y_axis)
            self._apply_series(state.series)
            if state.legend_visible is not None:
                self._set_legend(series.y_field_name, state.legend_visible)

    def save(self, output: Path) -> None:
        with origin_trace_step("opju_save", details={"filename": output.name}):
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                raise FileExistsError(
                    f"Origin refuses to overwrite existing X02 artifact: {output}"
                )
            self.op.save(str(output))
            if not output.is_file() or output.stat().st_size <= 0:
                raise RuntimeError("Origin did not save a non-empty X02 project")

    def verify(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> EngineReadback:
        series = xy_series(document, data, profile_id="X02")
        state = self._state(document, actions)
        with origin_trace_step("reopened_native_structure_verify"):
            native = self._assert_native_structure(verify_transform=True)
        record_origin_trace("reopened_drop_lines_confirmed", "completed", details=native)
        with origin_trace_step(
            "reopened_source_data_verify",
            details={"column_count": 2, "row_count": len(series.x_values)},
        ):
            self._assert_values(self.sheet.to_list(0), series.x_values, "X")
            self._assert_values(self.sheet.to_list(1), series.y_values, "Y")
        with origin_trace_step("reopened_agent_edits_verify"):
            self._assert_agent_edits(state, series)
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
                    semantic_id=f"series:{token}.primary",
                    backend="origin",
                    object_kind="drop_line_series",
                    native_ref=f"graph:{self.graph.name}.layer:1.plot:1",
                ),
                EngineObjectRef(
                    semantic_id=f"legend:{token}.main",
                    backend="origin",
                    object_kind="legend",
                    native_ref=f"graph:{self.graph.name}.layer:1.label:legend",
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(
                cast(
                    JsonValue,
                    {
                        "native_plot_id": 201,
                        "state": asdict(state),
                        "template": X02_ORIGIN_PROFILE.filename,
                    },
                )
            ),
        )

    def _bind_native_objects(self) -> None:
        layers = tuple(self.graph)
        if len(layers) != 1:
            raise RuntimeError("Origin DROPLINE must remain a single-layer graph")
        self.layer = layers[0]

    def _write(self, series: XYSeriesData) -> None:
        self.sheet.cols = 2
        self.sheet.from_list(0, list(series.x_values), lname=series.x_field_name, axis="X")
        self.sheet.from_list(1, list(series.y_values), lname=series.y_field_name, axis="Y")

    def _state(self, document: PlotDocument, actions: tuple[PlotEngineAction, ...]) -> _State:
        document.plot_id.removeprefix("plot:")
        state = _State()
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            raise ValueError(f"Origin X02 binder cannot apply {action.operation}")
        return state

    def _set_title(self, text: str) -> None:
        title = self.layer.label(_TITLE_NAME)
        if title is None and text:
            self.layer.activate()
            if not self.layer.obj.LT_execute(
                f"label -j 1 -n {_TITLE_NAME} PlotAgentTitlePlaceholder;"
            ):
                raise RuntimeError("Origin could not create the X02 title")
            title = self.layer.label(_TITLE_NAME)
            if title is None:
                raise RuntimeError("Origin did not expose the newly created X02 title")
        if title is not None:
            title.text = text
            title.set_int("attach", 1)
            title.set_float("x1", 0.5)
            title.set_float("y1", 0.012)
            title.set_int("fsize", 14)
            title.set_int("fstyle", 0)
            title.set_int("background", 0)
            title.set_int("show", int(bool(text)))

    def _apply_axis(self, axis_name: str, label_name: str, edits: _AxisEdits) -> None:
        if edits == _AxisEdits():
            return
        axis = self.layer.axis(axis_name)
        if edits.scale is not None:
            axis.scale = edits.scale
        if edits.minimum is not None and edits.maximum is not None:
            begin, end = edits.minimum, edits.maximum
            if edits.reverse:
                begin, end = end, begin
            axis.set_limits(begin, end)
        elif edits.reverse is not None:
            begin, end, step = (float(value) for value in axis.limits)
            if (begin > end) != edits.reverse:
                axis.set_limits(end, begin, abs(step))
        if edits.label is not None:
            label = self.layer.label(label_name) or self.layer.add_label(edits.label)
            if label is None:
                raise RuntimeError("Origin X02 template has no writable axis label")
            label.text = edits.label
            label.set_int("fstyle", 0)
            label.set_int("show", int(bool(edits.label)))

    def _plot_prefix(self) -> str:
        return (
            f"window -a {self.graph.name}; {self.graph.name}!page.active=1; "
            f"range __X02P=[{self.graph.name}]Layer1!1; "
        )

    def _apply_series(self, edits: _SeriesEdits) -> None:
        commands: list[str] = []
        if edits.color is not None:
            commands.extend(
                (
                    f'set __X02P -c color("{edits.color}")',
                    f'set __X02P -lvc color("{edits.color}")',
                )
            )
        if edits.line_width_pt is not None:
            # Origin 2024 SR1's native DROPLINE property accepts and returns
            # whole point values here.  The generic online LabTalk table says
            # 500 units per point, but a real save/reopen roundtrip on build
            # 10.1.0.178 proves that conversion produces grossly oversized
            # stems.  Keep the local, roundtripped contract explicit.
            commands.append(f"set __X02P -lvw {edits.line_width_pt}")
        if edits.line_style is not None:
            commands.append(f"set __X02P -lvs {_LINE_STYLE[edits.line_style]}")
        if edits.symbol is not None:
            commands.append(f"set __X02P -k {_SYMBOL[edits.symbol]}")
        if edits.symbol_size_pt is not None:
            commands.append(f"set __X02P -z {edits.symbol_size_pt}")
        if commands:
            self.op.lt_exec(self._plot_prefix() + "; ".join(commands) + ";")

    def _set_legend(self, label_text: str, visible: bool) -> None:
        legend = self.layer.label("legend")
        if legend is None and visible:
            self.layer.activate()
            if not self.layer.obj.LT_execute("legend"):
                raise RuntimeError("Origin could not create the X02 legend")
            legend = self.layer.label("legend")
        if legend is not None:
            legend.text = f"\\l(1, style:s) {_safe_legend_label(label_text)}"
            legend.set_int("link", 1)
            legend.set_int("show", int(visible))

    def _assert_native_structure(self, *, verify_transform: bool) -> dict[str, object]:
        command = (
            self._plot_prefix() + "layer -c; __X02COUNT=count; "
            "range -wx __X02X=1; range -wy __X02Y=1; "
            "get __X02P -pt __X02PT; get __X02P -lv __X02LV; "
            "string __X02XS$=%(__X02X); string __X02YS$=%(__X02Y);"
        )
        if verify_transform:
            command += " get __X02P -sy __X02SY; get __X02P -sys __X02SYS;"
        self.op.lt_exec(command)
        plot_id = float(self.op.lt_float("__X02PT"))
        vertical = float(self.op.lt_float("__X02LV"))
        plot_count = float(self.op.lt_float("__X02COUNT"))
        if (
            isnan(plot_id)
            or int(plot_id) != 201
            or not isclose(plot_count, 1.0)
            or not isclose(vertical, 1.0)
        ):
            raise RuntimeError(
                "Origin X02 native DROPLINE structure changed: "
                f"plots={plot_count}, pid={plot_id}, lv={vertical}"
            )
        x_range = str(self.op.get_lt_str("__X02XS"))
        y_range = str(self.op.get_lt_str("__X02YS"))
        source_prefix = f"[{self.book.name}]"
        if (
            not x_range.startswith(source_prefix)
            or '!A"' not in x_range
            or not y_range.startswith(source_prefix)
            or '!B"' not in y_range
        ):
            raise RuntimeError(
                "Origin X02 plot is not bound directly to source columns A/B: "
                f"x={x_range!r}, y={y_range!r}"
            )
        facts: dict[str, object] = {
            "native_plot_id": 201,
            "vertical_drop_lines": True,
            "x_range": x_range,
            "y_range": y_range,
        }
        if verify_transform:
            offset = float(self.op.lt_float("__X02SY"))
            multiplier = float(self.op.lt_float("__X02SYS"))
            if not isclose(offset, 0.0, abs_tol=1e-8) or not isclose(multiplier, 1.0, abs_tol=1e-8):
                raise RuntimeError(
                    f"Origin X02 plot transform changed: offset={offset}, scale={multiplier}"
                )
            facts.update(y_offset=offset, y_multiplier=multiplier)
        return facts

    def _assert_agent_edits(self, state: _State, series: XYSeriesData) -> None:
        title = self.layer.label(_TITLE_NAME)
        if state.title and (
            title is None
            or title.text != state.title
            or title.get_int("show") == 0
            or title.get_int("attach") != 1
            or title.get_int("fsize") != 14
            or title.get_int("fstyle") != 0
        ):
            raise RuntimeError("Origin X02 title changed after reopen")
        for axis_name, label_name, edits in (
            ("x", "xb", state.x_axis),
            ("y", "yl", state.y_axis),
        ):
            axis = self.layer.axis(axis_name)
            if edits.scale is not None and not axis_scale_matches(axis.scale, edits.scale):
                raise RuntimeError(f"Origin X02 {axis_name} scale changed after reopen")
            if edits.label is not None:
                label = self.layer.label(label_name)
                if label is None or label.text != edits.label or label.get_int("fstyle") != 0:
                    raise RuntimeError(f"Origin X02 {axis_name} label changed after reopen")
            if edits.minimum is not None and edits.maximum is not None:
                expected = (
                    (edits.maximum, edits.minimum)
                    if edits.reverse
                    else (edits.minimum, edits.maximum)
                )
                observed = tuple(float(value) for value in axis.limits[:2])
                if not all(
                    isclose(left, right, abs_tol=1e-8)
                    for left, right in zip(observed, expected, strict=True)
                ):
                    raise RuntimeError(f"Origin X02 {axis_name} bounds changed after reopen")
            elif edits.reverse is not None:
                begin, end = (float(value) for value in axis.limits[:2])
                if (begin > end) != edits.reverse:
                    raise RuntimeError(f"Origin X02 {axis_name} direction changed after reopen")
        series_edits = state.series
        if series_edits != _SeriesEdits():
            self.op.lt_exec(
                self._plot_prefix() + "get __X02P -c __X02C; get __X02P -lvc __X02LVC; "
                "get __X02P -lvw __X02LVW; get __X02P -lvs __X02LVS; "
                "get __X02P -k __X02K; get __X02P -z __X02Z;"
            )
            if series_edits.color is not None:
                expected_color = int(self.op.lt_float(f'color("{series_edits.color}")'))
                if any(
                    int(self.op.lt_float(name)) != expected_color for name in ("__X02C", "__X02LVC")
                ):
                    raise RuntimeError("Origin X02 symbol/drop-line color changed")
            if series_edits.line_width_pt is not None and not isclose(
                float(self.op.lt_float("__X02LVW")),
                series_edits.line_width_pt,
                abs_tol=1e-8,
            ):
                raise RuntimeError("Origin X02 drop-line width changed")
            if (
                series_edits.line_style is not None
                and int(self.op.lt_float("__X02LVS")) != _LINE_STYLE[series_edits.line_style]
            ):
                raise RuntimeError("Origin X02 drop-line style changed")
            if (
                series_edits.symbol is not None
                and int(self.op.lt_float("__X02K")) != _SYMBOL[series_edits.symbol]
            ):
                raise RuntimeError("Origin X02 symbol changed")
            if series_edits.symbol_size_pt is not None and not isclose(
                float(self.op.lt_float("__X02Z")),
                series_edits.symbol_size_pt,
                abs_tol=1e-8,
            ):
                raise RuntimeError("Origin X02 symbol size changed")
        if state.legend_visible is not None:
            legend = self.layer.label("legend")
            if legend is None or bool(legend.get_int("show")) != state.legend_visible:
                raise RuntimeError("Origin X02 legend visibility changed")
            if state.legend_visible and (
                str(legend.text).count(r"\l(") != 1
                or _safe_legend_label(series.y_field_name) not in str(legend.text)
            ):
                raise RuntimeError("Origin X02 legend content changed")

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[float, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin X02 {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            observed_number = float(cast(Any, observed))
            if (isnan(observed_number) and isnan(wanted)) or isclose(
                observed_number, wanted, abs_tol=1e-9
            ):
                continue
            else:
                raise RuntimeError(f"Origin X02 {role} values differ after reopen")


def execute_x02_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    structure_output = output.with_name(f"{output.stem}.official-structure.opju")
    project = X02OriginProject(op)
    project.create(install_dir, request.document, request.data)
    project.save(structure_output)

    editable = X02OriginProject(op)
    editable.open(structure_output)
    editable.reconcile(request.document, request.actions, request.data)
    editable.save(output)

    reopened = X02OriginProject(op)
    reopened.open(output)
    readback = reopened.verify(request.document, request.actions, request.data)
    structure_output.unlink(missing_ok=True)
    return readback
