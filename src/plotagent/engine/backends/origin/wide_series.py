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
    WideSeriesData,
    wide_series,
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
_LINE_TYPE = {"solid": 1, "dash": 2, "dot": 3, "dash_dot": 4}
_SYMBOL_CODES = {"circle": 2, "square": 1, "triangle": 3, "triangle_up": 3, "diamond": 5}
_TITLE_NAME = "_ENGINE_TITLE"
_X03_OFFICIAL_MENU_COMMAND = (
    "worksheet -s 1 0 {last_column} 0; "
    "run.section(Plot,general,201 Lollipop 0);"
)
_X39_OFFICIAL_MENU_COMMAND = (
    "worksheet -s 1 0 {last_column} 0; run.section(Plot,LineSeries);"
)
_X40_OFFICIAL_MENU_COMMAND = (
    "worksheet -s 1 0 {last_column} 0; run.section(Plot,BeforeAfter);"
)


def _pipe_strings(value: str) -> tuple[str, ...]:
    return tuple(item for item in value.split("|") if item)


def _pipe_ints(value: str) -> tuple[int, ...]:
    return tuple(int(item) for item in _pipe_strings(value))


def read_wide_series_native_snapshot(
    op: Any,
    sheet: Any,
    graph: Any,
    *,
    profile_id: Literal["X39", "X40"],
    column_count: int,
) -> dict[str, object]:
    """Read the documented type-206 row-wise signature without ``plot_list``.

    Origin's Python ``GraphLayer_GetDataPlots`` bridge is unstable for the
    box-chart-backed Line Series family.  This probe therefore uses only the
    documented LabTalk plot/group objects, ``doc -e D`` iteration, worksheet
    dataset names and worksheet label-row accessors.
    """

    if column_count < 2:
        raise ValueError("row-wise Line Series snapshots require at least two Y columns")
    graph_name = str(graph.name)
    if not graph_name.replace("_", "").isalnum():
        raise RuntimeError(f"unsafe Origin {profile_id} graph name: {graph_name!r}")
    probe = f"__{profile_id}"
    sheet.activate()
    source_dataset_names: list[str] = []
    for index in range(1, column_count + 1):
        variable = f"{probe}SOURCE{index}"
        op.lt_exec(f"{variable}$=nameof(!wcol({index}))$;")
        source_dataset_names.append(str(op.get_lt_str(variable)))
    graph.activate()
    op.lt_exec(
        f'page.active=1; {probe}COUNT=0; {probe}NAMES$=""; '
        f'{probe}MEMBERS$=""; {probe}HEADS$=""; '
        f"doc -e D {{{probe}COUNT={probe}COUNT+1; "
        f'{probe}NAMES$={probe}NAMES$+"|%C"; '
        f'{probe}MEMBERS$={probe}MEMBERS$+"|$(layer.plot0.index)"; '
        f'{probe}HEADS$={probe}HEADS$+"|$(layer.plot.index)";}};'
    )
    member_count = int(op.lt_float(f"{probe}COUNT"))
    member_dataset_names = _pipe_strings(str(op.get_lt_str(f"{probe}NAMES")))
    member_indices = _pipe_ints(str(op.get_lt_str(f"{probe}MEMBERS")))
    group_head_indices = _pipe_ints(str(op.get_lt_str(f"{probe}HEADS")))
    native_plot_types = tuple(
        int(op.lt_float(f"layer.plot{index}.pid"))
        for index in range(1, member_count + 1)
    )
    plot_indices = tuple(
        int(op.lt_float(f"layer.plot{index}.index"))
        for index in range(1, member_count + 1)
    )
    member_colors = tuple(
        int(op.lt_float(f"layer.plot{index}.color"))
        for index in range(1, member_count + 1)
    )
    member_symbol_kinds = tuple(
        int(op.lt_float(f"layer.plot{index}.symbol.kind"))
        for index in range(1, member_count + 1)
    )
    member_symbol_sizes = tuple(
        float(op.lt_float(f"layer.plot{index}.symbol.size"))
        for index in range(1, member_count + 1)
    )
    values = tuple(tuple(sheet.to_list(index)) for index in range(column_count))
    long_names = tuple(str(value) for value in sheet.get_labels("L")[:column_count])
    comments = tuple(str(value) for value in sheet.get_labels("C")[:column_count])
    designations = tuple(
        int(sheet.get_int(f"col{index}.type")) for index in range(1, column_count + 1)
    )
    row_counts = tuple(len(column) for column in values)
    unique_heads = tuple(dict.fromkeys(group_head_indices))
    return {
        "profile_id": profile_id,
        "graph_name": graph_name,
        "source_layout": "worksheet_wide",
        "worksheet_column_count": int(sheet.cols),
        "source_column_count": column_count,
        "source_row_counts": row_counts,
        "worksheet_designations": designations,
        "long_names": long_names,
        "comments": comments,
        "source_dataset_names": tuple(source_dataset_names),
        "native_member_count": member_count,
        "native_plot_types": native_plot_types,
        "plot_indices": plot_indices,
        "member_colors": member_colors,
        "member_symbol_kinds": member_symbol_kinds,
        "member_symbol_sizes": member_symbol_sizes,
        "iterated_member_indices": member_indices,
        "group_head_indices": group_head_indices,
        "native_group_count": len(unique_heads),
        "native_group_heads": unique_heads,
        "member_dataset_names": member_dataset_names,
        "members_bind_source_columns": (
            member_dataset_names == tuple(source_dataset_names)
        ),
        "boxchart_type": int(op.lt_float("layer.plot1.boxchart.type")),
        "subgroup_size": int(op.lt_float("layer.plot1.subgroupsize")),
        "subgroup_label_row": int(op.lt_float("layer.plot1.subgrouplabelrow")),
        "use_properties_by_subgroup": int(
            op.lt_float("layer.plot1.usepropssubgroup")
        ),
        "connector_color": int(op.lt_float("layer.plot1.color")),
        "connector_line_width": float(op.lt_float("layer.plot1.line.width")),
        "connector_line_type": int(op.lt_float("layer.plot1.line.type")),
    }


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
        self.native_member_count = 0
        self.native_snapshot: dict[str, object] = {}

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

        series = wide_series(document, data, profile_id=self.profile_id)
        with origin_trace_step(
            "source_data_write",
            details={
                "column_count": len(series.column_values),
                "row_count": series.row_count,
                "source_layout": "worksheet_wide",
            },
        ):
            self._write_wide(series)
            self._remove_workbook_residue(book)
        command_template = (
            _X39_OFFICIAL_MENU_COMMAND
            if self.profile_id == "X39"
            else _X40_OFFICIAL_MENU_COMMAND
        )
        command = command_template.format(last_column=len(series.column_values))
        with origin_trace_step(
            "official_plot_command_execute",
            details={"labtalk": command, "template_filename": template.name},
        ):
            self.sheet.activate()
            self.op.lt_exec(command)
        with origin_trace_step("native_structure_readback"):
            graphs = list(self.op.pages("g"))
            if len(graphs) != 1:
                raise RuntimeError(
                    f"Origin {self.profile_id} official menu command must create one graph"
                )
            if len(list(self.op.pages("w"))) != 1:
                raise RuntimeError(
                    f"Origin {self.profile_id} must preserve one authoritative wide workbook"
                )
            self.graph = graphs[0]
            self.graph.name = f"G{token}"
            self.graph.lname = f"{self.profile_id} {template.stem} / {document.plot_id}"
            self.layer = self.graph[0]
            self.native_snapshot = self._assert_official_wide_structure(series)
        record_origin_trace(
            "native_row_wise_group_confirmed",
            "completed",
            details=self.native_snapshot,
        )
        self.layer.rescale()

    def _remove_workbook_residue(self, authoritative_book: Any) -> None:
        for residue in tuple(self.op.pages("w")):
            if residue.name == authoritative_book.name:
                continue
            if residue.name == "Book1":
                residue.destroy()

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
        self.plots = (
            [plot for plot in self.layer.plot_list() if plot.get_int("show") != 0]
            if self.profile_id == "X03"
            else []
        )
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
            if self.profile_id != "X03":
                self._apply_wide_series_style(action, token)
                return
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
                legend.text = "\n".join(
                    f"\\l({index}) {_safe_label(label)}"
                    for index, label in enumerate(self._legend_labels(document, data), start=1)
                )
                legend.set_int("link", 1)
                legend.set_int("show", int(action.visible))
            return
        raise ValueError(f"Origin {self.profile_id} binder cannot apply {action.operation}")

    def _apply_wide_series_style(self, action: SetSeriesStyle, token: str) -> None:
        self.graph.activate()
        commands = ["page.active=1"]
        if action.target == f"series:{token}.connector":
            if action.symbol is not None or action.symbol_size_pt is not None:
                raise ValueError(
                    f"Origin {self.profile_id} connector supports line style, width and "
                    "color only"
                )
            if action.line_style == "none":
                raise ValueError(
                    f"Origin {self.profile_id} cannot hide its native connector group"
                )
            if action.color is not None:
                commands.append(f"layer.plot1.color=color({action.color})")
            if action.line_width_pt is not None:
                commands.append(f"layer.plot1.line.width={action.line_width_pt:.12g}")
            if action.line_style is not None:
                commands.append(f"layer.plot1.line.type={_LINE_TYPE[action.line_style]}")
        else:
            ordinal = self._series_ordinal(action.target, token)
            if action.line_width_pt is not None or action.line_style is not None:
                raise ValueError(
                    f"Origin {self.profile_id} column targets support marker color, symbol "
                    "and size only"
                )
            if action.color is not None:
                commands.append(f"layer.plot{ordinal}.color=color({action.color})")
            if action.symbol is not None:
                try:
                    symbol = _SYMBOL_CODES[action.symbol]
                except KeyError as error:
                    raise ValueError(
                        f"Origin {self.profile_id} does not support symbol {action.symbol}"
                    ) from error
                commands.append(f"layer.plot{ordinal}.symbol.kind={symbol}")
            if action.symbol_size_pt is not None:
                commands.append(
                    f"layer.plot{ordinal}.symbol.size={action.symbol_size_pt:.12g}"
                )
        if len(commands) > 1:
            self.op.lt_exec("; ".join(commands) + ";")

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
        for index, values in enumerate(expected):
            self._assert_values(self.sheet.to_list(index), values, f"column {index + 1}")
        token = document.plot_id.removeprefix("plot:")
        snapshot: dict[str, object] = {"profile": self.profile_id}
        if self.profile_id == "X03":
            if len(self.plots) != len(expected) - 1:
                raise RuntimeError(
                    "Origin X03 native plot count differs after reopen"
                )
            snapshot["series"] = len(self.plots)
            snapshot.update(self._assert_official_x03_structure(x03_lollipop(document, data)))
        else:
            series = wide_series(document, data, profile_id=self.profile_id)
            snapshot["series"] = len(series.column_values)
            snapshot["connector_groups"] = 1
            snapshot.update(self._assert_official_wide_structure(series))
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if title is None or title.text != action.text or not title.get_int("show"):
                    raise RuntimeError(f"Origin {self.profile_id} title did not survive readback")
            elif isinstance(action, SetSeriesStyle):
                if self.profile_id == "X03":
                    ordinal = self._series_ordinal(action.target, token)
                    plot = self.plots[ordinal - 1]
                    if action.color is not None and tuple(plot.color) != self._hex_rgb(
                        action.color
                    ):
                        raise RuntimeError(
                            "Origin X03 series color did not survive readback"
                        )
                    if action.symbol_size_pt is not None and (
                        abs(float(plot.symbol_size) - action.symbol_size_pt) > 0.01
                    ):
                        raise RuntimeError(
                            "Origin X03 symbol size did not survive readback"
                        )
                else:
                    self._verify_wide_series_style(action, token)
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layer.label("legend")
                if legend is None or bool(legend.get_int("show")) != action.visible:
                    raise RuntimeError(
                        f"Origin {self.profile_id} legend visibility did not survive readback"
                    )
        if self.profile_id == "X03":
            native_series_objects = tuple(
                EngineObjectRef(
                    semantic_id=f"series:{token}.column_{index}",
                    backend="origin",
                    object_kind="x03_native_series",
                    native_ref=f"graph:{self.graph.name}.layer:1.plot:{index}",
                )
                for index in range(1, len(self.plots) + 1)
            )
        else:
            native_series_objects = (
                EngineObjectRef(
                    semantic_id=f"series:{token}.connector",
                    backend="origin",
                    object_kind=f"{self.profile_id.lower()}_native_connector_group",
                    native_ref=f"graph:{self.graph.name}.layer:1.plot-group:1.connect-data",
                ),
                *tuple(
                    EngineObjectRef(
                        semantic_id=f"series:{token}.column_{index}",
                        backend="origin",
                        object_kind=f"{self.profile_id.lower()}_native_column_position",
                        native_ref=f"graph:{self.graph.name}.layer:1.plot:{index}",
                    )
                    for index in range(1, self.native_member_count + 1)
                ),
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
            *native_series_objects,
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

    def _series_ordinal(self, target: str, token: str) -> int:
        prefix = f"series:{token}.column_"
        suffix = target.removeprefix(prefix) if target.startswith(prefix) else ""
        count = len(self.plots) if self.profile_id == "X03" else self.native_member_count
        if not suffix.isdigit() or not 1 <= int(suffix) <= count:
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

    def _write_wide(self, series: WideSeriesData) -> None:
        for index, (label, values) in enumerate(
            zip(series.column_labels, series.column_values, strict=True)
        ):
            self.sheet.from_list(
                index,
                list(values),
                lname=label,
                comments="",
                axis="Y",
            )

    def _assert_official_wide_structure(
        self, series: WideSeriesData
    ) -> dict[str, object]:
        if self.profile_id not in {"X39", "X40"}:
            raise RuntimeError("wide-series structure readback is only valid for X39/X40")
        profile_id = cast(Literal["X39", "X40"], self.profile_id)
        expected_count = len(series.column_values)
        snapshot = read_wide_series_native_snapshot(
            self.op,
            self.sheet,
            self.graph,
            profile_id=profile_id,
            column_count=expected_count,
        )
        self.native_member_count = cast(int, snapshot["native_member_count"])
        if snapshot["worksheet_column_count"] != expected_count:
            raise RuntimeError(
                f"Origin {self.profile_id} worksheet must remain the untransposed "
                f"{expected_count}-column source table: "
                f"actual={snapshot['worksheet_column_count']}"
            )
        expected_designations = (1,) * expected_count
        if snapshot["worksheet_designations"] != expected_designations:
            raise RuntimeError(
                f"Origin {self.profile_id} worksheet must contain only selected Y columns: "
                f"expected={expected_designations}, "
                f"actual={snapshot['worksheet_designations']}"
            )
        expected_rows = (series.row_count,) * expected_count
        if snapshot["source_row_counts"] != expected_rows:
            raise RuntimeError(
                f"Origin {self.profile_id} wide worksheet changed row shape: "
                f"expected={expected_rows}, actual={snapshot['source_row_counts']}"
            )
        if snapshot["long_names"] != series.column_labels:
            raise RuntimeError(
                f"Origin {self.profile_id} Long Name metadata changed: "
                f"expected={series.column_labels}, actual={snapshot['long_names']}"
            )
        if snapshot["comments"] != ("",) * expected_count:
            raise RuntimeError(
                f"Origin {self.profile_id} renderer must preserve empty source Comments: "
                f"actual={snapshot['comments']}"
            )
        plot_types = cast(tuple[int, ...], snapshot["native_plot_types"])
        if self.native_member_count != expected_count or any(
            plot_type != 206 for plot_type in plot_types
        ):
            raise RuntimeError(
                f"Origin {self.profile_id} must keep one type-206 group member per source "
                f"Y column: count={self.native_member_count}, plot_types={plot_types}, "
                f"source_y_count={expected_count}"
            )
        if snapshot["boxchart_type"] != 2:
            raise RuntimeError(
                f"Origin {self.profile_id} must remain a data-only BoxChart row-wise "
                f"group: boxchart.type={snapshot['boxchart_type']}"
            )
        expected_indices = tuple(range(1, expected_count + 1))
        if snapshot["plot_indices"] != expected_indices or snapshot[
            "iterated_member_indices"
        ] != expected_indices:
            raise RuntimeError(
                f"Origin {self.profile_id} type-206 member order changed: "
                f"plot_indices={snapshot['plot_indices']}, "
                f"iterated={snapshot['iterated_member_indices']}"
            )
        if snapshot["native_group_count"] != 1 or snapshot[
            "native_group_heads"
        ] != (1,):
            raise RuntimeError(
                f"Origin {self.profile_id} must retain one native plot group headed by "
                f"member 1: heads={snapshot['group_head_indices']}"
            )
        if not snapshot["members_bind_source_columns"]:
            raise RuntimeError(
                f"Origin {self.profile_id} members no longer bind the unchanged source "
                f"Y columns: source={snapshot['source_dataset_names']}, "
                f"members={snapshot['member_dataset_names']}"
            )
        subgroup_size = cast(int, snapshot["subgroup_size"])
        if self.profile_id == "X40" and subgroup_size != 2:
            raise RuntimeError(
                "Origin X40 official BeforeAfter group must keep Subgroup Size=2; "
                f"observed={subgroup_size}"
            )
        command = (
            _X39_OFFICIAL_MENU_COMMAND
            if self.profile_id == "X39"
            else _X40_OFFICIAL_MENU_COMMAND
        ).format(last_column=expected_count)
        return {
            **snapshot,
            "official_menu_command": command,
            "source_row_count": series.row_count,
            "connector_semantics": "manual_live_plot_details_gate",
        }

    def _verify_wide_series_style(self, action: SetSeriesStyle, token: str) -> None:
        self.graph.activate()
        self.op.lt_exec("page.active=1;")
        if action.target == f"series:{token}.connector":
            prefix = "layer.plot1"
            if action.color is not None:
                self._assert_lt_float(
                    f"{prefix}.color",
                    self.op.lt_float(f"color({action.color})"),
                    "connector color",
                )
            if action.line_width_pt is not None:
                self._assert_lt_float(
                    f"{prefix}.line.width",
                    action.line_width_pt,
                    "connector line width",
                )
            if action.line_style is not None:
                self._assert_lt_float(
                    f"{prefix}.line.type",
                    float(_LINE_TYPE[action.line_style]),
                    "connector line type",
                )
            return
        ordinal = self._series_ordinal(action.target, token)
        prefix = f"layer.plot{ordinal}"
        if action.color is not None:
            self._assert_lt_float(
                f"{prefix}.color",
                self.op.lt_float(f"color({action.color})"),
                f"column {ordinal} marker color",
            )
        if action.symbol is not None:
            self._assert_lt_float(
                f"{prefix}.symbol.kind",
                float(_SYMBOL_CODES[action.symbol]),
                f"column {ordinal} symbol",
            )
        if action.symbol_size_pt is not None:
            self._assert_lt_float(
                f"{prefix}.symbol.size",
                action.symbol_size_pt,
                f"column {ordinal} symbol size",
            )

    def _assert_lt_float(self, expression: str, expected: float, name: str) -> None:
        observed = float(self.op.lt_float(expression))
        if abs(observed - expected) > 0.01:
            raise RuntimeError(
                f"Origin {self.profile_id} {name} did not survive readback: "
                f"expected={expected}, observed={observed}"
            )

    def _expected_columns(
        self, document: PlotDocument, data: EngineDataView
    ) -> tuple[tuple[object, ...], ...]:
        if self.profile_id == "X03":
            lollipop = x03_lollipop(document, data)
            return (lollipop.categories, *lollipop.columns.values)
        series = wide_series(document, data, profile_id=self.profile_id)
        return series.column_values

    def _legend_labels(self, document: PlotDocument, data: EngineDataView) -> tuple[str, ...]:
        if self.profile_id == "X03":
            return x03_lollipop(document, data).columns.labels
        return wide_series(document, data, profile_id=self.profile_id).column_labels

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
