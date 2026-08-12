"""Official-template binders for K09/K10/K11 native column families."""

from __future__ import annotations

from math import isnan
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
    CategorySeriesGrid,
    GroupedIndexedData,
    category_series_grid,
    k09_grouped_indexed_data,
)
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import (
    K09_ORIGIN_PROFILE,
    K10_ORIGIN_PROFILE,
    K11_ORIGIN_PROFILE,
    OriginTemplateProfile,
    resolve_official_template,
)
from .trace import origin_trace_step, record_origin_trace

_TITLE_NAME = "_ENGINE_TITLE"
_K09_OFFICIAL_HELP = "https://docs.originlab.com/origin-help/grouped-column-index-data/"
_K09_OFFICIAL_MENU = "Plot > Categorical: Grouped Columns - Indexed Data"
_K09_OFFICIAL_MENU_ID = 33240
_K09_OFFICIAL_XFUNCTION = "plot_gindexed"
_PALETTE = (
    "#1676D2",
    "#D97800",
    "#299764",
    "#C53D4D",
    "#7656B5",
    "#008A99",
    "#A55A2A",
    "#667085",
)


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


def _effective_actions(
    actions: tuple[PlotEngineAction, ...],
) -> tuple[PlotEngineAction, ...]:
    last_binding = max(
        (index for index, action in enumerate(actions) if isinstance(action, BindFields)),
        default=-1,
    )
    return tuple(
        action
        for index, action in enumerate(actions)
        if not (isinstance(action, SetSeriesStyle) and index < last_binding)
    )


class ColumnFamilyOriginProject:
    """One explicit binder; the official template retains chart semantics."""

    def __init__(
        self,
        op: Any,
        *,
        profile_id: Literal["K09", "K10", "K11"],
    ) -> None:
        self.op = op
        self.profile_id = profile_id
        self.profile: OriginTemplateProfile = {
            "K09": K09_ORIGIN_PROFILE,
            "K10": K10_ORIGIN_PROFILE,
            "K11": K11_ORIGIN_PROFILE,
        }[profile_id]
        self.series_key = "group" if profile_id == "K09" else "component"
        self.graph: Any = None
        self.layer: Any = None
        self.book: Any = None
        self.sheet: Any = None
        self.plots: list[Any] = []
        self._color_overrides: dict[int, str] = {}

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={"template_filename": self.profile.filename},
        ):
            template = resolve_official_template(install_dir, self.profile)
        grid = self._grid(document, data)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError(f"Origin could not create the {self.profile_id} workbook")
        self.book = book
        if self.profile_id == "K09":
            for residue in tuple(self.op.pages("w")):
                if residue.name == "Book1" and residue.name != book.name:
                    residue.destroy()
        self.sheet = book[0]
        if self.profile_id == "K09":
            indexed = k09_grouped_indexed_data(document, data)
            with origin_trace_step(
                "source_data_write",
                details={"column_count": 4, "row_count": len(indexed.values)},
            ):
                self._write_grouped_indexed(indexed)
            self.sheet.activate()
            source = self.sheet.lt_range(False)
            command = (
                f"worksheet -px ? gColumn plot_gindexed iy:={source}!(,B) "
                f"group:={source}!(C,D) plottype:=0;"
            )
            with origin_trace_step(
                "official_plot_command_execute",
                details={
                    "help_url": _K09_OFFICIAL_HELP,
                    "labtalk": command,
                    "menu": _K09_OFFICIAL_MENU,
                    "menu_id": _K09_OFFICIAL_MENU_ID,
                    "template_filename": template.name,
                    "template_sha256": self.profile.sha256,
                    "x_function": _K09_OFFICIAL_XFUNCTION,
                },
            ):
                if not self.op.lt_exec(command):
                    raise RuntimeError("Origin could not execute official K09 plot_gindexed")
            graphs = list(self.op.pages("g"))
            if len(graphs) != 1:
                raise RuntimeError("Origin plot_gindexed must create exactly one graph")
            self.graph = graphs[0]
            self.graph.lname = f"K09 Grouped Columns / {document.plot_id}"
            self.layer = self.graph[0]
            self.plots = [plot for plot in self.layer.plot_list() if plot.get_int("show") != 0]
            if len(self.plots) != 1:
                raise RuntimeError("Origin K09 must retain one native indexed DataPlot")
            legend = self.layer.label("legend")
            if legend is None or legend.text.count("\\l(") != len(indexed.group_labels):
                raise RuntimeError("Origin K09 did not create one legend sample per subgroup")
            self._materialize_k09_legend(indexed.group_labels)
            self.layer.rescale()
            native_structure = self._native_k09_structure()
            record_origin_trace(
                "native_column_family_confirmed",
                "completed",
                details=native_structure,
            )
            return
        with origin_trace_step(
            "source_data_write",
            details={
                "column_count": len(grid.series_labels) + 1,
                "row_count": len(grid.category_labels),
                "series_order": list(grid.series_labels),
            },
        ):
            self._write_data(grid)
        menu_name = "StackColumn" if self.profile_id == "K10" else "StackColP"
        self.sheet.activate()
        command = f"worksheet -s 1 0 {len(grid.series_labels) + 1} 0; worksheet -p 213 {menu_name};"
        with origin_trace_step(
            "official_plot_command_execute",
            details={
                "labtalk": command,
                "menu_name": menu_name,
                "template_filename": template.name,
            },
        ):
            self.op.lt_exec(command)
        with origin_trace_step(
            "template_residue_remove",
            details={"authoritative_workbook": book.name},
        ):
            for residue in tuple(self.op.pages("w")):
                if residue.name != book.name:
                    residue.destroy()
        graphs = list(self.op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError(f"Origin {menu_name} must create exactly one native graph")
        self.graph = graphs[0]
        self.graph.lname = f"{self.profile_id} Official Stack / {document.plot_id}"
        self.layer = self.graph[0]
        self.plots = list(self.layer.plot_list())
        if len(self.plots) != len(grid.series_labels):
            raise RuntimeError(f"Origin {menu_name} did not create one native member per source Y")
        native_structure = self._native_stack_structure(grid)
        native_plot_ids = tuple(cast(list[int], native_structure["plot_ids"]))
        offset, percent = self._native_stack_state()
        if offset != 1 or percent != int(self.profile_id == "K11"):
            raise RuntimeError(f"Origin {menu_name} did not retain its native stack semantics")
        self.layer.rescale()
        with origin_trace_step(
            "native_legend_reconstruct",
            details={"entry_count": len(grid.series_labels), "mode": "lname"},
        ):
            self.graph.activate()
            self.op.lt_exec(
                "legendupdate dest:=layer update:=reconstruct legend:=separate mode:=lname;"
            )
        legend = self.layer.label("legend")
        if legend is None or legend.text.count("\\l(") != len(grid.series_labels):
            raise RuntimeError(f"Origin {menu_name} did not create a complete native legend")
        record_origin_trace(
            "native_column_family_confirmed",
            "completed",
            details={
                "native_plot_count": len(self.plots),
                "native_plot_ids": list(native_plot_ids),
                "source_bindings": native_structure["source_bindings"],
                "official_menu_name": menu_name,
                "profile_id": self.profile_id,
                "stack_state": [offset, percent],
            },
        )

    def reopen(self, project_path: Path) -> None:
        with origin_trace_step(
            "saved_project_reopen",
            details={"filename": project_path.name, "readonly": False},
        ):
            self.op.new(asksave=False)
            if not self.op.open(str(project_path), readonly=False, asksave=False):
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
        self.plots = list(self.layer.plot_list())
        self.book = books[0]
        self.sheet = self.book[0]

    def apply(
        self,
        document: PlotDocument,
        action: PlotEngineAction,
        data: EngineDataView,
    ) -> None:
        grid = self._grid(document, data)
        token = document.plot_id.removeprefix("plot:")
        if isinstance(action, (CreatePlot, BindFields)):
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError(f"{self.profile_id} title target does not belong to this plot")
            label = self.layer.label(_TITLE_NAME)
            if label is None and action.text:
                self.layer.activate()
                if not self.layer.obj.LT_execute(
                    f"label -j 1 -n {_TITLE_NAME} PlotAgentTitlePlaceholder;"
                ):
                    raise RuntimeError(f"Origin could not create the {self.profile_id} title")
                label = self.layer.label(_TITLE_NAME)
                if label is None:
                    raise RuntimeError(f"Origin could not create the {self.profile_id} title")
            if label is not None:
                label.text = action.text
                label.set_int("attach", 1)
                label.set_float("x1", 0.5)
                label.set_float("y1", 0.012)
                label.set_int("fsize", 14)
                label.set_int("fstyle", 0)
                label.set_int("background", 0)
                label.set_int("show", int(bool(action.text)))
            return
        if isinstance(action, SetAxis):
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
            if axis_name is None:
                raise ValueError(f"{self.profile_id} axis target does not belong to this plot")
            axis = self.layer.axis(axis_name)
            if action.scale is not None:
                if axis_name == "x" and action.scale != "categorical":
                    raise ValueError("Origin column category axes support only categorical scale")
                if axis_name == "y":
                    if action.scale not in {"linear", "log10"}:
                        raise ValueError("Origin column value axes support only linear or log10")
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
            ordinal = self._series_ordinal(action.target, token, len(grid.series_labels))
            plot = self.plots[0] if self.profile_id == "K09" else self.plots[ordinal - 1]
            if action.color is not None:
                self._set_series_rgb(grid, ordinal, action.color)
            if action.line_width_pt is not None:
                if self.profile_id == "K09":
                    raise ValueError(
                        "Origin K09 exposes subgroup fill color but not per-subgroup edge width"
                    )
                plot.set_float("line.width", action.line_width_pt)
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError(f"{self.profile_id} legend target does not belong to this plot")
            self._set_legend(grid, bool(action.visible))
            return
        raise ValueError(f"Origin {self.profile_id} binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        with origin_trace_step("opju_save", details={"filename": output_path.name}):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.exists():
                raise FileExistsError(
                    f"Origin refuses to overwrite existing {self.profile_id} artifact: "
                    f"{output_path}"
                )
            self.op.save(str(output_path))
            if not output_path.is_file() or output_path.stat().st_size <= 0:
                raise RuntimeError(f"Origin did not save a non-empty {self.profile_id} project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        grid = self._grid(document, data)
        if self.profile_id == "K09":
            indexed = k09_grouped_indexed_data(document, data)
            if len(self.plots) != 1:
                raise RuntimeError("Origin K09 lost its single native indexed DataPlot")
            self._assert_values(self.sheet.to_list(0), indexed.indexes, "row index")
            self._assert_values(self.sheet.to_list(1), indexed.values, "values")
            self._assert_values(self.sheet.to_list(2), indexed.categories, "categories")
            self._assert_values(self.sheet.to_list(3), indexed.groups, "groups")
            native_structure = self._native_k09_structure()
            legend = self.layer.label("legend")
            if legend is None or legend.text.count("\\l(") != len(grid.series_labels):
                raise RuntimeError("Origin K09 legend lost a subgroup sample")
        else:
            if len(self.plots) != len(grid.series_labels):
                raise RuntimeError(
                    f"Origin {self.profile_id} native series count differs after reopen"
                )
            self._assert_values(self.sheet.to_list(0), grid.category_labels, "category")
            for index, expected in enumerate(zip(*grid.values, strict=True), start=1):
                self._assert_values(self.sheet.to_list(index), tuple(expected), f"series {index}")
            native_structure = self._native_stack_structure(grid)
            native_plot_ids = tuple(cast(list[int], native_structure["plot_ids"]))
        token = document.plot_id.removeprefix("plot:")
        snapshot: dict[str, object] = {
            "series_count": len(grid.series_labels),
            "profile": self.profile_id,
        }
        if self.profile_id == "K09":
            snapshot["native_structure"] = native_structure
        if self.profile_id in {"K10", "K11"}:
            offset, percent = self._native_stack_state()
            if offset != 1 or percent != int(self.profile_id == "K11"):
                raise RuntimeError(
                    f"Origin {self.profile_id} native stack state differs after reopen"
                )
            snapshot["native_stack_offset"] = offset
            snapshot["native_percent_normalization"] = percent
            snapshot["native_plot_ids"] = list(native_plot_ids)
            snapshot["source_bindings"] = native_structure["source_bindings"]
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if (
                    title is None
                    or title.text != action.text
                    or not title.get_int("show")
                    or title.get_int("attach") != 1
                ):
                    raise RuntimeError(f"Origin {self.profile_id} title did not survive readback")
                snapshot["title"] = title.text
            elif isinstance(action, SetAxis) and action.label is not None:
                axis_name = "x" if action.target == f"axis:{token}.x" else "y"
                label = self.layer.label("xb" if axis_name == "x" else "yl")
                if label is None or label.text != action.label:
                    raise RuntimeError(
                        f"Origin {self.profile_id} axis label did not survive readback"
                    )
            elif isinstance(action, SetSeriesStyle):
                ordinal = self._series_ordinal(action.target, token, len(grid.series_labels))
                plot = self.plots[0] if self.profile_id == "K09" else self.plots[ordinal - 1]
                if action.color is not None:
                    self._assert_series_rgb(grid, ordinal, action.color)
                if action.line_width_pt is not None and (
                    abs(float(plot.get_float("line.width")) - action.line_width_pt) > 0.01
                ):
                    raise RuntimeError(
                        f"Origin {self.profile_id} edge width did not survive readback"
                    )
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layer.label("legend")
                if legend is None or bool(legend.get_int("show")) != action.visible:
                    raise RuntimeError(
                        f"Origin {self.profile_id} legend visibility did not survive readback"
                    )
                if action.visible and legend.text.count("\\l(") != len(grid.series_labels):
                    raise RuntimeError(f"Origin {self.profile_id} legend lost a native sample")
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
                    semantic_id=f"series:{token}.{self.series_key}_{index}",
                    backend="origin",
                    object_kind=(
                        "k09_native_subset"
                        if self.profile_id == "K09"
                        else f"{self.profile_id.lower()}_native_series"
                    ),
                    native_ref=(
                        f"graph:{self.graph.name}.layer:1.plot:1.subset:{index}"
                        if self.profile_id == "K09"
                        else f"graph:{self.graph.name}.layer:1.plot:{index}"
                    ),
                )
                for index in range(1, len(grid.series_labels) + 1)
            ),
            EngineObjectRef(
                semantic_id=f"legend:{token}.main",
                backend="origin",
                object_kind="legend",
                native_ref=f"graph:{self.graph.name}.layer:1.label:legend",
            ),
        )
        record_origin_trace("reopened_column_family_confirmed", "completed", details=snapshot)
        return EngineReadback(
            document=document_ref(document),
            backend="origin",
            objects=objects,
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(cast(JsonValue, snapshot)),
        )

    def _grid(self, document: PlotDocument, data: EngineDataView) -> CategorySeriesGrid:
        grid = category_series_grid(document, data, profile_id=self.profile_id)
        if self.profile_id == "K11" and any(
            value < 0 for row in grid.values for value in row if not isnan(value)
        ):
            raise ValueError("K11 percent-stack values must be non-negative")
        if self.profile_id == "K11" and any(
            sum(value for value in row if not isnan(value)) <= 0 for row in grid.values
        ):
            raise ValueError("K11 each category must have a positive total")
        return grid

    def _set_native_stack(self, *, percent: bool) -> None:
        theme = self.layer.obj.GetTheme()
        stack = next((node for node in theme.Children if node.Name == "Stack"), None)
        if stack is None:
            raise RuntimeError(f"Origin {self.profile_id} COLUMN template has no Stack theme")
        offset = next((node for node in stack.Children if node.Name == "Offset"), None)
        normalize = next(
            (node for node in stack.Children if node.Name == "StackOffset"),
            None,
        )
        if offset is None or normalize is None:
            raise RuntimeError(f"Origin {self.profile_id} Stack theme is incomplete")
        offset.SetIntValue(1)
        normalize.SetIntValue(int(percent))
        self.layer.obj.PutTheme(theme)
        self.layer.rescale()

    def _native_stack_state(self) -> tuple[int, int]:
        theme = self.layer.obj.GetTheme()
        stack = next((node for node in theme.Children if node.Name == "Stack"), None)
        if stack is None:
            raise RuntimeError(f"Origin {self.profile_id} lost the native Stack theme")
        values = {
            node.Name: int(node.GetValue())
            for node in stack.Children
            if node.Name in {"Offset", "StackOffset"}
        }
        if set(values) != {"Offset", "StackOffset"}:
            raise RuntimeError(f"Origin {self.profile_id} lost native stack properties")
        return values["Offset"], values["StackOffset"]

    def _write_data(self, grid: CategorySeriesGrid) -> None:
        self.sheet.from_list(
            0,
            list(grid.category_labels),
            lname=grid.category_field_name,
            axis="X",
        )
        for index, (label, values) in enumerate(
            zip(grid.series_labels, zip(*grid.values, strict=True), strict=True),
            start=1,
        ):
            self.sheet.from_list(index, list(values), lname=label, axis="Y")

    def _native_stack_structure(self, grid: CategorySeriesGrid) -> dict[str, object]:
        expected_count = len(grid.series_labels)
        commands = [
            f"window -a {self.graph.name}",
            f"{self.graph.name}!page.active=1",
            "layer -c",
            f"__{self.profile_id}COUNT=count",
        ]
        for plot_index in range(1, expected_count + 1):
            commands.extend(
                (
                    f"range __{self.profile_id}P{plot_index}="
                    f"[{self.graph.name}]Layer1!{plot_index}",
                    f"get __{self.profile_id}P{plot_index} -pt __{self.profile_id}PT{plot_index}",
                    f"range -wx __{self.profile_id}X{plot_index}={plot_index}",
                    f"range -wy __{self.profile_id}Y{plot_index}={plot_index}",
                    f"string __{self.profile_id}XS{plot_index}$="
                    f"%(__{self.profile_id}X{plot_index})",
                    f"string __{self.profile_id}YS{plot_index}$="
                    f"%(__{self.profile_id}Y{plot_index})",
                )
            )
        self.op.lt_exec("; ".join(commands) + ";")
        observed_count = int(self.op.lt_float(f"__{self.profile_id}COUNT"))
        if observed_count != expected_count:
            raise RuntimeError(
                f"Origin {self.profile_id} native group count changed: {observed_count}"
            )
        source_prefix = f"[{self.book.name}]"
        source_bindings: list[dict[str, object]] = []
        plot_ids: list[int] = []
        for plot_index in range(1, expected_count + 1):
            plot_id = int(self.op.lt_float(f"__{self.profile_id}PT{plot_index}"))
            x_range = str(self.op.get_lt_str(f"__{self.profile_id}XS{plot_index}"))
            y_range = str(self.op.get_lt_str(f"__{self.profile_id}YS{plot_index}"))
            expected_y_letter = chr(ord("B") + plot_index - 1)
            if plot_id != 213:
                raise RuntimeError(
                    f"Origin {self.profile_id} plot {plot_index} is not native PID 213"
                )
            if not x_range.startswith(source_prefix) or '!A"' not in x_range:
                raise RuntimeError(
                    f"Origin {self.profile_id} plot {plot_index} lost category source A"
                )
            if not y_range.startswith(source_prefix) or f'!{expected_y_letter}"' not in y_range:
                raise RuntimeError(
                    f"Origin {self.profile_id} plot {plot_index} lost source "
                    f"{expected_y_letter}: {y_range!r}"
                )
            plot_ids.append(plot_id)
            source_bindings.append({"plot": plot_index, "x": x_range, "y": y_range})
        expected_designations = [4, *([1] * expected_count)]
        actual_designations = [
            self.sheet.get_int(f"col{index + 1}.type")
            for index in range(len(expected_designations))
        ]
        if actual_designations != expected_designations:
            raise RuntimeError(
                f"Origin {self.profile_id} worksheet designations changed: {actual_designations}"
            )
        return {
            "designations": actual_designations,
            "plot_ids": plot_ids,
            "source_bindings": source_bindings,
        }

    def _write_grouped_indexed(self, indexed: GroupedIndexedData) -> None:
        self.sheet.cols = 4
        self.sheet.from_list(0, list(indexed.indexes), lname="Index", axis="X")
        self.sheet.from_list(
            1,
            list(indexed.values),
            lname=indexed.value_field_name,
            axis="Y",
        )
        self.sheet.from_list(
            2,
            list(indexed.categories),
            lname=indexed.category_field_name,
            axis="N",
        )
        self.sheet.from_list(
            3,
            list(indexed.groups),
            lname=indexed.group_field_name,
            axis="N",
        )

    def _native_k09_structure(self) -> dict[str, object]:
        self.graph.activate()
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe K09 graph name for native readback: {graph_name!r}")
        command = (
            "page.active=1; layer -c; __K09COUNT=count; "
            f"range __K09P=[{graph_name}]1!1; "
            "get __K09P -pt __K09PID;"
        )
        if not self.op.lt_exec(command):
            raise RuntimeError("Origin could not read native K09 grouped-column structure")
        plot_count = int(self.op.lt_float("__K09COUNT"))
        plot_id = int(self.op.lt_float("__K09PID"))
        designations = tuple(int(self.sheet.get_int(f"col{index}.type")) for index in range(1, 5))
        if plot_count != 1 or plot_id != 203:
            raise RuntimeError("Origin K09 must retain one native PID 203 indexed column plot")
        if designations != (4, 1, 2, 2):
            raise RuntimeError("Origin K09 worksheet must retain X/Y/None/None designations")
        return {
            "designation_codes": list(designations),
            "help_url": _K09_OFFICIAL_HELP,
            "native_plot_count": plot_count,
            "native_plot_type": plot_id,
            "official_menu": _K09_OFFICIAL_MENU,
            "official_menu_id": _K09_OFFICIAL_MENU_ID,
            "official_template": K09_ORIGIN_PROFILE.filename,
            "profile_id": self.profile_id,
            "x_function": _K09_OFFICIAL_XFUNCTION,
        }

    def _set_series_rgb(
        self,
        grid: CategorySeriesGrid,
        ordinal: int,
        color: str,
    ) -> None:
        """Persist an arbitrary member color without breaking native grouping."""

        if self.profile_id == "K09":
            self._color_overrides[ordinal] = color
            colors = tuple(
                self._color_overrides.get(index, _PALETTE[(index - 1) % len(_PALETTE)])
                for index in range(1, len(grid.series_labels) + 1)
            )
            values = ",".join(f'color("{item}")' for item in colors)
            self.graph.activate()
            self.op.lt_exec(
                f"dataset __K09COLORS={{{values}}}; "
                "set %C -pfbi 1; set %C -cue 1; set %C -cuf __K09COLORS;"
            )
            return
        prefix = f"window -a {self.graph.name}; {self.graph.name}!page.active=1; "
        self.op.lt_exec(
            prefix
            + f"range __{self.profile_id}HEAD=[{self.graph.name}]Layer1!1; "
            + f"range __{self.profile_id}MEMBER=[{self.graph.name}]Layer1!{ordinal}; "
            + f"set __{self.profile_id}HEAD -gm 1; "
            + f'set __{self.profile_id}MEMBER -pfb color("{color}");'
        )

    def _assert_series_rgb(
        self,
        grid: CategorySeriesGrid,
        ordinal: int,
        color: str,
    ) -> None:
        if self.profile_id == "K09":
            self.graph.activate()
            self.op.lt_exec("get %C -cue __K09ENABLED; dataset __K09READ; get %C -cuf __K09READ;")
            enabled = int(self.op.lt_float("__K09ENABLED"))
            observed = int(self.op.lt_float(f"__K09READ[{ordinal}]"))
            wanted = int(self.op.lt_float(f'color("{color}")'))
            if enabled != 1 or observed != wanted:
                raise RuntimeError("Origin K09 native group color list did not survive readback")
            return
        prefix = f"window -a {self.graph.name}; {self.graph.name}!page.active=1; "
        self.op.lt_exec(
            prefix
            + f"range __{self.profile_id}HEAD=[{self.graph.name}]Layer1!1; "
            + f"range __{self.profile_id}MEMBER=[{self.graph.name}]Layer1!{ordinal}; "
            + f"get __{self.profile_id}HEAD -gm __{self.profile_id}GROUPMODE; "
            + f"get __{self.profile_id}MEMBER -pfb __{self.profile_id}FILL;"
        )
        mode = int(self.op.lt_float(f"__{self.profile_id}GROUPMODE"))
        observed = int(self.op.lt_float(f"__{self.profile_id}FILL"))
        wanted = int(self.op.lt_float(f'color("{color}")'))
        if mode != 1 or observed != wanted:
            raise RuntimeError(
                f"Origin {self.profile_id} native member fill did not survive readback"
            )
        record_origin_trace(
            "reopened_native_member_color_confirmed",
            "completed",
            details={
                "group_edit_mode": mode,
                "ordinal": ordinal,
                "resolved_color": observed,
            },
        )

    def _set_legend(self, grid: CategorySeriesGrid, visible: bool) -> None:
        legend = self.layer.label("legend")
        if self.profile_id == "K09":
            if legend is None:
                raise RuntimeError("Origin K09 native grouped-column graph lost its legend")
            if legend.text.count("\\l(") != len(grid.series_labels):
                raise RuntimeError("Origin K09 native legend does not match subgroup count")
            self._materialize_k09_legend(grid.series_labels)
            legend.set_int("show", int(visible))
            return
        if visible and legend is None:
            self.layer.activate()
            if not self.layer.obj.LT_execute("legend"):
                raise RuntimeError(f"Origin could not create the {self.profile_id} legend")
            legend = self.layer.label("legend")
        if legend is not None:
            if legend.text.count("\\l(") != len(grid.series_labels):
                raise RuntimeError(
                    f"Origin {self.profile_id} native legend does not match source series"
                )
            legend.set_int("link", 1)
            legend.set_int("show", int(visible))

    def _materialize_k09_legend(self, labels: tuple[str, ...]) -> None:
        legend = self.layer.label("legend")
        if legend is None:
            raise RuntimeError("Origin K09 native grouped-column graph lost its legend")
        legend.text = "\n".join(
            f"\\l(1,m{index},2) {_safe_legend_label(label)}"
            for index, label in enumerate(labels, start=1)
        )
        legend.set_int("link", 1)

    def _series_ordinal(self, target: str, token: str, series_count: int) -> int:
        prefix = f"series:{token}.{self.series_key}_"
        suffix = target.removeprefix(prefix) if target.startswith(prefix) else ""
        if not suffix.isdigit() or not 1 <= int(suffix) <= series_count:
            raise ValueError(f"{self.profile_id} series target is outside the materialized data")
        return int(suffix)

    def _assert_values(
        self,
        actual: list[object],
        expected: tuple[object, ...],
        role: str,
    ) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin {self.profile_id} {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if isinstance(wanted, float) and isnan(wanted) and observed is None:
                continue
            if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
                if abs(float(cast(Any, observed)) - float(wanted)) <= 1e-9:
                    continue
            elif observed == wanted:
                continue
            raise RuntimeError(f"Origin {self.profile_id} {role} values differ after reopen")


def _execute(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
    profile_id: Literal["K09", "K10", "K11"],
) -> EngineReadback:
    # Dynamic group/component counts make recreating from the official
    # template safer than mutating an earlier project's native plot group.
    project = ColumnFamilyOriginProject(op, profile_id=profile_id)
    project.create(install_dir, request.document, request.data)
    actions = _effective_actions(request.actions)
    with origin_trace_step("agent_actions_apply", details={"action_count": len(actions)}):
        for action in actions:
            details = cast(dict[str, object], action.model_dump(exclude_none=True))
            with origin_trace_step("agent_action_apply", details=details):
                project.apply(request.document, action, request.data)
    project.save(output)
    reopened = ColumnFamilyOriginProject(op, profile_id=profile_id)
    reopened.reopen(output)
    with origin_trace_step("reopened_native_structure_verify"):
        return reopened.verify(request.document, actions, request.data)


def execute_k09_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "K09")


def execute_k10_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "K10")


def execute_k11_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "K11")
