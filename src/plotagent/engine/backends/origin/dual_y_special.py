"""Official two-layer binders for X35 dual-column and X36 column-line."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import isclose, isnan
from pathlib import Path
from typing import Any, Literal, cast

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
from plotagent.engine.profile_data import X23SeriesData, x35_series, x36_series
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import (
    X35_ORIGIN_PROFILE,
    X36_ORIGIN_PROFILE,
    OriginTemplateProfile,
    resolve_official_template,
)
from .trace import origin_trace_step, record_origin_trace

_LINE_STYLE = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}
_SYMBOL = {"circle": 2, "square": 1, "diamond": 5, "triangle": 3, "triangle_up": 3}
_TITLE_NAME = "_ENGINE_TITLE"
_OFFICIAL_HELP_URLS = {
    "X35": "https://docs.originlab.com/origin-help/2ys-column-graph/",
    "X36": "https://docs.originlab.com/origin-help/2ys-column-linesym-graph/",
}
_OFFICIAL_MENUS = {
    "X35": "Plot > Multi-Panel/Axis > 2Ys Column",
    "X36": "Plot > Multi-Panel/Axis > 2Ys Column - Line Symbol",
}
_OFFICIAL_SECTIONS = {"X35": "2YsCol", "X36": "2YsColSymb"}


@dataclass(frozen=True, slots=True)
class _AxisState:
    label: str
    scale: Literal["linear", "log10", "datetime", "categorical"]
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool = False


@dataclass(frozen=True, slots=True)
class _SeriesState:
    color: str | None = None
    line_width_pt: float | None = None
    line_style: str | None = None
    symbol: str | None = None
    symbol_size_pt: float | None = None


@dataclass(frozen=True, slots=True)
class _State:
    title: str
    x_axis: _AxisState
    left_axis: _AxisState
    right_axis: _AxisState
    left_series: _SeriesState = _SeriesState()
    right_series: _SeriesState = _SeriesState()
    legend_visible: bool = True


class DualYSpecialOriginProject:
    def __init__(self, op: Any, *, profile_id: Literal["X35", "X36"]) -> None:
        self.op = op
        self.profile_id = profile_id
        self.profile: OriginTemplateProfile = {
            "X35": X35_ORIGIN_PROFILE,
            "X36": X36_ORIGIN_PROFILE,
        }[profile_id]
        self.graph: Any = None
        self.layers: tuple[Any, Any] | None = None
        self.plots: tuple[Any, Any] | None = None
        self.book: Any = None
        self.sheet: Any = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={"template_filename": self.profile.filename},
        ):
            template = resolve_official_template(install_dir, self.profile)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            self.book = self.op.new_book("w", f"D{token}", hidden=True)
            if self.book is None:
                raise RuntimeError(f"Origin could not create the {self.profile_id} workbook")
            for residue in tuple(self.op.pages("w")):
                if residue.name == "Book1" and residue.name != self.book.name:
                    residue.destroy()
            self.sheet = self.book[0]
        values = self._data(document, data)
        with origin_trace_step(
            "source_data_write",
            details={"column_count": 3, "row_count": len(values.left_values)},
        ):
            self._write(values)
        section = _OFFICIAL_SECTIONS[self.profile_id]
        with origin_trace_step(
            "official_plot_section_execute",
            details={
                "official_help_url": _OFFICIAL_HELP_URLS[self.profile_id],
                "official_menu": _OFFICIAL_MENUS[self.profile_id],
                "plot_section": section,
                "template_filename": template.name,
            },
        ):
            self.sheet.activate()
            self.op.lt_exec(
                f"worksheet -s 1 0 3 0; run.section(plot,{section});"
            )
        with origin_trace_step(
            "categorical_source_order_restore",
            details={"categorical_sort": "first_source_appearance"},
        ):
            # The Origin 2024 double-Y menu sections reset the worksheet X
            # column's categorical flag while constructing the graph.  Restore
            # the documented Unsorted map *after* the official section and
            # update the native plots so linked layers use source-row order.
            self.sheet.activate()
            self.sheet.lt_exec(
                "wks.col1.categorical.type=2; wks.col1.categorical.sort=0;"
            )
            self.op.lt_exec("doc -u;")
        with origin_trace_step("native_structure_readback"):
            graphs = list(self.op.pages("g"))
            if len(graphs) != 1:
                raise RuntimeError(
                    f"Origin official {section} section must create exactly one graph"
                )
            self.graph = graphs[0]
            self.graph.name = f"G{token}"
            self.graph.lname = f"{self.profile_id} {template.stem} / {document.plot_id}"
            layers = tuple(self.graph)
            if len(layers) != 2:
                raise RuntimeError(
                    f"Origin {self.profile.filename} must provide exactly two layers"
                )
            self.layers = (layers[0], layers[1])
            native = tuple(tuple(layer.plot_list()) for layer in self.layers)
            if tuple(len(items) for items in native) != (1, 1):
                raise RuntimeError(
                    f"Origin {self.profile_id} must create one native plot per layer"
                )
            self.plots = (native[0][0], native[1][0])
            self._assert_native_structure(verify_offsets=False)
        record_origin_trace(
            "native_structure_confirmed",
            "completed",
            details={
                "layer_count": 2,
                "native_plot_ids": [203, 203] if self.profile_id == "X35" else [203, 202],
                "plot_offsets": "verified_after_reopen",
            },
        )

    def open(self, project_path: Path) -> None:
        with origin_trace_step("saved_project_reopen", details={"readonly": False}):
            self.op.new(asksave=False)
            if not self.op.open(str(project_path), readonly=False, asksave=False):
                raise RuntimeError(f"Origin could not open the prior {self.profile_id} project")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError(f"{self.profile_id} project must contain one graph and workbook")
        self.graph, self.book = graphs[0], books[0]
        layers = tuple(self.graph)
        if len(layers) != 2:
            raise RuntimeError(f"{self.profile_id} project lost one official layer")
        self.layers = (layers[0], layers[1])
        native = tuple(tuple(layer.plot_list()) for layer in self.layers)
        if tuple(len(items) for items in native) != (1, 1):
            raise RuntimeError(f"{self.profile_id} project must retain one plot per layer")
        self.plots = (native[0][0], native[1][0])
        self.sheet = self.book[0]

    def reconcile(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> None:
        values = self._data(document, data)
        state = self._state(document, actions, values)
        with origin_trace_step(
            "agent_actions_apply", details={"action_count": len(actions)}
        ):
            self._set_title(state.title)
            self._configure_x(values, state.x_axis)
            self._configure_y(self._layers()[0], "yl", state.left_axis)
            self._configure_y(self._layers()[1], "yr", state.right_axis)
            self._apply_column_style(1, state.left_series)
            if self.profile_id == "X35":
                self._apply_column_style(2, state.right_series)
            else:
                self._apply_line_symbol_style(2, state.right_series)
            self._set_legend(values, state.legend_visible)

    def save(self, output: Path) -> None:
        with origin_trace_step("opju_save", details={"filename": output.name}):
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                raise FileExistsError(
                    f"Origin refuses to overwrite existing {self.profile_id} artifact: {output}"
                )
            self.op.save(str(output))
            if not output.is_file() or output.stat().st_size <= 0:
                raise RuntimeError(f"Origin did not save a non-empty {self.profile_id} project")

    def verify(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: EngineDataView
    ) -> EngineReadback:
        values = self._data(document, data)
        state = self._state(document, actions, values)
        with origin_trace_step("reopened_native_structure_verify"):
            self._assert_native_structure(verify_offsets=True)
            self._assert_default_column_baselines(state)
        record_origin_trace(
            "reopened_native_offsets_confirmed",
            "completed",
            details={
                "plot_offsets": [[0.0, 1.0], [0.0, 1.0]],
                "x35_default_column_baselines": (
                    "zero_in_both_y_axis_ranges" if self.profile_id == "X35" else "not_applicable"
                ),
            },
        )
        with origin_trace_step(
            "reopened_source_data_verify",
            details={"column_count": 3, "row_count": len(values.left_values)},
        ):
            self._assert_values(self.sheet.to_list(0), tuple(values.x_values), "category")
            self._assert_values(self.sheet.to_list(1), values.left_values, "left")
            self._assert_values(self.sheet.to_list(2), values.right_values, "right")
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
                semantic_id=f"series:{token}.left",
                backend="origin",
                object_kind="dual_y_column_series",
                native_ref=f"graph:{self.graph.name}.layer:1.plot:1",
            ),
            EngineObjectRef(
                semantic_id=f"series:{token}.right",
                backend="origin",
                object_kind="dual_y_column_series"
                if self.profile_id == "X35"
                else "dual_y_line_series",
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
                        "native_plot_ids": (
                            [203, 203] if self.profile_id == "X35" else [203, 202]
                        ),
                        "state": asdict(state),
                        "template": self.profile.filename,
                    },
                )
            ),
        )

    def _data(self, document: PlotDocument, data: EngineDataView) -> X23SeriesData:
        return (
            x35_series(document, data) if self.profile_id == "X35" else x36_series(document, data)
        )

    def _write(self, values: X23SeriesData) -> None:
        self.sheet.cols = 3
        self.sheet.from_list(0, list(values.x_values), lname=values.x_field_name, axis="X")
        self.sheet.from_list(1, list(values.left_values), lname=values.left_field_name, axis="Y")
        self.sheet.from_list(2, list(values.right_values), lname=values.right_field_name, axis="Y")
        # Origin templates can retain an ascending/descending categorical sort
        # from their saved state.  Auto-categorical alone therefore does not
        # guarantee source-row order.  The official ``categorical.sort``
        # contract defines 0 as Unsorted, i.e. first appearance in the source
        # column, which is the canonical order for these two chart profiles.
        self.sheet.lt_exec(
            "wks.col1.categorical.type=2; wks.col1.categorical.sort=0;"
        )

    def _configure_x(self, values: X23SeriesData, state: _AxisState) -> None:
        if values.x_labels is None or state.scale != "categorical":
            raise ValueError(f"Origin {self.profile_id} requires categorical X data")
        self._set_axis_label(self._layers()[0], "xb", state.label)
        for layer in self._layers():
            axis = layer.axis("x")
            if state.minimum is not None and state.maximum is not None:
                begin, end = state.minimum, state.maximum
                if state.reverse:
                    begin, end = end, begin
                axis.set_limits(begin, end)
            elif state.reverse:
                limits = tuple(float(item) for item in axis.limits)
                axis.set_limits(limits[1], limits[0], limits[2])

    def _configure_y(self, layer: Any, label_name: str, state: _AxisState) -> None:
        if state.scale not in {"linear", "log10"}:
            raise ValueError(f"Origin {self.profile_id} Y axes support linear or log10")
        axis = layer.axis("y")
        axis.scale = state.scale
        if state.minimum is not None and state.maximum is not None:
            begin, end = state.minimum, state.maximum
            if state.reverse:
                begin, end = end, begin
            axis.set_limits(begin, end)
        self._set_axis_label(layer, label_name, state.label)

    def _set_title(self, text: str) -> None:
        title = self._layers()[0].label(_TITLE_NAME)
        if title is None and text:
            self._layers()[0].activate()
            if not self._layers()[0].obj.LT_execute(
                f"label -j 1 -n {_TITLE_NAME} PlotAgentTitlePlaceholder;"
            ):
                raise RuntimeError(f"Origin could not create the {self.profile_id} title")
            title = self._layers()[0].label(_TITLE_NAME)
            if title is None:
                raise RuntimeError(f"Origin could not create the {self.profile_id} title")
        if title is not None:
            title.text = text
            title.set_int("attach", 1)
            title.set_float("x1", 0.5)
            title.set_float("y1", 0.012)
            title.set_int("fsize", 18)
            title.set_int("background", 0)
            title.set_int("show", int(bool(text)))

    @staticmethod
    def _set_axis_label(layer: Any, name: str, text: str) -> None:
        label = (
            layer.label(name)
            or (layer.label("yl") if name == "yr" else None)
            or layer.add_label(text)
        )
        if label is None:
            raise RuntimeError("Origin dual-Y template has no writable axis label")
        label.text = text
        label.set_int("show", 1)

    def _set_legend(self, values: X23SeriesData, visible: bool) -> None:
        layer = self._layers()[0]
        legend = layer.label("legend")
        if legend is None:
            layer.activate()
            layer.obj.LT_execute("legend")
            legend = layer.label("legend")
        if legend is None:
            raise RuntimeError(f"Origin {self.profile_id} has no writable legend")
        sample = "b" if self.profile_id == "X35" else "l"
        legend.text = (
            f"\\l(1, style:b) {values.left_field_name}\n"
            f"\\l(2.1, style:{sample}) {values.right_field_name}"
        )
        legend.set_int("link", 1)
        legend.set_int("attach", 1)
        legend.set_float("x1", 0.08)
        legend.set_float("y1", 0.045)
        legend.set_int("fsize", 14)
        legend.set_int("background", 0)
        legend.set_int("show", int(visible))

    def _graph_layer_prefix(self, layer_index: int) -> str:
        """Return a LabTalk prefix that scopes the same command to one layer.

        ``GraphLayer.activate()`` does not reliably change ``page.active`` for
        linked double-Y templates in Origin 2024.  All ``set/get %C`` commands
        therefore use the documented one-based ``page.active`` property in the
        *same* LabTalk command as the edit/readback.  Keeping activation and
        mutation in separate RPC calls was observed to reset to Layer2.
        """

        return (
            f"window -a {self.graph.name}; "
            f"{self.graph.name}!page.active={layer_index}; "
        )

    def _apply_column_style(self, layer_index: int, state: _SeriesState) -> None:
        if (
            state.line_style is not None
            or state.symbol is not None
            or state.symbol_size_pt is not None
        ):
            raise ValueError("Origin column series exposes only color and border width")
        commands: list[str] = []
        if state.color is not None:
            commands.extend(
                (
                    f'set %C -pfb color("{state.color}")',
                    f'set %C -pbc color("{state.color}")',
                )
            )
        if state.line_width_pt is not None:
            commands.append(f"set %C -pbw {state.line_width_pt}")
        if commands:
            self.op.lt_exec(
                self._graph_layer_prefix(layer_index) + "; ".join(commands) + ";"
            )

    def _apply_line_symbol_style(self, layer_index: int, state: _SeriesState) -> None:
        commands: list[str] = []
        if state.color is not None:
            commands.extend(
                (
                    f'set %C -cl color("{state.color}")',
                    f'set %C -cse color("{state.color}")',
                    f'set %C -csf color("{state.color}")',
                )
            )
        if state.line_width_pt is not None:
            commands.append(f"set %C -wp {state.line_width_pt}")
        if state.line_style is not None:
            if state.line_style == "none":
                raise ValueError("Origin dual-Y series cannot be hidden through line style")
            commands.append(f"set %C -d {_LINE_STYLE[state.line_style]}")
        if state.symbol is not None:
            commands.append(f"set %C -k {_SYMBOL[state.symbol]}")
        if state.symbol_size_pt is not None:
            commands.append(f"set %C -z {state.symbol_size_pt}")
        if commands:
            self.op.lt_exec(
                self._graph_layer_prefix(layer_index) + "; ".join(commands) + ";"
            )

    def _assert_native_structure(self, *, verify_offsets: bool) -> None:
        self.sheet.activate()
        self.op.lt_exec(
            f"__{self.profile_id}CATTYPE=wks.col1.categorical.type; "
            f"__{self.profile_id}CATSORT=wks.col1.categorical.sort;"
        )
        category_type = int(self.op.lt_float(f"__{self.profile_id}CATTYPE"))
        category_sort = int(self.op.lt_float(f"__{self.profile_id}CATSORT"))
        if category_type != 2 or category_sort != 0:
            raise RuntimeError(
                f"Origin {self.profile_id} category order must follow first source "
                f"appearance; observed type={category_type}, sort={category_sort}"
            )
        expected = [203, 203] if self.profile_id == "X35" else [203, 202]
        observed: list[int] = []
        for index, _layer in enumerate(self._layers(), 1):
            prefix = f"__{self.profile_id}PT{index}"
            command = self._graph_layer_prefix(index) + f"get %C -pt {prefix};"
            if verify_offsets:
                command += (
                    f" get %C -sy __{self.profile_id}SY{index}; "
                    f"get %C -sys __{self.profile_id}SYS{index};"
                )
            self.op.lt_exec(command)
            plot_id = float(self.op.lt_float(prefix))
            if isnan(plot_id):
                raise RuntimeError(f"Origin {self.profile_id} native plot type is unreadable")
            observed.append(int(plot_id))
            if verify_offsets:
                offset = float(self.op.lt_float(f"__{self.profile_id}SY{index}"))
                multiplier = float(self.op.lt_float(f"__{self.profile_id}SYS{index}"))
                if not isclose(offset, 0.0, abs_tol=1e-8) or not isclose(
                    multiplier, 1.0, abs_tol=1e-8
                ):
                    raise RuntimeError(
                        f"Origin {self.profile_id} columns/line must retain "
                        f"zero Y offset and unit scale; observed layer {index}: "
                        f"offset={offset}, multiplier={multiplier}"
                    )
        if observed != expected:
            raise RuntimeError(
                f"Origin {self.profile_id} native plot IDs {observed} differ from {expected}"
            )
        datasets = tuple(str(plot.obj.DatasetName) for plot in self._plots())
        if not datasets[0].endswith("_B") or not datasets[1].endswith("_C"):
            raise RuntimeError(
                f"Origin {self.profile_id} plots are not bound directly to source Y columns B/C"
            )

    def _assert_default_column_baselines(self, state: _State) -> None:
        """Reject an unintended floating-column appearance in X35's default state.

        The official 2Ys Column graph uses two ordinary Column plots (PID 203),
        each with zero plot offset.  For automatic linear axes, zero must also
        remain inside both native Y-axis ranges; otherwise a positive-only axis
        can make a correctly bound column look like a floating interval.
        Explicit user bounds and logarithmic axes are respected and are not
        treated as renderer regressions.
        """

        if self.profile_id != "X35":
            return
        for ordinal, (layer, axis_state) in enumerate(
            zip(self._layers(), (state.left_axis, state.right_axis), strict=True),
            start=1,
        ):
            if (
                axis_state.scale != "linear"
                or axis_state.minimum is not None
                or axis_state.maximum is not None
            ):
                continue
            begin, end, *_rest = (float(value) for value in layer.axis("y").limits)
            if min(begin, end) > 0.0 or max(begin, end) < 0.0:
                raise RuntimeError(
                    "Origin X35 automatic Y axis must include zero so its ordinary "
                    f"column cannot appear floating; observed layer {ordinal}: "
                    f"begin={begin}, end={end}"
                )

    def _assert_labels(self, state: _State) -> None:
        for layer, name, expected in (
            (self._layers()[0], "xb", state.x_axis.label),
            (self._layers()[0], "yl", state.left_axis.label),
            (self._layers()[1], "yr", state.right_axis.label),
        ):
            label = layer.label(name)
            if label is None or label.text != expected or label.get_int("show") == 0:
                raise RuntimeError(f"Origin {self.profile_id} axis label {name} changed")
        title = self._layers()[0].label(_TITLE_NAME)
        if state.title and (
            title is None or title.text != state.title or title.get_int("show") == 0
        ):
            raise RuntimeError(f"Origin {self.profile_id} title changed after reopen")

    def _assert_styles(self, state: _State) -> None:
        self._assert_column_style(1, state.left_series, "left")
        if self.profile_id == "X35":
            self._assert_column_style(2, state.right_series, "right")
        else:
            self._assert_line_symbol_style(2, state.right_series)

    def _assert_column_style(
        self, layer_index: int, state: _SeriesState, role: str
    ) -> None:
        if state.color is None and state.line_width_pt is None:
            return
        self.op.lt_exec(
            self._graph_layer_prefix(layer_index)
            + f"get %C -pfb __{self.profile_id}{role}C; "
            f"get %C -pbw __{self.profile_id}{role}W;"
        )
        if state.color is not None:
            expected = int(self.op.lt_float(f'color("{state.color}")'))
            if int(self.op.lt_float(f"__{self.profile_id}{role}C")) != expected:
                raise RuntimeError(f"Origin {self.profile_id} {role} column color changed")
        if state.line_width_pt is not None and not isclose(
            float(self.op.lt_float(f"__{self.profile_id}{role}W")),
            state.line_width_pt,
            abs_tol=1e-8,
        ):
            raise RuntimeError(f"Origin {self.profile_id} {role} column border width changed")

    def _assert_line_symbol_style(self, layer_index: int, state: _SeriesState) -> None:
        if all(
            value is None
            for value in (
                state.color,
                state.line_width_pt,
                state.line_style,
                state.symbol,
                state.symbol_size_pt,
            )
        ):
            return
        self.op.lt_exec(
            self._graph_layer_prefix(layer_index)
            + f"get %C -cl __{self.profile_id}LC; get %C -w __{self.profile_id}LW; "
            f"get %C -d __{self.profile_id}LS; get %C -k __{self.profile_id}SK; "
            f"get %C -z __{self.profile_id}SZ;"
        )
        if state.color is not None:
            expected = int(self.op.lt_float(f'color("{state.color}")'))
            if int(self.op.lt_float(f"__{self.profile_id}LC")) != expected:
                raise RuntimeError(f"Origin {self.profile_id} line color changed")
        if state.line_width_pt is not None and not isclose(
            float(self.op.lt_float(f"__{self.profile_id}LW")) / 500.0,
            state.line_width_pt,
            abs_tol=1e-8,
        ):
            raise RuntimeError(f"Origin {self.profile_id} line width changed")
        if state.line_style is not None and int(
            self.op.lt_float(f"__{self.profile_id}LS")
        ) != _LINE_STYLE[state.line_style]:
            raise RuntimeError(f"Origin {self.profile_id} line style changed")
        if state.symbol is not None and int(
            self.op.lt_float(f"__{self.profile_id}SK")
        ) != _SYMBOL[state.symbol]:
            raise RuntimeError(f"Origin {self.profile_id} symbol changed")
        if state.symbol_size_pt is not None and not isclose(
            float(self.op.lt_float(f"__{self.profile_id}SZ")),
            state.symbol_size_pt,
            abs_tol=1e-8,
        ):
            raise RuntimeError(f"Origin {self.profile_id} symbol size changed")

    def _assert_legend(self, visible: bool) -> None:
        legend = self._layers()[0].label("legend")
        if visible:
            if (
                legend is None
                or legend.get_int("show") == 0
                or str(legend.text).count(r"\l(") != 2
                or legend.get_int("attach") != 1
                or not isclose(legend.get_float("x1"), 0.08, abs_tol=1e-8)
                or not isclose(legend.get_float("y1"), 0.045, abs_tol=1e-8)
            ):
                raise RuntimeError(f"Origin {self.profile_id} native legend changed")
        elif legend is not None and legend.get_int("show") != 0:
            raise RuntimeError(f"Origin {self.profile_id} hidden legend reappeared")

    def _state(
        self, document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: X23SeriesData
    ) -> _State:
        token = document.plot_id.removeprefix("plot:")
        state = _State(
            title="",
            x_axis=_AxisState(data.x_field_name, "categorical"),
            left_axis=_AxisState(data.left_field_name, "linear"),
            right_axis=_AxisState(data.right_field_name, "linear"),
        )
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError(f"{self.profile_id} title target does not belong")
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                key = {
                    f"axis:{token}.x": "x_axis",
                    f"axis:{token}.y_left": "left_axis",
                    f"axis:{token}.y_right": "right_axis",
                }.get(action.target)
                if key is None:
                    raise ValueError(f"{self.profile_id} axis target does not belong")
                current = getattr(state, key)
                requested_scale = current.scale if action.scale is None else action.scale
                if (key == "x_axis" and requested_scale != "categorical") or (
                    key != "x_axis" and requested_scale not in {"linear", "log10"}
                ):
                    raise ValueError(f"{self.profile_id} axis scale is not supported")
                state = replace(
                    state,
                    **{
                        key: replace(
                            current,
                            label=current.label if action.label is None else action.label,
                            scale=current.scale if action.scale is None else action.scale,
                            minimum=current.minimum if action.minimum is None else action.minimum,
                            maximum=current.maximum if action.maximum is None else action.maximum,
                            reverse=current.reverse if action.reverse is None else action.reverse,
                        )
                    },
                )
            elif isinstance(action, SetSeriesStyle):
                key = {
                    f"series:{token}.left": "left_series",
                    f"series:{token}.right": "right_series",
                }.get(action.target)
                if key is None:
                    raise ValueError(f"{self.profile_id} series target does not belong")
                if key == "left_series" and (
                    action.line_style is not None
                    or action.symbol is not None
                    or action.symbol_size_pt is not None
                ):
                    raise ValueError(f"{self.profile_id} left column exposes no line or symbol")
                if self.profile_id == "X35" and key == "right_series" and (
                    action.line_style is not None
                    or action.symbol is not None
                    or action.symbol_size_pt is not None
                ):
                    raise ValueError("X35 right column exposes no line or symbol")
                current = getattr(state, key)
                state = replace(
                    state,
                    **{
                        key: replace(
                            current,
                            color=current.color if action.color is None else action.color,
                            line_width_pt=current.line_width_pt
                            if action.line_width_pt is None
                            else action.line_width_pt,
                            line_style=current.line_style
                            if action.line_style is None
                            else action.line_style,
                            symbol=current.symbol if action.symbol is None else action.symbol,
                            symbol_size_pt=current.symbol_size_pt
                            if action.symbol_size_pt is None
                            else action.symbol_size_pt,
                        )
                    },
                )
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main" or action.anchor is not None:
                    raise ValueError(f"{self.profile_id} exposes only native legend visibility")
                state = replace(
                    state,
                    legend_visible=state.legend_visible
                    if action.visible is None
                    else action.visible,
                )
            else:
                raise ValueError(f"Origin {self.profile_id} binder cannot apply {action.operation}")
        return state

    def _layers(self) -> tuple[Any, Any]:
        if self.layers is None:
            raise RuntimeError(f"{self.profile_id} layers are not initialized")
        return self.layers

    def _plots(self) -> tuple[Any, Any]:
        if self.plots is None:
            raise RuntimeError(f"{self.profile_id} plots are not initialized")
        return self.plots

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[object, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
                if abs(float(cast(Any, observed)) - float(wanted)) <= 1e-9:
                    continue
            elif observed == wanted:
                continue
            raise RuntimeError(f"Origin {role} values differ after reopen")


def _execute(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
    profile_id: Literal["X35", "X36"],
) -> EngineReadback:
    structure_output = output.with_name(f"{output.stem}.official-structure.opju")
    project = DualYSpecialOriginProject(op, profile_id=profile_id)
    project.create(install_dir, request.document, request.data)
    project.save(structure_output)

    # Origin 2024's linked double-Y templates restore Layer1's template style
    # when the never-saved graph is reopened.  Freeze the official structure
    # once, then apply Agent edits to that native project.  This mirrors the
    # documented UI workflow (create graph, then edit Plot Details) and makes
    # both layers' edits persist independently.
    editable = DualYSpecialOriginProject(op, profile_id=profile_id)
    editable.open(structure_output)
    editable.reconcile(request.document, request.actions, request.data)
    with origin_trace_step("native_agent_edits_verify"):
        state = editable._state(
            request.document,
            request.actions,
            editable._data(request.document, request.data),
        )
        editable._assert_styles(state)
    editable.save(output)
    with origin_trace_step("saved_agent_edits_verify"):
        editable._assert_styles(state)
    reopened = DualYSpecialOriginProject(op, profile_id=profile_id)
    reopened.open(output)
    readback = reopened.verify(request.document, request.actions, request.data)
    structure_output.unlink(missing_ok=True)
    return readback


def execute_x35_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "X35")


def execute_x36_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "X36")
