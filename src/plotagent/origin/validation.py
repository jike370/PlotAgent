"""Deterministic structural evidence for native Origin projects."""

from __future__ import annotations

from typing import cast

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.rendering import OriginExportPlan


def primitive_count(native_kind: str) -> int:
    """Return the fixed number of native Origin primitives used by one plan plot."""

    if native_kind in {"band", "box", "forest_interval"}:
        return {"band": 2, "box": 5, "forest_interval": 3}[native_kind]
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
                "content_sha256": canonical_hash(data),
            }
        )
    graphs: list[JsonValue] = []
    for graph in plan.graph_objects:
        graphs.append(
            {
                "graph_id": graph.graph_id,
                "origin_name": graph.internal_name,
                "layer_count": len(graph.layers),
                "native_plot_count": sum(
                    primitive_count(plot.native_kind)
                    for layer in graph.layers
                    for plot in layer.plots
                ),
                "data_object_ids": list(graph.data_object_ids),
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
        "origin_plan_sha256": canonical_hash(plan),
        "render_plan_sha256": plan.render_plan_hash,
        "manifest_sha256": canonical_hash(plan.manifest),
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
    return canonical_hash(cast(JsonValue, expected_validation_report(plan)))
