"""K19 official LINE template binder with native Origin Date/Time X data."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

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
from plotagent.engine.profile_data import TimeSeriesData, k19_time_series
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K19_ORIGIN_PROFILE, resolve_official_template
from .readback import datetime_values_match
from .trace import origin_trace_step, record_origin_trace

_TITLE_NAME = "_ENGINE_TITLE"
_LINE_STYLE_CODES = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3, "none": 10}
_DEFAULT_DATE_TIME_FORMAT = 1


class K19OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.plots: list[Any] = []
        self.book: Any = None
        self.sheet: Any = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={"template_filename": K19_ORIGIN_PROFILE.filename},
        ):
            template = resolve_official_template(install_dir, K19_ORIGIN_PROFILE)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the K19 workbook")
        self.book = book
        self.sheet = book[0]
        series = k19_time_series(document, data)
        with origin_trace_step(
            "source_data_write",
            details={
                "column_count": len(series.series) + 1,
                "row_count": len(series.time_values),
                "time_field": series.time_field_name,
                "series_fields": [item.value_field_name for item in series.series],
            },
        ):
            self._write_data(document, data)
        self.sheet.activate()
        command = (
            f"worksheet -s 1 0 {len(series.series) + 1} 0; "
            "worksheet -p 200 Line;"
        )
        with origin_trace_step(
            "official_plot_command_execute",
            details={
                "labtalk": command,
                "native_plot_type": 200,
                "template_filename": template.name,
            },
        ):
            if not self.op.lt_exec(command):
                raise RuntimeError("Origin could not execute the official K19 Line menu")
        graphs = list(self.op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError("Origin Line menu must create exactly one native graph")
        self.graph = graphs[0]
        with origin_trace_step(
            "template_residue_remove",
            details={"authoritative_workbook": book.name},
        ):
            for residue in tuple(self.op.pages("w")):
                if residue.name != book.name:
                    residue.destroy()
        self.graph.lname = f"K19 Date/Time Line / {document.plot_id}"
        self.layer = self.graph[0]
        self.plots = list(self.layer.plot_list())
        if len(self.plots) != len(series.series):
            raise RuntimeError("Origin Line menu did not create one plot per bound series")
        self.graph.activate()
        axis_label_type, axis_time_format, axis_display = self._axis_tick_display(series)
        with origin_trace_step(
            "datetime_axis_configure",
            details={
                "label_type": axis_label_type,
                "time_format": axis_time_format,
                "display": axis_display,
                "worksheet_format": "Date",
            },
        ):
            if not self.op.lt_exec(
                "page.active=1; "
                f"layer.x.label.type={axis_label_type}; "
                f"layer.x.label.timeFormat={axis_time_format};"
            ):
                raise RuntimeError("Origin could not set the K19 Date/Time tick labels")
            self.layer.rescale()
        self._set_legend(series, visible=len(series.series) > 1)
        native = self._native_line_structure(series)
        record_origin_trace("native_datetime_line_confirmed", "completed", details=native)

    def open(self, project_path: Path) -> None:
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        with origin_trace_step(
            "opju_open", details={"filename": project_path.name, "readonly": False}
        ):
            if not self.op.open(str(project_path), readonly=False, asksave=False):
                raise RuntimeError(
                    f"Origin could not open the previous K19 project: {project_path}"
                )
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("K19 project must contain one graph and one workbook")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        self.plots = list(self.layer.plot_list())
        if not self.plots:
            raise RuntimeError("K19 project must contain at least one native datetime plot")
        self.book = books[0]
        self.sheet = self.book[0]

    def apply(self, document: PlotDocument, action: PlotEngineAction, data: EngineDataView) -> None:
        token = document.plot_id.removeprefix("plot:")
        series = k19_time_series(document, data)
        if isinstance(action, (CreatePlot, BindFields)):
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError("K19 title target does not belong to this plot")
            label = self.layer.label(_TITLE_NAME)
            if label is None and action.text:
                self.layer.activate()
                if not self.layer.obj.LT_execute(
                    f"label -j 1 -n {_TITLE_NAME} PlotAgentTitlePlaceholder;"
                ):
                    raise RuntimeError("Origin could not create the K19 title")
                label = self.layer.label(_TITLE_NAME)
            if label is not None:
                label.text = action.text
                label.set_int("attach", 1)
                label.set_float("x1", 0.5)
                label.set_float("y1", 0.012)
                label.set_int("fsize", 14)
                label.set_int("fstyle", 0)
                label.set_int("background", 0)
                label.set_int("show", int(bool(action.text)))
            return
        if isinstance(action, SetAxis):
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
            if axis_name is None:
                raise ValueError("K19 axis target does not belong to this plot")
            if axis_name == "x" and action.scale not in {None, "datetime"}:
                raise ValueError("K19 x axis requires datetime scale")
            if axis_name == "y" and action.scale not in {None, "linear", "log10"}:
                raise ValueError("K19 y axis supports only linear or log10 scale")
            axis = self.layer.axis(axis_name)
            if axis_name == "y" and action.scale is not None:
                axis.scale = action.scale
            if axis_name == "x" and (
                action.minimum is not None or action.maximum is not None
            ):
                raise ValueError("K19 public datetime axes do not expose numeric bounds")
            if axis_name == "y" and (
                action.minimum is not None or action.maximum is not None
            ):
                if action.minimum is None or action.maximum is None:
                    raise ValueError("K19 y-axis bounds require both minimum and maximum")
                begin, end = action.minimum, action.maximum
                if action.reverse:
                    begin, end = end, begin
                axis.set_limits(begin, end)
            if action.reverse is not None:
                begin, end, step = (float(value) for value in axis.limits)
                should_reverse = begin < end if action.reverse else begin > end
                if should_reverse:
                    axis.set_limits(end, begin, abs(step))
            if action.label is not None:
                label = self.layer.label("xb" if axis_name == "x" else "yl")
                if label is None:
                    label = self.layer.add_label(action.label)
                if label is None:
                    raise RuntimeError("Origin LINE.otpu has no writable axis label")
                label.text = action.label
                label.set_int("show", 1)
            return
        if isinstance(action, SetSeriesStyle):
            ordinal = self._series_ordinal(action.target, token, len(series.series))
            plot = self.plots[ordinal - 1]
            if action.symbol is not None or action.symbol_size_pt is not None:
                raise ValueError("K19 Line does not expose symbol edits")
            if action.line_style == "none":
                raise ValueError("K19 Line cannot hide its line through series style")
            self.graph.activate()
            graph_name = str(self.graph.name)
            if not graph_name.replace("_", "").isalnum():
                raise RuntimeError("unsafe K19 graph name for native style edit")
            if not self.op.lt_exec(
                f"range __K19HEAD=[{graph_name}]Layer1!1; "
                f"range __K19MEMBER=[{graph_name}]Layer1!{ordinal}; "
                "set __K19HEAD -gm 1;"
            ):
                raise RuntimeError("Origin could not make the K19 line group independent")
            if action.color is not None:
                plot.color = action.color
            if action.line_width_pt is not None:
                plot.set_float("line.width", action.line_width_pt)
            if action.line_style is not None and not self.op.lt_exec(
                f"set __K19MEMBER -d {_LINE_STYLE_CODES[action.line_style]};"
            ):
                raise RuntimeError("Origin could not apply the K19 native line style")
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError("K19 legend target does not belong to this plot")
            if action.anchor not in {None, "inside"}:
                raise ValueError("K19 currently exposes only the template legend anchor")
            self._set_legend(
                series,
                visible=len(series.series) > 1 if action.visible is None else action.visible,
            )
            return
        raise ValueError(f"Origin K19 binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        with origin_trace_step("opju_save", details={"filename": output_path.name}):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.exists():
                raise FileExistsError(
                    f"Origin refuses to overwrite existing K19 artifact: {output_path}"
                )
            self.op.save(str(output_path))
            if not output_path.is_file() or output_path.stat().st_size <= 0:
                raise RuntimeError("Origin did not save a non-empty K19 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        expected = k19_time_series(document, data)
        frame = self.sheet.to_df()
        observed_times = tuple(pd.to_datetime(frame.iloc[:, 0]).dt.to_pydatetime())
        if not datetime_values_match(observed_times, expected.time_values):
            raise RuntimeError("Origin K19 datetime values differ after reopen")
        for index, item in enumerate(expected.series, start=1):
            observed_values = frame.iloc[:, index].to_numpy(dtype=float)
            if not np.allclose(
                observed_values, item.values, rtol=0, atol=1e-12, equal_nan=True
            ):
                raise RuntimeError(f"Origin K19 series {index} values differ after reopen")
        if len(self.plots) != len(expected.series):
            raise RuntimeError("Origin K19 series count differs after reopen")
        native_structure = self._native_line_structure(expected)
        token = document.plot_id.removeprefix("plot:")
        style_snapshot: dict[str, object] = {}
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if action.text:
                    if (
                        title is None
                        or title.text != action.text
                        or not title.get_int("show")
                    ):
                        raise RuntimeError("Origin K19 title did not survive readback")
                elif title is not None and title.get_int("show"):
                    raise RuntimeError("Origin K19 cleared title became visible again")
                style_snapshot["title"] = action.text
            elif isinstance(action, SetAxis):
                axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(
                    action.target
                )
                if axis_name is None:
                    raise RuntimeError("Origin K19 axis target changed during readback")
                axis = self.layer.axis(axis_name)
                if action.label is not None:
                    label = self.layer.label("xb" if axis_name == "x" else "yl")
                    if label is None or label.text != action.label:
                        raise RuntimeError("Origin K19 axis label did not survive readback")
                if (
                    axis_name == "y"
                    and action.scale is not None
                    and self._axis_scale_code(axis_name)
                    != {"linear": 0, "log10": 1}[action.scale]
                ):
                    raise RuntimeError("Origin K19 y-axis scale did not survive readback")
                begin, end, step = (float(value) for value in axis.limits)
                if axis_name == "y" and action.minimum is not None:
                    if action.maximum is None:
                        raise RuntimeError("Origin K19 y-axis maximum disappeared")
                    expected_limits = (action.minimum, action.maximum)
                    if action.reverse:
                        expected_limits = (expected_limits[1], expected_limits[0])
                    if not np.allclose(
                        (begin, end), expected_limits, rtol=0, atol=1e-12
                    ):
                        raise RuntimeError("Origin K19 y-axis bounds did not survive readback")
                if action.reverse is not None and ((begin > end) != action.reverse):
                    raise RuntimeError("Origin K19 axis direction did not survive readback")
                style_snapshot[f"axis_{axis_name}"] = {
                    "label": action.label,
                    "scale_code": self._axis_scale_code(axis_name),
                    "limits": [begin, end, step],
                }
            elif isinstance(action, SetSeriesStyle):
                ordinal = self._series_ordinal(action.target, token, len(expected.series))
                plot = self.plots[ordinal - 1]
                if action.color is not None:
                    observed_color = tuple(int(value) for value in plot.color)
                    expected_color = tuple(
                        int(action.color[index : index + 2], 16) for index in (1, 3, 5)
                    )
                    if observed_color != expected_color:
                        raise RuntimeError("Origin K19 series color did not survive readback")
                if action.line_width_pt is not None and abs(
                    plot.get_float("line.width") - action.line_width_pt
                ) > 0.01:
                    raise RuntimeError("Origin K19 line width did not survive readback")
                style_code = self._line_style_code(ordinal)
                if action.line_style is not None and style_code != _LINE_STYLE_CODES[
                    action.line_style
                ]:
                    raise RuntimeError("Origin K19 line style did not survive readback")
                style_snapshot[f"series_{ordinal}"] = {
                    "color": tuple(int(value) for value in plot.color),
                    "line_width": plot.get_float("line.width"),
                    "line_style": style_code,
                }
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layer.label("legend")
                if legend is None or bool(legend.get_int("show")) != action.visible:
                    raise RuntimeError("Origin K19 legend visibility did not survive readback")
                if action.visible and legend.text.count("\\l(") != len(expected.series):
                    raise RuntimeError("Origin K19 legend lost a linked series entry")
                style_snapshot["legend"] = action.visible
        style_snapshot["native_structure"] = native_structure
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
                *(
                    EngineObjectRef(
                        semantic_id=f"series:{token}.line_{index}",
                        backend="origin",
                        object_kind="datetime_line",
                        native_ref=f"graph:{self.graph.name}.layer:1.plot:{index}",
                    )
                    for index in range(1, len(expected.series) + 1)
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(cast(JsonValue, style_snapshot)),
        )

    def _write_data(self, document: PlotDocument, data: EngineDataView) -> None:
        series = k19_time_series(document, data)
        columns: dict[str, object] = {
            series.time_field_name: pd.to_datetime(series.time_values)
        }
        for item in series.series:
            columns[item.value_field_name] = item.values
        self.sheet.from_df(pd.DataFrame(columns))
        self.sheet.cols_axis("x" + "y" * len(series.series))
        self.sheet.as_date(0, "yyyy-MM-dd HH:mm:ss")

    def _native_line_structure(self, expected: TimeSeriesData) -> dict[str, object]:
        self.graph.activate()
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe K19 graph name for native readback: {graph_name!r}")
        command = "page.active=1; layer -c; __k19_count=count; "
        if not self.op.lt_exec(command):
            raise RuntimeError("Origin could not read back the native K19 structure")
        plot_count = int(self.op.lt_float("__k19_count"))
        plots: list[dict[str, object]] = []
        for plot_index in range(1, plot_count + 1):
            plot_command = (
                f"range __k19_plot=[{graph_name}]1!{plot_index}; "
                "range -wx __k19_x=__k19_plot; range -wy __k19_y=__k19_plot; "
                "get __k19_plot -pt __k19_pid; "
                "string __k19_xs$=%(__k19_x); string __k19_ys$=%(__k19_y);"
            )
            if not self.op.lt_exec(plot_command):
                raise RuntimeError("Origin could not read a K19 Line member")
            plots.append(
                {
                    "plot_index": plot_index,
                    "plot_id": int(self.op.lt_float("__k19_pid")),
                    "x_range": self.op.get_lt_str("__k19_xs"),
                    "y_range": self.op.get_lt_str("__k19_ys"),
                }
            )
        if not self.op.lt_exec(
            "__k19_axis_label_type=layer.x.label.type; "
            "__k19_axis_time_format=layer.x.label.timeFormat;"
        ):
            raise RuntimeError("Origin could not read the K19 Date tick-label type")
        axis_label_type = int(self.op.lt_float("__k19_axis_label_type"))
        axis_time_format = int(self.op.lt_float("__k19_axis_time_format"))
        designation = tuple(
            int(self.sheet.get_int(f"col{index + 1}.type"))
            for index in range(len(expected.series) + 1)
        )
        date_format_code = int(self.sheet.obj[0].GetDataFormat())
        if plot_count != len(expected.series) or any(
            item["plot_id"] != 200 for item in plots
        ):
            raise RuntimeError("Origin K19 must retain one native PID 200 plot per series")
        if designation != (4,) + (1,) * len(expected.series):
            raise RuntimeError("Origin K19 worksheet must retain X + N Y designations")
        if date_format_code != 3:
            raise RuntimeError("Origin K19 X column must retain Origin Date format")
        expected_label_type, expected_time_format, expected_display = self._axis_tick_display(
            expected
        )
        if axis_label_type != expected_label_type:
            raise RuntimeError(f"Origin K19 X tick labels must retain {expected_display}")
        if axis_time_format != expected_time_format:
            raise RuntimeError(f"Origin K19 X tick labels lost {expected_display} format")
        for index, item in enumerate(plots, start=1):
            x_head = str(item["x_range"]).split('"', 1)[0]
            y_head = str(item["y_range"]).split('"', 1)[0]
            if not x_head.endswith("!A") or not y_head.endswith(
                "!" + self._column_name(index + 1)
            ):
                raise RuntimeError("Origin K19 native Line plot lost its X/Y source bindings")
        return {
            "axis_label_type": axis_label_type,
            "axis_time_format": axis_time_format,
            "axis_display": expected_display,
            "date_format_code": date_format_code,
            "designation_codes": list(designation),
            "plot_count": plot_count,
            "plots": plots,
        }

    def _set_legend(self, expected: TimeSeriesData, *, visible: bool) -> None:
        self.graph.activate()
        command = (
            "page.active=1; legendupdate dest:=layer update:=reconstruct "
            "legend:=separate mode:=lname;"
        )
        if not self.op.lt_exec(command):
            raise RuntimeError("Origin could not reconstruct the linked K19 legend")
        legend = self.layer.label("legend")
        if legend is None:
            if visible:
                raise RuntimeError("Origin K19 did not create its linked legend")
            return
        legend.set_int("link", 1)
        legend.set_int("show", int(visible))
        if visible and legend.text.count("\\l(") != len(expected.series):
            raise RuntimeError("Origin K19 legend entry count differs from the series count")

    def _line_style_code(self, ordinal: int) -> int:
        self.graph.activate()
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError("unsafe K19 graph name for native style readback")
        command = (
            f"range __K19STYLE=[{graph_name}]Layer1!{ordinal}; "
            "get __K19STYLE -d __K19STYLECODE;"
        )
        if not self.op.lt_exec(command):
            raise RuntimeError("Origin could not read the K19 native line style")
        return int(self.op.lt_float("__K19STYLECODE"))

    def _axis_scale_code(self, axis_name: str) -> int:
        self.graph.activate()
        axis_token = {"x": "X", "y": "Y"}.get(axis_name)
        if axis_token is None:
            raise ValueError("K19 native scale readback requires x or y axis")
        if not self.op.lt_exec(f"axis -pg {axis_token} S __K19SCALECODE;"):
            raise RuntimeError("Origin could not read the K19 native axis scale")
        return int(self.op.lt_float("__K19SCALECODE"))

    @staticmethod
    def _axis_tick_display(expected: TimeSeriesData) -> tuple[int, int, str]:
        calendar_dates = {value.date() for value in expected.time_values}
        if len(calendar_dates) == 1:
            return 3, _DEFAULT_DATE_TIME_FORMAT, "Time / HH:mm"
        return 4, _DEFAULT_DATE_TIME_FORMAT, "Date / Windows Short Date"

    @staticmethod
    def _series_ordinal(target: str, token: str, series_count: int) -> int:
        prefix = f"series:{token}.line_"
        if not target.startswith(prefix):
            raise ValueError("K19 series target does not belong to this plot")
        try:
            ordinal = int(target.removeprefix(prefix))
        except ValueError as error:
            raise ValueError("K19 series target requires a numeric ordinal") from error
        if ordinal < 1 or ordinal > series_count:
            raise ValueError("K19 series target ordinal is outside the bound data")
        return ordinal

    @staticmethod
    def _column_name(ordinal: int) -> str:
        if ordinal < 1:
            raise ValueError("worksheet columns start at one")
        output = ""
        value = ordinal
        while value:
            value, remainder = divmod(value - 1, 26)
            output = chr(65 + remainder) + output
        return output


def execute_k19_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = K19OriginProject(op)
    # Replaying the declared action history onto the official template makes
    # an artifact reproducible from its request and avoids inheriting stale
    # Date/Time axis state from a previous OPJU revision.
    project.create(install_dir, request.document, request.data)
    with origin_trace_step(
        "agent_actions_apply", details={"action_count": len(request.actions)}
    ):
        for action in request.actions:
            with origin_trace_step(
                "agent_action_apply",
                details=cast(dict[str, object], action.model_dump(exclude_none=True)),
            ):
                project.apply(request.document, action, request.data)
    project.save(output)
    reopened = K19OriginProject(op)
    reopened.open(output)
    with origin_trace_step("reopened_native_structure_verify"):
        return reopened.verify(request.document, request.actions, request.data)
