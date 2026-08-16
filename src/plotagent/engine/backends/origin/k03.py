"""K03 grouped scatter bound directly to Origin's official SCATTER template."""

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
from plotagent.engine.profile_data import K03ScatterData, k03_scatter
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K03_ORIGIN_PROFILE, resolve_official_template
from .trace import origin_trace_step, record_origin_trace

_SYMBOL_CODES = {"square": 1, "circle": 2, "triangle": 3, "triangle_up": 3, "diamond": 5}
_TITLE_NAME = "_ENGINE_TITLE"


def _effective_actions(
    actions: tuple[PlotEngineAction, ...],
) -> tuple[PlotEngineAction, ...]:
    return actions


class K03OriginProject:
    """One worksheet pair and one native scatter plot per materialized group."""

    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.sheet: Any = None
        self.plots: list[Any] = []

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={"template_filename": K03_ORIGIN_PROFILE.filename},
        ):
            template = resolve_official_template(install_dir, K03_ORIGIN_PROFILE)
        scatter = k03_scatter(document, data)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the K03 workbook")
        self.sheet = book[0]
        with origin_trace_step(
            "source_data_write",
            details={
                "designation": "XY repeated",
                "group_count": len(scatter.groups),
            },
        ):
            self._write_data(scatter)
        command = f"worksheet -s 1 0 {len(scatter.groups) * 2} 0; worksheet -p 201 Scatter;"
        with origin_trace_step(
            "official_plot_command_execute",
            details={
                "labtalk": command,
                "native_plot_type": 201,
                "template_filename": template.name,
                "group_count": len(scatter.groups),
            },
        ):
            self.sheet.activate()
            if not self.op.lt_exec(command):
                raise RuntimeError("Origin could not execute the official K03 Scatter menu")
        graphs = list(self.op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError("Origin Scatter menu must create exactly one graph")
        self.graph = graphs[0]
        self.graph.name = f"G{token}"
        self.graph.lname = f"K03 2D Scatter / {document.plot_id}"
        self.layer = self.graph[0]
        self.plots = list(self.layer.plot_list())
        if len(self.plots) != len(scatter.groups):
            raise RuntimeError("Origin Scatter menu did not create one plot per data group")
        with origin_trace_step("template_residue_remove"):
            for residue in tuple(self.op.pages("w")):
                if residue.name != book.name:
                    residue.destroy()
        self._set_legend(scatter, visible=len(scatter.groups) > 1)
        self.layer.rescale()
        native = self._assert_native_structure(scatter)
        record_origin_trace("native_scatter_groups_confirmed", "completed", details=native)

    def reopen(self, project_path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=True, asksave=False):
            raise RuntimeError("fresh Origin session could not reopen the staged K03 project")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("fresh K03 project has unexpected graph or workbook count")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        self.plots = list(self.layer.plot_list())
        self.sheet = books[0][0]

    def apply(self, document: PlotDocument, action: PlotEngineAction, data: EngineDataView) -> None:
        k03_scatter(document, data)
        document.plot_id.removeprefix("plot:")
        if isinstance(action, (CreatePlot, BindFields)):
            return
        raise ValueError(f"Origin K03 binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output_path))
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError("Origin did not save a non-empty K03 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        scatter = k03_scatter(document, data)
        native = self._assert_native_structure(scatter)
        record_origin_trace("reopened_scatter_groups_confirmed", "completed", details=native)
        visible = len(scatter.groups) > 1
        self._assert_linked_legend(scatter, visible=visible)
        if len(self.plots) != len(scatter.groups):
            raise RuntimeError("Origin K03 native plot count differs after reopen")
        for index, group in enumerate(scatter.groups):
            self._assert_values(self.sheet.to_list(index * 2), group.x_values, "x")
            self._assert_values(self.sheet.to_list(index * 2 + 1), group.y_values, "y")
        token = document.plot_id.removeprefix("plot:")
        snapshot: dict[str, object] = {
            "group_count": len(scatter.groups),
            "native_structure": native,
        }
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
                    object_kind="scatter_series",
                    native_ref=f"graph:{self.graph.name}.layer:1.plot:{index}",
                )
                for index in range(1, len(self.plots) + 1)
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
            style_hash=canonical_hash(cast(JsonValue, snapshot)),
        )

    def _write_data(self, scatter: K03ScatterData) -> None:
        for index, group in enumerate(scatter.groups):
            self.sheet.from_list(
                index * 2,
                list(group.x_values),
                lname=scatter.x_field_name,
                axis="X",
            )
            self.sheet.from_list(
                index * 2 + 1,
                list(group.y_values),
                lname=group.label,
                axis="Y",
            )

    def _set_legend(self, scatter: K03ScatterData, *, visible: bool) -> None:
        self.graph.activate()
        command = (
            "page.active=1; legendupdate dest:=layer update:=reconstruct "
            "legend:=separate mode:=lname;"
        )
        if not self.op.lt_exec(command):
            raise RuntimeError("Origin could not reconstruct the linked K03 legend")
        legend = self.layer.label("legend")
        if legend is None:
            if visible:
                raise RuntimeError("Origin K03 did not create its linked legend")
            return
        legend.text = "\n".join(
            f"\\l({index}) %({index})" for index in range(1, len(scatter.groups) + 1)
        )
        legend.set_int("link", 1)
        legend.set_int("show", int(visible))

    def _assert_linked_legend(self, scatter: K03ScatterData, *, visible: bool) -> None:
        legend = self.layer.label("legend")
        if legend is None:
            if visible:
                raise RuntimeError("Origin K03 lost its linked legend")
            return
        if bool(legend.get_int("show")) != visible:
            raise RuntimeError("Origin K03 legend visibility differs after reopen")
        expected = tuple(f"\\l({index}) %({index})" for index in range(1, len(scatter.groups) + 1))
        actual = tuple(line.strip() for line in str(legend.text).splitlines() if line.strip())
        if actual != expected or int(legend.get_int("link")) != 1:
            raise RuntimeError("Origin K03 legend lost a linked group entry")

    def _assert_native_structure(self, scatter: K03ScatterData) -> dict[str, object]:
        self.graph.activate()
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe K03 graph name for native readback: {graph_name!r}")
        if not self.op.lt_exec("page.active=1; layer -c; __K03COUNT=count;"):
            raise RuntimeError("Origin could not read the native K03 Scatter structure")
        plot_count = int(self.op.lt_float("__K03COUNT"))
        if plot_count != len(scatter.groups):
            raise RuntimeError("Origin K03 native plot count differs from data groups")
        plots: list[dict[str, object]] = []
        for index in range(1, plot_count + 1):
            command = (
                f"range __K03P=[{graph_name}]1!{index}; "
                "range -wx __K03X=__K03P; range -wy __K03Y=__K03P; "
                "get __K03P -pt __K03PID; "
                "string __K03XS$=%(__K03X); string __K03YS$=%(__K03Y);"
            )
            if not self.op.lt_exec(command):
                raise RuntimeError(f"Origin could not read K03 scatter group {index}")
            plot_id = int(self.op.lt_float("__K03PID"))
            x_range = str(self.op.get_lt_str("__K03XS"))
            y_range = str(self.op.get_lt_str("__K03YS"))
            x_letter = self._column_name(index * 2 - 1)
            y_letter = self._column_name(index * 2)
            if plot_id != 201:
                raise RuntimeError("Origin K03 must retain only native PID 201 Scatter plots")
            if not x_range.split('"', 1)[0].endswith(f"!{x_letter}") or not y_range.split('"', 1)[
                0
            ].endswith(f"!{y_letter}"):
                raise RuntimeError("Origin K03 Scatter lost a group/source binding")
            plots.append(
                {
                    "plot_index": index,
                    "plot_id": plot_id,
                    "x_range": x_range,
                    "y_range": y_range,
                }
            )
        designations = tuple(
            int(self.sheet.get_int(f"col{index}.type")) for index in range(1, plot_count * 2 + 1)
        )
        if designations != (4, 1) * plot_count:
            raise RuntimeError("Origin K03 worksheet must retain one X/Y pair per group")
        return {
            "official_template": K03_ORIGIN_PROFILE.filename,
            "official_menu": "Plot > Basic 2D: Scatter",
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
    def _assert_values(actual: list[object], expected: tuple[float, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin K03 {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if observed is None and wanted != wanted:
                continue
            if abs(float(cast(Any, observed)) - wanted) > 1e-12:
                raise RuntimeError(f"Origin K03 {role} values differ after reopen")


def execute_k03_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    """Recreate from the official template so changed group counts remain native."""

    project = K03OriginProject(op)
    project.create(install_dir, request.document, request.data)
    actions = _effective_actions(request.actions)
    with origin_trace_step("agent_actions_apply", details={"action_count": len(actions)}):
        for action in actions:
            project.apply(request.document, action, request.data)
    project.save(output)

    reopened = K03OriginProject(op)
    reopened.reopen(output)
    with origin_trace_step("reopened_native_structure_verify"):
        return reopened.verify(request.document, actions, request.data)
