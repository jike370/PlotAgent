"""Deterministic structural evidence for native Origin projects."""

from __future__ import annotations

import hashlib
import json
from typing import cast

from pydantic import BaseModel

from plotagent.contracts.canonical import JsonValue
from plotagent.contracts.rendering import OriginExportPlan

from .native import (
    materialize_primitive,
    native_primitives,
    physical_plot_count,
    primitive_book_name,
)


def origin_canonical_hash(value: BaseModel | JsonValue) -> str:
    """Hash an ASCII-only canonical payload across the two Origin processes.

    Origin's embedded Windows automation boundary can apply a process code page to
    non-ASCII text. Escaping Unicode before hashing keeps Chinese labels and scientific
    symbols byte-identical in the parent, build worker, and fresh-reopen worker.
    """

    payload = (
        value.model_dump(mode="json", by_alias=True, exclude_none=False)
        if isinstance(value, BaseModel)
        else value
    )
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def primitive_count(native_kind: str) -> int:
    """Return the fixed number of native Origin primitives used by one plan plot."""

    if native_kind in {"error_bar", "box"}:
        return {
            "error_bar": 2,
            "box": 2,
        }[native_kind]
    return 1


def expected_validation_report(plan: OriginExportPlan) -> dict[str, JsonValue]:
    """Build the report that both live and fresh-reopen inspection must reproduce."""

    data_objects: list[JsonValue] = []
    for data in plan.data_objects:
        if data.object_kind == "worksheet":
            row_count = data.data_ref.row_count
            column_count = len(data.columns)
        else:
            if data.matrix is None:  # protected by the strict OriginDataObject contract
                raise ValueError("matrixbook has no native matrix")
            row_count = data.matrix.row_count
            column_count = data.matrix.column_count
        data_objects.append(
            {
                "object_id": data.object_id,
                "object_kind": data.object_kind,
                "origin_name": data.internal_name,
                "row_count": row_count,
                "column_count": column_count,
                "content_sha256": origin_canonical_hash(data),
            }
        )
    graphs: list[JsonValue] = []
    for graph in plan.graph_objects:
        layers: list[JsonValue] = []
        primitive_data_pages: list[JsonValue] = []
        data_by_id = {item.object_id: item for item in plan.data_objects}
        for layer_index, layer in enumerate(graph.layers):
            primitive_bindings: list[JsonValue] = []
            for plot_index, plot in enumerate(layer.plots):
                data = data_by_id[plot.data_object_id]
                for primitive_index, primitive in enumerate(native_primitives(plot)):
                    table = materialize_primitive(primitive, data)
                    page_name = None
                    if table is not None:
                        page_name = primitive_book_name(
                            graph.internal_name,
                            layer_index,
                            plot_index,
                            primitive_index,
                        )
                        primitive_data_pages.append(
                            {
                                "origin_name": page_name,
                                "row_count": len(table.x),
                                "content_sha256": origin_canonical_hash(
                                    cast(
                                        JsonValue,
                                        {
                                            "x": list(table.x),
                                            "y": list(table.y),
                                            "y2": (
                                                list(table.y2) if table.y2 is not None else None
                                            ),
                                        },
                                    )
                                ),
                            }
                        )
                    primitive_bindings.append(
                        {
                            "plot_id": plot.plot_id,
                            "data_object_id": plot.data_object_id,
                            "primitive_index": primitive_index,
                            "plot_type": primitive.plot_type,
                            "transform": primitive.transform,
                            "x_role": primitive.x_role,
                            "y_role": primitive.y_role,
                            "error_role": primitive.error_role,
                            "y2_role": primitive.y2_role,
                            "size_role": primitive.size_role,
                            "color_role": primitive.color_role,
                            "cap_size_pt": primitive.cap_size_pt,
                            "primitive_data_page": page_name,
                            "color": plot.color.value if plot.color is not None else None,
                            "palette": [color.value for color in plot.palette],
                            "palette_spec": (
                                plot.palette_spec.model_dump(mode="json")
                                if plot.palette_spec is not None
                                else None
                            ),
                            "line_style": plot.line_style,
                            "symbol": plot.symbol.model_dump(mode="json"),
                        }
                    )
            layers.append(
                {
                    "layer_id": layer.layer_id,
                    "panel_id": layer.panel_id,
                    "frame_mm": [
                        layer.left_mm,
                        layer.top_mm,
                        layer.width_mm,
                        layer.height_mm,
                    ],
                    "primitive_bindings": primitive_bindings,
                }
            )
        graphs.append(
            {
                "graph_id": graph.graph_id,
                "origin_name": graph.internal_name,
                "layer_count": len(graph.layers),
                "native_plot_count": sum(
                    physical_plot_count(primitive)
                    for layer in graph.layers
                    for plot in layer.plots
                    for primitive in native_primitives(plot)
                ),
                "data_object_ids": list(graph.data_object_ids),
                "layers": layers,
                "primitive_data_pages": primitive_data_pages,
                "axes": [
                    {
                        "axis_id": axis.axis_id,
                        "orientation": axis.orientation,
                        "scale": axis.scale,
                        "minimum": axis.minimum,
                        "maximum": axis.maximum,
                        "reverse": axis.reverse,
                        "title": axis.title,
                    }
                    for layer in graph.layers
                    for axis in layer.axes
                ],
            }
        )
    return {
        "schema_version": plan.schema_version,
        "capability": "O1",
        "origin_plan_sha256": origin_canonical_hash(plan),
        "render_plan_sha256": plan.render_plan_hash,
        "manifest_sha256": origin_canonical_hash(plan.manifest),
        "folders": ["Data", "Analysis", "Graphs", "Metadata"],
        "data_objects": data_objects,
        "graphs": graphs,
        "object_map": cast(
            JsonValue,
            [item.model_dump(mode="json") for item in plan.manifest.object_map],
        ),
        "native_graphs": True,
        "native_data": True,
        "formulas": False,
        "external_links": False,
        "raster_objects": False,
    }


def expected_validation_sha256(plan: OriginExportPlan) -> str:
    return origin_canonical_hash(cast(JsonValue, expected_validation_report(plan)))
