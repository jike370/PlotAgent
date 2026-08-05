"""OriginPro implementation of the closed native execution backend.

Only fixed high-level Origin operations live here. User text is assigned as data or label
content and is never interpreted as a command, formula, property path, or template path.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, cast

import numpy as np

from plotagent.contracts.canonical import JsonValue, canonical_hash, canonical_json
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
from .validation import expected_validation_report, expected_validation_sha256

_MANIFEST_BOOK = "PAMETA"
_MANIFEST_SHEET = "Manifest"
_MANIFEST_CHUNK_CHARS = 16_000
_PLOT_TYPE = {
    "line": 200,
    "line_symbol": 202,
    "scatter": 201,
    "column": 203,
    "area": 204,
    "floating_column": 207,
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
        y2_values: tuple[OriginScalar, ...] | None = None,
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
        sheet.shape = (len(x_values), 3 if y2_values is not None else 2)
        sheet.from_list(0, [_safe_cell(value) for value in x_values], lname="X", axis="X")
        sheet.from_list(1, [_safe_cell(value) for value in y_values], lname="Y", axis="Y")
        if y2_values is not None:
            sheet.from_list(
                2,
                [_safe_cell(value) for value in y2_values],
                lname="Y2",
                axis="Y",
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
        if primitive.size_role is not None:
            y_indexes += (_role_index(data, plot_plan, primitive.size_role),)
        if primitive.color_role is not None:
            y_indexes += (_role_index(data, plot_plan, primitive.color_role),)
        data_range = self._data_range(sheet, x_index, *y_indexes)
        native_plot = layer.obj.AddPlot(data_range, _PLOT_TYPE[primitive.plot_type], True)
        if native_plot is None or not native_plot.IsValid():
            raise NativeOriginError(f"could not add native plot {plot_plan.plot_id}")
        plot = self._op.Plot(native_plot, layer.obj)
        if plot_plan.color is not None:
            plot.color = plot_plan.color.value
        if plot_plan.marker_size_pt is not None and primitive.plot_type in {
            "scatter",
            "line_symbol",
        }:
            plot.symbol_size = plot_plan.marker_size_pt
        if plot_plan.line_width_pt is not None and primitive.plot_type in {
            "line",
            "line_symbol",
        }:
            plot.set_float("line.width", plot_plan.line_width_pt)
        if plot_plan.alpha < 1:
            plot.transparency = round((1 - plot_plan.alpha) * 100)
        return plot

    def _configure_axis(self, layer: Any, axis: OriginAxisPlan) -> None:
        native_axis = layer.axis(axis.orientation)
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
        layer.set_int(f"{axis.orientation}.label.type", 10)
        layer.set_str(
            f"{axis.orientation}.label.string",
            _tick_label_string(axis),
        )
        label_name = "xb" if axis.orientation == "x" else "yl"
        label = layer.label(label_name)
        if label is None:
            label = layer.add_label(axis.title)
        if label is None:
            raise NativeOriginError(f"qualified template is missing axis label {label_name}")
        label.text = axis.title

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
        graph.name = graph_plan.internal_name
        graph.lname = graph_plan.long_name
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
            for axis in layer_plan.axes:
                self._configure_axis(layer, axis)
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
                            table.y2,
                        )
                        primitive_for_sheet = NativePrimitive(
                            plot_type=primitive.plot_type,
                            x_role="x",
                            y_role="y",
                            y2_role="y2" if primitive.y2_role is not None else None,
                            size_role=(
                                "y2"
                                if primitive.size_role is not None
                                and primitive.y2_role is None
                                else None
                            ),
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
                        if table.y2 is not None:
                            columns += (
                                data.columns[1].model_copy(
                                    update={
                                        "field_id": f"{data.columns[1].field_id}.upper",
                                        "role": "y2",
                                        "designation": "Y",
                                        "values": table.y2,
                                    }
                                ),
                            )
                        table_payload = {
                            "x": list(table.x),
                            "y": list(table.y),
                            "y2": list(table.y2) if table.y2 is not None else None,
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
                                    "object_hash": canonical_hash(
                                        cast(JsonValue, table_payload)
                                    ),
                                    "row_count": len(table.x),
                                    "field_ids": tuple(
                                        column.field_id for column in columns
                                    ),
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
            labels = [plot.label for plot in layer_plan.plots if plot.label]
            legend = layer.label("legend")
            if legend is not None:
                legend.text = "\n".join(labels) if graph_plan.legend_visible else ""
            for annotation in graph_plan.annotations:
                if annotation.panel_id != layer_plan.panel_id or annotation.text is None:
                    continue
                text = "".join(node.text for node in annotation.text.nodes)
                label = layer.add_label(text, annotation.x, annotation.y)
                if label is None:
                    raise NativeOriginError("could not create native text annotation")

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
                canonical_hash(plan),
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
            for layer_plan, layer in zip(graph_plan.layers, graph, strict=True):
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
                    axis = layer.axis(axis_plan.orientation)
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
                    expected_labels = _tick_label_string(axis_plan)
                    actual_label_type = layer.get_int(
                        f"{axis_plan.orientation}.label.type"
                    )
                    actual_labels = layer.get_str(
                        f"{axis_plan.orientation}.label.string"
                    )
                    if actual_label_type != 10 or actual_labels != expected_labels:
                        raise NativeOriginError(
                            f"native tick labels differ for {axis_plan.axis_id}"
                        )
                    label_name = "xb" if axis_plan.orientation == "x" else "yl"
                    label = layer.label(label_name)
                    if label is None or label.text != axis_plan.title:
                        raise NativeOriginError(
                            f"native axis title differs for {axis_plan.axis_id}"
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
            "origin_plan_sha256": canonical_hash(plan),
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
