"""K06 official ERRBAR template binder with symmetric X/Y error columns."""

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
from plotagent.engine.profile_data import k06_point_error
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K06_ORIGIN_PROFILE, resolve_official_template
from .readback import axis_scale_matches
from .trace import origin_trace_step, record_origin_trace

_SYMBOL_CODES = {
    "square": 1,
    "circle": 2,
    "triangle": 3,
    "triangle_up": 3,
    "diamond": 5,
}
_TITLE_NAME = "_ENGINE_TITLE"
_OFFICIAL_HELP = "https://docs.originlab.com/origin-help/xy-errbar-graph/"
_OFFICIAL_MENU = "Plot > Basic 2D: XY Error"
_OFFICIAL_MENU_ID = 33336
_OFFICIAL_COMMAND = "worksheet -s 1 0 4 0; worksheet -p 201 ERRBAR;"


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


class K06OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.plot: Any = None
        self.plots: list[Any] = []
        self.sheet: Any = None

    def create(
        self,
        install_dir: Path,
        document: PlotDocument,
        data: EngineDataView,
    ) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={
                "help_url": _OFFICIAL_HELP,
                "template_filename": K06_ORIGIN_PROFILE.filename,
                "template_sha256": K06_ORIGIN_PROFILE.sha256,
            },
        ):
            template = resolve_official_template(install_dir, K06_ORIGIN_PROFILE)
        k06_point_error(document, data)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the K06 data workbook")
        self.sheet = book[0]
        with origin_trace_step(
            "source_data_write",
            details={"designation": "XYEM", "order": ["x", "center", "y_error", "x_error"]},
        ):
            self._write_data(document, data)
        with origin_trace_step(
            "official_plot_command_execute",
            details={
                "labtalk": _OFFICIAL_COMMAND,
                "menu": _OFFICIAL_MENU,
                "menu_id": _OFFICIAL_MENU_ID,
                "native_plot_type": 201,
                "template_filename": template.name,
            },
        ):
            self.sheet.activate()
            if not self.op.lt_exec(_OFFICIAL_COMMAND):
                raise RuntimeError("Origin could not execute the official K06 XY Error menu")
        graphs = list(self.op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError("Origin XY Error menu must create exactly one graph")
        self.graph = graphs[0]
        self.graph.name = f"G{token}"
        self.graph.lname = f"K06 XY Error / {document.plot_id}"
        self.layer = self.graph[0]
        self.plots = list(self.layer.plot_list())
        if not self.plots:
            raise RuntimeError("Origin ERRBAR.otpu did not create a native XY error plot")
        self.plot = self.plots[0]
        with origin_trace_step(
            "template_residue_remove", details={"authoritative_workbook": book.name}
        ):
            for residue in tuple(self.op.pages("w")):
                if residue.name != book.name:
                    residue.destroy()
        self.layer.rescale()
        native = self._assert_native_structure()
        record_origin_trace("native_xy_error_confirmed", "completed", details=native)

    def open(self, project_path: Path) -> None:
        with origin_trace_step(
            "previous_project_reopen",
            details={"filename": project_path.name, "readonly": False},
        ):
            self.op.new(asksave=False)
            if not self.op.open(str(project_path), readonly=False, asksave=False):
                raise RuntimeError(f"Origin could not open the previous project: {project_path}")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("K06 Origin project must contain one graph and one workbook")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        plots = self.layer.plot_list()
        if not plots:
            raise RuntimeError("K06 Origin project must contain a native point plot")
        self.plots = list(plots)
        self.plot = self.plots[0]
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
            k06_point_error(document, data)
            self._write_data(document, data)
            self.layer.rescale()
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError("K06 title target does not belong to this plot")
            label = self.layer.label(_TITLE_NAME)
            if label is None:
                label = self.layer.add_label(action.text, 40, 2)
                if label is None:
                    raise RuntimeError("Origin could not create the K06 title")
                label.name = _TITLE_NAME
            label.text = action.text
            label.set_int("show", 1)
            return
        if isinstance(action, SetAxis):
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
            if axis_name is None:
                raise ValueError("K06 axis target does not belong to this plot")
            axis = self.layer.axis(axis_name)
            if action.scale is not None:
                if action.scale not in {"linear", "log10"}:
                    raise ValueError("Origin K06 axes support only linear or log10")
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
                    raise RuntimeError("Origin K06 template has no writable axis label")
                label.text = action.label
                label.set_int("show", 1)
            return
        if isinstance(action, SetSeriesStyle):
            if action.target != f"series:{token}.primary":
                raise ValueError("K06 series target does not belong to this plot")
            if action.color is not None:
                for plot in self.plots:
                    plot.color = action.color
            if action.line_width_pt is not None:
                for plot in self.plots:
                    plot.set_float("line.width", action.line_width_pt)
            if action.symbol is not None:
                try:
                    self.plot.symbol_kind = _SYMBOL_CODES[action.symbol]
                except KeyError as error:
                    raise ValueError(
                        f"Origin K06 does not support symbol {action.symbol}"
                    ) from error
            if action.symbol_size_pt is not None:
                self.plot.symbol_size = action.symbol_size_pt
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError("K06 legend target does not belong to this plot")
            legend = self.layer.label("legend")
            if action.visible and legend is None:
                self.layer.activate()
                if not self.layer.obj.LT_execute("legend"):
                    raise RuntimeError("Origin could not create a linked K06 legend")
                legend = self.layer.label("legend")
            if legend is not None and action.visible is not None:
                center_name = self._bound_columns(document, data)[1].field.name
                legend.text = f"\\l(1) {_safe_legend_label(center_name)}"
                legend.set_int("link", 1)
                legend.set_int("show", int(action.visible))
            return
        raise ValueError(f"Origin K06 binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        with origin_trace_step("opju_save", details={"filename": output_path.name}):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self.op.save(str(output_path))
            if not output_path.is_file() or output_path.stat().st_size <= 0:
                raise RuntimeError("Origin did not save a non-empty K06 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        native = self._assert_native_structure()
        record_origin_trace("reopened_xy_error_confirmed", "completed", details=native)
        columns = self._bound_columns(document, data)
        for index, (role, column) in enumerate(
            zip(("x", "center", "y_error", "x_error"), columns, strict=True)
        ):
            self._assert_values(self.sheet.to_list(index), column.values, role)
        token = document.plot_id.removeprefix("plot:")
        style_snapshot: dict[str, object] = {"native_structure": native}
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if title is None or title.text != action.text or not title.get_int("show"):
                    raise RuntimeError("Origin K06 title did not survive readback")
                style_snapshot["title"] = title.text
            elif isinstance(action, SetAxis):
                axis_name = "x" if action.target == f"axis:{token}.x" else "y"
                axis = self.layer.axis(axis_name)
                if action.scale is not None and not axis_scale_matches(axis.scale, action.scale):
                    raise RuntimeError("Origin K06 axis scale did not survive readback")
                if action.label is not None:
                    label = self.layer.label("xb" if axis_name == "x" else "yl")
                    if label is None or label.text != action.label:
                        raise RuntimeError("Origin K06 axis label did not survive readback")
                style_snapshot[f"axis_{axis_name}"] = {
                    "scale": axis.scale,
                    "limits": tuple(float(value) for value in axis.limits),
                }
            elif isinstance(action, SetSeriesStyle):
                if action.color is not None and any(
                    tuple(plot.color) != _hex_rgb(action.color) for plot in self.plots
                ):
                    raise RuntimeError("Origin K06 color did not survive readback")
                if action.line_width_pt is not None and any(
                    abs(plot.get_float("line.width") - action.line_width_pt) > 0.01
                    for plot in self.plots
                ):
                    raise RuntimeError("Origin K06 error width did not survive readback")
                if action.symbol_size_pt is not None and (
                    abs(float(self.plot.symbol_size) - action.symbol_size_pt) > 0.01
                ):
                    raise RuntimeError("Origin K06 symbol size did not survive readback")
                style_snapshot["series"] = {
                    "color": tuple(self.plot.color),
                    "line_width": self.plot.get_float("line.width"),
                    "native_member_count": len(self.plots),
                }
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layer.label("legend")
                if legend is None or bool(legend.get_int("show")) != action.visible:
                    raise RuntimeError("Origin K06 legend visibility did not survive readback")
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
                object_kind="point_error_series",
                native_ref=f"graph:{self.graph.name}.layer:1.plots:1-{len(self.plots)}",
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
        x, center, y_error, x_error = self._bound_columns(document, data)
        for index, (column, designation) in enumerate(
            zip((x, center, y_error, x_error), ("X", "Y", "E", "M"), strict=True)
        ):
            self.sheet.from_list(
                index,
                list(column.values),
                lname=column.field.name,
                units=column.field.unit_label or "",
                axis=designation,
            )

    @staticmethod
    def _bound_columns(
        document: PlotDocument,
        data: EngineDataView,
    ) -> tuple[EngineColumn, EngineColumn, EngineColumn, EngineColumn]:
        bindings = {binding.role: binding.field_id for binding in document.bindings}
        columns = {column.field.field_id: column for column in data.columns}
        return (
            columns[bindings["x"]],
            columns[bindings["center"]],
            columns[bindings["y_error"]],
            columns[bindings["x_error"]],
        )

    def _assert_native_structure(self) -> dict[str, object]:
        self.graph.activate()
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe K06 graph name for native readback: {graph_name!r}")
        command = (
            "page.active=1; layer -c; __K06COUNT=count; "
            f"range __K06P=[{graph_name}]1!1; "
            "range -wx __K06X=__K06P; range -wy __K06Y=__K06P; "
            "get __K06P -pt __K06PID; "
            "string __K06XS$=%(__K06X); string __K06YS$=%(__K06Y);"
        )
        if not self.op.lt_exec(command):
            raise RuntimeError("Origin could not read the native K06 XY Error structure")
        plot_count = int(self.op.lt_float("__K06COUNT"))
        plot_id = int(self.op.lt_float("__K06PID"))
        designations = tuple(int(self.sheet.get_int(f"col{index}.type")) for index in range(1, 5))
        x_range = str(self.op.get_lt_str("__K06XS"))
        y_range = str(self.op.get_lt_str("__K06YS"))
        if plot_count < 1 or plot_id != 201:
            raise RuntimeError("Origin K06 must retain a native PID 201 point/error plot")
        if designations != (4, 1, 3, 7):
            raise RuntimeError("Origin K06 worksheet must retain X/Y/YErr/XErr designations")
        if not x_range.split('"', 1)[0].endswith("!A") or not y_range.split('"', 1)[0].endswith(
            "!B"
        ):
            raise RuntimeError("Origin K06 XY Error lost its center-point source binding")
        return {
            "designation_codes": list(designations),
            "help_url": _OFFICIAL_HELP,
            "native_plot_count": plot_count,
            "native_plot_type": plot_id,
            "official_menu": _OFFICIAL_MENU,
            "official_menu_id": _OFFICIAL_MENU_ID,
            "official_template": K06_ORIGIN_PROFILE.filename,
            "x_range": x_range,
            "y_range": y_range,
        }

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[object, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin K06 {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if observed is None and wanted is None:
                continue
            if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
                if abs(float(cast(Any, observed)) - float(wanted)) <= 1e-12:
                    continue
            elif observed == wanted:
                continue
            raise RuntimeError(f"Origin K06 {role} values differ after reopen")


def execute_k06_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = K06OriginProject(op)
    if request.previous_opju is None:
        project.create(install_dir, request.document, request.data)
        pending = request.actions
    else:
        project.open(Path(request.previous_opju))
        pending = request.actions[-1:]
    with origin_trace_step("agent_actions_apply", details={"action_count": len(pending)}):
        for action in pending:
            details = cast(dict[str, object], action.model_dump(exclude_none=True))
            with origin_trace_step("agent_action_apply", details=details):
                project.apply(request.document, action, request.data)
    project.save(output)

    with origin_trace_step(
        "saved_project_reopen", details={"filename": output.name, "readonly": True}
    ):
        op.new(asksave=False)
        if not op.open(str(output), readonly=True, asksave=False):
            raise RuntimeError("fresh Origin session could not reopen the staged K06 project")
    reopened = K06OriginProject(op)
    graphs = list(op.pages("g"))
    books = list(op.pages("w"))
    if len(graphs) != 1 or len(books) != 1:
        raise RuntimeError("fresh K06 project has unexpected graph or workbook count")
    reopened.graph = graphs[0]
    reopened.layer = reopened.graph[0]
    plots = reopened.layer.plot_list()
    if not plots:
        raise RuntimeError("fresh K06 project has no native plot")
    reopened.plots = list(plots)
    reopened.plot = reopened.plots[0]
    reopened.sheet = books[0][0]
    with origin_trace_step("reopened_native_structure_verify"):
        return reopened.verify(request.document, request.actions, request.data)
