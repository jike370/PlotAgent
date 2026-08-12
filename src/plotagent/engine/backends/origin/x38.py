"""X38 official OffsetStackY binder that keeps worksheet Y values raw."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import isclose, isfinite, isnan
from pathlib import Path
from typing import Any, cast

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
from plotagent.engine.profile_data import OffsetStackData, x38_offset_stack
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import X38_ORIGIN_PROFILE, resolve_official_template
from .trace import origin_trace_step, record_origin_trace

_TITLE_NAME = "_ENGINE_TITLE"
_OFFICIAL_HELP_URL = "https://docs.originlab.com/origin-help/stacklineyoffset-graph"
_OFFICIAL_MENU = "Plot > Basic 2D > Stacked Lines by Y Offsets"
_OFFICIAL_SECTION = "OffsetYs"


@dataclass(frozen=True, slots=True)
class _State:
    title: str
    x_label: str
    y_label: str
    x_scale: str = "linear"
    y_scale: str = "linear"
    x_reverse: bool = False
    y_reverse: bool = False
    legend_visible: bool = True
    title_explicit: bool = False
    x_axis_explicit: bool = False
    y_axis_explicit: bool = False
    legend_explicit: bool = False


class X38OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.book: Any = None
        self.sheet: Any = None
        self.plots: list[Any] = []

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={"template_filename": X38_ORIGIN_PROFILE.filename},
        ):
            template = resolve_official_template(install_dir, X38_ORIGIN_PROFILE)
        offset = x38_offset_stack(document, data)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            self.book = self.op.new_book("w", f"D{token}", hidden=True)
            if self.book is None:
                raise RuntimeError("Origin could not create the X38 workbook")
            for residue in tuple(self.op.pages("w")):
                if residue.name == "Book1" and residue.name != self.book.name:
                    residue.destroy()
            self.sheet = self.book[0]
        with origin_trace_step(
            "source_data_write",
            details={
                "column_count": len(offset.series) + 1,
                "row_count": len(offset.series[0].x_values),
            },
        ):
            self._write(offset)
        with origin_trace_step(
            "official_plot_section_execute",
            details={
                "official_help_url": _OFFICIAL_HELP_URL,
                "official_menu": _OFFICIAL_MENU,
                "plot_section": _OFFICIAL_SECTION,
                "template_filename": template.name,
            },
        ):
            self.sheet.activate()
            self.op.lt_exec(
                f"worksheet -s 1 0 {len(offset.series) + 1} 0; "
                "run.section(plot,OffsetYs);"
            )
        with origin_trace_step("native_structure_readback"):
            graphs = list(self.op.pages("g"))
            if len(graphs) != 1:
                raise RuntimeError("Origin OffsetYs must create exactly one graph")
            self.graph = graphs[0]
            self.graph.name = f"G{token}"
            self.graph.lname = f"X38 {template.stem} / {document.plot_id}"
            layers = tuple(self.graph)
            if len(layers) != 1:
                raise RuntimeError("Origin OffsetStackY must remain a single-layer graph")
            self.layer = layers[0]
            self.plots = list(self.layer.plot_list())
            self._assert_native_structure(offset, verify_offsets=False)
        record_origin_trace(
            "native_structure_confirmed",
            "completed",
            details={
                "layer_count": 1,
                "native_plot_ids": [200] * len(offset.series),
                "plot_offsets": "verified_after_reopen",
                "worksheet_y_values": "raw",
            },
        )

    def open(self, path: Path) -> None:
        with origin_trace_step("saved_project_reopen", details={"readonly": False}):
            self.op.new(asksave=False)
            if not self.op.open(str(path), readonly=False, asksave=False):
                raise RuntimeError("Origin could not reopen the X38 project")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("X38 project must contain one graph and workbook")
        self.graph, self.book = graphs[0], books[0]
        layers = tuple(self.graph)
        if len(layers) != 1:
            raise RuntimeError("X38 project lost its official single layer")
        self.layer = layers[0]
        self.plots = list(self.layer.plot_list())
        self.sheet = self.book[0]

    def reconcile(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> None:
        offset = x38_offset_stack(document, data)
        state = self._state(document, actions, offset)
        with origin_trace_step(
            "agent_actions_apply", details={"action_count": len(actions)}
        ):
            if state.title_explicit:
                self._set_title(state.title)
            if state.x_axis_explicit:
                self._apply_axis("x", "xb", state.x_label, state.x_scale, state.x_reverse)
            if state.y_axis_explicit:
                self._apply_axis("y", "yl", state.y_label, state.y_scale, state.y_reverse)
            if state.legend_explicit:
                self._set_legend(offset, state.legend_visible)

    def save(self, output: Path) -> None:
        with origin_trace_step("opju_save", details={"filename": output.name}):
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                raise FileExistsError(
                    f"Origin refuses to overwrite existing X38 artifact: {output}"
                )
            self.op.save(str(output))
            if not output.is_file() or output.stat().st_size <= 0:
                raise RuntimeError("Origin did not save a non-empty X38 project")

    def verify(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> EngineReadback:
        offset = x38_offset_stack(document, data)
        state = self._state(document, actions, offset)
        with origin_trace_step("reopened_native_structure_verify"):
            native_offsets = self._assert_native_structure(offset, verify_offsets=True)
        record_origin_trace(
            "reopened_native_offsets_confirmed",
            "completed",
            details={"plot_offsets": native_offsets},
        )
        expected = (offset.series[0].x_values, *(series.y_values for series in offset.series))
        with origin_trace_step(
            "reopened_source_data_verify",
            details={
                "column_count": len(expected),
                "row_count": len(offset.series[0].x_values),
                "worksheet_y_values": "raw",
            },
        ):
            for index, values in enumerate(expected):
                self._assert_values(self.sheet.to_list(index), values, f"column {index + 1}")
        with origin_trace_step("reopened_agent_edits_verify"):
            self._assert_agent_edits(state, offset)
        token = document.plot_id.removeprefix("plot:")
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
                    object_kind="offset_line_series",
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
            style_hash=canonical_hash(
                cast(
                    JsonValue,
                    {
                        "native_plot_ids": [200] * len(offset.series),
                        "state": asdict(state),
                        "template": X38_ORIGIN_PROFILE.filename,
                    },
                )
            ),
        )

    def _state(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: OffsetStackData
    ) -> _State:
        token = document.plot_id.removeprefix("plot:")
        state = _State(
            title="",
            x_label=data.x_field_name,
            y_label=data.y_field_name,
        )
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("X38 title target does not belong to this plot")
                state = replace(state, title=action.text, title_explicit=True)
            elif isinstance(action, SetAxis):
                if action.minimum is not None or action.maximum is not None:
                    raise ValueError("X38 official offset template keeps automatic bounds")
                if action.target == f"axis:{token}.x":
                    if action.scale not in {None, "linear", "log10"}:
                        raise ValueError("X38 X axis supports linear or log10")
                    state = replace(
                        state,
                        x_label=state.x_label if action.label is None else action.label,
                        x_scale=state.x_scale if action.scale is None else action.scale,
                        x_reverse=state.x_reverse if action.reverse is None else action.reverse,
                        x_axis_explicit=True,
                    )
                elif action.target == f"axis:{token}.y":
                    if action.scale not in {None, "linear", "log10"}:
                        raise ValueError("X38 Y axis supports linear or log10")
                    state = replace(
                        state,
                        y_label=state.y_label if action.label is None else action.label,
                        y_scale=state.y_scale if action.scale is None else action.scale,
                        y_reverse=state.y_reverse if action.reverse is None else action.reverse,
                        y_axis_explicit=True,
                    )
                else:
                    raise ValueError("X38 axis target does not belong to this plot")
            elif isinstance(action, SetSeriesStyle):
                raise ValueError(
                    "X38 keeps the official dependent style group and does not expose "
                    "per-series style edits"
                )
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main" or action.anchor is not None:
                    raise ValueError("X38 exposes only legend visibility")
                state = replace(
                    state,
                    legend_visible=state.legend_visible
                    if action.visible is None
                    else action.visible,
                    legend_explicit=True,
                )
            else:
                raise ValueError(f"Origin X38 binder cannot apply {action.operation}")
        return state

    def _write(self, data: OffsetStackData) -> None:
        self.sheet.cols = len(data.series) + 1
        self.sheet.from_list(0, list(data.series[0].x_values), lname=data.x_field_name, axis="X")
        for index, series in enumerate(data.series, start=1):
            self.sheet.from_list(index, list(series.y_values), lname=series.label, axis="Y")

    def _set_title(self, text: str) -> None:
        title = self.layer.label(_TITLE_NAME)
        if title is None and text:
            self.layer.activate()
            if not self.layer.obj.LT_execute(
                f"label -j 1 -n {_TITLE_NAME} PlotAgentTitlePlaceholder;"
            ):
                raise RuntimeError("Origin could not create the X38 title")
            title = self.layer.label(_TITLE_NAME)
            if title is None:
                raise RuntimeError("Origin could not create the X38 title")
        if title is not None:
            title.text = text
            title.set_int("attach", 1)
            title.set_float("x1", 0.5)
            title.set_float("y1", 0.012)
            title.set_int("fsize", 14)
            title.set_int("background", 0)
            title.set_int("show", int(bool(text)))

    def _axis_label(self, name: str, text: str) -> None:
        label = self.layer.label(name) or self.layer.add_label(text)
        if label is None:
            raise RuntimeError("Origin X38 has no writable axis label")
        label.text = text
        label.set_int("show", 1)

    def _apply_axis(
        self, axis_name: str, label_name: str, label: str, scale: str, reverse: bool
    ) -> None:
        self._axis_label(label_name, label)
        axis = self.layer.axis(axis_name)
        axis.scale = scale
        begin, end, step = (float(value) for value in axis.limits)
        if (begin > end) != reverse:
            axis.set_limits(end, begin, abs(step))

    def _set_legend(self, data: OffsetStackData, visible: bool) -> None:
        legend = self.layer.label("legend")
        if legend is None:
            self.layer.activate()
            self.layer.obj.LT_execute("legend")
            legend = self.layer.label("legend")
        if legend is None:
            raise RuntimeError("Origin X38 has no writable legend")
        legend.text = "\n".join(
            f"\\l({index}, style:l) {series.label}"
            for index, series in enumerate(data.series, start=1)
        )
        legend.set_int("link", 1)
        legend.set_int("attach", 1)
        legend.set_float("x1", 0.72)
        legend.set_float("y1", 0.065)
        legend.set_int("fsize", 10)
        legend.set_int("background", 0)
        legend.set_int("show", int(visible))

    def _plot_prefix(self, index: int) -> str:
        variable = f"__X38P{index}"
        return (
            f"window -a {self.graph.name}; {self.graph.name}!page.active=1; "
            f"range {variable}=[{self.graph.name}]Layer1!{index}; "
        )

    def _assert_native_structure(
        self, data: OffsetStackData, *, verify_offsets: bool
    ) -> list[list[float]]:
        if len(self.plots) != len(data.series):
            raise RuntimeError("Origin X38 native series count differs after reopen")
        observed_ids: list[int] = []
        offsets: list[list[float]] = []
        for index, plot in enumerate(self.plots, start=1):
            prefix = f"__X38P{index}"
            command = self._plot_prefix(index) + f"get {prefix} -pt {prefix}PT;"
            if verify_offsets:
                command += f" get {prefix} -sy {prefix}SY; get {prefix} -sys {prefix}SYS;"
            self.op.lt_exec(command)
            plot_id = float(self.op.lt_float(f"{prefix}PT"))
            if isnan(plot_id):
                raise RuntimeError(f"Origin X38 plot {index} type is unreadable")
            observed_ids.append(int(plot_id))
            expected_dataset = f"_{chr(65 + index)}"
            if not str(plot.obj.DatasetName).endswith(expected_dataset):
                raise RuntimeError(
                    f"Origin X38 plot {index} is not bound to source column "
                    f"{chr(65 + index)}"
                )
            if verify_offsets:
                offset = float(self.op.lt_float(f"{prefix}SY"))
                multiplier = float(self.op.lt_float(f"{prefix}SYS"))
                if not isfinite(offset) or not isclose(multiplier, 1.0, abs_tol=1e-8):
                    raise RuntimeError(
                        f"Origin X38 plot {index} has invalid native offset/scale: "
                        f"{offset}, {multiplier}"
                    )
                offsets.append([offset, multiplier])
        if observed_ids != [200] * len(data.series):
            raise RuntimeError(
                f"Origin X38 native line IDs {observed_ids} differ from "
                f"{[200] * len(data.series)}"
            )
        if verify_offsets:
            native_y = [item[0] for item in offsets]
            if not isclose(native_y[0], 0.0, abs_tol=1e-8):
                raise RuntimeError("Origin X38 first native line must retain zero Y offset")
            deltas = [
                right - left
                for left, right in zip(native_y[:-1], native_y[1:], strict=True)
            ]
            if not deltas or any(isclose(delta, 0.0, abs_tol=1e-8) for delta in deltas):
                raise RuntimeError(
                    f"Origin X38 native Individual offsets are not distinct: {native_y}"
                )
            direction = 1.0 if deltas[0] > 0 else -1.0
            if any(delta * direction <= 0.0 for delta in deltas):
                raise RuntimeError(
                    f"Origin X38 native Individual offsets are not monotonic: {native_y}"
                )
        return offsets

    def _assert_agent_edits(self, state: _State, data: OffsetStackData) -> None:
        labels: list[tuple[str, str]] = []
        if state.x_axis_explicit:
            labels.append(("xb", state.x_label))
        if state.y_axis_explicit:
            labels.append(("yl", state.y_label))
        for name, expected in labels:
            label = self.layer.label(name)
            if label is None or label.text != expected or label.get_int("show") == 0:
                raise RuntimeError(f"Origin X38 axis label {name} changed after reopen")
        title = self.layer.label(_TITLE_NAME)
        if state.title_explicit and state.title and (
            title is None
            or title.text != state.title
            or title.get_int("show") == 0
            or title.get_int("attach") != 1
            or title.get_int("fsize") != 14
            or not isclose(title.get_float("x1"), 0.5, abs_tol=1e-8)
            or not isclose(title.get_float("y1"), 0.012, abs_tol=1e-8)
        ):
            raise RuntimeError("Origin X38 title changed after reopen")
        if not state.legend_explicit:
            return
        legend = self.layer.label("legend")
        if state.legend_visible:
            if (
                legend is None
                or legend.get_int("show") == 0
                or str(legend.text).count(r"\l(") != len(data.series)
                or legend.get_int("attach") != 1
                or legend.get_int("fsize") != 10
                or not isclose(legend.get_float("x1"), 0.72, abs_tol=1e-8)
                or not isclose(legend.get_float("y1"), 0.065, abs_tol=1e-8)
            ):
                raise RuntimeError("Origin X38 native legend changed after reopen")
        elif legend is not None and legend.get_int("show") != 0:
            raise RuntimeError("Origin X38 hidden legend reappeared")

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[object, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin X38 {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
                if abs(float(cast(Any, observed)) - float(wanted)) <= 1e-9:
                    continue
            elif observed == wanted:
                continue
            raise RuntimeError(f"Origin X38 {role} values differ after reopen")


def execute_x38_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    structure_output = output.with_name(f"{output.stem}.official-structure.opju")
    project = X38OriginProject(op)
    project.create(install_dir, request.document, request.data)
    project.save(structure_output)

    editable = X38OriginProject(op)
    editable.open(structure_output)
    editable.reconcile(request.document, request.actions, request.data)
    editable.save(output)
    reopened = X38OriginProject(op)
    reopened.open(output)
    readback = reopened.verify(request.document, request.actions, request.data)
    structure_output.unlink(missing_ok=True)
    return readback
