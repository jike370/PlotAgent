"""K01 official LINE template binder with incremental native edits."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineColumn,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K01_ORIGIN_PROFILE, resolve_official_template
from .readback import axis_scale_matches
from .trace import origin_trace_step, record_origin_trace

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


class K01OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.plot: Any = None
        self.sheet: Any = None

    def create(
        self,
        install_dir: Path,
        document: PlotDocument,
        data: EngineDataView,
    ) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={"template_filename": K01_ORIGIN_PROFILE.filename},
        ):
            template = resolve_official_template(install_dir, K01_ORIGIN_PROFILE)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the K01 data workbook")
        self.sheet = book[0]
        with origin_trace_step("source_data_write", details={"designation": "XY"}):
            self._write_data(document, data)
        command = "worksheet -s 1 0 2 0; worksheet -p 200 Line;"
        with origin_trace_step(
            "official_plot_command_execute",
            details={
                "labtalk": command,
                "native_plot_type": 200,
                "template_filename": template.name,
            },
        ):
            self.sheet.activate()
            if not self.op.lt_exec(command):
                raise RuntimeError("Origin could not execute the official K01 Line menu")
        graphs = list(self.op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError("Origin Line menu must create exactly one graph")
        self.graph = graphs[0]
        self.graph.name = f"G{token}"
        self.graph.lname = f"K01 Line / {document.plot_id}"
        self.layer = self.graph[0]
        plots = list(self.layer.plot_list())
        if len(plots) != 1:
            raise RuntimeError("Origin Line menu must create one native line")
        self.plot = plots[0]
        with origin_trace_step("template_residue_remove"):
            for residue in tuple(self.op.pages("w")):
                if residue.name != book.name:
                    residue.destroy()
        self.layer.rescale()
        native = self._assert_native_structure()
        record_origin_trace("native_line_confirmed", "completed", details=native)

    def open(self, project_path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=False, asksave=False):
            raise RuntimeError(f"Origin could not open the previous project: {project_path}")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("K01 Origin project must contain one graph and one workbook")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        plots = self.layer.plot_list()
        if len(plots) != 1:
            raise RuntimeError("K01 Origin project must contain one native data plot")
        self.plot = plots[0]
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
            self.layer.rescale()
            return
        if isinstance(action, SetTitle):
            label = self.layer.label(_TITLE_NAME)
            if label is None:
                label = self.layer.add_label(action.text, 40, 2)
                if label is None:
                    raise RuntimeError("Origin could not create the K01 title")
                label.name = _TITLE_NAME
            label.text = action.text
            label.set_int("show", 1)
            return
        if isinstance(action, SetAxis):
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
            if axis_name is None:
                raise ValueError("K01 axis target does not belong to this plot")
            axis = self.layer.axis(axis_name)
            if action.scale is not None:
                if action.scale not in {"linear", "log10"}:
                    raise ValueError(f"Origin K01 does not support {action.scale}")
                axis.scale = action.scale
            if action.minimum is not None and action.maximum is not None:
                begin, end = action.minimum, action.maximum
                if action.reverse:
                    begin, end = end, begin
                axis.set_limits(begin, end)
            elif action.reverse is not None:
                begin, end, step = (float(value) for value in axis.limits)
                should_reverse = begin < end if action.reverse else begin > end
                if should_reverse:
                    axis.set_limits(end, begin, abs(step))
            if action.label is not None:
                label = self.layer.label("xb" if axis_name == "x" else "yl")
                if label is None:
                    label = self.layer.add_label(action.label)
                if label is None:
                    raise RuntimeError("Origin K01 template has no writable axis label")
                label.text = action.label
                label.set_int("show", 1)
            return
        if isinstance(action, SetSeriesStyle):
            if action.target != f"series:{token}.primary":
                raise ValueError("K01 series target does not belong to this plot")
            if action.color is not None:
                self.plot.color = action.color
            if action.line_width_pt is not None:
                self.plot.set_float("line.width", action.line_width_pt)
            if action.line_style is not None:
                if action.line_style == "none":
                    raise ValueError("K01 cannot hide its only line")
                self.plot.set_int("line.style", _LINE_STYLE[action.line_style])
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError("K01 legend target does not belong to this plot")
            legend = self.layer.label("legend")
            if action.visible and legend is None:
                self.layer.activate()
                if not self.layer.obj.LT_execute("legend"):
                    raise RuntimeError("Origin could not create a linked K01 legend")
                legend = self.layer.label("legend")
            if legend is not None and action.visible is not None:
                y_name = self._bound_columns(document, data)[1].field.name
                legend.text = f"\\l(1, style:l) {_safe_legend_label(y_name)}"
                legend.set_int("link", 1)
                legend.set_int("show", int(action.visible))
            return
        raise ValueError(f"Origin K01 binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output_path))
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError("Origin did not save a non-empty K01 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        native = self._assert_native_structure()
        record_origin_trace("reopened_line_confirmed", "completed", details=native)
        x_column, y_column = self._bound_columns(document, data)
        self._assert_values(self.sheet.to_list(0), x_column.values, "x")
        self._assert_values(self.sheet.to_list(1), y_column.values, "y")
        token = document.plot_id.removeprefix("plot:")
        style_snapshot: dict[str, object] = {"native_structure": native}
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if title is None or title.text != action.text or not title.get_int("show"):
                    raise RuntimeError("Origin K01 title did not survive readback")
                style_snapshot["title"] = title.text
            elif isinstance(action, SetAxis):
                axis_name = "x" if action.target == f"axis:{token}.x" else "y"
                axis = self.layer.axis(axis_name)
                if action.scale is not None and not axis_scale_matches(axis.scale, action.scale):
                    raise RuntimeError("Origin K01 axis scale did not survive readback")
                if action.label is not None:
                    label = self.layer.label("xb" if axis_name == "x" else "yl")
                    if label is None or label.text != action.label:
                        raise RuntimeError("Origin K01 axis label did not survive readback")
                if action.minimum is not None and action.maximum is not None:
                    actual_begin, actual_end, _step = (float(value) for value in axis.limits)
                    expected = (
                        (action.maximum, action.minimum)
                        if action.reverse
                        else (action.minimum, action.maximum)
                    )
                    if any(
                        abs(actual - wanted) > 1e-9
                        for actual, wanted in zip(
                            (actual_begin, actual_end),
                            expected,
                            strict=True,
                        )
                    ):
                        raise RuntimeError("Origin K01 axis bounds did not survive readback")
                style_snapshot[f"axis_{axis_name}"] = {
                    "scale": axis.scale,
                    "limits": tuple(float(value) for value in axis.limits),
                }
            elif isinstance(action, SetSeriesStyle):
                if action.color is not None and tuple(self.plot.color) != _hex_rgb(action.color):
                    raise RuntimeError("Origin K01 line color did not survive readback")
                if (
                    action.line_width_pt is not None
                    and abs(self.plot.get_float("line.width") - action.line_width_pt) > 0.01
                ):
                    raise RuntimeError("Origin K01 line width did not survive readback")
                if (
                    action.line_style is not None
                    and self.plot.get_int("line.style") != _LINE_STYLE[action.line_style]
                ):
                    raise RuntimeError("Origin K01 line style did not survive readback")
                style_snapshot["series"] = {
                    "color": tuple(self.plot.color),
                    "line_width": self.plot.get_float("line.width"),
                    "line_style": self.plot.get_int("line.style"),
                }
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layer.label("legend")
                if legend is None or bool(legend.get_int("show")) != action.visible:
                    raise RuntimeError("Origin K01 legend visibility did not survive readback")
                style_snapshot["legend"] = {"visible": action.visible, "text": legend.text}
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
            EngineObjectRef(
                semantic_id=f"series:{token}.primary",
                backend="origin",
                object_kind="line",
                native_ref=f"graph:{self.graph.name}.layer:1.plot:1",
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
            style_hash=canonical_hash(cast(JsonValue, style_snapshot)),
        )

    def _write_data(self, document: PlotDocument, data: EngineDataView) -> None:
        x_column, y_column = self._bound_columns(document, data)
        self.sheet.from_list(
            0,
            list(x_column.values),
            lname=x_column.field.name,
            units=x_column.field.unit_label or "",
            axis="X",
        )
        self.sheet.from_list(
            1,
            list(y_column.values),
            lname=y_column.field.name,
            units=y_column.field.unit_label or "",
            axis="Y",
        )

    def _assert_native_structure(self) -> dict[str, object]:
        self.graph.activate()
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe K01 graph name for native readback: {graph_name!r}")
        command = (
            "page.active=1; layer -c; __K01COUNT=count; "
            f"range __K01P=[{graph_name}]1!1; "
            "range -wx __K01X=__K01P; range -wy __K01Y=__K01P; "
            "get __K01P -pt __K01PID; "
            "string __K01XS$=%(__K01X); string __K01YS$=%(__K01Y);"
        )
        if not self.op.lt_exec(command):
            raise RuntimeError("Origin could not read the native K01 Line structure")
        plot_count = int(self.op.lt_float("__K01COUNT"))
        plot_id = int(self.op.lt_float("__K01PID"))
        designations = tuple(int(self.sheet.get_int(f"col{index}.type")) for index in (1, 2))
        x_range = str(self.op.get_lt_str("__K01XS"))
        y_range = str(self.op.get_lt_str("__K01YS"))
        if plot_count != 1 or plot_id != 200:
            raise RuntimeError("Origin K01 must retain one native PID 200 Line plot")
        if designations != (4, 1):
            raise RuntimeError("Origin K01 worksheet must retain X/Y designations")
        if not x_range.split('"', 1)[0].endswith("!A") or not y_range.split('"', 1)[0].endswith(
            "!B"
        ):
            raise RuntimeError("Origin K01 Line lost its source-column binding")
        return {
            "official_template": K01_ORIGIN_PROFILE.filename,
            "official_menu": "Plot > Basic 2D: Line",
            "native_plot_type": plot_id,
            "plot_count": plot_count,
            "designation_codes": list(designations),
            "x_range": x_range,
            "y_range": y_range,
        }

    @staticmethod
    def _bound_columns(
        document: PlotDocument,
        data: EngineDataView,
    ) -> tuple[EngineColumn, EngineColumn]:
        bindings = {binding.role: binding.field_id for binding in document.bindings}
        columns = {column.field.field_id: column for column in data.columns}
        return columns[bindings["x"]], columns[bindings["y"]]

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[object, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin K01 {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if observed is None and wanted is None:
                continue
            if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
                if abs(float(cast(Any, observed)) - float(wanted)) <= 1e-12:
                    continue
            elif observed == wanted:
                continue
            raise RuntimeError(f"Origin K01 {role} values differ after reopen")


def execute_k01_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = K01OriginProject(op)
    project.create(install_dir, request.document, request.data)
    with origin_trace_step(
        "agent_actions_apply", details={"action_count": len(request.actions)}
    ):
        for action in request.actions:
            project.apply(request.document, action, request.data)
    project.save(output)

    op.new(asksave=False)
    if not op.open(str(output), readonly=True, asksave=False):
        raise RuntimeError("fresh Origin session could not reopen the staged K01 project")
    reopened = K01OriginProject(op)
    graphs = list(op.pages("g"))
    books = list(op.pages("w"))
    if len(graphs) != 1 or len(books) != 1:
        raise RuntimeError("fresh K01 project has unexpected graph or workbook count")
    reopened.graph = graphs[0]
    reopened.layer = reopened.graph[0]
    reopened.plot = reopened.layer.plot_list()[0]
    reopened.sheet = books[0][0]
    with origin_trace_step("reopened_native_structure_verify"):
        return reopened.verify(request.document, request.actions, request.data)
