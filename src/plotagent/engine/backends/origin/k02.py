"""K02 official LINESYMB template binder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plotagent.engine.contracts import EngineDataView, PlotDocument, PlotEngineAction
from plotagent.engine.ports import EngineReadback

from .messages import OriginWorkerRequest
from .profile import K02_ORIGIN_PROFILE, resolve_official_template
from .trace import origin_trace_step, record_origin_trace
from .xy import OriginXYDefinition, OriginXYProject

_DEFINITION = OriginXYDefinition(
    template=K02_ORIGIN_PROFILE,
    plot_type="y",
    object_kind="line_symbol_series",
    supports_line=True,
    supports_symbol=True,
)


class K02OriginProject(OriginXYProject):
    def __init__(self, op: Any) -> None:
        super().__init__(op, _DEFINITION)

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
        with origin_trace_step("source_data_write", details={"designation": "XY"}):
            self._write_data(document, data)
        command = "worksheet -s 1 0 2 0; worksheet -p 202 LineSymb;"
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
        plots = list(self.layer.plot_list())
        if len(plots) != 1:
            raise RuntimeError("Origin Line + Symbol menu must create one native plot")
        self.plot = plots[0]
        with origin_trace_step("template_residue_remove"):
            for residue in tuple(self.op.pages("w")):
                if residue.name != book.name:
                    residue.destroy()
        self.layer.rescale()
        native = self._assert_native_structure()
        record_origin_trace("native_line_symbol_confirmed", "completed", details=native)

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        native = self._assert_native_structure()
        record_origin_trace("reopened_line_symbol_confirmed", "completed", details=native)
        return super().verify(document, actions, data)

    def _assert_native_structure(self) -> dict[str, object]:
        self.graph.activate()
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe K02 graph name for native readback: {graph_name!r}")
        command = (
            "page.active=1; layer -c; __K02COUNT=count; "
            f"range __K02P=[{graph_name}]1!1; "
            "range -wx __K02X=__K02P; range -wy __K02Y=__K02P; "
            "get __K02P -pt __K02PID; "
            "string __K02XS$=%(__K02X); string __K02YS$=%(__K02Y);"
        )
        if not self.op.lt_exec(command):
            raise RuntimeError("Origin could not read the native K02 Line + Symbol structure")
        plot_count = int(self.op.lt_float("__K02COUNT"))
        plot_id = int(self.op.lt_float("__K02PID"))
        designations = tuple(int(self.sheet.get_int(f"col{index}.type")) for index in (1, 2))
        x_range = str(self.op.get_lt_str("__K02XS"))
        y_range = str(self.op.get_lt_str("__K02YS"))
        if plot_count != 1 or plot_id != 202:
            raise RuntimeError("Origin K02 must retain one native PID 202 Line + Symbol plot")
        if designations != (4, 1):
            raise RuntimeError("Origin K02 worksheet must retain X/Y designations")
        if not x_range.split('"', 1)[0].endswith("!A") or not y_range.split('"', 1)[0].endswith(
            "!B"
        ):
            raise RuntimeError("Origin K02 Line + Symbol lost its source-column binding")
        return {
            "official_template": K02_ORIGIN_PROFILE.filename,
            "official_menu": "Plot > Basic 2D: Line + Symbol",
            "native_plot_type": plot_id,
            "plot_count": plot_count,
            "designation_codes": list(designations),
            "x_range": x_range,
            "y_range": y_range,
        }


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
    plots = reopened.layer.plot_list()
    if len(plots) != 1:
        raise RuntimeError("fresh K02 project has an unexpected native plot count")
    reopened.plot = plots[0]
    reopened.sheet = books[0][0]
    with origin_trace_step("reopened_native_structure_verify"):
        return reopened.verify(request.document, request.actions, request.data)
