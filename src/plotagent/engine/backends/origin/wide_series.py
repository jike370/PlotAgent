"""Official-template binders for dynamic X03/X39/X40 wide-series plots."""

from __future__ import annotations

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
from plotagent.engine.profile_data import (
    LollipopData,
    TransposedSeriesData,
    transposed_series,
    x03_lollipop,
)
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import (
    X03_ORIGIN_PROFILE,
    X39_ORIGIN_PROFILE,
    X40_ORIGIN_PROFILE,
    OriginTemplateProfile,
    resolve_official_template,
)
from .trace import origin_trace_step, record_origin_trace

_LINE_STYLE = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}
_SYMBOL_CODES = {"circle": 2, "square": 1, "triangle": 3, "triangle_up": 3, "diamond": 5}
_TITLE_NAME = "_ENGINE_TITLE"
_X03_OFFICIAL_MENU_COMMAND = (
    "worksheet -s 1 0 {last_column} 0; "
    "run.section(Plot,general,201 Lollipop 0);"
)


def _safe_label(value: str) -> str:
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


def _effective_actions(actions: tuple[PlotEngineAction, ...]) -> tuple[PlotEngineAction, ...]:
    last_binding = max(
        (index for index, action in enumerate(actions) if isinstance(action, BindFields)),
        default=-1,
    )
    return tuple(
        action
        for index, action in enumerate(actions)
        if not (isinstance(action, SetSeriesStyle) and index < last_binding)
    )


class WideSeriesOriginProject:
    def __init__(self, op: Any, *, profile_id: Literal["X03", "X39", "X40"]) -> None:
        self.op = op
        self.profile_id = profile_id
        self.profile: OriginTemplateProfile = {
            "X03": X03_ORIGIN_PROFILE,
            "X39": X39_ORIGIN_PROFILE,
            "X40": X40_ORIGIN_PROFILE,
        }[profile_id]
        self.graph: Any = None
        self.layer: Any = None
        self.sheet: Any = None
        self.plots: list[Any] = []

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
            book = self.op.new_book("w", f"D{token}", hidden=True)
            if book is None:
                raise RuntimeError(f"Origin could not create the {self.profile_id} workbook")
            self.sheet = book[0]
            if self.profile_id == "X03":
                self._remove_workbook_residue(book)
        if self.profile_id == "X03":
            lollipop = x03_lollipop(document, data)
            with origin_trace_step(
                "source_data_write",
                details={
                    "column_count": len(lollipop.columns.values) + 1,
                    "row_count": len(lollipop.categories),
                },
            ):
                self._write_lollipop(lollipop)
            command = _X03_OFFICIAL_MENU_COMMAND.format(
                last_column=len(lollipop.columns.values) + 1
            )
            with origin_trace_step(
                "official_plot_command_execute",
                details={"labtalk": command, "template_filename": template.name},
            ):
                self.sheet.activate()
                self.op.lt_exec(command)
            with origin_trace_step("native_structure_readback"):
                graphs = list(self.op.pages("g"))
                if len(graphs) != 1:
                    raise RuntimeError("Origin Lollipop command must create exactly one graph")
                self.graph = graphs[0]
                self.graph.name = f"G{token}"
                self.graph.lname = f"X03 {template.stem} / {document.plot_id}"
                self.layer = self.graph[0]
                self.plots = [
                    plot for plot in self.layer.plot_list() if plot.get_int("show") != 0
                ]
                native = self._assert_official_x03_structure(lollipop)
            record_origin_trace("native_lollipop_confirmed", "completed", details=native)
            self.layer.rescale()
            return

        # X39 and X40 are intentionally left on their existing implementation
        # until the box-based row-wise group interface has live readback proof.
        # Their official menu commands create one native type-206 object rather
        # than one ordinary XY plot per source row; substituting that structure
        # without a verified action/readback mapping would be another guess.
        self.graph = self.op.new_graph(
            f"G{token}",
            template=str(template.with_suffix(template.suffix.lower())),
            hidden=True,
        )
        if self.graph is None:
            raise RuntimeError(
                f"Origin could not create {self.profile_id} from {self.profile.filename}"
            )
        self.layer = self.graph[0]
        for plot in self.layer.plot_list():
            plot.set_int("show", 0)
        self.plots = []
        series = transposed_series(document, data, profile_id=self.profile_id)
        self._write_transposed(series)
        for index in range(len(series.rows)):
            self._add_plot(colx=0, coly=index + 1)
        self.layer.rescale()

    def _remove_workbook_residue(self, authoritative_book: Any) -> None:
        for residue in tuple(self.op.pages("w")):
            if residue.name == authoritative_book.name:
                continue
            if residue.name == "Book1":
                residue.destroy()

    def _add_plot(self, *, colx: int, coly: int) -> None:
        plot = self.layer.add_plot(self.sheet, coly=coly, colx=colx, type="?")
        if plot is None:
            raise RuntimeError(
                f"Origin {self.profile.filename} rejected native plot {len(self.plots) + 1}"
            )
        self.plots.append(plot)

    def reopen(self, project_path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=True, asksave=False):
            raise RuntimeError(
                f"fresh Origin session could not reopen the staged {self.profile_id} project"
            )
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError(
                f"fresh {self.profile_id} project has unexpected graph or workbook count"
            )
        self.graph = graphs[0]
        self.layer = self.graph[0]
        self.plots = [plot for plot in self.layer.plot_list() if plot.get_int("show") != 0]
        self.sheet = books[0][0]

    def apply(
        self,
        document: PlotDocument,
        action: PlotEngineAction,
        data: EngineDataView,
    ) -> None:
        token = document.plot_id.removeprefix("plot:")
        if isinstance(action, (CreatePlot, BindFields)):
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError(f"{self.profile_id} title target does not belong to this plot")
            title = self.layer.label(_TITLE_NAME)
            if title is None:
                title = self.layer.add_label(action.text, 40, 2)
                if title is None:
                    raise RuntimeError(f"Origin could not create the {self.profile_id} title")
                title.name = _TITLE_NAME
            title.text = action.text
            title.set_int("show", 1)
            return
        if isinstance(action, SetAxis):
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
            if axis_name is None:
                raise ValueError(f"{self.profile_id} axis target does not belong to this plot")
            axis = self.layer.axis(axis_name)
            if action.scale is not None:
                categorical_axis = "y" if self.profile_id == "X03" else "x"
                if axis_name == categorical_axis:
                    if action.scale != "categorical":
                        raise ValueError(
                            f"Origin {self.profile_id} {axis_name.upper()} axis is categorical"
                        )
                else:
                    if action.scale not in {"linear", "log10"}:
                        raise ValueError(
                            f"Origin {self.profile_id} {axis_name.upper()} axis supports "
                            "linear or log10"
                        )
                    axis.scale = action.scale
            if action.minimum is not None and action.maximum is not None:
                begin, end = action.minimum, action.maximum
                if action.reverse:
                    begin, end = end, begin
                axis.set_limits(begin, end)
            elif action.reverse is not None:
                begin, end, step = (float(value) for value in axis.limits)
                should_reverse = begin < end if action.reverse else begin > end
                if should_reverse:
                    axis.set_limits(end, begin, abs(step))
            if action.label is not None:
                label = self.layer.label("xb" if axis_name == "x" else "yl")
                if label is None:
                    label = self.layer.add_label(action.label)
                if label is None:
                    raise RuntimeError(f"Origin {self.profile_id} has no writable axis label")
                label.text = action.label
                label.set_int("show", 1)
            return
        if isinstance(action, SetSeriesStyle):
            ordinal = self._series_ordinal(action.target, token)
            plot = self.plots[ordinal - 1]
            if action.color is not None:
                plot.color = action.color
            if action.line_width_pt is not None:
                plot.set_float("line.width", action.line_width_pt)
            if action.line_style is not None:
                if action.line_style == "none" and self.profile_id != "X03":
                    raise ValueError(f"Origin {self.profile_id} cannot hide its connector")
                plot.set_int(
                    "line.style",
                    -1 if action.line_style == "none" else _LINE_STYLE[action.line_style],
                )
            if action.symbol is not None:
                try:
                    plot.symbol_kind = _SYMBOL_CODES[action.symbol]
                except KeyError as error:
                    raise ValueError(
                        f"Origin {self.profile_id} does not support symbol {action.symbol}"
                    ) from error
            if action.symbol_size_pt is not None:
                plot.symbol_size = action.symbol_size_pt
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError(f"{self.profile_id} legend target does not belong to this plot")
            legend = self.layer.label("legend")
            if action.visible and legend is None:
                self.layer.activate()
                if not self.layer.obj.LT_execute("legend"):
                    raise RuntimeError(f"Origin could not create the {self.profile_id} legend")
                legend = self.layer.label("legend")
            if legend is not None and action.visible is not None:
                if self.profile_id != "X40":
                    legend.text = "\n".join(
                        f"\\l({index}) {_safe_label(label)}"
                        for index, label in enumerate(self._legend_labels(document, data), start=1)
                    )
                    legend.set_int("link", 1)
                legend.set_int("show", int(action.visible))
            return
        raise ValueError(f"Origin {self.profile_id} binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output_path))
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError(f"Origin did not save a non-empty {self.profile_id} project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        expected = self._expected_columns(document, data)
        if len(self.plots) != len(expected) - 1:
            raise RuntimeError(f"Origin {self.profile_id} native plot count differs after reopen")
        for index, values in enumerate(expected):
            self._assert_values(self.sheet.to_list(index), values, f"column {index + 1}")
        token = document.plot_id.removeprefix("plot:")
        snapshot: dict[str, object] = {"profile": self.profile_id, "series": len(self.plots)}
        if self.profile_id == "X03":
            snapshot.update(self._assert_official_x03_structure(x03_lollipop(document, data)))
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if title is None or title.text != action.text or not title.get_int("show"):
                    raise RuntimeError(f"Origin {self.profile_id} title did not survive readback")
            elif isinstance(action, SetSeriesStyle):
                ordinal = self._series_ordinal(action.target, token)
                plot = self.plots[ordinal - 1]
                if action.color is not None and tuple(plot.color) != self._hex_rgb(action.color):
                    raise RuntimeError(
                        f"Origin {self.profile_id} series color did not survive readback"
                    )
                if action.symbol_size_pt is not None and (
                    abs(float(plot.symbol_size) - action.symbol_size_pt) > 0.01
                ):
                    raise RuntimeError(
                        f"Origin {self.profile_id} symbol size did not survive readback"
                    )
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layer.label("legend")
                if legend is None or bool(legend.get_int("show")) != action.visible:
                    raise RuntimeError(
                        f"Origin {self.profile_id} legend visibility did not survive readback"
                    )
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
                    semantic_id=f"series:{token}.{self._series_key}_{index}",
                    backend="origin",
                    object_kind=f"{self.profile_id.lower()}_native_series",
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

    @property
    def _series_key(self) -> str:
        return "column" if self.profile_id == "X03" else "row"

    def _series_ordinal(self, target: str, token: str) -> int:
        prefix = f"series:{token}.{self._series_key}_"
        suffix = target.removeprefix(prefix) if target.startswith(prefix) else ""
        if not suffix.isdigit() or not 1 <= int(suffix) <= len(self.plots):
            raise ValueError(f"{self.profile_id} series target is outside materialized data")
        return int(suffix)

    def _write_lollipop(self, lollipop: LollipopData) -> None:
        self.sheet.from_list(
            0,
            list(lollipop.categories),
            lname=lollipop.category_field_name,
            axis="X",
        )
        # Origin 2024's external Column proxy does not expose the newer
        # SetAsCategorical API.  The official sample uses auto-generated
        # categorical levels on the associated X column.
        self.sheet.lt_exec(
            "wks.col1.categorical.type=2; wks.col1.categorical.sort=0;"
        )
        for index, (label, values) in enumerate(
            zip(lollipop.columns.labels, lollipop.columns.values, strict=True),
            start=1,
        ):
            self.sheet.from_list(index, list(values), lname=label, axis="Y")

    def _assert_official_x03_structure(self, lollipop: LollipopData) -> dict[str, object]:
        self.sheet.activate()
        self.op.lt_exec(
            "__X03CATTYPE=wks.col1.categorical.type; "
            "__X03CATSORT=wks.col1.categorical.sort;"
        )
        category_type = int(self.op.lt_float("__X03CATTYPE"))
        category_sort = int(self.op.lt_float("__X03CATSORT"))
        if category_type != 2 or category_sort != 0:
            raise RuntimeError(
                "Origin X03 categories must preserve first source appearance; "
                f"observed type={category_type}, sort={category_sort}"
            )
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe Origin X03 graph name: {graph_name!r}")
        self.graph.activate()
        self.op.lt_exec("page.active=1; layer -c; __X03COUNT=count;")
        plot_count = int(self.op.lt_float("__X03COUNT"))
        plot_types: list[int] = []
        for index in range(1, plot_count + 1):
            self.op.lt_exec(
                f"range __X03P=[{graph_name}]1!{index}; "
                f"get __X03P -pt __X03PT{index};"
            )
            plot_types.append(int(self.op.lt_float(f"__X03PT{index}")))
        if len(plot_types) != len(lollipop.columns.values) or any(
            plot_type != 201 for plot_type in plot_types
        ):
            raise RuntimeError(
                "Origin X03 native Lollipop signature differs from the unverified "
                f"assumption: observed plot_types={plot_types}, "
                f"source_y_count={len(lollipop.columns.values)}"
            )
        expected_designations = [4, *([1] * len(lollipop.columns.values))]
        actual_designations = [
            int(self.sheet.get_int(f"col{index + 1}.type"))
            for index in range(len(expected_designations))
        ]
        if actual_designations != expected_designations:
            raise RuntimeError(
                "Origin X03 worksheet designation changed: "
                f"expected={expected_designations}, actual={actual_designations}"
            )
        return {
            "official_menu_command": _X03_OFFICIAL_MENU_COMMAND.format(
                last_column=len(lollipop.columns.values) + 1
            ),
            "native_plot_types": plot_types,
            "worksheet_designations": actual_designations,
            "category_order": "first_source_appearance",
            "axes_exchanged_and_drop_to_follow_plot": "requires_live_theme_readback",
        }

    def _write_transposed(self, series: TransposedSeriesData) -> None:
        self.sheet.from_list(
            0,
            list(range(1, len(series.axis_labels) + 1)),
            lname="Series",
            axis="X",
        )
        for index, (label, values) in enumerate(
            zip(series.row_labels, series.rows, strict=True),
            start=1,
        ):
            self.sheet.from_list(index, list(values), lname=label, axis="Y")
        self.layer.set_int("x.label.type", 10)
        self.layer.set_str(
            "x.label.string",
            " ".join(f'"{_safe_label(label)}"' for label in series.axis_labels),
        )

    def _expected_columns(
        self, document: PlotDocument, data: EngineDataView
    ) -> tuple[tuple[object, ...], ...]:
        if self.profile_id == "X03":
            lollipop = x03_lollipop(document, data)
            return (lollipop.categories, *lollipop.columns.values)
        series = transposed_series(document, data, profile_id=self.profile_id)
        return (
            tuple(range(1, len(series.axis_labels) + 1)),
            *series.rows,
        )

    def _legend_labels(self, document: PlotDocument, data: EngineDataView) -> tuple[str, ...]:
        if self.profile_id == "X03":
            return x03_lollipop(document, data).columns.labels
        return transposed_series(document, data, profile_id=self.profile_id).row_labels

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[object, ...], name: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin {name} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
                if abs(float(cast(Any, observed)) - float(wanted)) <= 1e-9:
                    continue
            elif observed == wanted:
                continue
            raise RuntimeError(f"Origin {name} values differ after reopen")

    @staticmethod
    def _hex_rgb(value: str) -> tuple[int, int, int]:
        return cast(
            tuple[int, int, int],
            tuple(int(value[index : index + 2], 16) for index in (1, 3, 5)),
        )


def _execute(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
    profile_id: Literal["X03", "X39", "X40"],
) -> EngineReadback:
    project = WideSeriesOriginProject(op, profile_id=profile_id)
    project.create(install_dir, request.document, request.data)
    actions = _effective_actions(request.actions)
    for action in actions:
        project.apply(request.document, action, request.data)
    project.save(output)
    reopened = WideSeriesOriginProject(op, profile_id=profile_id)
    reopened.reopen(output)
    return reopened.verify(request.document, actions, request.data)


def execute_x03_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "X03")


def execute_x39_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "X39")


def execute_x40_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "X40")
