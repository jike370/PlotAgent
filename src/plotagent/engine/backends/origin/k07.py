"""K07 official ERRORBAND template binder."""

from __future__ import annotations

from math import isnan
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
from plotagent.engine.profile_data import k07_error_band
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K07_ORIGIN_PROFILE, resolve_official_template
from .readback import axis_scale_matches
from .trace import origin_trace_step, record_origin_trace

_LINE_STYLE_CODES = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3, "none": 10}
_TITLE_NAME = "_ENGINE_TITLE"
_OFFICIAL_HELP = "https://docs.originlab.com/origin-help/error-band-graph/"
_OFFICIAL_MENU = "Plot > Basic 2D: Error Band"
_OFFICIAL_MENU_ID = 2097172
_OFFICIAL_COMMAND = "worksheet -s 1 0 4 0; run.section(plot,ScatterErrorBand);"


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


class K07OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.plots: list[Any] = []
        self.sheet: Any = None

    @property
    def center_plot(self) -> Any:
        return self.plots[0]

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
                "template_filename": K07_ORIGIN_PROFILE.filename,
                "template_sha256": K07_ORIGIN_PROFILE.sha256,
            },
        ):
            template = resolve_official_template(install_dir, K07_ORIGIN_PROFILE)
        k07_error_band(document, data)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the K07 data workbook")
        self.sheet = book[0]
        with origin_trace_step(
            "source_data_write",
            details={
                "designation": "XYEE",
                "error_values": ["center-lower", "upper-center"],
            },
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
                raise RuntimeError("Origin could not execute the official K07 Error Band menu")
        graphs = list(self.op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError("Origin Error Band menu must create exactly one graph")
        self.graph = graphs[0]
        self.graph.name = f"G{token}"
        self.graph.lname = f"K07 Error Band / {document.plot_id}"
        self.layer = self.graph[0]
        self.plots = list(self.layer.plot_list())
        if len(self.plots) != 3:
            raise RuntimeError("Origin ERRORBAND.otp must create center/minus/plus native plots")
        with origin_trace_step(
            "native_asymmetric_direction_assign",
            details={
                "minus": "center-lower",
                "plus": "upper-center",
                "source": "official LabTalk set -om/-op",
            },
        ):
            self._set_error_directions()
        with origin_trace_step(
            "native_error_band_fill_enable",
            details={
                "connect_line_mode": 1,
                "connect_line_fill_area": 1,
                "source": "official Error Bar theme",
            },
        ):
            self._enable_error_band_fill()
        with origin_trace_step(
            "template_residue_remove", details={"authoritative_workbook": book.name}
        ):
            for residue in tuple(self.op.pages("w")):
                if residue.name != book.name:
                    residue.destroy()
        self.layer.rescale()
        native = self._assert_native_structure()
        record_origin_trace("native_error_band_confirmed", "completed", details=native)

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
            raise RuntimeError("K07 Origin project must contain one graph and one workbook")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        self.plots = list(self.layer.plot_list())
        if len(self.plots) != 3:
            raise RuntimeError("K07 Origin project must contain center/lower/upper native plots")
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
            k07_error_band(document, data)
            self._write_data(document, data)
            self.layer.rescale()
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError("K07 title target does not belong to this plot")
            label = self.layer.label(_TITLE_NAME)
            if label is None:
                label = self.layer.add_label(action.text, 40, 2)
                if label is None:
                    raise RuntimeError("Origin could not create the K07 title")
                label.name = _TITLE_NAME
            label.text = action.text
            label.set_int("show", 1)
            return
        if isinstance(action, SetAxis):
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
            if axis_name is None:
                raise ValueError("K07 axis target does not belong to this plot")
            axis = self.layer.axis(axis_name)
            if action.scale is not None:
                if action.scale not in {"linear", "log10"}:
                    raise ValueError("Origin K07 axes support only linear or log10")
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
                    raise RuntimeError("Origin K07 template has no writable axis label")
                label.text = action.label
                label.set_int("show", 1)
            return
        if isinstance(action, SetSeriesStyle):
            if action.target != f"series:{token}.primary":
                raise ValueError("K07 series target does not belong to this plot")
            if action.color is not None:
                for plot in self.plots:
                    plot.color = action.color
            if action.line_width_pt is not None:
                self.center_plot.set_float("line.width", action.line_width_pt)
            if action.line_style is not None:
                self.center_plot.set_int("line.style", _LINE_STYLE_CODES[action.line_style])
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError("K07 legend target does not belong to this plot")
            legend = self.layer.label("legend")
            if action.visible and legend is None:
                self.layer.activate()
                if not self.layer.obj.LT_execute("legend"):
                    raise RuntimeError("Origin could not create a linked K07 legend")
                legend = self.layer.label("legend")
            if legend is not None and action.visible is not None:
                center_name = self._bound_columns(document, data)[1].field.name
                # Only the center curve owns the public logical series.  Lower
                # and upper native boundaries never become legend entries.
                legend.text = f"\\l(1) {_safe_legend_label(center_name)}"
                legend.set_int("link", 1)
                legend.set_int("show", int(action.visible))
            return
        raise ValueError(f"Origin K07 binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        with origin_trace_step("opju_save", details={"filename": output_path.name}):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self.op.save(str(output_path))
            if not output_path.is_file() or output_path.stat().st_size <= 0:
                raise RuntimeError("Origin did not save a non-empty K07 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        native = self._assert_native_structure()
        record_origin_trace("reopened_error_band_confirmed", "completed", details=native)
        band = k07_error_band(document, data)
        expected_columns = (
            band.x_values,
            band.center_values,
            tuple(
                center - lower
                for center, lower in zip(band.center_values, band.lower_values, strict=True)
            ),
            tuple(
                upper - center
                for center, upper in zip(band.center_values, band.upper_values, strict=True)
            ),
        )
        for index, (role, values) in enumerate(
            zip(("x", "center", "minus_error", "plus_error"), expected_columns, strict=True)
        ):
            self._assert_values(self.sheet.to_list(index), values, role)
        token = document.plot_id.removeprefix("plot:")
        style_snapshot: dict[str, object] = {"native_structure": native}
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if title is None or title.text != action.text or not title.get_int("show"):
                    raise RuntimeError("Origin K07 title did not survive readback")
                style_snapshot["title"] = title.text
            elif isinstance(action, SetAxis):
                axis_name = "x" if action.target == f"axis:{token}.x" else "y"
                axis = self.layer.axis(axis_name)
                if action.scale is not None and not axis_scale_matches(axis.scale, action.scale):
                    raise RuntimeError("Origin K07 axis scale did not survive readback")
                if action.label is not None:
                    label = self.layer.label("xb" if axis_name == "x" else "yl")
                    if label is None or label.text != action.label:
                        raise RuntimeError("Origin K07 axis label did not survive readback")
                style_snapshot[f"axis_{axis_name}"] = {
                    "scale": axis.scale,
                    "limits": tuple(float(value) for value in axis.limits),
                }
            elif isinstance(action, SetSeriesStyle):
                if action.color is not None and any(
                    tuple(plot.color) != _hex_rgb(action.color) for plot in self.plots
                ):
                    raise RuntimeError("Origin K07 band color did not survive readback")
                if (
                    action.line_width_pt is not None
                    and abs(self.center_plot.get_float("line.width") - action.line_width_pt) > 0.01
                ):
                    raise RuntimeError("Origin K07 line width did not survive readback")
                style_snapshot["series"] = {
                    "color": tuple(self.center_plot.color),
                    "line_width": self.center_plot.get_float("line.width"),
                }
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layer.label("legend")
                if legend is None or bool(legend.get_int("show")) != action.visible:
                    raise RuntimeError("Origin K07 legend visibility did not survive readback")
                if legend.text.count("\\l(") != 1:
                    raise RuntimeError("Origin K07 legend exposed native band boundaries")
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
                object_kind="error_band_series",
                native_ref=f"graph:{self.graph.name}.layer:1.plots:1-3",
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
        band = k07_error_band(document, data)
        x, center, lower, upper = self._bound_columns(document, data)
        minus_error = tuple(
            middle - low for middle, low in zip(band.center_values, band.lower_values, strict=True)
        )
        plus_error = tuple(
            high - middle
            for middle, high in zip(band.center_values, band.upper_values, strict=True)
        )
        values = (band.x_values, band.center_values, minus_error, plus_error)
        names = (
            x.field.name,
            center.field.name,
            f"{lower.field.name} (center-lower)",
            f"{upper.field.name} (upper-center)",
        )
        units = (
            x.field.unit_label or "",
            center.field.unit_label or "",
            lower.field.unit_label or center.field.unit_label or "",
            upper.field.unit_label or center.field.unit_label or "",
        )
        for index, (column_values, name, unit, designation) in enumerate(
            zip(values, names, units, ("X", "Y", "E", "E"), strict=True)
        ):
            self.sheet.from_list(
                index,
                list(column_values),
                lname=name,
                units=unit,
                axis=designation,
            )

    def _set_error_directions(self) -> None:
        source = self.sheet.lt_range(False)
        command = (
            f"range __K07CENTER={source}!B; "
            f"range __K07MINUS={source}!C; "
            f"range __K07PLUS={source}!D; "
            "set __K07MINUS -om __K07CENTER; "
            "set __K07PLUS -op __K07CENTER;"
        )
        if not self.op.lt_exec(command):
            raise RuntimeError("Origin could not assign native K07 minus/plus error directions")

    @staticmethod
    def _theme_child(node: Any, name: str) -> Any | None:
        if node is None:
            return None
        return next((item for item in node.Children if str(item.Name) == name), None)

    def _enable_error_band_fill(self) -> None:
        if len(self.plots) != 3:
            raise RuntimeError("Origin K07 requires center/minus/plus before enabling the band")
        for plot in self.plots[1:]:
            theme = plot.obj.GetTheme()
            error = self._theme_child(theme, "ErrorBar2D")
            connect = self._theme_child(error, "ConnectLineMode")
            fill = self._theme_child(error, "ConnectLineFillArea")
            if connect is None or fill is None:
                raise RuntimeError("Origin K07 ErrorBar2D theme lacks the official band fields")
            connect.SetIntValue(1)
            fill.SetIntValue(1)
            plot.obj.PutTheme(theme)

    def _native_error_band_state(self) -> list[dict[str, int]]:
        states: list[dict[str, int]] = []
        for plot in self.plots[1:]:
            theme = plot.obj.GetTheme()
            error = self._theme_child(theme, "ErrorBar2D")
            values: dict[str, int] = {}
            for name in (
                "DirectionX",
                "DirectionPlus",
                "DirectionMinus",
                "ConnectLineMode",
                "ConnectLineFillArea",
            ):
                child = self._theme_child(error, name)
                if child is None:
                    raise RuntimeError(f"Origin K07 ErrorBar2D theme lacks {name}")
                values[name] = int(child.GetValue())
            states.append(values)
        expected_directions = {(0, 0, 1), (0, 1, 0)}
        observed_directions = {
            (item["DirectionX"], item["DirectionPlus"], item["DirectionMinus"])
            for item in states
        }
        if observed_directions != expected_directions:
            raise RuntimeError("Origin K07 lost the native minus/plus error directions")
        if any(
            item["ConnectLineMode"] != 1 or item["ConnectLineFillArea"] != 1
            for item in states
        ):
            raise RuntimeError("Origin K07 lost the official connected filled error band")
        return states

    def _assert_native_structure(self) -> dict[str, object]:
        self.graph.activate()
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe K07 graph name for native readback: {graph_name!r}")
        command = (
            "page.active=1; layer -c; __K07COUNT=count; "
            f"range __K07P=[{graph_name}]1!1; "
            "range -wx __K07X=__K07P; range -wy __K07Y=__K07P; "
            "get __K07P -pt __K07PID; "
            "string __K07XS$=%(__K07X); string __K07YS$=%(__K07Y);"
        )
        if not self.op.lt_exec(command):
            raise RuntimeError("Origin could not read the native K07 Error Band structure")
        plot_count = int(self.op.lt_float("__K07COUNT"))
        plot_id = int(self.op.lt_float("__K07PID"))
        designations = tuple(int(self.sheet.get_int(f"col{index}.type")) for index in range(1, 5))
        x_range = str(self.op.get_lt_str("__K07XS"))
        y_range = str(self.op.get_lt_str("__K07YS"))
        if plot_count != 3 or plot_id != 201:
            raise RuntimeError("Origin K07 must retain center/minus/plus with PID 201 center")
        if designations != (4, 1, 3, 3):
            raise RuntimeError("Origin K07 worksheet must retain X/Y/YErr/YErr designations")
        if not x_range.split('"', 1)[0].endswith("!A") or not y_range.split('"', 1)[0].endswith(
            "!B"
        ):
            raise RuntimeError("Origin K07 Error Band lost its center-curve source binding")
        error_band_state = self._native_error_band_state()
        return {
            "designation_codes": list(designations),
            "error_direction_command": "set minus -om center; set plus -op center",
            "error_band_state": error_band_state,
            "help_url": _OFFICIAL_HELP,
            "native_plot_count": plot_count,
            "native_plot_type": plot_id,
            "official_menu": _OFFICIAL_MENU,
            "official_menu_id": _OFFICIAL_MENU_ID,
            "official_template": K07_ORIGIN_PROFILE.filename,
            "x_range": x_range,
            "y_range": y_range,
        }

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
            columns[bindings["lower"]],
            columns[bindings["upper"]],
        )

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[object, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin K07 {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if observed is None and wanted is None:
                continue
            if isinstance(wanted, float) and isnan(wanted) and observed is None:
                continue
            if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
                if abs(float(cast(Any, observed)) - float(wanted)) <= 1e-12:
                    continue
            elif observed == wanted:
                continue
            raise RuntimeError(f"Origin K07 {role} values differ after reopen")


def execute_k07_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = K07OriginProject(op)
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
            raise RuntimeError("fresh Origin session could not reopen the staged K07 project")
    reopened = K07OriginProject(op)
    graphs = list(op.pages("g"))
    books = list(op.pages("w"))
    if len(graphs) != 1 or len(books) != 1:
        raise RuntimeError("fresh K07 project has unexpected graph or workbook count")
    reopened.graph = graphs[0]
    reopened.layer = reopened.graph[0]
    reopened.plots = list(reopened.layer.plot_list())
    if len(reopened.plots) != 3:
        raise RuntimeError("fresh K07 project has an unexpected native plot count")
    reopened.sheet = books[0][0]
    with origin_trace_step("reopened_native_structure_verify"):
        return reopened.verify(request.document, request.actions, request.data)
