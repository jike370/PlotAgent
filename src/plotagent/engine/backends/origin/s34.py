"""S34 Origin 2024 native Line + Symbol binder for Nyquist data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
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
    SetChartParameter,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import NyquistData, s34_nyquist
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import S34_ORIGIN_PROFILE, resolve_official_template
from .trace import origin_trace_step, record_origin_trace

_TITLE = "_ENGINE_TITLE"
_LINE_STYLE = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}
_SYMBOL = {"circle": 1, "square": 2, "diamond": 3, "triangle": 4, "plus": 5}


@dataclass(frozen=True, slots=True)
class _AxesState:
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    x_minimum: float | None = None
    x_maximum: float | None = None
    y_minimum: float | None = None
    y_maximum: float | None = None
    x_reverse: bool = False
    y_reverse: bool = False


@dataclass(frozen=True, slots=True)
class _Style:
    color: str | None = None
    line_width_pt: float | None = None
    line_style: str | None = None
    symbol: str | None = None
    symbol_size_pt: float | None = None


class S34OriginProject:
    """Create and verify S34 through Origin's official Line + Symbol route."""

    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.book: Any = None
        self.sheet: Any = None
        self.plots: tuple[Any, ...] = ()
        self.last_native_structure: dict[str, JsonValue] | None = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={"template_filename": S34_ORIGIN_PROFILE.filename},
        ):
            template = resolve_official_template(install_dir, S34_ORIGIN_PROFILE)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            self.book = self.op.new_book("w", f"D{token}", hidden=True)
            if self.book is None:
                raise RuntimeError("Origin could not create the S34 workbook")
            for residue in tuple(self.op.pages("w")):
                if residue.name == "Book1" and residue.name != self.book.name:
                    residue.destroy()
            self.sheet = self.book[0]
        nyquist = s34_nyquist(document, data)
        with origin_trace_step(
            "source_data_write",
            details={
                "series_count": len(nyquist.series),
                "row_counts": [len(series.z_real) for series in nyquist.series],
                "frequency_storage": "N metadata columns",
            },
        ):
            self._write(nyquist)
        with origin_trace_step(
            "official_line_symbol_execute",
            details={
                "official_menu": "Plot > Basic 2D > Line + Symbol",
                "plot_type": 202,
                "template_filename": template.name,
                "ordinary_primitive_fallback_used": False,
            },
        ):
            self.sheet.activate()
            xy_columns = len(nyquist.series) * 2
            self.op.lt_exec(f"worksheet -s 1 0 {xy_columns} 0; worksheet -p 202 LINESYMB;")
        graphs = tuple(self.op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError("Origin official Line + Symbol route must create one graph")
        self.graph = graphs[0]
        self.graph.name = f"G{token}"
        self.graph.lname = f"S34 {template.stem} / {document.plot_id}"
        layers = tuple(self.graph)
        if len(layers) != 1:
            raise RuntimeError("Origin S34 must contain exactly one native graph layer")
        self.layer = layers[0]
        self.plots = tuple(self.layer.plot_list())
        with origin_trace_step("native_structure_readback"):
            native = self._native_structure(nyquist)
        self.last_native_structure = native
        record_origin_trace("native_structure_confirmed", "completed", details=native)

    def open(self, output: Path, *, readonly: bool = False) -> None:
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        with origin_trace_step(
            "opju_open", details={"filename": output.name, "readonly": readonly}
        ):
            if not self.op.open(str(output), readonly=readonly, asksave=False):
                raise RuntimeError("Origin could not reopen S34")
        graphs, books = tuple(self.op.pages("g")), tuple(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("Origin S34 must retain one graph and one source workbook")
        self.graph, self.book = graphs[0], books[0]
        layers = tuple(self.graph)
        if len(layers) != 1:
            raise RuntimeError("Origin S34 lost its native graph layer")
        self.layer, self.sheet = layers[0], self.book[0]
        self.plots = tuple(self.layer.plot_list())

    def reconcile(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> None:
        nyquist = s34_nyquist(document, data)
        axes, styles, legend_visible, equal_axes = self._state(document, actions, nyquist)
        if len(self.plots) != len(nyquist.series):
            raise RuntimeError("Origin S34 official route returned a wrong series count")
        with origin_trace_step(
            "agent_actions_apply",
            details={
                "series_count": len(styles),
                "legend_visible": legend_visible,
                "equal_axes": equal_axes,
            },
        ):
            self._apply_styles(styles)
            self.layer.rescale()
            self._set_title(axes.title)
            self._set_axis("x", axes)
            self._set_axis("y", axes)
            if equal_axes:
                self._set_equal_physical_scale()
            self._set_legend(nyquist, legend_visible)

    def save(self, output: Path) -> None:
        with origin_trace_step("opju_save", details={"filename": output.name}):
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                raise FileExistsError(f"Origin refuses to overwrite S34 artifact: {output}")
            self.op.save(str(output))
            if not output.is_file() or output.stat().st_size <= 0:
                raise RuntimeError("Origin did not save a non-empty S34 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        nyquist = s34_nyquist(document, data)
        axes, styles, legend_visible, equal_axes = self._state(document, actions, nyquist)
        with origin_trace_step("reopened_native_structure_verify"):
            native = self._native_structure(nyquist)
        self.last_native_structure = native
        with origin_trace_step("reopened_agent_edits_verify"):
            self._assert_axes(axes, equal_axes)
            self._assert_styles(styles)
            self._assert_legend(nyquist, legend_visible)
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
                semantic_id=f"legend:{token}.main",
                backend="origin",
                object_kind="legend",
                native_ref=f"graph:{self.graph.name}.layer:1.label:legend",
            ),
        ]
        objects.extend(
            EngineObjectRef(
                semantic_id=f"series:{token}.group_{index + 1}",
                backend="origin",
                object_kind="nyquist_series",
                native_ref=f"graph:{self.graph.name}.layer:1.plot:{index + 1}",
            )
            for index in range(len(self.plots))
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
                        "axes": asdict(axes),
                        "styles": [asdict(style) for style in styles],
                        "legend": legend_visible,
                        "equal_axes": equal_axes,
                        "native_structure": native,
                    },
                )
            ),
        )

    def _write(self, nyquist: NyquistData) -> None:
        series_count = len(nyquist.series)
        self.sheet.cols = series_count * 3
        for index, series in enumerate(nyquist.series):
            self.sheet.from_list(
                index * 2,
                list(series.z_real),
                lname=f"{series.label} / {nyquist.z_real_field_name}",
                axis="X",
            )
            self.sheet.from_list(
                index * 2 + 1,
                list(series.z_imaginary),
                lname=series.label,
                axis="Y",
            )
        for index, series in enumerate(nyquist.series):
            self.sheet.from_list(
                series_count * 2 + index,
                list(series.frequency or ()),
                lname=f"{series.label} / Frequency",
                axis="N",
            )

    def _native_structure(self, nyquist: NyquistData) -> dict[str, JsonValue]:
        series_count = len(nyquist.series)
        if len(tuple(self.graph)) != 1 or len(self.plots) != series_count:
            raise RuntimeError("Origin S34 native series structure changed")
        designations = [
            int(self.sheet.get_int(f"col{index + 1}.type")) for index in range(series_count * 3)
        ]
        expected_designations = [value for _ in nyquist.series for value in (4, 1)] + [
            2
        ] * series_count
        if designations != expected_designations:
            raise RuntimeError("Origin S34 X/Y/frequency designations changed")
        source_ranges: list[dict[str, JsonValue]] = []
        self.graph.activate()
        for index in range(series_count):
            ordinal = index + 1
            self.op.lt_exec(
                f"range __S34P=[{self.graph.name}]1!{ordinal}; "
                f"get __S34P -pt __S34PID{ordinal}; "
                f"range -wx __S34X=__S34P; range -wy __S34Y=__S34P; "
                f"string __S34XS{ordinal}$=%(__S34X); "
                f"string __S34YS{ordinal}$=%(__S34Y);"
            )
            pid = int(self.op.lt_float(f"__S34PID{ordinal}"))
            x_source = str(self.op.get_lt_str(f"__S34XS{ordinal}"))
            y_source = str(self.op.get_lt_str(f"__S34YS{ordinal}"))
            x_letter = _column_letter(index * 2)
            y_letter = _column_letter(index * 2 + 1)
            if pid != 202 or f"!{x_letter}" not in x_source or f"!{y_letter}" not in y_source:
                raise RuntimeError("Origin S34 lost PID 202 or its ordered XY source binding")
            source_ranges.append({"plot": ordinal, "pid": pid, "x": x_source, "y": y_source})
        for index, series in enumerate(nyquist.series):
            self._assert_values(self.sheet.to_list(index * 2), series.z_real, "z_real")
            self._assert_values(
                self.sheet.to_list(index * 2 + 1), series.z_imaginary, "z_imaginary"
            )
            self._assert_values(
                self.sheet.to_list(series_count * 2 + index),
                series.frequency or (),
                "frequency",
            )
        return cast(
            dict[str, JsonValue],
            {
                "official_template": S34_ORIGIN_PROFILE.filename,
                "official_plot_type": 202,
                "ordinary_primitive_fallback_used": False,
                "layer_count": 1,
                "series_count": series_count,
                "source_designations": designations,
                "source_ranges": source_ranges,
                "frequency_columns_plotted": False,
                "row_counts": [len(series.z_real) for series in nyquist.series],
            },
        )

    def _set_title(self, text: str) -> None:
        label = self.layer.label(_TITLE)
        if label is None and text:
            self.layer.activate()
            if not self.layer.obj.LT_execute(f"label -j 1 -n {_TITLE} PlotAgentTitlePlaceholder;"):
                raise RuntimeError("Origin S34 could not create its title")
            label = self.layer.label(_TITLE)
            if label is None:
                raise RuntimeError("Origin S34 could not create its title")
        if label is not None:
            label.text = text
            label.set_int("attach", 1)
            label.set_float("x1", 0.5)
            label.set_float("y1", 0.012)
            label.set_int("fsize", 14)
            label.set_int("fstyle", 0)
            label.set_int("background", 0)
            label.set_int("show", int(bool(text)))

    def _apply_styles(self, styles: tuple[_Style, ...]) -> None:
        if all(style == _Style() for style in styles):
            return
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError("Origin S34 graph name is unsafe for native style edits")
        self.graph.activate()
        self.op.lt_exec(f"range __S34HEAD=[{graph_name}]1!1; set __S34HEAD -gm 1;")
        for ordinal, style in enumerate(styles, start=1):
            commands = [f"range __S34STYLE=[{graph_name}]1!{ordinal}"]
            if style.color is not None:
                commands.extend(
                    (
                        f'set __S34STYLE -cl color("{style.color}")',
                        f'set __S34STYLE -cse color("{style.color}")',
                        f'set __S34STYLE -csf color("{style.color}")',
                    )
                )
            if style.line_width_pt is not None:
                commands.append(f"set __S34STYLE -wp {style.line_width_pt}")
            if style.line_style is not None:
                commands.append(f"set __S34STYLE -d {_LINE_STYLE[style.line_style]}")
            if style.symbol is not None:
                commands.append(f"set __S34STYLE -k {_SYMBOL[style.symbol]}")
            if style.symbol_size_pt is not None:
                commands.append(f"set __S34STYLE -z {style.symbol_size_pt}")
            self.op.lt_exec("; ".join(commands) + ";")

    def _set_axis(self, axis_name: str, state: _AxesState) -> None:
        label_name = "xb" if axis_name == "x" else "yl"
        text = state.x_label if axis_name == "x" else state.y_label
        label = self.layer.label(label_name) or self.layer.add_label(text)
        if label is None:
            raise RuntimeError("Origin S34 has no writable axis label")
        label.text = text
        label.set_int("fstyle", 0)
        label.set_int("show", 1)
        minimum = state.x_minimum if axis_name == "x" else state.y_minimum
        maximum = state.x_maximum if axis_name == "x" else state.y_maximum
        reverse = state.x_reverse if axis_name == "x" else state.y_reverse
        axis = self.layer.axis(axis_name)
        if minimum is not None and maximum is not None:
            begin, end = minimum, maximum
            if reverse:
                begin, end = end, begin
            axis.set_limits(begin, end)
        elif reverse:
            limits = tuple(float(value) for value in axis.limits)
            axis.set_limits(limits[1], limits[0], limits[2])

    def _set_equal_physical_scale(self) -> None:
        x_from, x_to, _ = self.layer.xlim
        y_from, y_to, _ = self.layer.ylim
        x_span, y_span = abs(float(x_to) - float(x_from)), abs(float(y_to) - float(y_from))
        page_width = float(self.graph.get_float("width"))
        page_height = float(self.graph.get_float("height"))
        if min(x_span, y_span, page_width, page_height) <= 0:
            raise RuntimeError("Origin S34 cannot establish an equal physical scale")
        ratio = (x_span / y_span) * (page_height / page_width)
        maximum = 68.0
        if ratio >= 1.0:
            width, height = maximum, maximum / ratio
        else:
            width, height = maximum * ratio, maximum
        if min(width, height) < 18.0:
            raise ValueError("S34 data aspect is too extreme for an editable equal-scale graph")
        self.layer.set_float("width", width)
        self.layer.set_float("height", height)

    def _set_legend(self, nyquist: NyquistData, visible: bool) -> None:
        legend = self.layer.label("legend")
        if legend is None:
            self.layer.activate()
            self.layer.obj.LT_execute("legend")
            legend = self.layer.label("legend")
        if legend is None:
            raise RuntimeError("Origin S34 has no writable legend")
        legend.text = "\n".join(
            f"\\l({index + 1}, style:sls) {series.label}"
            for index, series in enumerate(nyquist.series)
        )
        legend.set_int("show", int(visible))
        legend.set_int("link", 0)

    def _assert_axes(self, state: _AxesState, equal_axes: bool) -> None:
        for name, expected in (("xb", state.x_label), ("yl", state.y_label)):
            label = self.layer.label(name)
            if label is None or label.text != expected or label.get_int("show") == 0:
                raise RuntimeError(f"Origin S34 axis label {name} changed")
        title = self.layer.label(_TITLE)
        if state.title and (
            title is None
            or title.text != state.title
            or title.get_int("show") == 0
            or title.get_int("attach") != 1
            or not isclose(title.get_float("x1"), 0.5, abs_tol=1e-8)
            or not isclose(title.get_float("y1"), 0.012, abs_tol=1e-8)
        ):
            raise RuntimeError("Origin S34 title changed")
        if equal_axes:
            snapshot = self._equal_scale_snapshot()
            if float(snapshot["relative_error"]) > 0.02:
                raise RuntimeError("Origin S34 equal physical axis scale changed")

    def _assert_styles(self, styles: tuple[_Style, ...]) -> None:
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError("Origin S34 graph name is unsafe for native style readback")
        self.graph.activate()
        for ordinal, style in enumerate(styles, start=1):
            if style == _Style():
                continue
            self.op.lt_exec(
                f"range __S34STYLE=[{graph_name}]1!{ordinal}; "
                "get __S34STYLE -cl __S34LC; get __S34STYLE -cse __S34SEC; "
                "get __S34STYLE -csf __S34SFC; get __S34STYLE -w __S34LW; "
                "get __S34STYLE -d __S34LS; get __S34STYLE -k __S34SK; "
                "get __S34STYLE -z __S34SZ;"
            )
            if style.color is not None:
                expected_color = int(self.op.lt_float(f'color("{style.color}")'))
                if any(
                    int(self.op.lt_float(name)) != expected_color
                    for name in ("__S34LC", "__S34SEC", "__S34SFC")
                ):
                    raise RuntimeError("Origin S34 series color changed")
            if style.line_width_pt is not None and not isclose(
                float(self.op.lt_float("__S34LW")) / 500.0,
                style.line_width_pt,
                abs_tol=0.01,
            ):
                raise RuntimeError("Origin S34 line width changed")
            if (
                style.line_style is not None
                and int(self.op.lt_float("__S34LS")) != (_LINE_STYLE[style.line_style])
            ):
                raise RuntimeError("Origin S34 line style changed")
            if (
                style.symbol is not None
                and int(self.op.lt_float("__S34SK")) != (_SYMBOL[style.symbol])
            ):
                raise RuntimeError("Origin S34 symbol changed")
            if style.symbol_size_pt is not None and not isclose(
                float(self.op.lt_float("__S34SZ")),
                style.symbol_size_pt,
                abs_tol=0.01,
            ):
                raise RuntimeError("Origin S34 symbol size changed")

    def _assert_legend(self, nyquist: NyquistData, visible: bool) -> None:
        legend = self.layer.label("legend")
        if visible:
            if legend is None or legend.get_int("show") == 0:
                raise RuntimeError("Origin S34 legend disappeared")
            text = str(legend.text)
            if text.count(r"\l(") != len(nyquist.series) or any(
                series.label not in text for series in nyquist.series
            ):
                raise RuntimeError("Origin S34 legend entries changed")
        elif legend is not None and legend.get_int("show") != 0:
            raise RuntimeError("Origin S34 hidden legend reappeared")

    def _equal_scale_snapshot(self) -> dict[str, float]:
        x_from, x_to, _ = self.layer.xlim
        y_from, y_to, _ = self.layer.ylim
        page_width = float(self.graph.get_float("width"))
        page_height = float(self.graph.get_float("height"))
        layer_width = float(self.layer.get_float("width"))
        layer_height = float(self.layer.get_float("height"))
        physical_width = page_width * layer_width / 100.0
        physical_height = page_height * layer_height / 100.0
        x_units = abs(float(x_to) - float(x_from)) / physical_width
        y_units = abs(float(y_to) - float(y_from)) / physical_height
        if not all(isfinite(value) and value > 0 for value in (x_units, y_units)):
            raise RuntimeError("Origin S34 equal-scale readback is invalid")
        return {
            "x_units_per_physical": x_units,
            "y_units_per_physical": y_units,
            "relative_error": abs(x_units - y_units) / max(x_units, y_units),
        }

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        nyquist: NyquistData,
    ) -> tuple[_AxesState, tuple[_Style, ...], bool, bool]:
        document.plot_id.removeprefix("plot:")
        axes = _AxesState(
            x_label=nyquist.z_real_field_name,
            y_label=nyquist.z_imaginary_field_name,
        )
        styles = tuple(_Style() for _series in nyquist.series)
        legend_visible, equal_axes = len(nyquist.series) > 1, True
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetChartParameter):
                if (
                    action.target != document.plot_id
                    or action.parameter != "equal_axes"
                    or (not isinstance(action.value, bool))
                ):
                    raise ValueError("S34 equal_axes must be boolean")
                equal_axes = action.value
            else:
                raise ValueError(f"Origin S34 cannot apply {action.operation}")
        return axes, styles, legend_visible, equal_axes

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[float, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin S34 {role} row count changed")
        for observed, wanted in zip(actual, expected, strict=True):
            value = float(cast(Any, observed))
            if isnan(value) or not isclose(value, wanted, rel_tol=0.0, abs_tol=1e-10):
                raise RuntimeError(f"Origin S34 {role} values changed")


def _column_letter(zero_based: int) -> str:
    value = zero_based + 1
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def execute_s34_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    project = S34OriginProject(op)
    project.create(install_dir, request.document, request.data)
    project.reconcile(request.document, request.actions, request.data)
    project.save(output)
    reopened = S34OriginProject(op)
    reopened.open(output, readonly=True)
    return reopened.verify(request.document, request.actions, request.data)
