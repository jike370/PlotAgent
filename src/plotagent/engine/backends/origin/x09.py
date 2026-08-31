"""X09 native Floating Column binder using Origin's official plot command."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isclose, isnan
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
from plotagent.engine.product_style import (
    X09_FLOATING_COLUMN_STYLE,
    x09_auto_range_bounds,
)
from plotagent.engine.profile_data import FloatingIntervalData, x09_floating_intervals
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .native_visual_t1 import (
    read_x09_group_fill_colors,
    set_x09_group_fill_colors,
)
from .profile import X09_ORIGIN_PROFILE, resolve_official_template
from .readback import axis_scale_matches
from .trace import origin_trace_step, record_origin_trace

_FLOATING_COLUMN = 207
_TITLE_NAME = "_ENGINE_TITLE"


@dataclass(frozen=True, slots=True)
class _AxisEdits:
    label: str | None = None
    scale: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool | None = None


@dataclass(frozen=True, slots=True)
class _State:
    title: str | None = None
    x_axis: _AxisEdits = _AxisEdits()
    y_axis: _AxisEdits = _AxisEdits()
    legend_visible: bool | None = None


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


def _boundary_columns(
    intervals: FloatingIntervalData,
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    columns: list[tuple[str, tuple[float, ...]]] = [
        (intervals.start_field_name, intervals.start_values)
    ]
    if intervals.middle_values is not None:
        columns.append((cast(str, intervals.middle_field_name), intervals.middle_values))
    columns.append((intervals.end_field_name, intervals.end_values))
    return tuple(columns)


class X09OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.book: Any = None
        self.sheet: Any = None
        self.graph: Any = None
        self.layer: Any = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={"template_filename": X09_ORIGIN_PROFILE.filename},
        ):
            template = resolve_official_template(install_dir, X09_ORIGIN_PROFILE)
        intervals = x09_floating_intervals(document, data)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            self.book = self.op.new_book("w", f"D{token}", hidden=True)
            if self.book is None:
                raise RuntimeError("Origin could not create the X09 data workbook")
            for residue in tuple(self.op.pages("w")):
                if residue.name == "Book1" and residue.name != self.book.name:
                    residue.destroy()
            self.sheet = self.book[0]
        boundaries = _boundary_columns(intervals)
        with origin_trace_step(
            "source_data_write",
            details={
                "column_count": len(boundaries) + 1,
                "row_count": len(intervals.categories),
                "boundary_order": [name for name, _values in boundaries],
            },
        ):
            self._write(intervals)
        command = f"worksheet -s 1 0 {len(boundaries) + 1} 0; worksheet -p 207 FloatCol;"
        with origin_trace_step(
            "official_plot_command_execute",
            details={"labtalk": command, "template_filename": template.name},
        ):
            self.sheet.activate()
            self.op.lt_exec(command)
        with origin_trace_step("native_structure_readback"):
            graphs = list(self.op.pages("g"))
            if len(graphs) != 1:
                raise RuntimeError("Origin FLOATCOL must create exactly one graph")
            self.graph = graphs[0]
            self.graph.name = f"G{token}"
            self.graph.lname = f"X09 {template.stem} / {document.plot_id}"
            self._bind_native_objects()
            self._apply_product_defaults(intervals)
            with origin_trace_step(
                "native_legend_rebuild",
                details={"visible_interval_count": max(len(boundaries) - 1, 1)},
            ):
                self._set_legend(intervals, True)
            native = self._assert_native_structure(intervals)
        record_origin_trace("native_floating_column_confirmed", "completed", details=native)

    def open(self, path: Path) -> None:
        with origin_trace_step(
            "saved_project_reopen", details={"filename": path.name, "readonly": False}
        ):
            self.op.new(asksave=False)
            if not self.op.open(str(path), readonly=False, asksave=False):
                raise RuntimeError("Origin could not reopen the X09 project")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("X09 project must contain one graph and one workbook")
        self.graph, self.book = graphs[0], books[0]
        self.sheet = self.book[0]
        self._bind_native_objects()

    def reconcile(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> None:
        intervals = x09_floating_intervals(document, data)
        with origin_trace_step("agent_actions_apply", details={"action_count": len(actions)}):
            for action in actions:
                details = cast(dict[str, object], action.model_dump(exclude_none=True))
                with origin_trace_step("agent_action_apply", details=details):
                    self._apply_action(document, action, intervals)

    def save(self, output: Path) -> None:
        with origin_trace_step("opju_save", details={"filename": output.name}):
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                raise FileExistsError(
                    f"Origin refuses to overwrite existing X09 artifact: {output}"
                )
            self.op.save(str(output))
            if not output.is_file() or output.stat().st_size <= 0:
                raise RuntimeError("Origin did not save a non-empty X09 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        intervals = x09_floating_intervals(document, data)
        state = self._state(document, actions, intervals)
        with origin_trace_step("reopened_native_structure_verify"):
            native = self._assert_native_structure(intervals)
        record_origin_trace("reopened_floating_column_confirmed", "completed", details=native)
        with origin_trace_step(
            "reopened_source_data_verify",
            details={
                "column_count": len(_boundary_columns(intervals)) + 1,
                "row_count": len(intervals.categories),
            },
        ):
            self._assert_source_data(intervals)
        with origin_trace_step("reopened_agent_edits_verify"):
            self._assert_agent_edits(state, intervals)

        token = document.plot_id.removeprefix("plot:")
        objects: list[EngineObjectRef] = [
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
                object_kind="native_floating_column_group",
                native_ref=f"graph:{self.graph.name}.layer:1.group:1",
            ),
        ]
        objects.append(
            EngineObjectRef(
                semantic_id=f"legend:{token}.main",
                backend="origin",
                object_kind="legend",
                native_ref=f"graph:{self.graph.name}.layer:1.label:legend",
            )
        )
        return EngineReadback(
            document=document_ref(document),
            backend="origin",
            objects=tuple(objects),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(
                cast(
                    JsonValue,
                    {
                        "native_plot_id": _FLOATING_COLUMN,
                        "state": asdict(state),
                        "template": X09_ORIGIN_PROFILE.filename,
                    },
                )
            ),
        )

    def _bind_native_objects(self) -> None:
        layers = tuple(self.graph)
        if len(layers) != 1:
            raise RuntimeError("Origin FLOATCOL must remain a single-layer graph")
        self.layer = layers[0]

    def _write(self, intervals: FloatingIntervalData) -> None:
        boundaries = _boundary_columns(intervals)
        self.sheet.cols = len(boundaries) + 1
        self.sheet.from_list(
            0,
            list(intervals.categories),
            lname=intervals.category_field_name,
            axis="X",
        )
        for index, (name, values) in enumerate(boundaries, start=1):
            self.sheet.from_list(index, list(values), lname=name, axis="Y")

    def _apply_action(
        self, document: PlotDocument, action: PlotEngineAction, intervals: FloatingIntervalData
    ) -> None:
        document.plot_id.removeprefix("plot:")
        if isinstance(action, (CreatePlot, BindFields)):
            return
        raise ValueError(f"Origin X09 binder cannot apply {action.operation}")

    def _state(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        intervals: FloatingIntervalData,
    ) -> _State:
        document.plot_id.removeprefix("plot:")
        state = _State()
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            raise ValueError(f"Origin X09 binder cannot apply {action.operation}")
        return state

    def _set_legend(self, intervals: FloatingIntervalData, visible: bool) -> None:
        legend = self.layer.label("legend")
        if legend is None and visible:
            self.layer.activate()
            if not self.layer.obj.LT_execute("legend"):
                raise RuntimeError("Origin could not create the X09 legend")
            legend = self.layer.label("legend")
        if legend is not None:
            labels = (
                (intervals.end_field_name,)
                if intervals.middle_values is None
                else (cast(str, intervals.middle_field_name), intervals.end_field_name)
            )
            legend.text = "\n".join(
                f"\\l({index + 2}) {_safe_legend_label(label)}"
                for index, label in enumerate(labels)
            )
            legend.set_int("link", 1)
            legend.set_int("show", int(visible))

    def _apply_product_defaults(self, intervals: FloatingIntervalData) -> None:
        style = X09_FLOATING_COLUMN_STYLE
        colors = tuple(
            int(self.op.lt_float(f'color("{value}")')) for value in style.interval_colors
        )
        group_colors = (
            (colors[0], colors[0])
            if intervals.middle_values is None
            else (colors[0], colors[1], colors[1])
        )
        set_x09_group_fill_colors(self.op, str(self.graph.name), 1, group_colors)
        y_label = self.layer.label("yl")
        if y_label is None:
            raise RuntimeError("Origin X09 is missing its Y-axis title object")
        y_label.text = f"{intervals.start_field_name}–{intervals.end_field_name}"
        y_label.set_int("show", 1)
        boundaries = tuple(values for _name, values in _boundary_columns(intervals))
        minimum, maximum = x09_auto_range_bounds(boundaries)
        self.layer.axis("y").limits = (minimum, maximum)
        self.op.lt_exec(
            f"range __X09PRODUCT=[{self.graph.name}]Layer1!1; "
            f"set __X09PRODUCT -vg {(1 - style.bar_width_fraction) * 100:.12g};"
        )

    def _assert_native_structure(self, intervals: FloatingIntervalData) -> dict[str, object]:
        boundaries = _boundary_columns(intervals)
        expected_y_letters = [chr(ord("B") + index) for index in range(len(boundaries))]
        expected_plot_count = len(boundaries)
        commands = [
            f"window -a {self.graph.name}",
            f"{self.graph.name}!page.active=1",
            "layer -c",
            "__X09COUNT=count",
            "__X09EXCHANGE=layer.exchangexy",
        ]
        for plot_index in range(1, expected_plot_count + 1):
            commands.extend(
                (
                    f"range __X09P{plot_index}=[{self.graph.name}]Layer1!{plot_index}",
                    f"get __X09P{plot_index} -pt __X09PT{plot_index}",
                    f"range -wx __X09X{plot_index}={plot_index}",
                    f"range -wy __X09Y{plot_index}={plot_index}",
                    f"string __X09XS{plot_index}$=%(__X09X{plot_index})",
                    f"string __X09YS{plot_index}$=%(__X09Y{plot_index})",
                )
            )
        self.op.lt_exec("; ".join(commands) + ";")
        plot_count = float(self.op.lt_float("__X09COUNT"))
        exchange_xy = float(self.op.lt_float("__X09EXCHANGE"))
        if not isclose(plot_count, float(expected_plot_count)) or not isclose(exchange_xy, 0.0):
            raise RuntimeError(
                "Origin X09 FLOATCOL structure changed: "
                f"plots={plot_count}, exchange_xy={exchange_xy}"
            )
        x_ranges: list[str] = []
        y_ranges: list[str] = []
        plot_ids: list[int] = []
        for plot_index, expected_y_letter in enumerate(expected_y_letters, start=1):
            plot_id = float(self.op.lt_float(f"__X09PT{plot_index}"))
            x_range = str(self.op.get_lt_str(f"__X09XS{plot_index}"))
            y_range = str(self.op.get_lt_str(f"__X09YS{plot_index}"))
            if isnan(plot_id) or int(plot_id) != _FLOATING_COLUMN:
                raise RuntimeError(
                    f"Origin X09 plot {plot_index} is not native type {_FLOATING_COLUMN}"
                )
            source_prefix = f"[{self.book.name}]"
            if not x_range.startswith(source_prefix) or '!A"' not in x_range:
                raise RuntimeError(
                    f"Origin X09 plot {plot_index} lost category source A: {x_range!r}"
                )
            if not y_range.startswith(source_prefix) or f'!{expected_y_letter}"' not in y_range:
                raise RuntimeError(
                    "Origin X09 adjacent boundary binding changed: "
                    f"plot={plot_index}, expected={expected_y_letter}, actual={y_range!r}"
                )
            plot_ids.append(int(plot_id))
            x_ranges.append(x_range)
            y_ranges.append(y_range)
        expected_designations = [4, *([1] * len(boundaries))]
        actual_designations = [
            self.sheet.get_int(f"col{index + 1}.type")
            for index in range(len(expected_designations))
        ]
        if actual_designations != expected_designations:
            raise RuntimeError(
                "Origin X09 worksheet designation changed: "
                f"expected={expected_designations}, actual={actual_designations}"
            )
        expected_legend_labels = (
            (intervals.end_field_name,)
            if intervals.middle_values is None
            else (cast(str, intervals.middle_field_name), intervals.end_field_name)
        )
        legend = self.layer.label("legend")
        legend_text = "" if legend is None else str(legend.text)
        if (
            legend is None
            or not bool(legend.get_int("show"))
            or legend_text.count(r"\l(") != len(expected_legend_labels)
            or any(_safe_legend_label(label) not in legend_text for label in expected_legend_labels)
        ):
            raise RuntimeError(
                "Origin X09 linked legend does not match the visible intervals: "
                f"expected={expected_legend_labels!r}, actual={legend_text!r}"
            )
        self._assert_product_defaults(intervals)
        return {
            "native_plot_ids": plot_ids,
            "exchange_xy": False,
            "orientation": "vertical_floating_column",
            "x_ranges": x_ranges,
            "y_ranges": y_ranges,
            "boundary_order": [name for name, _values in boundaries],
            "worksheet_designations": actual_designations,
            "linked_legend_entry_count": len(expected_legend_labels),
            "linked_legend_labels": list(expected_legend_labels),
        }

    def _assert_product_defaults(self, intervals: FloatingIntervalData) -> None:
        style = X09_FLOATING_COLUMN_STYLE
        colors = tuple(
            int(self.op.lt_float(f'color("{value}")')) for value in style.interval_colors
        )
        expected_colors = (
            (colors[0], colors[0])
            if intervals.middle_values is None
            else (colors[0], colors[1], colors[1])
        )
        actual_colors = read_x09_group_fill_colors(self.op, str(self.graph.name), 1)
        if actual_colors != expected_colors:
            raise RuntimeError("Origin X09 product interval colors changed after reopen")
        y_label = self.layer.label("yl")
        expected_label = f"{intervals.start_field_name}–{intervals.end_field_name}"
        if y_label is None or y_label.text != expected_label or not y_label.get_int("show"):
            raise RuntimeError("Origin X09 product Y-axis title changed after reopen")
        boundaries = tuple(values for _name, values in _boundary_columns(intervals))
        expected_limits = x09_auto_range_bounds(boundaries)
        actual_limits = tuple(float(value) for value in self.layer.axis("y").limits[:2])
        if any(
            not isclose(actual, expected, abs_tol=1e-8)
            for actual, expected in zip(actual_limits, expected_limits, strict=True)
        ):
            raise RuntimeError("Origin X09 product Y-axis range changed after reopen")

    def _assert_source_data(self, intervals: FloatingIntervalData) -> None:
        boundaries = _boundary_columns(intervals)
        if int(self.sheet.shape[1]) != len(boundaries) + 1:
            raise RuntimeError("Origin X09 worksheet gained derived bottom/height columns")
        actual_categories = tuple(str(value) for value in self.sheet.to_list(0))
        if actual_categories != intervals.categories:
            raise RuntimeError("Origin X09 category order or values changed after reopen")
        for index, (name, expected) in enumerate(boundaries, start=1):
            self._assert_numeric_values(self.sheet.to_list(index), expected, name)

    def _assert_agent_edits(self, state: _State, intervals: FloatingIntervalData) -> None:
        if state.title is not None:
            title = self.layer.label(_TITLE_NAME)
            if (
                title is None
                or title.text != state.title
                or bool(title.get_int("show")) != bool(state.title)
            ):
                raise RuntimeError("Origin X09 title changed after reopen")
        for axis_name, label_name, edits in (
            ("x", "xb", state.x_axis),
            ("y", "yl", state.y_axis),
        ):
            if edits == _AxisEdits():
                continue
            axis = self.layer.axis(axis_name)
            if (
                edits.scale is not None
                and axis_name == "y"
                and not axis_scale_matches(axis.scale, edits.scale)
            ):
                raise RuntimeError(f"Origin X09 {axis_name} scale changed after reopen")
            if edits.label is not None:
                label = self.layer.label(label_name)
                if label is None or label.text != edits.label or not label.get_int("show"):
                    raise RuntimeError(f"Origin X09 {axis_name} label changed after reopen")
            if edits.minimum is not None and edits.maximum is not None:
                expected = (
                    (edits.maximum, edits.minimum)
                    if edits.reverse
                    else (edits.minimum, edits.maximum)
                )
                actual = tuple(float(value) for value in axis.limits[:2])
                if any(
                    not isclose(left, right, abs_tol=1e-8)
                    for left, right in zip(actual, expected, strict=True)
                ):
                    raise RuntimeError(f"Origin X09 {axis_name} bounds changed after reopen")
            elif edits.reverse is not None:
                begin, end = (float(value) for value in axis.limits[:2])
                if (begin > end) != edits.reverse:
                    raise RuntimeError(f"Origin X09 {axis_name} direction changed after reopen")
        if state.legend_visible is not None:
            legend = self.layer.label("legend")
            if legend is None or bool(legend.get_int("show")) != state.legend_visible:
                raise RuntimeError("Origin X09 legend visibility changed after reopen")
            if state.legend_visible:
                labels = (
                    (intervals.end_field_name,)
                    if intervals.middle_values is None
                    else (cast(str, intervals.middle_field_name), intervals.end_field_name)
                )
                text = str(legend.text)
                if text.count(r"\l(") != len(labels) or any(
                    _safe_legend_label(label) not in text for label in labels
                ):
                    raise RuntimeError("Origin X09 legend content changed after reopen")

    @staticmethod
    def _assert_numeric_values(
        actual: list[object], expected: tuple[float, ...], role: str
    ) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin X09 {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            observed_number = float(cast(Any, observed))
            if (isnan(observed_number) and isnan(wanted)) or isclose(
                observed_number, wanted, abs_tol=1e-9
            ):
                continue
            raise RuntimeError(f"Origin X09 {role} values differ after reopen")


def execute_x09_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    structure_output = output.with_name(f"{output.stem}.official-structure.opju")
    project = X09OriginProject(op)
    project.create(install_dir, request.document, request.data)
    project.save(structure_output)

    editable = X09OriginProject(op)
    editable.open(structure_output)
    editable.reconcile(request.document, request.actions, request.data)
    editable.save(output)

    reopened = X09OriginProject(op)
    reopened.open(output)
    readback = reopened.verify(request.document, request.actions, request.data)
    structure_output.unlink(missing_ok=True)
    return readback
