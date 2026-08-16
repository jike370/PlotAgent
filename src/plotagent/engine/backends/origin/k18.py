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
        command = f"worksheet -s 1 0 {len(expected.series) + 1} 0; worksheet -p 204 Area;"
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
        document.plot_id.removeprefix("plot:")
        k18_area_series(document, data)
        if isinstance(action, (CreatePlot, BindFields)):
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
        cast(list[dict[str, object]], native_structure["plots"])
        token = document.plot_id.removeprefix("plot:")
        style_snapshot: dict[str, object] = {"native_structure": native_structure}

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
        if plot_count != len(expected.series) or any(item["plot_id"] != 204 for item in plots):
            raise RuntimeError("Origin K18 must retain one native PID 204 plot per series")
        if designation != (4,) + (1,) * len(expected.series):
            raise RuntimeError("Origin K18 worksheet must retain X + N Y designations")
        for index, item in enumerate(plots, start=1):
            x_head = str(item["x_range"]).split('"', 1)[0]
            y_head = str(item["y_range"]).split('"', 1)[0]
            if not x_head.endswith("!A") or not y_head.endswith("!" + self._column_name(index + 1)):
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
    with origin_trace_step("agent_actions_apply", details={"action_count": len(request.actions)}):
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
