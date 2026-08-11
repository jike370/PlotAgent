"""X24 binder for Origin's official binned-data Pareto workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
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
    SetAxis,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import (
    ParetoData,
    ParetoSourceData,
    x24_pareto,
    x24_pareto_source,
)
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import X24_ORIGIN_PROFILE, resolve_official_template
from .trace import origin_trace_step, record_origin_trace

_TITLE = "_ENGINE_TITLE"
_STYLE = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}


@dataclass(frozen=True, slots=True)
class _State:
    title: str = ""
    x_label: str = ""
    left_label: str = ""
    right_label: str = "Cumulative (%)"
    bar_color: str | None = None
    bar_line_width_pt: float | None = None
    bar_line_style: str | None = None
    line_color: str | None = None
    line_width_pt: float | None = None
    line_style: str | None = None
    legend_visible: bool = False


class X24OriginProject:
    """Create a native ParetoBin report; never pre-sort or pre-cumulate in Python."""

    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layers: tuple[Any, Any] | None = None
        self.book: Any = None
        self.source_sheet: Any = None
        self.report_sheet: Any = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={"template_filename": X24_ORIGIN_PROFILE.filename},
        ):
            template = resolve_official_template(install_dir, X24_ORIGIN_PROFILE)
        source_data = x24_pareto_source(document, data)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            self.book = self.op.new_book("w", f"D{token}", hidden=True)
            if self.book is None:
                raise RuntimeError("Origin could not create the X24 source workbook")
            for residue in tuple(self.op.pages("w")):
                if residue.name == "Book1" and residue.name != self.book.name:
                    residue.destroy()
            self.source_sheet = self.book[0]
        with origin_trace_step(
            "source_data_write",
            details={
                "column_count": 2,
                "duplicate_categories_allowed": True,
                "row_count": len(source_data.categories),
                "sorting": "origin",
            },
        ):
            self._write_source(source_data)
        with origin_trace_step(
            "official_plot_paretobin_execute",
            details={
                "combine_smaller_values": False,
                "show_cumulative_percent": True,
                "template_filename": template.name,
            },
        ):
            self.source_sheet.activate()
            source_range = self.source_sheet.lt_range(False)
            self.op.lt_exec(
                f"plot_paretobin datarng:={source_range}!(A) "
                f"countrng:={source_range}!(B) cum:=1 combine:=0;"
            )
        with origin_trace_step("native_structure_readback"):
            graphs = list(self.op.pages("g"))
            if len(graphs) != 1:
                raise RuntimeError("Origin plot_paretobin must create exactly one X24 graph")
            self.graph = graphs[0]
            self.graph.lname = f"X24 ParetoBin / {document.plot_id}"
            layers = tuple(self.graph)
            if len(layers) != 2:
                raise RuntimeError("Origin ParetoBin must create two native graph layers")
            self.layers = layers
            self.report_sheet = self._find_report_sheet(self.book)
            self._assert_native_structure()
        record_origin_trace(
            "native_structure_confirmed",
            "completed",
            details={
                "layer_count": 2,
                "native_plot_ids": [203, 202],
                "right_y_axis_limits": [0.0, 110.0],
            },
        )

    def open(self, path: Path) -> None:
        with origin_trace_step("saved_project_reopen", details={"readonly": False}):
            self.op.new(asksave=False)
            if not self.op.open(str(path), readonly=False, asksave=False):
                raise RuntimeError("Origin could not reopen the X24 project")
        graphs, books = list(self.op.pages("g")), list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("X24 must contain exactly one graph and one workbook")
        self.graph, self.book = graphs[0], books[0]
        layers = tuple(self.graph)
        if len(layers) != 2:
            raise RuntimeError("X24 lost one native Pareto layer after reopen")
        self.layers = layers
        self.source_sheet, self.report_sheet = self._find_source_and_report(self.book)

    def reconcile(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> None:
        state = self._state(document, actions, x24_pareto(document, data))
        with origin_trace_step(
            "agent_actions_apply", details={"action_count": len(actions)}
        ):
            self._set_title(state.title)
            self._set_axis_labels(state)
            self._apply_styles(state)
            self._set_legend(state.legend_visible, state)

    def save(self, output: Path) -> None:
        with origin_trace_step("opju_save", details={"filename": output.name}):
            output.parent.mkdir(parents=True, exist_ok=True)
            self.op.save(str(output))
            if not output.is_file() or output.stat().st_size <= 0:
                raise RuntimeError("Origin did not save a non-empty X24 project")

    def verify(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> EngineReadback:
        source_data = x24_pareto_source(document, data)
        pareto = x24_pareto(document, data)
        state = self._state(document, actions, pareto)
        with origin_trace_step("reopened_native_structure_verify"):
            self._assert_native_structure()
        with origin_trace_step(
            "reopened_source_data_verify",
            details={"column_count": 2, "row_count": len(source_data.categories)},
        ):
            self._assert_values(
                self.source_sheet.to_list(0), source_data.categories, "raw categories"
            )
            self._assert_values(self.source_sheet.to_list(1), source_data.values, "raw counts")
        with origin_trace_step(
            "reopened_origin_calculation_verify",
            details={"output_rows": len(pareto.categories)},
        ):
            self._assert_values(
                self.report_sheet.to_list(0), pareto.categories, "Origin sorted categories"
            )
            self._assert_values(
                self.report_sheet.to_list(1), pareto.values, "Origin aggregated counts"
            )
            self._assert_values(
                self.report_sheet.to_list(2),
                pareto.cumulative_percent,
                "Origin cumulative percent",
            )
        with origin_trace_step("reopened_agent_edits_verify"):
            self._assert_labels(state)
            self._assert_styles(state)
            self._assert_legend(state.legend_visible)

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
                semantic_id=f"axis:{token}.y_left",
                backend="origin",
                object_kind="axis",
                native_ref=f"graph:{self.graph.name}.layer:1.axis:y",
            ),
            EngineObjectRef(
                semantic_id=f"axis:{token}.y_right",
                backend="origin",
                object_kind="axis",
                native_ref=f"graph:{self.graph.name}.layer:2.axis:y",
            ),
            EngineObjectRef(
                semantic_id=f"series:{token}.bars",
                backend="origin",
                object_kind="pareto_bar_series",
                native_ref=f"graph:{self.graph.name}.layer:1.plot:1",
            ),
            EngineObjectRef(
                semantic_id=f"series:{token}.cumulative",
                backend="origin",
                object_kind="pareto_cumulative_series",
                native_ref=f"graph:{self.graph.name}.layer:2.plot:1",
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
                        "native_plot_ids": [203, 202],
                        "state": asdict(state),
                        "template": X24_ORIGIN_PROFILE.filename,
                    },
                )
            ),
        )

    @staticmethod
    def _state(
        document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: ParetoData
    ) -> _State:
        token = document.plot_id.removeprefix("plot:")
        state = _State(x_label="", left_label=data.value_field_name)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("X24 title target does not belong")
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                key = {
                    f"axis:{token}.x": "x_label",
                    f"axis:{token}.y_left": "left_label",
                    f"axis:{token}.y_right": "right_label",
                }.get(action.target)
                if key is None:
                    raise ValueError("X24 axis target does not belong")
                expected_scale = "categorical" if key == "x_label" else "linear"
                if (
                    action.scale not in {None, expected_scale}
                    or action.minimum is not None
                    or action.maximum is not None
                    or action.reverse is not None
                ):
                    raise ValueError("X24 exposes axis labels while Pareto scales remain native")
                label = getattr(state, key) if action.label is None else action.label
                if key == "x_label":
                    state = replace(state, x_label=label)
                elif key == "left_label":
                    state = replace(state, left_label=label)
                else:
                    state = replace(state, right_label=label)
            elif isinstance(action, SetSeriesStyle):
                if action.symbol is not None or action.symbol_size_pt is not None:
                    raise ValueError("X24 does not expose symbol construction")
                if action.target == f"series:{token}.bars":
                    state = replace(
                        state,
                        bar_color=state.bar_color if action.color is None else action.color,
                        bar_line_width_pt=(
                            state.bar_line_width_pt
                            if action.line_width_pt is None
                            else action.line_width_pt
                        ),
                        bar_line_style=(
                            state.bar_line_style
                            if action.line_style is None
                            else action.line_style
                        ),
                    )
                elif action.target == f"series:{token}.cumulative":
                    if action.line_style == "none":
                        raise ValueError("X24 cumulative curve cannot be hidden by line style")
                    state = replace(
                        state,
                        line_color=state.line_color if action.color is None else action.color,
                        line_width_pt=(
                            state.line_width_pt
                            if action.line_width_pt is None
                            else action.line_width_pt
                        ),
                        line_style=(
                            state.line_style if action.line_style is None else action.line_style
                        ),
                    )
                else:
                    raise ValueError("X24 series target does not belong")
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main" or action.anchor is not None:
                    raise ValueError("X24 exposes only native legend visibility")
                state = replace(
                    state,
                    legend_visible=(
                        state.legend_visible if action.visible is None else action.visible
                    ),
                )
            else:
                raise ValueError(f"Origin X24 binder cannot apply {action.operation}")
        return state

    def _write_source(self, source: ParetoSourceData) -> None:
        self.source_sheet.cols = 2
        self.source_sheet.from_list(
            0, list(source.categories), lname=source.category_field_name, axis="X"
        )
        self.source_sheet.from_list(
            1, list(source.values), lname=source.value_field_name, axis="Y"
        )
        self.source_sheet.lt_exec("wks.col1.categorical.type=2;")

    def _set_title(self, text: str) -> None:
        top_axis_title = self._layers()[0].label("xt")
        if top_axis_title is not None:
            top_axis_title.set_int("show", 0)
        title = self._layers()[0].label(_TITLE)
        if title is None and text:
            self._layers()[0].activate()
            if not self._layers()[0].obj.LT_execute(
                f"label -j 1 -n {_TITLE} PlotAgentTitlePlaceholder;"
            ):
                raise RuntimeError("Origin could not create the X24 title")
            title = self._layers()[0].label(_TITLE)
        if title is not None:
            title.text = text
            title.set_int("attach", 1)
            title.set_float("x1", 0.5)
            title.set_float("y1", 0.035)
            title.set_int("show", int(bool(text)))

    def _set_axis_labels(self, state: _State) -> None:
        for layer, name, text in (
            (self._layers()[0], "xb", state.x_label),
            (self._layers()[0], "yl", state.left_label),
            (self._layers()[1], "yr", state.right_label),
        ):
            label = layer.label(name)
            if label is None:
                raise RuntimeError(f"Origin X24 is missing native axis label {name}")
            label.text = text
            label.set_int("show", int(bool(text)))

    def _apply_styles(self, state: _State) -> None:
        commands: list[str] = []
        if state.bar_color is not None:
            commands.extend(
                (
                    f'set %C -pfb color("{state.bar_color}")',
                    f'set %C -pbc color("{state.bar_color}")',
                )
            )
        if state.bar_line_width_pt is not None:
            commands.append(f"set %C -pbw {state.bar_line_width_pt}")
        if state.bar_line_style is not None:
            commands.append(f"set %C -pbs {_STYLE[state.bar_line_style]}")
        if commands:
            self._layers()[0].activate()
            self.op.lt_exec("; ".join(commands) + ";")

        commands = []
        if state.line_color is not None:
            commands.extend(
                (
                    f'set %C -cl color("{state.line_color}")',
                    f'set %C -cse color("{state.line_color}")',
                    f'set %C -csf color("{state.line_color}")',
                )
            )
        if state.line_width_pt is not None:
            commands.append(f"set %C -wp {state.line_width_pt}")
        if state.line_style is not None:
            commands.append(f"set %C -d {_STYLE[state.line_style]}")
        if commands:
            self._layers()[1].activate()
            self.op.lt_exec("; ".join(commands) + ";")

    def _set_legend(self, visible: bool, state: _State) -> None:
        layer = self._layers()[0]
        legend = layer.label("legend")
        if legend is None and visible:
            layer.activate()
            if not layer.obj.LT_execute("legend"):
                raise RuntimeError("Origin could not create the X24 native legend")
            legend = layer.label("legend")
        if legend is not None:
            legend.text = (
                f"\\l(1) {state.left_label}\n"
                f"\\l(2.1, style:l) {state.right_label}"
            )
            legend.set_int("link", 1)
            legend.set_int("attach", 1)
            legend.set_float("x1", 0.18)
            legend.set_float("y1", 0.05)
            legend.set_int("fsize", 18)
            legend.set_int("background", 0)
            legend.set_int("show", int(visible))

    def _assert_native_structure(self) -> None:
        observed: list[int] = []
        for layer in self._layers():
            layer.activate()
            plot_id = float(self.op.lt_float("layer.plot1.pid"))
            if isnan(plot_id):
                raise RuntimeError("Origin X24 native plot type is unreadable")
            observed.append(int(plot_id))
        if observed != [203, 202]:
            raise RuntimeError(
                "Origin X24 must retain native PID 203 columns and PID 202 cumulative line"
            )
        limits = tuple(float(value) for value in self._layers()[1].axis("y").limits[:2])
        if len(limits) != 2 or not (
            isclose(limits[0], 0.0, abs_tol=1e-8)
            and isclose(limits[1], 110.0, abs_tol=1e-8)
        ):
            raise RuntimeError(
                "Origin X24 right Y axis must retain the official 0..110 percent range"
            )

    def _assert_labels(self, state: _State) -> None:
        for layer, name, expected in (
            (self._layers()[0], "xb", state.x_label),
            (self._layers()[0], "yl", state.left_label),
            (self._layers()[1], "yr", state.right_label),
        ):
            label = layer.label(name)
            if expected:
                if label is None or label.text != expected or label.get_int("show") == 0:
                    raise RuntimeError(f"Origin X24 axis label {name} changed after reopen")
            elif label is not None and label.get_int("show") != 0:
                raise RuntimeError(f"Origin X24 axis label {name} reappeared after reopen")
        title = self._layers()[0].label(_TITLE)
        if state.title and (
            title is None or title.text != state.title or title.get_int("show") == 0
        ):
            raise RuntimeError("Origin X24 title changed after reopen")

    def _assert_styles(self, state: _State) -> None:
        if any(
            value is not None
            for value in (state.bar_color, state.bar_line_width_pt, state.bar_line_style)
        ):
            self._layers()[0].activate()
            self.op.lt_exec(
                "get %C -pfb __X24BF; get %C -pbw __X24BW; get %C -pbs __X24BS;"
            )
            if state.bar_color is not None:
                expected = int(self.op.lt_float(f'color("{state.bar_color}")'))
                if int(self.op.lt_float("__X24BF")) != expected:
                    raise RuntimeError("Origin X24 bar color changed after reopen")
            if state.bar_line_width_pt is not None and not isclose(
                float(self.op.lt_float("__X24BW")), state.bar_line_width_pt, abs_tol=1e-8
            ):
                raise RuntimeError("Origin X24 bar border width changed after reopen")
            if state.bar_line_style is not None and int(
                self.op.lt_float("__X24BS")
            ) != _STYLE[state.bar_line_style]:
                raise RuntimeError("Origin X24 bar border style changed after reopen")

        if any(
            value is not None
            for value in (state.line_color, state.line_width_pt, state.line_style)
        ):
            self._layers()[1].activate()
            self.op.lt_exec("get %C -cl __X24LC; get %C -w __X24LW; get %C -d __X24LS;")
            if state.line_color is not None:
                expected = int(self.op.lt_float(f'color("{state.line_color}")'))
                if int(self.op.lt_float("__X24LC")) != expected:
                    raise RuntimeError("Origin X24 cumulative line color changed after reopen")
            if state.line_width_pt is not None and not isclose(
                float(self.op.lt_float("__X24LW")) / 500.0,
                state.line_width_pt,
                abs_tol=1e-8,
            ):
                raise RuntimeError("Origin X24 cumulative line width changed after reopen")
            if state.line_style is not None and int(
                self.op.lt_float("__X24LS")
            ) != _STYLE[state.line_style]:
                raise RuntimeError("Origin X24 cumulative line style changed after reopen")

    def _assert_legend(self, visible: bool) -> None:
        legend = self._layers()[0].label("legend")
        if visible:
            if (
                legend is None
                or legend.get_int("show") == 0
                or str(legend.text).count(r"\l(") != 2
                or legend.get_int("attach") != 1
                or not isclose(legend.get_float("x1"), 0.18, abs_tol=1e-8)
                or not isclose(legend.get_float("y1"), 0.05, abs_tol=1e-8)
            ):
                raise RuntimeError("Origin X24 native legend changed after reopen")
        elif legend is not None and legend.get_int("show") != 0:
            raise RuntimeError("Origin X24 hidden legend reappeared after reopen")

    @staticmethod
    def _find_report_sheet(book: Any) -> Any:
        sheets = tuple(book)
        candidates = tuple(sheet for sheet in sheets if int(sheet.cols) >= 3)
        if len(candidates) != 1:
            raise RuntimeError("Origin X24 must create one ParetoBin output sheet")
        return candidates[0]

    @classmethod
    def _find_source_and_report(cls, book: Any) -> tuple[Any, Any]:
        sheets = tuple(book)
        source = tuple(sheet for sheet in sheets if int(sheet.cols) == 2)
        if len(source) != 1:
            raise RuntimeError("Origin X24 must retain one two-column raw source sheet")
        return source[0], cls._find_report_sheet(book)

    def _layers(self) -> tuple[Any, Any]:
        if self.layers is None:
            raise RuntimeError("X24 layers are not initialized")
        return self.layers

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[object, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin X24 {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
                if isclose(float(cast(Any, observed)), float(wanted), abs_tol=1e-8):
                    continue
            elif observed == wanted:
                continue
            raise RuntimeError(f"Origin X24 {role} values differ after reopen")


def execute_x24_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    project = X24OriginProject(op)
    project.create(install_dir, request.document, request.data)
    project.reconcile(request.document, request.actions, request.data)
    project.save(output)
    reopened = X24OriginProject(op)
    reopened.open(output)
    return reopened.verify(request.document, request.actions, request.data)
