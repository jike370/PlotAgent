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
        column_count = self._worksheet_column_count(series)
        with origin_trace_step(
            "source_data_write",
            details={
                "column_count": column_count,
                "row_count": max(len(item.time_values) for item in series.series),
                "time_field": series.time_field_name,
                "series_fields": [item.value_field_name for item in series.series],
                "layout": "shared_x" if self._uses_shared_time_axis(series) else "paired_xy",
            },
        ):
            self._write_data(document, data)
        self.sheet.activate()
        command = f"worksheet -s 1 0 {column_count} 0; worksheet -p 200 Line;"
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
        document.plot_id.removeprefix("plot:")
        k19_time_series(document, data)
        if isinstance(action, (CreatePlot, BindFields)):
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
        shared_time_axis = self._uses_shared_time_axis(expected)
        for index, item in enumerate(expected.series, start=1):
            time_column = 0 if shared_time_axis else (index - 1) * 2
            value_column = index if shared_time_axis else time_column + 1
            observed_times = tuple(
                pd.to_datetime(frame.iloc[: len(item.time_values), time_column]).dt.to_pydatetime()
            )
            if not datetime_values_match(observed_times, item.time_values):
                raise RuntimeError(f"Origin K19 series {index} datetime values differ after reopen")
            observed_values = frame.iloc[: len(item.values), value_column].to_numpy(dtype=float)
            if not np.allclose(observed_values, item.values, rtol=0, atol=1e-12, equal_nan=True):
                raise RuntimeError(f"Origin K19 series {index} values differ after reopen")
        if len(self.plots) != len(expected.series):
            raise RuntimeError("Origin K19 series count differs after reopen")
        native_structure = self._native_line_structure(expected)
        self._assert_linked_legend(expected)
        token = document.plot_id.removeprefix("plot:")
        style_snapshot: dict[str, object] = {}
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
                EngineObjectRef(
                    semantic_id=f"legend:{token}.main",
                    backend="origin",
                    object_kind="legend",
                    native_ref=f"graph:{self.graph.name}.layer:1.label:legend",
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(cast(JsonValue, style_snapshot)),
        )

    def _write_data(self, document: PlotDocument, data: EngineDataView) -> None:
        series = k19_time_series(document, data)
        shared_time_axis = self._uses_shared_time_axis(series)
        columns: dict[str, object] = {}
        date_columns: tuple[int, ...]
        if shared_time_axis:
            columns[series.time_field_name] = pd.Series(pd.to_datetime(series.time_values))
            for item in series.series:
                columns[item.value_field_name] = pd.Series(item.values, dtype=float)
            designation = "x" + "y" * len(series.series)
            date_columns = (0,)
        else:
            for item in series.series:
                columns[f"{series.time_field_name} · {item.value_field_name}"] = pd.Series(
                    pd.to_datetime(item.time_values)
                )
                columns[item.value_field_name] = pd.Series(item.values, dtype=float)
            designation = "xy" * len(series.series)
            date_columns = tuple(range(0, len(series.series) * 2, 2))
        self.sheet.from_df(pd.DataFrame(columns))
        self.sheet.cols_axis(designation)
        for index in date_columns:
            self.sheet.as_date(index, "yyyy-MM-dd HH:mm:ss")

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
        column_count = self._worksheet_column_count(expected)
        designation = tuple(
            int(self.sheet.get_int(f"col{index + 1}.type")) for index in range(column_count)
        )
        shared_time_axis = self._uses_shared_time_axis(expected)
        expected_designation = (
            (4,) + (1,) * len(expected.series)
            if shared_time_axis
            else (4, 1) * len(expected.series)
        )
        date_column_ordinals = (1,) if shared_time_axis else tuple(range(1, column_count + 1, 2))
        date_format_codes = tuple(
            int(self.sheet.obj[ordinal - 1].GetDataFormat()) for ordinal in date_column_ordinals
        )
        if plot_count != len(expected.series) or any(item["plot_id"] != 200 for item in plots):
            raise RuntimeError("Origin K19 must retain one native PID 200 plot per series")
        if designation != expected_designation:
            raise RuntimeError("Origin K19 worksheet lost its native X/Y designations")
        if any(code != 3 for code in date_format_codes):
            raise RuntimeError("Origin K19 X columns must retain Origin Date format")
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
            x_ordinal = 1 if shared_time_axis else index * 2 - 1
            y_ordinal = index + 1 if shared_time_axis else index * 2
            if not x_head.endswith("!" + self._column_name(x_ordinal)) or not y_head.endswith(
                "!" + self._column_name(y_ordinal)
            ):
                raise RuntimeError("Origin K19 native Line plot lost its X/Y source bindings")
        return {
            "axis_label_type": axis_label_type,
            "axis_time_format": axis_time_format,
            "axis_display": expected_display,
            "date_format_codes": list(date_format_codes),
            "designation_codes": list(designation),
            "layout": "shared_x" if shared_time_axis else "paired_xy",
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

    def _assert_linked_legend(self, expected: TimeSeriesData) -> None:
        legend = self.layer.label("legend")
        should_be_visible = len(expected.series) > 1
        if legend is None:
            if should_be_visible:
                raise RuntimeError("Origin K19 lost the required multi-series legend")
            return
        if bool(legend.get_int("show")) != should_be_visible:
            raise RuntimeError("Origin K19 default legend visibility differs from series count")
        if not should_be_visible:
            return
        text = str(legend.text)
        expected_names = tuple(item.value_field_name for item in expected.series)
        expected_tokens = tuple(
            f"\\l({index}) %({index})" for index in range(1, len(expected_names) + 1)
        )
        actual_tokens = tuple(line.strip() for line in text.splitlines() if line.strip())
        if actual_tokens != expected_tokens or int(legend.get_int("link")) != 1:
            raise RuntimeError(
                "Origin K19 linked legend tokens differ from the native plot order: "
                f"expected={expected_tokens!r}, actual={actual_tokens!r}"
            )
        frame = self.sheet.to_df()
        frame_names = tuple(
            str(frame.columns[index if self._uses_shared_time_axis(expected) else index * 2 - 1])
            for index in range(1, len(expected.series) + 1)
        )
        if frame_names != expected_names:
            raise RuntimeError(
                "Origin K19 legend metadata source differs from the bound series: "
                f"expected={expected_names!r}, actual={frame_names!r}"
            )

    @staticmethod
    def _axis_tick_display(expected: TimeSeriesData) -> tuple[int, int, str]:
        calendar_dates = {value.date() for value in expected.time_values}
        if len(calendar_dates) == 1:
            return 3, _DEFAULT_DATE_TIME_FORMAT, "Time / HH:mm"
        return 4, _DEFAULT_DATE_TIME_FORMAT, "Date / Windows Short Date"

    @staticmethod
    def _uses_shared_time_axis(expected: TimeSeriesData) -> bool:
        return all(item.time_values == expected.time_values for item in expected.series)

    @classmethod
    def _worksheet_column_count(cls, expected: TimeSeriesData) -> int:
        return (
            len(expected.series) + 1
            if cls._uses_shared_time_axis(expected)
            else 2 * len(expected.series)
        )

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
    with origin_trace_step("agent_actions_apply", details={"action_count": len(request.actions)}):
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
