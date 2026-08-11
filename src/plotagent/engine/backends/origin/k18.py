"""K18 native Area renderer through Origin's official menu dispatcher."""

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
from plotagent.engine.profile_data import AreaSeriesData, k18_area_series
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K18_ORIGIN_PROFILE, resolve_official_template
from .trace import origin_trace_step, record_origin_trace

_TITLE_NAME = "_ENGINE_TITLE"
_LINE_STYLE_CODES = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}


class K18OriginProject:
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
            details={"template_filename": K18_ORIGIN_PROFILE.filename},
        ):
            template = resolve_official_template(install_dir, K18_ORIGIN_PROFILE)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the K18 workbook")
        self.book = book
        self.sheet = book[0]
        expected = k18_area_series(document, data)
        with origin_trace_step(
            "source_data_write",
            details={
                "column_count": len(expected.series) + 1,
                "row_count": len(expected.x_values),
                "x_field": expected.x_field_name,
                "series_fields": [item.value_field_name for item in expected.series],
            },
        ):
            self._write_data(document, data)
        self.sheet.activate()
        command = (
            f"worksheet -s 1 0 {len(expected.series) + 1} 0; "
            "worksheet -p 204 Area;"
        )
        with origin_trace_step(
            "official_plot_command_execute",
            details={
                "labtalk": command,
                "native_plot_type": 204,
                "template_filename": template.name,
            },
        ):
            if not self.op.lt_exec(command):
                raise RuntimeError("Origin could not execute the official K18 Area menu")
        graphs = list(self.op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError("Origin Area menu must create exactly one native graph")
        self.graph = graphs[0]
        with origin_trace_step(
            "template_residue_remove",
            details={"authoritative_workbook": book.name},
        ):
            for residue in tuple(self.op.pages("w")):
                if residue.name != book.name:
                    residue.destroy()
        self.graph.lname = f"K18 Area / {document.plot_id}"
        self.layer = self.graph[0]
        self.plots = list(self.layer.plot_list())
        if len(self.plots) != len(expected.series):
            raise RuntimeError("Origin Area menu did not create one plot per bound series")
        self.layer.rescale()
        self._set_legend(expected, visible=len(expected.series) > 1)
        native = self._native_area_structure(expected)
        record_origin_trace("native_area_confirmed", "completed", details=native)

    def open(self, project_path: Path) -> None:
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        with origin_trace_step(
            "opju_open", details={"filename": project_path.name, "readonly": False}
        ):
            if not self.op.open(str(project_path), readonly=False, asksave=False):
                raise RuntimeError(
                    f"Origin could not open the previous K18 project: {project_path}"
                )
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("K18 project must contain one graph and one workbook")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        self.plots = list(self.layer.plot_list())
        if not self.plots:
            raise RuntimeError("K18 project must contain at least one native Area plot")
        self.book = books[0]
        self.sheet = self.book[0]

    def apply(self, document: PlotDocument, action: PlotEngineAction, data: EngineDataView) -> None:
        token = document.plot_id.removeprefix("plot:")
        expected = k18_area_series(document, data)
        if isinstance(action, (CreatePlot, BindFields)):
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError("K18 title target does not belong to this plot")
            label = self.layer.label(_TITLE_NAME)
            if label is None and action.text:
                self.layer.activate()
                if not self.layer.obj.LT_execute(
                    f"label -j 1 -n {_TITLE_NAME} PlotAgentTitlePlaceholder;"
                ):
                    raise RuntimeError("Origin could not create the K18 title")
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
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(
                action.target
            )
            if axis_name is None:
                raise ValueError("K18 axis target does not belong to this plot")
            if action.scale not in {None, "linear", "log10"}:
                raise ValueError("K18 axes support only linear or log10 scale")
            if action.scale == "log10":
                values = (
                    expected.x_values
                    if axis_name == "x"
                    else tuple(value for item in expected.series for value in item.values)
                )
                if any(np.isfinite(value) and value <= 0 for value in values):
                    raise ValueError(
                        f"K18 {axis_name} values must be positive on a log10 axis"
                    )
            axis = self.layer.axis(axis_name)
            if action.scale is not None:
                axis.scale = action.scale
            if action.minimum is not None or action.maximum is not None:
                if action.minimum is None or action.maximum is None:
                    raise ValueError("K18 axis bounds require both minimum and maximum")
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
                    raise RuntimeError("Origin AREA.otpu has no writable axis label")
                label.text = action.label
                label.set_int("show", 1)
            return
        if isinstance(action, SetSeriesStyle):
            ordinal = self._series_ordinal(action.target, token, len(expected.series))
            if action.symbol is not None or action.symbol_size_pt is not None:
                raise ValueError("K18 Area does not expose symbol edits")
            if action.line_style == "none":
                raise ValueError("K18 Area cannot hide its boundary line")
            self.graph.activate()
            graph_name = str(self.graph.name)
            if not graph_name.replace("_", "").isalnum():
                raise RuntimeError("unsafe K18 graph name for native style edit")
            command = (
                f"range __K18HEAD=[{graph_name}]1!1; "
                f"range __K18MEMBER=[{graph_name}]1!{ordinal}; "
                "set __K18HEAD -gm 1;"
            )
            if action.color is not None:
                command += (
                    f'set __K18MEMBER -c color("{action.color}"); '
                    f'set __K18MEMBER -cf color("{action.color}");'
                )
            if action.line_style is not None:
                command += f"set __K18MEMBER -d {_LINE_STYLE_CODES[action.line_style]};"
            if not self.op.lt_exec(command):
                raise RuntimeError("Origin could not apply the K18 native Area style")
            if action.line_width_pt is not None:
                self.plots[ordinal - 1].set_float("line.width", action.line_width_pt)
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError("K18 legend target does not belong to this plot")
            if action.anchor not in {None, "inside"}:
                raise ValueError("K18 currently exposes only the template legend anchor")
            self._set_legend(
                expected,
                visible=len(expected.series) > 1 if action.visible is None else action.visible,
            )
            return
        raise ValueError(f"Origin K18 binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        with origin_trace_step("opju_save", details={"filename": output_path.name}):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.exists():
                raise FileExistsError(
                    f"Origin refuses to overwrite existing K18 artifact: {output_path}"
                )
            self.op.save(str(output_path))
            if not output_path.is_file() or output_path.stat().st_size <= 0:
                raise RuntimeError("Origin did not save a non-empty K18 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        expected = k18_area_series(document, data)
        frame = self.sheet.to_df()
        if frame.shape != (len(expected.x_values), len(expected.series) + 1):
            raise RuntimeError("Origin K18 worksheet shape differs after reopen")
        if not np.allclose(
            frame.iloc[:, 0].to_numpy(dtype=float),
            expected.x_values,
            rtol=0,
            atol=1e-12,
            equal_nan=True,
        ):
            raise RuntimeError("Origin K18 X values differ after reopen")
        for index, item in enumerate(expected.series, start=1):
            if not np.allclose(
                frame.iloc[:, index].to_numpy(dtype=float),
                item.values,
                rtol=0,
                atol=1e-12,
                equal_nan=True,
            ):
                raise RuntimeError(f"Origin K18 series {index} values differ after reopen")
        if len(self.plots) != len(expected.series):
            raise RuntimeError("Origin K18 series count differs after reopen")
        native_structure = self._native_area_structure(expected)
        native_plots = cast(list[dict[str, object]], native_structure["plots"])
        token = document.plot_id.removeprefix("plot:")
        style_snapshot: dict[str, object] = {"native_structure": native_structure}
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if action.text:
                    if title is None or title.text != action.text or not title.get_int("show"):
                        raise RuntimeError("Origin K18 title did not survive readback")
                elif title is not None and title.get_int("show"):
                    raise RuntimeError("Origin K18 cleared title became visible again")
                style_snapshot["title"] = action.text
            elif isinstance(action, SetAxis):
                axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(
                    action.target
                )
                if axis_name is None:
                    raise RuntimeError("Origin K18 axis target changed during readback")
                axis = self.layer.axis(axis_name)
                if action.label is not None:
                    label = self.layer.label("xb" if axis_name == "x" else "yl")
                    if label is None or label.text != action.label:
                        raise RuntimeError("Origin K18 axis label did not survive readback")
                if action.scale is not None and self._axis_scale_code(axis_name) != {
                    "linear": 0,
                    "log10": 1,
                }[action.scale]:
                    raise RuntimeError("Origin K18 axis scale did not survive readback")
                begin, end, step = (float(value) for value in axis.limits)
                if action.minimum is not None:
                    if action.maximum is None:
                        raise RuntimeError("Origin K18 axis maximum disappeared")
                    limits = (action.minimum, action.maximum)
                    if action.reverse:
                        limits = (limits[1], limits[0])
                    if not np.allclose((begin, end), limits, rtol=0, atol=1e-12):
                        raise RuntimeError("Origin K18 axis bounds did not survive readback")
                if action.reverse is not None and ((begin > end) != action.reverse):
                    raise RuntimeError("Origin K18 axis direction did not survive readback")
                style_snapshot[f"axis_{axis_name}"] = {
                    "label": action.label,
                    "scale_code": self._axis_scale_code(axis_name),
                    "limits": [begin, end, step],
                }
            elif isinstance(action, SetSeriesStyle):
                ordinal = self._series_ordinal(action.target, token, len(expected.series))
                observed = native_plots[ordinal - 1]
                if action.color is not None:
                    expected_color = self._origin_color_code(action.color)
                    if observed["line_color"] != expected_color:
                        raise RuntimeError("Origin K18 boundary color did not survive readback")
                    if observed["fill_color"] != expected_color:
                        raise RuntimeError("Origin K18 fill color did not survive readback")
                if action.line_width_pt is not None and abs(
                    cast(float, observed["line_width_pt"]) - action.line_width_pt
                ) > 0.01:
                    raise RuntimeError("Origin K18 boundary width did not survive readback")
                if action.line_style is not None and observed["line_style"] != (
                    _LINE_STYLE_CODES[action.line_style]
                ):
                    raise RuntimeError("Origin K18 boundary style did not survive readback")
                style_snapshot[f"series_{ordinal}"] = observed
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layer.label("legend")
                if legend is None or bool(legend.get_int("show")) != action.visible:
                    raise RuntimeError("Origin K18 legend visibility did not survive readback")
                if action.visible and legend.text.count("\\l(") != len(expected.series):
                    raise RuntimeError("Origin K18 legend lost a linked series entry")
                style_snapshot["legend"] = action.visible

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
                        semantic_id=f"series:{token}.area_{index}",
                        backend="origin",
                        object_kind="area_series",
                        native_ref=f"graph:{self.graph.name}.layer:1.plot:{index}",
                    )
                    for index in range(1, len(expected.series) + 1)
                ),
                EngineObjectRef(
                    semantic_id=f"legend:{token}.main",
                    backend="origin",
                    object_kind="legend",
                    native_ref=f"graph:{self.graph.name}.layer:1.legend",
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(cast(JsonValue, style_snapshot)),
        )

    def _write_data(self, document: PlotDocument, data: EngineDataView) -> None:
        expected = k18_area_series(document, data)
        columns: dict[str, object] = {expected.x_field_name: expected.x_values}
        for item in expected.series:
            columns[item.value_field_name] = item.values
        self.sheet.from_df(pd.DataFrame(columns))
        self.sheet.cols_axis("x" + "y" * len(expected.series))

    def _native_area_structure(self, expected: AreaSeriesData) -> dict[str, object]:
        self.graph.activate()
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe K18 graph name for native readback: {graph_name!r}")
        if not self.op.lt_exec("page.active=1; layer -c; __K18COUNT=count;"):
            raise RuntimeError("Origin could not read back the native K18 structure")
        plot_count = int(self.op.lt_float("__K18COUNT"))
        plots: list[dict[str, object]] = []
        for plot_index in range(1, plot_count + 1):
            command = (
                f"range __K18P=[{graph_name}]1!{plot_index}; "
                "range -wx __K18X=__K18P; range -wy __K18Y=__K18P; "
                "get __K18P -pt __K18PID; get __K18P -c __K18LINE; "
                "get __K18P -cf __K18FILL; get __K18P -d __K18STYLE; "
                "get __K18P -w __K18WIDTH; "
                "string __K18XS$=%(__K18X); string __K18YS$=%(__K18Y);"
            )
            if not self.op.lt_exec(command):
                raise RuntimeError("Origin could not read a K18 Area member")
            plots.append(
                {
                    "plot_index": plot_index,
                    "plot_id": int(self.op.lt_float("__K18PID")),
                    "x_range": self.op.get_lt_str("__K18XS"),
                    "y_range": self.op.get_lt_str("__K18YS"),
                    "line_color": int(self.op.lt_float("__K18LINE")),
                    "fill_color": int(self.op.lt_float("__K18FILL")),
                    "line_style": int(self.op.lt_float("__K18STYLE")),
                    "line_width_pt": self.op.lt_float("__K18WIDTH") / 500.0,
                }
            )
        designation = tuple(
            int(self.sheet.get_int(f"col{index + 1}.type"))
            for index in range(len(expected.series) + 1)
        )
        if plot_count != len(expected.series) or any(
            item["plot_id"] != 204 for item in plots
        ):
            raise RuntimeError("Origin K18 must retain one native PID 204 plot per series")
        if designation != (4,) + (1,) * len(expected.series):
            raise RuntimeError("Origin K18 worksheet must retain X + N Y designations")
        for index, item in enumerate(plots, start=1):
            x_head = str(item["x_range"]).split('"', 1)[0]
            y_head = str(item["y_range"]).split('"', 1)[0]
            if not x_head.endswith("!A") or not y_head.endswith(
                "!" + self._column_name(index + 1)
            ):
                raise RuntimeError("Origin K18 native Area plot lost its X/Y source bindings")
        return {
            "designation_codes": list(designation),
            "plot_count": plot_count,
            "plots": plots,
            "from_y_gate": "manual_visual_review",
        }

    def _set_legend(self, expected: AreaSeriesData, *, visible: bool) -> None:
        self.graph.activate()
        if not self.op.lt_exec("page.active=1; legendupdate dest:=layer update:=reconstruct;"):
            raise RuntimeError("Origin could not create the K18 legend object")
        legend = self.layer.label("legend")
        if legend is None:
            if visible:
                raise RuntimeError("Origin K18 did not create its linked legend")
            return
        legend.text = "\n".join(
            f"\\l({index}) %({index},@LL)" for index in range(1, len(expected.series) + 1)
        )
        legend.set_int("link", 1)
        legend.set_int("show", int(visible))
        if visible and legend.text.count("\\l(") != len(expected.series):
            raise RuntimeError("Origin K18 legend entry count differs from the series count")

    def _axis_scale_code(self, axis_name: str) -> int:
        self.graph.activate()
        token = {"x": "X", "y": "Y"}.get(axis_name)
        if token is None:
            raise ValueError("K18 native scale readback requires x or y axis")
        if not self.op.lt_exec(f"axis -pg {token} S __K18SCALE;"):
            raise RuntimeError("Origin could not read the K18 native axis scale")
        return int(self.op.lt_float("__K18SCALE"))

    def _origin_color_code(self, color: str) -> int:
        return int(self.op.lt_float(f'color("{color}")'))

    @staticmethod
    def _series_ordinal(target: str, token: str, series_count: int) -> int:
        prefix = f"series:{token}.area_"
        if not target.startswith(prefix):
            raise ValueError("K18 series target does not belong to this plot")
        try:
            ordinal = int(target.removeprefix(prefix))
        except ValueError as error:
            raise ValueError("K18 series target requires a numeric ordinal") from error
        if ordinal < 1 or ordinal > series_count:
            raise ValueError("K18 series target ordinal is outside the bound data")
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


def execute_k18_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = K18OriginProject(op)
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
    reopened = K18OriginProject(op)
    reopened.open(output)
    with origin_trace_step("reopened_native_structure_verify"):
        return reopened.verify(request.document, request.actions, request.data)
