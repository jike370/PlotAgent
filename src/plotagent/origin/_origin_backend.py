"""OriginPro implementation of the closed native execution backend.

Only fixed high-level Origin operations live here. User text is assigned as data or label
content and is never interpreted as a command, formula, property path, or template path.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np

from plotagent.contracts.canonical import JsonValue, canonical_json
from plotagent.contracts.rendering import (
    OriginAxisPlan,
    OriginColumnPlan,
    OriginDataObject,
    OriginExportPlan,
    OriginGraphObject,
    OriginLayerPlan,
    OriginPlotPlan,
    OriginScalar,
)

from .native import (
    PROJECT_FOLDERS,
    NativePrimitive,
    materialize_primitive,
    native_primitives,
    physical_plot_count,
    primitive_book_name,
)
from .validation import (
    expected_validation_report,
    expected_validation_sha256,
    origin_canonical_hash,
)

_MANIFEST_BOOK = "PAMETA"
_MANIFEST_SHEET = "Manifest"
# Origin's automation string path can truncate worksheet text near 4 KiB even though
# the interactive worksheet supports larger cells. Keep chunks below that boundary.
_MANIFEST_CHUNK_CHARS = 3_000
_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}\Z")
_PLOT_TYPE = {
    "line": 200,
    "line_symbol": 202,
    "scatter": 201,
    "column": 203,
    "area": 204,
    "floating_column": 207,
    "bar": 215,
    "bubble": 193,
    "bubble_color": 248,
    "fill_area": 249,
    "heatmap": 105,
    "contour": 226,
}
_COLUMN_AXIS = {
    "X": "X",
    "Y": "Y",
    "Z": "Z",
    "XError": "M",
    "YError": "E",
    "Label": "L",
    "Group": "N",
    "None": "N",
}


class NativeOriginError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _AxisVisualStyle:
    axis_width_pt: float
    major_tick_width_pt: float
    minor_tick_width_pt: float
    tick_label_bold: int
    title_bold: int


def _finite_float(value: Any, fallback: float | None = None) -> float:
    numeric = float(value)
    if math.isfinite(numeric):
        return numeric
    if fallback is None:
        raise NativeOriginError("qualified template axis style is not finite")
    return fallback


def _read_template_y_axis_style(layer: Any) -> _AxisVisualStyle:
    """Read the qualified template's fixed left-Y visual weight."""

    axis_width = _finite_float(layer.get_float("y.thickness"))
    shared_tick_width = _finite_float(layer.get_float("tickW"), axis_width)
    title = layer.label("yl")
    if title is None:
        raise NativeOriginError("qualified template is missing the left Y title")
    return _AxisVisualStyle(
        axis_width_pt=axis_width,
        major_tick_width_pt=_finite_float(
            layer.get_float("y.tickthickness"), shared_tick_width
        ),
        minor_tick_width_pt=_finite_float(
            layer.get_float("y.mtickthickness"), shared_tick_width
        ),
        tick_label_bold=int(round(_finite_float(layer.get_float("y.label.bold"), 0.0))),
        title_bold=int(round(_finite_float(title.get_float("font.bold"), 0.0))),
    )


def _apply_right_y_axis_style(layer: Any, style: _AxisVisualStyle) -> None:
    """Apply only fixed, object-level right-axis weight properties."""

    layer.set_float("y2.thickness", style.axis_width_pt)
    layer.set_float("y2.tickthickness", style.major_tick_width_pt)
    layer.set_float("y2.mtickthickness", style.minor_tick_width_pt)
    layer.set_int("y2.label.bold", style.tick_label_bold)
    title = layer.label("yr")
    if title is None:
        raise NativeOriginError("qualified template is missing the right Y title")
    title.set_int("font.bold", style.title_bold)


def _assert_right_y_axis_style(layer: Any, expected: _AxisVisualStyle) -> None:
    actual_values = (
        _finite_float(layer.get_float("y2.thickness")),
        _finite_float(layer.get_float("y2.tickthickness")),
        _finite_float(layer.get_float("y2.mtickthickness")),
    )
    expected_values = (
        expected.axis_width_pt,
        expected.major_tick_width_pt,
        expected.minor_tick_width_pt,
    )
    if any(
        not math.isclose(actual, target, rel_tol=0.0, abs_tol=1e-9)
        for actual, target in zip(actual_values, expected_values, strict=True)
    ):
        raise NativeOriginError("native right Y axis visual weight differs from template")
    title = layer.label("yr")
    if title is None:
        raise NativeOriginError("native right Y title is missing")
    if layer.get_int("y2.label.bold") != expected.tick_label_bold or title.get_int(
        "font.bold"
    ) != expected.title_bold:
        raise NativeOriginError("native right Y axis text weight differs from template")


def _area_fill_command(color: str) -> str:
    """Return the only typed dynamic Set option admitted by the Origin backend."""

    if _HEX_COLOR.fullmatch(color) is None:
        raise NativeOriginError("area fill color must be a validated #RRGGBB token")
    return f'-cf color("{color}")'


def _floating_column_gap_command(width: float) -> str:
    """Map one validated categorical-unit width to Origin's gap percentage."""

    if isinstance(width, bool) or not math.isfinite(width) or not 0 < width <= 1:
        raise NativeOriginError("floating-column width must be finite and in (0, 1]")
    return f"-vg {round((1.0 - width) * 100)}"


def _legend_text(graph_id: str, labels: list[str]) -> str:
    """Add native sample tokens only for the closed S07 legend vocabulary.

    S07 layer labels are a closed fixed-calculation vocabulary, so it can safely use
    Origin's fixed ``\\l(n)`` sample tokens. Other chart labels retain the existing
    plain-text path and never receive generated enhanced-text syntax here.
    """

    if graph_id.startswith("graph.S07."):
        expected = ("Down", "Not significant", "Up")
        if tuple(labels) != expected:
            raise NativeOriginError("S07 fixed legend vocabulary differs from the resolver")
        return "\n".join(f"\\l({index}) {label}" for index, label in enumerate(labels, 1))
    return "\n".join(labels)


def _place_inside_legend(
    graph: Any, graph_plan: OriginGraphObject, layer_plan: OriginLayerPlan, legend: Any
) -> None:
    """Place the legend inside its typed anchor so it cannot cross the page edge."""

    page_width = _finite_float(graph.get_float("width"))
    page_height = _finite_float(graph.get_float("height"))
    legend_width = _finite_float(legend.get_float("width"), 0.0)
    legend_height = _finite_float(legend.get_float("height"), 0.0)
    layer_left = layer_plan.left_mm / graph_plan.page_width_mm * page_width
    layer_top = layer_plan.top_mm / graph_plan.page_height_mm * page_height
    layer_width = layer_plan.width_mm / graph_plan.page_width_mm * page_width
    layer_height = layer_plan.height_mm / graph_plan.page_height_mm * page_height
    anchor_x = layer_left + layer_width * graph_plan.legend_anchor_x
    # Resolved anchors use Matplotlib's bottom-up Y convention; Origin's object
    # coordinates run from the page top.
    anchor_y = layer_top + layer_height * (1.0 - graph_plan.legend_anchor_y)
    if graph_plan.graph_id.startswith("graph.S07."):
        # Volcano extremes occupy both upper corners. Centering the three-entry
        # fixed legend keeps it clear of those points as the X range expands.
        left = layer_left + (layer_width - legend_width) / 2
    else:
        left = anchor_x - legend_width if graph_plan.legend_anchor_x >= 0.5 else anchor_x
    top = anchor_y if graph_plan.legend_anchor_y >= 0.5 else anchor_y - legend_height
    legend.set_float("left", min(max(left, 0.0), max(page_width - legend_width, 0.0)))
    legend.set_float("top", min(max(top, 0.0), max(page_height - legend_height, 0.0)))


def _folder_items(collection: Any) -> list[Any]:
    return [collection.GetItem(index) for index in range(collection.GetCount())]


def _folder_by_name(root: Any, name: str) -> Any:
    for folder in _folder_items(root.obj.Folders):
        if folder.GetName() == name:
            return folder
    raise NativeOriginError(f"missing Project Explorer folder: {name}")


def _page_names(folder: Any) -> list[str]:
    pages = folder.PageBases()
    return [pages.GetItem(index).GetName() for index in range(pages.GetCount())]


def _get_page(op: Any, name: str, wrapper: Any) -> Any:
    try:
        return wrapper(op.config.po.Pages[name])
    except Exception as exc:
        raise NativeOriginError(f"could not read Origin page {name}") from exc


def _safe_cell(value: OriginScalar) -> OriginScalar | float:
    return math.nan if value is None else value


def _same_cell(actual: object, expected: OriginScalar) -> bool:
    if expected is None:
        return actual is None or (isinstance(actual, float) and math.isnan(actual))
    if isinstance(expected, bool):
        return bool(actual) is expected
    if isinstance(expected, (int, float)):
        try:
            return math.isclose(float(cast(Any, actual)), float(expected), rel_tol=0, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    return str(actual) == expected


def _assert_values(actual: list[object], expected: tuple[OriginScalar, ...], context: str) -> None:
    if len(actual) != len(expected) or any(
        not _same_cell(actual_value, expected_value)
        for actual_value, expected_value in zip(actual, expected, strict=True)
    ):
        raise NativeOriginError(f"native Origin values differ for {context}")


def _role_index(data: OriginDataObject, plot: OriginPlotPlan, role: str | None) -> int:
    if role is not None:
        direct = next(
            (index for index, column in enumerate(data.columns) if column.role == role),
            None,
        )
        if direct is not None:
            return direct
        field_id = next(
            (item.field_id for item in plot.role_columns if item.role == role),
            None,
        )
        if field_id is not None:
            return next(
                index for index, column in enumerate(data.columns) if column.field_id == field_id
            )
    preferred = "X" if role is None else "Y"
    candidate = next(
        (index for index, column in enumerate(data.columns) if column.designation == preferred),
        None,
    )
    if candidate is not None:
        return candidate
    return 0 if role is None or len(data.columns) == 1 else 1


def _tick_step(axis: OriginAxisPlan) -> float:
    values = tuple(item.value for item in axis.ticks)
    if len(values) > 1:
        if axis.scale == "log10" and values[0] > 0 and values[1] > 0:
            return float(math.log10(values[1]) - math.log10(values[0]))
        return float(values[1] - values[0])
    span = axis.maximum - axis.minimum
    return float(span if span > 0 else 1.0)


def _tick_label_string(axis: OriginAxisPlan) -> str:
    return " ".join(
        f'"{item.label.replace(chr(34), chr(92) + chr(34)).replace(chr(10), " ")}"'
        for item in axis.ticks
    )


def _uses_custom_tick_labels(axis: OriginAxisPlan) -> bool:
    if axis.scale in {"categorical", "datetime"}:
        return True
    try:
        return any(
            not math.isclose(float(item.label), item.value, rel_tol=0, abs_tol=1e-12)
            for item in axis.ticks
        )
    except ValueError:
        return True


class OriginProBackend:
    """One independent hidden Origin project, owned by one dedicated worker process."""

    def __init__(self, op: Any, template_path: Path) -> None:
        self._op = op
        self._template_path = template_path
        self._root = op.root_folder()
        self._folders: dict[str, Any] = {}
        self._data_sheets: dict[str, Any] = {}

    def ensure_blank(self) -> None:
        if self._root.obj.Folders.GetCount() or self._root.obj.PageBases().GetCount():
            raise NativeOriginError("dedicated Origin instance did not start from a blank project")

    def create_folder(self, name: str) -> None:
        if name not in PROJECT_FOLDERS:
            raise NativeOriginError(f"unsupported fixed project folder: {name}")
        folder = self._root.obj.Folders.Add(name)
        if folder is None or not folder.IsValid():
            raise NativeOriginError(f"could not create Project Explorer folder {name}")
        self._folders[name] = folder

    def _folder(self, name: str) -> Any:
        folder = self._folders.get(name)
        if folder is None:
            folder = _folder_by_name(self._root, name)
        return folder

    def write_data_object(self, data: OriginDataObject) -> None:
        self._folder(data.folder).Activate()
        if data.object_kind == "worksheet":
            book = self._op.new_book("w", data.internal_name, hidden=True)
            if book is None:
                raise NativeOriginError(f"could not create worksheet {data.internal_name}")
            book.name = data.internal_name
            book.lname = data.long_name
            sheet = book[0]
            sheet.name = "Data"
            sheet.lname = data.long_name
            sheet.shape = (data.data_ref.row_count, len(data.columns))
            for index, column in enumerate(data.columns):
                sheet.from_list(
                    index,
                    [_safe_cell(value) for value in column.values],
                    lname=column.long_name,
                    units=column.units,
                    comments=column.comments,
                    axis=_COLUMN_AXIS[column.designation],
                )
            self._data_sheets[data.object_id] = sheet
            return
        matrix = data.matrix
        if matrix is None:
            raise NativeOriginError("matrixbook plan omitted matrix data")
        book = self._op.new_book("m", data.internal_name, hidden=True)
        if book is None:
            raise NativeOriginError(f"could not create matrixbook {data.internal_name}")
        book.name = data.internal_name
        book.lname = data.long_name
        sheet = book[0]
        sheet.name = "Matrix"
        sheet.lname = data.long_name
        array = np.asarray(
            [[math.nan if value is None else value for value in row] for row in matrix.values],
            dtype=float,
        )
        sheet.from_np(array)
        sheet.xymap = (
            matrix.x_coordinates[0],
            matrix.x_coordinates[-1],
            matrix.y_coordinates[0],
            matrix.y_coordinates[-1],
        )
        sheet.set_label(0, data.long_name, "L")
        self._data_sheets[data.object_id] = sheet

    def _write_primitive_table(
        self,
        page_name: str,
        x_values: tuple[OriginScalar, ...],
        y_values: tuple[OriginScalar, ...],
        third_values: tuple[OriginScalar, ...] | None = None,
        *,
        third_name: str = "Y2",
        third_axis: str = "Y",
    ) -> Any:
        self._folder("Analysis").Activate()
        book = self._op.new_book("w", page_name, hidden=True)
        if book is None:
            raise NativeOriginError(f"could not create primitive worksheet {page_name}")
        book.name = page_name
        book.lname = "PlotAgent Native Primitive Data"
        sheet = book[0]
        sheet.name = "Primitive"
        sheet.lname = "Native Primitive Data"
        sheet.shape = (len(x_values), 3 if third_values is not None else 2)
        sheet.from_list(0, [_safe_cell(value) for value in x_values], lname="X", axis="X")
        sheet.from_list(1, [_safe_cell(value) for value in y_values], lname="Y", axis="Y")
        if third_values is not None:
            sheet.from_list(
                2,
                [_safe_cell(value) for value in third_values],
                lname=third_name,
                axis=third_axis,
            )
        return sheet

    def _data_range(self, sheet: Any, x_index: int, *y_indexes: int) -> Any:
        args: list[Any] = ["X", sheet.obj[x_index]]
        for y_index in y_indexes:
            args.extend(("Y", sheet.obj[y_index]))
        return self._op.make_DataRange(*args)

    def _add_worksheet_primitive(
        self,
        layer: Any,
        plot_plan: OriginPlotPlan,
        primitive: NativePrimitive,
        primitive_index: int,
        data: OriginDataObject,
        sheet: Any,
    ) -> Any:
        x_index = _role_index(data, plot_plan, primitive.x_role)
        y_index = _role_index(data, plot_plan, primitive.y_role)
        y_indexes: tuple[int, ...] = (y_index,)
        if primitive.y2_role is not None:
            y_indexes += (_role_index(data, plot_plan, primitive.y2_role),)
        data_range = self._data_range(sheet, x_index, *y_indexes)
        first_plot_index = len(layer.plot_list())
        native_plot = layer.obj.AddPlot(data_range, _PLOT_TYPE[primitive.plot_type], True)
        if native_plot is None or not native_plot.IsValid():
            raise NativeOriginError(f"could not add native plot {plot_plan.plot_id}")
        plot = self._op.Plot(native_plot, layer.obj)
        layer_plots = layer.plot_list()
        created_plots = layer_plots[-physical_plot_count(primitive) :]
        if primitive.plot_type == "floating_column":
            # Origin's native floating column is an XYY group: the first Y is
            # the hidden starting boundary and the second Y is the visible end.
            # Grouping activates that native behavior; fill-only transparency
            # hides the boundary without changing any process-global preference.
            layer.group(True, first_plot_index, first_plot_index + len(created_plots) - 1)
        if plot_plan.color is not None:
            for created_plot in created_plots:
                created_plot.color = plot_plan.color.value
            if primitive.plot_type == "area":
                # Origin's fill-color property accepts palette indexes. ColorValue
                # is a validated #RRGGBB token, so this closed option preserves the
                # exact palette without admitting labels or arbitrary commands.
                plot.set_cmd(_area_fill_command(plot_plan.color.value))
        if primitive.transform in {"floating_polygon", "horizontal_polygon"}:
            for created_plot in created_plots:
                created_plot.set_float("line.width", 0)
        if (
            plot_plan.marker_size_pt is not None
            and primitive.plot_type in {"scatter", "line_symbol"}
        ):
            plot.symbol_size = plot_plan.marker_size_pt
        if primitive.plot_type in {"scatter", "line_symbol"}:
            plot.symbol_kind = 2
        if primitive.size_role is not None:
            size_index = _role_index(data, plot_plan, primitive.size_role)
            plot.symbol_size = self._op.modi_col(size_index - y_index)
            # Origin's modifier values are interpreted in points. The fixed factor
            # keeps the PlotSpec's scientific bubble weights legible without turning
            # one large observation into a page-sized symbol.
            plot.symbol_sizefactor = 0.25
        if primitive.color_role is not None:
            color_index = _role_index(data, plot_plan, primitive.color_role)
            plot.color = self._op.color_col(color_index - y_index, "m")
        if primitive.transform == "forest_interval":
            # Origin exposes 2-point-segment connection through the fixed Set -l
            # option. The Plot property-tree path is not reliable for this control
            # across supported Origin builds. Keep the command literal and
            # allowlisted: no user or Agent content enters it.
            plot.set_cmd("-l 2")
        if primitive.transform == "lollipop_drop":
            # Native Origin drop lines terminate at the bottom X-axis frame and
            # continue to do so when the user edits the Y display range.
            plot.set_cmd("-pd 1")
        if plot_plan.native_kind == "grouped_bar" and primitive.plot_type == "column":
            # Origin has no stable property path for this Spacing-tab control.
            # Keep the command fully allowlisted and literal; no user text enters it.
            plot.set_cmd("-vg 70")
        if (
            plot_plan.line_width_pt is not None
            and primitive.plot_type
            in {
                "line",
                "line_symbol",
            }
        ):
            plot.set_float("line.width", plot_plan.line_width_pt)
        if primitive.bar_width_role is not None:
            width_index = _role_index(data, plot_plan, primitive.bar_width_role)
            widths = tuple(
                float(value)
                for value in data.columns[width_index].values
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            )
            if not widths:
                raise NativeOriginError("floating-column width cannot be resolved")
            width = widths[0]
            created_plots[0].set_cmd(
                "-paaf 100",
                "-pbw 0",
                _floating_column_gap_command(width),
            )
        if plot_plan.alpha < 1:
            plot.transparency = round((1 - plot_plan.alpha) * 100)
        return plot

    def _configure_axis(
        self,
        layer: Any,
        axis: OriginAxisPlan,
        font_size_pt: float,
        right_y_style: _AxisVisualStyle,
    ) -> None:
        is_right_y = axis.orientation == "y" and axis.position == "right"
        native_axis = layer.axis("y2" if is_right_y else axis.orientation)
        native_axis.scale = "log10" if axis.scale == "log10" else "linear"
        begin, end = (
            (axis.maximum, axis.minimum)
            if axis.reverse
            else (
                axis.minimum,
                axis.maximum,
            )
        )
        native_axis.set_limits(begin, end, _tick_step(axis))
        prefix = "y2" if is_right_y else axis.orientation
        if is_right_y:
            layer.set_int("y.showAxes", 2)
            layer.set_int("y.showLabels", 2)
            layer.set_int("y.showlabel", 0)
            layer.set_int("y2.showlabel", 1)
            left_title = layer.label("yl")
            if left_title is not None:
                left_title.set_int("show", 0)
        elif axis.orientation == "y":
            layer.set_int("y.showAxes", 1)
            layer.set_int("y.showLabels", 1)
            layer.set_int("y.showlabel", 1)
            layer.set_int("y2.showlabel", 0)
            right_title = layer.label("yr")
            if right_title is not None:
                right_title.set_int("show", 0)
        elif axis.orientation == "x":
            layer.set_int("x.showAxes", 1)
            layer.set_int("x.showLabels", 1)
        custom_tick_labels = _uses_custom_tick_labels(axis)
        layer.set_int(f"{prefix}.label.type", 10 if custom_tick_labels else 1)
        layer.set_float(f"{prefix}.label.fsize", max(5.0, font_size_pt - 1.0))
        if custom_tick_labels:
            layer.set_str(
                f"{prefix}.label.string",
                _tick_label_string(axis),
            )
        label_name = "xb" if axis.orientation == "x" else "yr" if axis.position == "right" else "yl"
        label = layer.label(label_name)
        if label is None:
            label = layer.add_label(axis.title)
        if label is None:
            raise NativeOriginError(f"qualified template is missing axis label {label_name}")
        label.text = axis.title
        label.set_float("fsize", font_size_pt)
        label.set_int("show", 1)
        if is_right_y:
            _apply_right_y_axis_style(layer, right_y_style)

    def _configure_layer_frame(
        self, graph: OriginGraphObject, layer_plan: OriginLayerPlan, layer: Any
    ) -> None:
        # Fixed literal Origin properties; callers cannot supply property paths.
        layer.set_float("left", layer_plan.left_mm / graph.page_width_mm * 100)
        layer.set_float("top", layer_plan.top_mm / graph.page_height_mm * 100)
        layer.set_float("width", layer_plan.width_mm / graph.page_width_mm * 100)
        layer.set_float("height", layer_plan.height_mm / graph.page_height_mm * 100)

    def write_graph_object(self, graph_plan: OriginGraphObject) -> None:
        self._folder("Graphs").Activate()
        graph = self._op.new_graph(
            graph_plan.internal_name,
            template=str(self._template_path),
            hidden=True,
        )
        if graph is None:
            raise NativeOriginError(f"could not create graph {graph_plan.internal_name}")
        template_y_style = _read_template_y_axis_style(graph[0])
        graph.name = graph_plan.internal_name
        graph.lname = graph_plan.long_name
        # Derived interval, outline, and polygon tables use missing rows as explicit
        # segment boundaries. The qualified template may retain the user's global
        # Origin preference, so freeze the safe scientific default on every page.
        graph.set_int("connect", 0)
        # The qualified base template has printer-derived sizing disabled, so the
        # typed physical canvas can be applied through the native page API.
        graph.obj.SetWidth(graph_plan.page_width_mm)
        graph.obj.SetHeight(graph_plan.page_height_mm)
        data_by_id = {
            object_id: self._data_sheets[object_id] for object_id in graph_plan.data_object_ids
        }
        for layer_index, layer_plan in enumerate(graph_plan.layers):
            if layer_index == 0:
                layer = graph[0]
            else:
                native_layer = graph.obj.AddLayer()
                if native_layer is None or not native_layer.IsValid():
                    raise NativeOriginError("could not add native graph layer")
                layer = self._op.GLayer(native_layer)
            layer.lname = layer_plan.panel_id
            self._configure_layer_frame(graph_plan, layer_plan, layer)
            for plot_index, plot_plan in enumerate(layer_plan.plots):
                data = next(
                    item
                    for item in self._active_plan.data_objects
                    if item.object_id == plot_plan.data_object_id
                )
                source_sheet = data_by_id[plot_plan.data_object_id]
                for primitive_index, primitive in enumerate(native_primitives(plot_plan)):
                    if data.object_kind == "matrixbook":
                        data_range = self._op.make_DataRange("Z", source_sheet.obj[0])
                        native_plot = layer.obj.AddPlot(
                            data_range,
                            _PLOT_TYPE[primitive.plot_type],
                            True,
                        )
                        if native_plot is None or not native_plot.IsValid():
                            raise NativeOriginError("could not add native matrix plot")
                        # A generic qualified template has no initialized color-map
                        # range. Native rescale initializes it from the matrix before
                        # typed levels and axes are applied.
                        layer.rescale()
                        plot = self._op.Plot(native_plot, layer.obj)
                        if plot_plan.levels:
                            plot.zlevels = {
                                "minors": 0,
                                "levels": list(plot_plan.levels),
                            }
                        if primitive.plot_type == "contour":
                            plot.colormap = "Viridis.pal"
                            layer.set_int("cmap.flippal", 1)
                        continue
                    table = materialize_primitive(primitive, data)
                    plot_sheet = source_sheet
                    if table is not None:
                        page_name = primitive_book_name(
                            graph_plan.internal_name,
                            layer_index,
                            plot_index,
                            primitive_index,
                        )
                        plot_sheet = self._write_primitive_table(
                            page_name,
                            table.x,
                            table.y,
                            table.y2 if table.y2 is not None else table.auxiliary,
                            third_name="Y2" if table.y2 is not None else "Width",
                            third_axis="Y" if table.y2 is not None else "N",
                        )
                        primitive_for_sheet = NativePrimitive(
                            plot_type=primitive.plot_type,
                            x_role="x",
                            y_role="y",
                            y2_role="y2" if primitive.y2_role is not None else None,
                            size_role=(
                                "y2"
                                if primitive.size_role is not None and primitive.y2_role is None
                                else None
                            ),
                            transform=primitive.transform,
                        )
                        x_column = data.columns[0].model_copy(
                            update={
                                "role": "x",
                                "designation": "X",
                                "values": table.x,
                            }
                        )
                        y_column = data.columns[1].model_copy(
                            update={
                                "role": "y",
                                "designation": "Y",
                                "values": table.y,
                            }
                        )
                        columns: tuple[OriginColumnPlan, ...] = (x_column, y_column)
                        third_values = table.y2 if table.y2 is not None else table.auxiliary
                        if third_values is not None:
                            third_role = "y2" if table.y2 is not None else "width"
                            columns += (
                                data.columns[1].model_copy(
                                    update={
                                        "field_id": f"{data.columns[1].field_id}.upper",
                                        "role": third_role,
                                        "designation": "Y" if table.y2 is not None else "None",
                                        "values": third_values,
                                    }
                                ),
                            )
                        table_payload = {
                            "x": list(table.x),
                            "y": list(table.y),
                            "y2": list(table.y2) if table.y2 is not None else None,
                            "auxiliary": (
                                list(table.auxiliary) if table.auxiliary is not None else None
                            ),
                        }
                        primitive_data = OriginDataObject(
                            object_id=data.object_id,
                            object_kind="worksheet",
                            folder=data.folder,
                            internal_name=page_name,
                            long_name=data.long_name,
                            data_chain=data.data_chain,
                            data_ref=data.data_ref.model_copy(
                                update={
                                    "object_hash": origin_canonical_hash(
                                        cast(JsonValue, table_payload)
                                    ),
                                    "row_count": len(table.x),
                                    "field_ids": tuple(column.field_id for column in columns),
                                }
                            ),
                            columns=columns,
                        )
                        self._add_worksheet_primitive(
                            layer,
                            plot_plan,
                            primitive_for_sheet,
                            primitive_index,
                            primitive_data,
                            plot_sheet,
                        )
                    else:
                        self._add_worksheet_primitive(
                            layer,
                            plot_plan,
                            primitive,
                            primitive_index,
                            data,
                            plot_sheet,
                        )
            for axis in layer_plan.axes:
                self._configure_axis(
                    layer,
                    axis,
                    graph_plan.font_size_pt,
                    template_y_style,
                )
            if any(
                previous.left_mm == layer_plan.left_mm
                and previous.top_mm == layer_plan.top_mm
                and previous.width_mm == layer_plan.width_mm
                and previous.height_mm == layer_plan.height_mm
                for previous in graph_plan.layers[:layer_index]
            ):
                layer.set_int("x.showAxes", 0)
                layer.set_int("x.showLabels", 0)
                layer.set_int("x.showlabel", 0)
                layer.set_int("x2.showlabel", 0)
                x_title = layer.label("xb")
                if x_title is not None:
                    x_title.set_int("show", 0)
            labels = [
                plot.label
                for graph_layer in graph_plan.layers
                for plot in graph_layer.plots
                if plot.label
            ]
            legend = layer.label("legend")
            if legend is not None:
                legend.text = (
                    _legend_text(graph_plan.graph_id, labels)
                    if graph_plan.legend_visible and layer_index == 0
                    else ""
                )
                legend.set_float("fsize", graph_plan.font_size_pt)
                if (
                    graph_plan.legend_visible
                    and layer_index == 0
                    and graph_plan.graph_id.startswith("graph.S07.")
                ):
                    _place_inside_legend(graph, graph_plan, layer_plan, legend)
            for annotation in graph_plan.annotations:
                if annotation.panel_id != layer_plan.panel_id or annotation.text is None:
                    continue
                text = "".join(node.text for node in annotation.text.nodes)
                label = layer.add_label(text, annotation.x, annotation.y)
                if label is None:
                    raise NativeOriginError("could not create native text annotation")
        # Origin may defer one dimension while layers and plots are being created.
        # Reapply both typed dimensions after construction so inspection and save see
        # the final physical canvas.
        graph.obj.Activate()
        graph.obj.PutWidth(graph_plan.page_width_mm)
        graph.obj.PutHeight(graph_plan.page_height_mm)

    def write_manifest(self, plan: OriginExportPlan) -> None:
        self._active_plan = plan
        # Graph construction runs after data construction but needs the full plan. The
        # executor assigns this before graph calls through set_plan; this method writes data.
        self._folder("Metadata").Activate()
        book = self._op.new_book("w", _MANIFEST_BOOK, hidden=True)
        if book is None:
            raise NativeOriginError("could not create Origin manifest workbook")
        book.name = _MANIFEST_BOOK
        book.lname = "PlotAgent Export Metadata"
        sheet = book[0]
        sheet.name = _MANIFEST_SHEET
        sheet.lname = "Origin Export Manifest"
        manifest_json = canonical_json(plan.manifest)
        chunks = [
            manifest_json[index : index + _MANIFEST_CHUNK_CHARS]
            for index in range(0, len(manifest_json), _MANIFEST_CHUNK_CHARS)
        ]
        keys = [f"manifest_json.{index:04d}" for index in range(len(chunks))]
        values = list(chunks)
        keys.extend(("origin_plan_sha256", "render_plan_sha256", "validation_report_sha256"))
        values.extend(
            (
                origin_canonical_hash(plan),
                plan.render_plan_hash,
                expected_validation_sha256(plan),
            )
        )
        sheet.shape = (len(keys), 2)
        sheet.from_list(0, keys, lname="Key", axis="N")
        sheet.from_list(1, values, lname="Value", axis="N")

    def set_plan(self, plan: OriginExportPlan) -> None:
        self._active_plan = plan

    def _inspect_data(self, plan: OriginExportPlan) -> None:
        for data in plan.data_objects:
            if data.object_kind == "worksheet":
                book = _get_page(self._op, data.internal_name, self._op.WBook)
                sheet = book[0]
                rows, columns = sheet.shape
                if rows != data.data_ref.row_count or columns != len(data.columns):
                    raise NativeOriginError(f"worksheet shape differs for {data.object_id}")
                for index, column in enumerate(data.columns):
                    _assert_values(sheet.to_list(index), column.values, column.field_id)
                    native_column = sheet.obj[index]
                    metadata = (
                        native_column.GetLongName(),
                        native_column.GetUnits(),
                        native_column.GetComments(),
                    )
                    if metadata != (column.long_name, column.units, column.comments):
                        raise NativeOriginError(
                            f"worksheet column metadata differs for {column.field_id}"
                        )
            else:
                matrix = data.matrix
                if matrix is None:
                    raise NativeOriginError("matrixbook plan omitted matrix data")
                book = _get_page(self._op, data.internal_name, self._op.MBook)
                sheet = book[0]
                actual = np.asarray(sheet.to_np2d(), dtype=float)
                expected = np.asarray(
                    [
                        [math.nan if value is None else value for value in row]
                        for row in matrix.values
                    ],
                    dtype=float,
                )
                if actual.shape != expected.shape or not np.allclose(
                    actual, expected, rtol=0, atol=1e-12, equal_nan=True
                ):
                    raise NativeOriginError(f"matrix values differ for {data.object_id}")
                actual_xy = tuple(float(value) for value in sheet.xymap)
                expected_xy = (
                    matrix.x_coordinates[0],
                    matrix.x_coordinates[-1],
                    matrix.y_coordinates[0],
                    matrix.y_coordinates[-1],
                )
                if any(
                    not math.isclose(actual_value, expected_value, rel_tol=0, abs_tol=1e-12)
                    for actual_value, expected_value in zip(actual_xy, expected_xy, strict=True)
                ):
                    raise NativeOriginError(f"matrix coordinate map differs for {data.object_id}")

    def _inspect_primitive_pages(self, plan: OriginExportPlan) -> None:
        data_by_id = {item.object_id: item for item in plan.data_objects}
        for graph in plan.graph_objects:
            for layer_index, layer in enumerate(graph.layers):
                for plot_index, plot in enumerate(layer.plots):
                    data = data_by_id[plot.data_object_id]
                    for primitive_index, primitive in enumerate(native_primitives(plot)):
                        table = materialize_primitive(primitive, data)
                        if table is None:
                            continue
                        page_name = primitive_book_name(
                            graph.internal_name,
                            layer_index,
                            plot_index,
                            primitive_index,
                        )
                        book = _get_page(self._op, page_name, self._op.WBook)
                        sheet = book[0]
                        _assert_values(sheet.to_list(0), table.x, f"{page_name}/X")
                        _assert_values(sheet.to_list(1), table.y, f"{page_name}/Y")
                        if table.y2 is not None:
                            _assert_values(sheet.to_list(2), table.y2, f"{page_name}/Y2")

    def _inspect_graphs(self, plan: OriginExportPlan) -> None:
        for graph_plan in plan.graph_objects:
            graph = _get_page(self._op, graph_plan.internal_name, self._op.GPage)
            if graph.lname != graph_plan.long_name or len(graph) != len(graph_plan.layers):
                raise NativeOriginError(f"graph structure differs for {graph_plan.graph_id}")
            page_units = int(graph.obj.GetUnits())
            if page_units != 2:
                raise NativeOriginError(
                    f"qualified graph template units differ for {graph_plan.graph_id}: "
                    f"actual={page_units}, expected=2 (mm)"
                )
            width_mm = float(graph.obj.GetWidth())
            height_mm = float(graph.obj.GetHeight())
            if not math.isclose(
                width_mm, graph_plan.page_width_mm, abs_tol=0.2
            ) or not math.isclose(height_mm, graph_plan.page_height_mm, abs_tol=0.2):
                raise NativeOriginError(
                    f"graph page size differs for {graph_plan.graph_id}: "
                    f"actual=({width_mm:.6f}, {height_mm:.6f}) mm, "
                    f"expected=({graph_plan.page_width_mm:.6f}, "
                    f"{graph_plan.page_height_mm:.6f}) mm, "
                    f"units={page_units}, "
                    f"view_mode={graph.obj.GetPageViewMode()}"
                )
            template_y_style = _read_template_y_axis_style(graph[0])
            legend_labels = [
                plot.label for item in graph_plan.layers for plot in item.plots if plot.label
            ]
            for layer_index, (layer_plan, layer) in enumerate(
                zip(graph_plan.layers, graph, strict=True)
            ):
                expected_plot_count = sum(
                    physical_plot_count(primitive)
                    for plot in layer_plan.plots
                    for primitive in native_primitives(plot)
                )
                plots = layer.plot_list()
                if len(plots) != expected_plot_count:
                    raise NativeOriginError(
                        f"native plot count differs for {layer_plan.layer_id}: "
                        f"actual={len(plots)}, expected={expected_plot_count}"
                    )
                if any(not plot.obj.GetDatasetName() for plot in plots):
                    raise NativeOriginError(
                        f"native plot lost its dataset link in {layer_plan.layer_id}"
                    )
                for axis_plan in layer_plan.axes:
                    axis = layer.axis(
                        "y2"
                        if axis_plan.orientation == "y" and axis_plan.position == "right"
                        else axis_plan.orientation
                    )
                    actual_from, actual_to, unused_step = (float(value) for value in axis.limits)
                    expected_from, expected_to = (
                        (axis_plan.maximum, axis_plan.minimum)
                        if axis_plan.reverse
                        else (axis_plan.minimum, axis_plan.maximum)
                    )
                    if not math.isclose(
                        actual_from, expected_from, abs_tol=1e-10
                    ) or not math.isclose(actual_to, expected_to, abs_tol=1e-10):
                        raise NativeOriginError(
                            f"native axis range differs for {axis_plan.axis_id}"
                        )
                    expected_scale = 2 if axis_plan.scale == "log10" else 1
                    if axis.scale != expected_scale:
                        raise NativeOriginError(
                            f"native axis scale differs for {axis_plan.axis_id}"
                        )
                    prefix = (
                        "y2"
                        if axis_plan.orientation == "y" and axis_plan.position == "right"
                        else axis_plan.orientation
                    )
                    uses_custom_labels = _uses_custom_tick_labels(axis_plan)
                    actual_label_type = layer.get_int(f"{prefix}.label.type")
                    if actual_label_type != (10 if uses_custom_labels else 1):
                        raise NativeOriginError(
                            f"native tick label mode differs for {axis_plan.axis_id}"
                        )
                    if uses_custom_labels:
                        expected_labels = _tick_label_string(axis_plan)
                        actual_labels = layer.get_str(f"{prefix}.label.string")
                        if actual_labels != expected_labels:
                            raise NativeOriginError(
                                f"native tick labels differ for {axis_plan.axis_id}"
                            )
                    label_name = (
                        "xb"
                        if axis_plan.orientation == "x"
                        else "yr"
                        if axis_plan.position == "right"
                        else "yl"
                    )
                    label = layer.label(label_name)
                    if label is None or label.text != axis_plan.title:
                        raise NativeOriginError(
                            f"native axis title differs for {axis_plan.axis_id}"
                        )
                    if axis_plan.orientation == "y" and axis_plan.position == "right":
                        _assert_right_y_axis_style(layer, template_y_style)
                if (
                    graph_plan.legend_visible
                    and layer_index == 0
                    and graph_plan.graph_id.startswith("graph.S07.")
                ):
                    legend = layer.label("legend")
                    expected_legend = _legend_text(graph_plan.graph_id, legend_labels)
                    if legend is None or legend.text.replace("\r\n", "\n") != expected_legend:
                        raise NativeOriginError(
                            f"native legend text differs for {graph_plan.graph_id}"
                        )
                    page_width = _finite_float(graph.get_float("width"))
                    page_height = _finite_float(graph.get_float("height"))
                    if (
                        legend.get_float("left") < 0
                        or legend.get_float("top") < 0
                        or legend.get_float("left") + legend.get_float("width")
                        > page_width + 1e-9
                        or legend.get_float("top") + legend.get_float("height")
                        > page_height + 1e-9
                    ):
                        raise NativeOriginError(
                            f"native legend crosses page edge for {graph_plan.graph_id}"
                        )

    def _inspect_manifest(self, plan: OriginExportPlan) -> None:
        book = _get_page(self._op, _MANIFEST_BOOK, self._op.WBook)
        sheet = book[0]
        metadata = dict(
            zip(
                (str(value) for value in sheet.to_list(0)),
                (str(value) for value in sheet.to_list(1)),
                strict=True,
            )
        )
        chunks = [metadata[key] for key in sorted(metadata) if key.startswith("manifest_json.")]
        if json.loads("".join(chunks)) != plan.manifest.model_dump(mode="json"):
            raise NativeOriginError("Origin manifest JSON differs from the typed plan")
        expected = {
            "origin_plan_sha256": origin_canonical_hash(plan),
            "render_plan_sha256": plan.render_plan_hash,
            "validation_report_sha256": expected_validation_sha256(plan),
        }
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise NativeOriginError("Origin manifest checksums differ from the typed plan")

    def inspect(self, plan: OriginExportPlan) -> dict[str, object]:
        root = self._op.root_folder()
        actual_folders = sorted(folder.GetName() for folder in _folder_items(root.obj.Folders))
        if actual_folders != sorted(PROJECT_FOLDERS):
            raise NativeOriginError("Project Explorer folder set differs from the plan")
        folders = {name: _folder_by_name(root, name) for name in PROJECT_FOLDERS}
        expected_pages: dict[str, list[str]] = {name: [] for name in PROJECT_FOLDERS}
        for data in plan.data_objects:
            expected_pages[data.folder].append(data.internal_name)
        expected_pages["Graphs"].extend(graph.internal_name for graph in plan.graph_objects)
        expected_pages["Metadata"].append(_MANIFEST_BOOK)
        for graph in plan.graph_objects:
            for layer_index, layer in enumerate(graph.layers):
                for plot_index, plot in enumerate(layer.plots):
                    data = next(
                        item for item in plan.data_objects if item.object_id == plot.data_object_id
                    )
                    for primitive_index, primitive in enumerate(native_primitives(plot)):
                        if materialize_primitive(primitive, data) is not None:
                            expected_pages["Analysis"].append(
                                primitive_book_name(
                                    graph.internal_name,
                                    layer_index,
                                    plot_index,
                                    primitive_index,
                                )
                            )
        for folder_name, expected in expected_pages.items():
            if sorted(_page_names(folders[folder_name])) != sorted(expected):
                raise NativeOriginError(f"unexpected native pages in {folder_name}")
        self._inspect_data(plan)
        self._inspect_primitive_pages(plan)
        self._inspect_graphs(plan)
        self._inspect_manifest(plan)
        return cast(dict[str, object], expected_validation_report(plan))

    def save(self, path: str) -> None:
        target = Path(path)
        try:
            saved = bool(self._op.save(str(target)))
        except Exception as exc:
            raise NativeOriginError("Origin could not save the temporary OPJU") from exc
        if not saved or not target.is_file() or target.stat().st_size == 0:
            raise NativeOriginError("Origin did not create a non-empty temporary OPJU")
