"""K02 official LINESYMB template binder with grouped native series."""

from __future__ import annotations

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
from plotagent.engine.profile_data import K03ScatterData, grouped_xy
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K02_ORIGIN_PROFILE, resolve_official_template
from .trace import origin_trace_step, record_origin_trace


class K02OriginProject:
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
            details={"template_filename": K02_ORIGIN_PROFILE.filename},
        ):
            template = resolve_official_template(install_dir, K02_ORIGIN_PROFILE)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the K02 data workbook")
        self.sheet = book[0]
        grouped = grouped_xy(document, data, profile_id="K02")
        with origin_trace_step(
            "source_data_write",
            details={"designation": "XY repeated", "group_count": len(grouped.groups)},
        ):
            self._write_data(grouped)
        command = (
            f"worksheet -s 1 0 {len(grouped.groups) * 2} 0; "
            "worksheet -p 202 LineSymb;"
        )
        with origin_trace_step(
            "official_plot_command_execute",
            details={
                "labtalk": command,
                "native_plot_type": 202,
                "template_filename": template.name,
            },
        ):
            self.sheet.activate()
            if not self.op.lt_exec(command):
                raise RuntimeError(
                    "Origin could not execute the official K02 Line + Symbol menu"
                )
        graphs = list(self.op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError("Origin Line + Symbol menu must create exactly one graph")
        self.graph = graphs[0]
        self.graph.name = f"G{token}"
        self.graph.lname = f"K02 Line + Symbol / {document.plot_id}"
        self.layer = self.graph[0]
        self.plots = list(self.layer.plot_list())
        if len(self.plots) != len(grouped.groups):
            raise RuntimeError(
                "Origin Line + Symbol menu must create one native plot per data group"
            )
        self.plot = self.plots[0]
        with origin_trace_step("template_residue_remove"):
            for residue in tuple(self.op.pages("w")):
                if residue.name != book.name:
                    residue.destroy()
        self.layer.rescale()
        self._set_legend(grouped, visible=len(grouped.groups) > 1)
        native = self._assert_native_structure(grouped)
        record_origin_trace("native_line_symbol_confirmed", "completed", details=native)

    def open(self, project_path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=False, asksave=False):
            raise RuntimeError(f"Origin could not open the previous project: {project_path}")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("K02 Origin project must contain one graph and one workbook")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        self.plots = list(self.layer.plot_list())
        if not self.plots:
            raise RuntimeError("K02 Origin project must contain native data plots")
        self.plot = self.plots[0]
        self.sheet = books[0][0]

    def apply(self, document: PlotDocument, action: PlotEngineAction, data: EngineDataView) -> None:
        document.plot_id.removeprefix("plot:")
        if isinstance(action, CreatePlot):
            return
        if isinstance(action, BindFields):
            grouped = grouped_xy(document, data, profile_id="K02")
            if len(grouped.groups) != len(self.plots):
                raise RuntimeError("K02 group count changes require a native graph rebuild")
            self._write_data(grouped)
            self._set_legend(grouped, visible=len(grouped.groups) > 1)
            self.layer.rescale()
            return
        raise ValueError(f"Origin K02 binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output_path))
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError("Origin did not save a non-empty K02 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        grouped = grouped_xy(document, data, profile_id="K02")
        native = self._assert_native_structure(grouped)
        record_origin_trace("reopened_line_symbol_confirmed", "completed", details=native)
        self._assert_linked_legend(grouped, visible=len(grouped.groups) > 1)
        for index, group in enumerate(grouped.groups):
            self._assert_values(self.sheet.to_list(index * 2), group.x_values, "x")
            self._assert_values(self.sheet.to_list(index * 2 + 1), group.y_values, "y")
        token = document.plot_id.removeprefix("plot:")
        style_snapshot: dict[str, object] = {"native_structure": native}
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
            *tuple(
                EngineObjectRef(
                    semantic_id=f"series:{token}.group_{index}",
                    backend="origin",
                    object_kind="line_symbol_series",
                    native_ref=f"graph:{self.graph.name}.layer:1.plot:{index}",
                )
                for index in range(1, len(grouped.groups) + 1)
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

    def _write_data(self, grouped: K03ScatterData) -> None:
        for index, group in enumerate(grouped.groups):
            self.sheet.from_list(
                index * 2,
                list(group.x_values),
                lname=grouped.x_field_name,
                axis="X",
            )
            self.sheet.from_list(
                index * 2 + 1,
                list(group.y_values),
                lname=group.label,
                axis="Y",
            )

    def _set_legend(self, grouped: K03ScatterData, *, visible: bool) -> None:
        self.graph.activate()
        if not visible:
            legend = self.layer.label("legend")
            if legend is not None:
                legend.set_int("show", 0)
            return
        if not self.op.lt_exec(
            "page.active=1; legendupdate dest:=layer update:=reconstruct "
            "legend:=separate mode:=lname;"
        ):
            raise RuntimeError("Origin could not reconstruct the linked K02 legend")
        legend = self.layer.label("legend")
        if legend is None:
            if visible:
                raise RuntimeError("Origin K02 did not create its linked legend")
            return
        legend.text = "\n".join(
            f"\\l({index}) %({index})" for index in range(1, len(grouped.groups) + 1)
        )
        legend.set_int("link", 1)
        legend.set_int("show", int(visible))

    def _assert_linked_legend(self, grouped: K03ScatterData, *, visible: bool) -> None:
        legend = self.layer.label("legend")
        if legend is None:
            if visible:
                raise RuntimeError("Origin K02 lost its linked legend")
            return
        if bool(legend.get_int("show")) != visible:
            raise RuntimeError("Origin K02 legend visibility differs after reopen")
        expected = tuple(
            f"\\l({index}) %({index})" for index in range(1, len(grouped.groups) + 1)
        )
        actual = tuple(line.strip() for line in str(legend.text).splitlines() if line.strip())
        if actual != expected or int(legend.get_int("link")) != 1:
            raise RuntimeError("Origin K02 legend lost a linked group entry")

    def _assert_native_structure(self, grouped: K03ScatterData) -> dict[str, object]:
        self.graph.activate()
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe K02 graph name for native readback: {graph_name!r}")
        if not self.op.lt_exec("page.active=1; layer -c; __K02COUNT=count;"):
            raise RuntimeError("Origin could not read the native K02 structure")
        plot_count = int(self.op.lt_float("__K02COUNT"))
        if plot_count != len(grouped.groups):
            raise RuntimeError("Origin K02 native plot count differs from data groups")
        plots: list[dict[str, object]] = []
        for index in range(1, plot_count + 1):
            command = (
                f"range __K02P=[{graph_name}]1!{index}; "
                "range -wx __K02X=__K02P; range -wy __K02Y=__K02P; "
                "get __K02P -pt __K02PID; "
                "string __K02XS$=%(__K02X); string __K02YS$=%(__K02Y);"
            )
            if not self.op.lt_exec(command):
                raise RuntimeError(f"Origin could not read K02 line-symbol group {index}")
            plot_id = int(self.op.lt_float("__K02PID"))
            x_range = str(self.op.get_lt_str("__K02XS"))
            y_range = str(self.op.get_lt_str("__K02YS"))
            x_letter = self._column_name(index * 2 - 1)
            y_letter = self._column_name(index * 2)
            if plot_id != 202:
                raise RuntimeError("Origin K02 must retain only native PID 202 plots")
            if not x_range.split('"', 1)[0].endswith(f"!{x_letter}") or not y_range.split(
                '"', 1
            )[0].endswith(f"!{y_letter}"):
                raise RuntimeError("Origin K02 lost a group/source binding")
            plots.append(
                {
                    "plot_index": index,
                    "plot_id": plot_id,
                    "x_range": x_range,
                    "y_range": y_range,
                }
            )
        designations = tuple(
            int(self.sheet.get_int(f"col{index}.type"))
            for index in range(1, plot_count * 2 + 1)
        )
        if designations != (4, 1) * plot_count:
            raise RuntimeError("Origin K02 worksheet must retain repeated X/Y designations")
        return {
            "official_template": K02_ORIGIN_PROFILE.filename,
            "official_menu": "Plot > Basic 2D: Line + Symbol",
            "plot_count": plot_count,
            "designation_codes": list(designations),
            "plots": plots,
        }

    @staticmethod
    def _column_name(ordinal: int) -> str:
        output = ""
        value = ordinal
        while value:
            value, remainder = divmod(value - 1, 26)
            output = chr(65 + remainder) + output
        return output

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[object, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin K02 {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if observed is None and wanted is None:
                continue
            if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
                if abs(float(cast(Any, observed)) - float(wanted)) <= 1e-12:
                    continue
            elif observed == wanted:
                continue
            raise RuntimeError(f"Origin K02 {role} values differ after reopen")


def execute_k02_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = K02OriginProject(op)
    project.create(install_dir, request.document, request.data)
    with origin_trace_step(
        "agent_actions_apply", details={"action_count": len(request.actions)}
    ):
        for action in request.actions:
            project.apply(request.document, action, request.data)
    project.save(output)

    op.new(asksave=False)
    if not op.open(str(output), readonly=True, asksave=False):
        raise RuntimeError("fresh Origin session could not reopen the staged K02 project")
    reopened = K02OriginProject(op)
    graphs = list(op.pages("g"))
    books = list(op.pages("w"))
    if len(graphs) != 1 or len(books) != 1:
        raise RuntimeError("fresh K02 project has unexpected graph or workbook count")
    reopened.graph = graphs[0]
    reopened.layer = reopened.graph[0]
    reopened.plots = list(reopened.layer.plot_list())
    if not reopened.plots:
        raise RuntimeError("fresh K02 project has no native plots")
    reopened.plot = reopened.plots[0]
    reopened.sheet = books[0][0]
    with origin_trace_step("reopened_native_structure_verify"):
        return reopened.verify(request.document, request.actions, request.data)
