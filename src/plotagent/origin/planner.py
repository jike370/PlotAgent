"""Compile renderer-neutral resolved plots into a closed typed Origin execution plan."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, cast

from plotagent.contracts.base import (
    ChartTypeId,
    ExportSpecRef,
    ObjectVersionRef,
    ResourceRef,
)
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.plots import SafeRichText
from plotagent.contracts.rendering import (
    ExportSpec,
    ExportValidationRequirements,
    OriginAxisPlan,
    OriginColumnPlan,
    OriginDataObject,
    OriginExactVersion,
    OriginExportPlan,
    OriginGraphObject,
    OriginLayerPlan,
    OriginManifestPlan,
    OriginMatrixPlan,
    OriginObjectMapEntry,
    OriginPlotPlan,
    OriginRoleColumn,
    OriginSizeKeyEntry,
    OriginSizeKeyPlan,
    OriginTemplateRef,
    OriginTickPlan,
    ResolvedAxis,
    ResolvedLayer,
)
from plotagent.rendering.data import RenderTable, ResolvedPlot, Scalar
from plotagent.rendering.size_key import representative_size_key

from .constants import (
    DECLARED_ORIGIN_DISPLAY_VERSION,
    DECLARED_ORIGIN_RUNTIME_VERSION,
    ORIGIN_TEMPLATE_ID,
    ORIGIN_TEMPLATE_SHA256,
    ORIGIN_VARIABLE_SIZE_FACTOR,
)
from .registry import OriginAdapterRegistration, get_origin_adapter

_NATIVE_KINDS = {
    "xy.line": "line",
    "xy.datetime_line": "line",
    "xy.symbol": "scatter",
    "xy.bubble": "bubble",
    "xy.error": "error_bar",
    "xy.band": "band",
    "xy.area": "area",
    "xy.spectrum": "spectrum",
    "xy.nyquist": "nyquist",
    "bar.single": "bar",
    "bar.grouped": "grouped_bar",
    "bar.stacked": "stacked_bar",
    "bar.floating": "floating_bar",
    "special.drop_line": "drop_line",
    "bar.percent": "percent_bar",
    "bar.horizontal": "horizontal_bar",
    "distribution.strip": "strip",
    "distribution.box": "box",
    "distribution.violin": "violin",
    "distribution.histogram": "histogram",
    "distribution.density": "density",
    "distribution.step": "step",
    "matrix.heatmap": "heatmap",
    "matrix.correlation": "heatmap",
    "matrix.contour": "contour",
    "matrix.confusion": "heatmap",
    "special.survival_step": "survival_step",
    "special.survival_band": "survival_band",
    "special.risk_table": "risk_table",
    "special.forest_interval": "forest_interval",
    "special.forest_symbol": "forest_symbol",
    "facet.xy": "facet_line",
}

_X_ROLES = {
    "x",
    "time",
    "dose",
    "spectral_axis",
    "angle",
    "z_real",
    "grid",
    "left",
}
_Y_ROLES = {
    "y",
    "center",
    "value",
    "response",
    "intensity",
    "z_imaginary",
    "height",
    "density",
    "probability",
    "survival",
    "effect",
}
_LABEL_ROLES = {"label", "peak_label", "risk_count"}
_GROUP_ROLES = {"group", "category", "component", "facet", "panel"}


class OriginPlanError(ValueError):
    code = "CAPABILITY_MISSING"


def _safe_text(value: SafeRichText | None) -> str:
    if value is None:
        return ""
    output: list[str] = []
    for node in value.nodes:
        if node.kind == "newline":
            output.append("\n")
        elif node.kind == "fraction":
            output.append(f"{node.text}/{node.denominator}")
        else:
            output.append(node.text)
    return "".join(output)


def _data_chain(source_kind: str) -> str:
    if source_kind in {"direct", "panel_plan"}:
        return "direct"
    if source_kind == "fixed":
        return "fixed_plot_calculation"
    if source_kind == "user_precomputed":
        return "user_provided_precomputed"
    raise OriginPlanError(f"unsupported resolved data source {source_kind!r}")


def _designation(role: str) -> str:
    if role in _X_ROLES:
        return "X"
    if role in _Y_ROLES:
        return "Y"
    if role in {"z", "top"}:
        return "Z"
    if role in {"x_lower", "x_upper"}:
        return "XError"
    if role in {"lower", "upper", "error"}:
        return "YError"
    if role in _LABEL_ROLES:
        return "Label"
    if role in _GROUP_ROLES:
        return "Group"
    return "None"


def _logical_type(role: str, values: tuple[Scalar, ...], axes: Sequence[ResolvedAxis]) -> str:
    if role == "time" and any(axis.scale == "datetime" for axis in axes):
        return "datetime"
    if role in _GROUP_ROLES or role in _LABEL_ROLES:
        return "categorical"
    nonmissing = tuple(value for value in values if value is not None)
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in nonmissing):
        return "numeric"
    return "text"


def _column_plans(
    layer: ResolvedLayer,
    table: RenderTable,
    axes: Sequence[ResolvedAxis],
) -> tuple[OriginColumnPlan, ...]:
    columns: list[OriginColumnPlan] = []
    for binding in layer.field_bindings:
        values = table.column(binding.field_id)
        columns.append(
            OriginColumnPlan(
                field_id=binding.field_id,
                role=binding.role,
                designation=cast(Any, _designation(binding.role)),
                logical_type=cast(Any, _logical_type(binding.role, values, axes)),
                long_name=binding.role.replace("_", " ").title(),
                units="",
                comments=f"plotagent_field_id={binding.field_id};role={binding.role}",
                values=values,
            )
        )
    return tuple(columns)


def _matrix_roles(layer: ResolvedLayer) -> tuple[str, str, str]:
    roles = {binding.role for binding in layer.field_bindings}
    for candidate in (
        ("column", "row", "value"),
        ("column_label", "row_label", "value"),
        ("x", "y", "z"),
        ("predicted", "actual", "value"),
    ):
        if set(candidate).issubset(roles):
            return candidate
    raise OriginPlanError(f"{layer.geometry} does not expose a complete matrix role set")


def _axis_labels(axis: ResolvedAxis, coordinates: tuple[float, ...]) -> tuple[str, ...]:
    labels: list[str] = []
    for coordinate in coordinates:
        matching = next(
            (
                tick
                for tick in axis.ticks
                if math.isclose(tick.value, coordinate, rel_tol=0.0, abs_tol=1e-12)
            ),
            None,
        )
        labels.append(_safe_text(matching.label) if matching is not None else str(coordinate))
    return tuple(labels)


def _matrix_plan(
    layer: ResolvedLayer,
    table: RenderTable,
    axes: Sequence[ResolvedAxis],
) -> OriginMatrixPlan:
    x_role, y_role, value_role = _matrix_roles(layer)
    fields = {binding.role: binding.field_id for binding in layer.field_bindings}
    x_values = tuple(_matrix_number(value) for value in table.column(fields[x_role]))
    y_values = tuple(_matrix_number(value) for value in table.column(fields[y_role]))
    z_values = table.column(fields[value_role])
    x_coordinates = tuple(sorted(set(x_values)))
    y_coordinates = tuple(sorted(set(y_values)))
    values_by_coordinate: dict[tuple[float, float], float | None] = {}
    for x_value, y_value, raw_value in zip(x_values, y_values, z_values, strict=True):
        key = (x_value, y_value)
        if key in values_by_coordinate:
            raise OriginPlanError("matrix coordinates must be unique")
        values_by_coordinate[key] = None if raw_value is None else _matrix_number(raw_value)
    expected = {(x, y) for y in y_coordinates for x in x_coordinates}
    if set(values_by_coordinate) != expected:
        raise OriginPlanError("matrix coordinates must form a complete rectangular grid")
    x_axis = next(axis for axis in axes if axis.orientation == "x")
    y_axis = next(axis for axis in axes if axis.orientation == "y")
    return OriginMatrixPlan(
        row_count=len(y_coordinates),
        column_count=len(x_coordinates),
        x_coordinates=x_coordinates,
        y_coordinates=y_coordinates,
        x_labels=_axis_labels(x_axis, x_coordinates),
        y_labels=_axis_labels(y_axis, y_coordinates),
        values=tuple(
            tuple(values_by_coordinate[(x, y)] for x in x_coordinates) for y in y_coordinates
        ),
    )


def _matrix_number(value: Scalar) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise OriginPlanError("matrix coordinates and values must be finite numeric data")
    return float(value)


def _axis_plan(axis: ResolvedAxis) -> OriginAxisPlan:
    if axis.minimum is None or axis.maximum is None or not axis.ticks:
        raise OriginPlanError(f"resolved axis {axis.axis_id} is incomplete")
    return OriginAxisPlan(
        axis_id=axis.axis_id,
        orientation=cast(Any, axis.orientation),
        position=axis.position,
        scale=axis.scale,
        minimum=axis.minimum,
        maximum=axis.maximum,
        reverse=axis.reverse,
        ticks=tuple(
            OriginTickPlan(value=tick.value, label=_safe_text(tick.label)) for tick in axis.ticks
        ),
        title=_safe_text(axis.label),
        color=axis.color,
        line_width_pt=axis.line_width.value,
        cross_at=axis.cross_at,
    )


def _size_key_plan(resolved: ResolvedPlot) -> OriginSizeKeyPlan:
    pairs: list[tuple[float, float]] = []
    for layer in resolved.plan.layers:
        if layer.geometry != "xy.bubble":
            continue
        fields = {binding.role: binding.field_id for binding in layer.field_bindings}
        if "size" not in fields or "marker_area" not in fields:
            continue
        table = resolved.table_for(layer)
        sizes = table.column(fields["size"])
        areas = table.column(fields["marker_area"])
        for size, area in zip(sizes, areas, strict=True):
            if not isinstance(size, (int, float)) or isinstance(size, bool):
                raise OriginPlanError("bubble size key requires numeric size values")
            if not isinstance(area, (int, float)) or isinstance(area, bool):
                raise OriginPlanError("bubble size key requires numeric marker areas")
            pairs.append((float(size), float(area)))
    entries = representative_size_key(pairs)
    if not entries:
        return OriginSizeKeyPlan()
    return OriginSizeKeyPlan(
        visible=True,
        entries=tuple(
            OriginSizeKeyEntry(
                value=entry.value,
                marker_size_pt=max(entry.value, 0.0) * ORIGIN_VARIABLE_SIZE_FACTOR,
                label=f"{entry.value:.4g}",
            )
            for entry in entries
        ),
    )


def _composite_render_hash(resolved_plots: Sequence[ResolvedPlot]) -> str:
    if len(resolved_plots) == 1:
        return resolved_plots[0].render_plan_hash
    return canonical_hash(cast(JsonValue, [item.render_plan_hash for item in resolved_plots]))


def build_origin_export_spec(
    resolved_plots: Sequence[ResolvedPlot],
    *,
    export_id: str = "export:origin",
    target_scope: str = "current_plot",
    output_name: str = "plotagent.opju",
) -> ExportSpec:
    """Build the narrow local ExportSpec used by tests and the gated qualification runner."""

    if not resolved_plots:
        raise ValueError("Origin export requires at least one resolved plot")
    refs: list[ObjectVersionRef] = []
    seen: set[tuple[str, int]] = set()
    for resolved in resolved_plots:
        for ref in resolved.plan.source_refs:
            identity = (ref.object_id, ref.expected_version)
            if identity not in seen:
                seen.add(identity)
                refs.append(ref)
    return ExportSpec(
        export_id=export_id,
        export_version=1,
        format="opju",
        target_scope=cast(Any, target_scope),
        target_refs=tuple(refs),
        target_resource=ResourceRef(
            resource_id="resource:origin_output",
            resource_kind="authorized_directory",
        ),
        output_name=output_name,
        render_plan_hash=_composite_render_hash(resolved_plots),
        validation=ExportValidationRequirements(require_fresh_reopen=True),
    )


def compile_origin_plan(
    resolved_plots: Sequence[ResolvedPlot],
    export_spec: ExportSpec,
) -> OriginExportPlan:
    """Compile one or more formal ResolvedPlots without recalculating any geometry."""

    resolved_plots = tuple(resolved_plots)
    if not resolved_plots:
        raise OriginPlanError("Origin export requires at least one resolved plot")
    if export_spec.format != "opju" or not export_spec.validation.require_fresh_reopen:
        raise OriginPlanError("Origin execution requires an OPJU ExportSpec with fresh reopen")
    if export_spec.render_plan_hash != _composite_render_hash(resolved_plots):
        raise OriginPlanError("ExportSpec render plan hash does not match the resolved plots")

    data_objects: list[OriginDataObject] = []
    graph_objects: list[OriginGraphObject] = []
    object_map: list[OriginObjectMapEntry] = []
    data_by_key: dict[tuple[str, str, str], str] = {}
    adapters: list[OriginAdapterRegistration] = []
    data_chains: list[str] = []

    for graph_index, resolved in enumerate(resolved_plots):
        plan = resolved.plan
        if plan.quality_tier != "formal" or plan.data_integrity.simplification_applied:
            raise OriginPlanError("Origin O1 only accepts unsimplified formal render plans")
        if plan.chart_type_id is None:
            raise OriginPlanError("Origin export requires an explicit chart type ID")
        adapter = get_origin_adapter(plan.chart_type_id)
        adapters.append(adapter)
        actual_geometries = {layer.geometry for layer in plan.layers}
        if not actual_geometries.issubset(set(adapter.allowed_geometries)):
            raise OriginPlanError(
                f"{plan.chart_type_id} contains geometry outside its qualified adapter"
            )
        graph_name = f"G{plan.chart_type_id}{graph_index:02d}"
        graph_id = f"graph.{plan.chart_type_id}.{graph_index}"
        axes_by_panel: dict[str, list[ResolvedAxis]] = {}
        for axis in plan.axes:
            if axis.orientation in {"x", "y"}:
                axes_by_panel.setdefault(axis.panel_id, []).append(axis)
        layer_plans: list[OriginLayerPlan] = []
        graph_data_ids: list[str] = []

        for panel_index, panel in enumerate(plan.panels):
            panel_layers = tuple(layer for layer in plan.layers if layer.panel_id == panel.panel_id)
            if not panel_layers:
                raise OriginPlanError(f"Origin panel {panel.panel_id} has no native data plot")
            axes = tuple(axes_by_panel.get(panel.panel_id, ()))
            if {axis.orientation for axis in axes} != {"x", "y"} or len(axes) != 2:
                raise OriginPlanError(
                    f"Origin panel {panel.panel_id} requires one X and one Y axis"
                )
            plot_plans: list[OriginPlotPlan] = []
            for plot_index, layer in enumerate(panel_layers):
                table = resolved.table_for(layer)
                chain = _data_chain(layer.data_source_kind)
                if chain not in data_chains:
                    data_chains.append(chain)
                object_kind = "matrixbook" if layer.geometry.startswith("matrix.") else "worksheet"
                key = (table.object_hash, chain, object_kind)
                data_id = data_by_key.get(key)
                if data_id is None:
                    data_index = len(data_objects)
                    data_id = f"data.{plan.chart_type_id}.{data_index}"
                    data_by_key[key] = data_id
                    folder = "Data" if chain == "direct" else "Analysis"
                    prefix = "D" if folder == "Data" else "A"
                    internal_name = f"{prefix}{plan.chart_type_id}{data_index:03d}"
                    matrix = (
                        _matrix_plan(layer, table, axes) if object_kind == "matrixbook" else None
                    )
                    columns = () if matrix is not None else _column_plans(layer, table, axes)
                    data_objects.append(
                        OriginDataObject(
                            object_id=data_id,
                            object_kind=cast(Any, object_kind),
                            folder=cast(Any, folder),
                            internal_name=internal_name,
                            long_name=(
                                f"{plan.chart_type_id} {chain.replace('_', ' ').title()} Data"
                            ),
                            data_chain=cast(Any, chain),
                            data_ref=layer.data_ref,
                            columns=columns,
                            matrix=matrix,
                        )
                    )
                    object_map.append(
                        OriginObjectMapEntry(
                            plotagent_object_id=data_id,
                            origin_object_ref=f"{folder}/{internal_name}",
                        )
                    )
                if data_id not in graph_data_ids:
                    graph_data_ids.append(data_id)
                plot_id = f"plot.{plan.chart_type_id}.{graph_index}.{panel_index}.{plot_index}"
                plot_plans.append(
                    OriginPlotPlan(
                        plot_id=plot_id,
                        source_layer_id=layer.layer_id,
                        native_kind=cast(Any, _NATIVE_KINDS[layer.geometry]),
                        data_object_id=data_id,
                        role_columns=tuple(
                            OriginRoleColumn(role=item.role, field_id=item.field_id)
                            for item in layer.field_bindings
                        ),
                        z_order=layer.z_order,
                        label=_safe_text(layer.label),
                        color=layer.color,
                        palette=layer.palette,
                        levels=layer.levels,
                        line_width_pt=(
                            layer.line_width.value if layer.line_width is not None else None
                        ),
                        marker_size_pt=(
                            layer.marker_size.value if layer.marker_size is not None else None
                        ),
                        line_style=layer.line_style,
                        symbol=layer.symbol,
                        palette_spec=layer.palette_spec,
                        fill_color=layer.fill_color,
                        edge_color=layer.edge_color,
                        edge_width_pt=(
                            layer.edge_width.value if layer.edge_width is not None else None
                        ),
                        width_ratio=layer.width_ratio,
                        alpha=layer.alpha,
                        uncertainty_color=layer.uncertainty_color,
                        uncertainty_line_width_pt=(
                            layer.uncertainty_line_width.value
                            if layer.uncertainty_line_width is not None
                            else None
                        ),
                        cap_size_pt=(layer.cap_size.value if layer.cap_size is not None else None),
                        band_alpha=layer.band_alpha,
                        step_where=layer.step_where,
                    )
                )
                object_map.append(
                    OriginObjectMapEntry(
                        plotagent_object_id=plot_id,
                        origin_object_ref=f"Graphs/{graph_name}/L{panel_index:02d}/P{plot_index:02d}",
                    )
                )
            layer_id = f"originlayer.{plan.chart_type_id}.{graph_index}.{panel_index}"
            layer_plans.append(
                OriginLayerPlan(
                    layer_id=layer_id,
                    panel_id=panel.panel_id,
                    left_mm=panel.left.value,
                    top_mm=panel.top.value,
                    width_mm=panel.width.value,
                    height_mm=panel.height.value,
                    axes=tuple(
                        _axis_plan(axis) for axis in sorted(axes, key=lambda item: item.orientation)
                    ),
                    plots=tuple(plot_plans),
                    label=_safe_text(panel.label),
                )
            )
        font = plan.fonts[0]
        graph_objects.append(
            OriginGraphObject(
                graph_id=graph_id,
                internal_name=graph_name,
                long_name=f"{plan.chart_type_id} Native Plot",
                page_width_mm=plan.canvas.width.value,
                page_height_mm=plan.canvas.height.value,
                font_family=font.family,
                font_size_pt=font.size.value,
                title=_safe_text(plan.title),
                legend_visible=plan.legend.visible,
                legend_anchor_x=plan.legend.anchor_x,
                legend_anchor_y=plan.legend.anchor_y,
                layers=tuple(layer_plans),
                data_object_ids=tuple(graph_data_ids),
                annotations=plan.annotations,
                colorbar=plan.colorbar,
                size_key=_size_key_plan(resolved),
            )
        )
        object_map.append(
            OriginObjectMapEntry(
                plotagent_object_id=graph_id,
                origin_object_ref=f"Graphs/{graph_name}",
            )
        )

    chart_ids = tuple(cast(ChartTypeId, item.plan.chart_type_id) for item in resolved_plots)
    manifest = OriginManifestPlan(
        chart_type_ids=chart_ids,
        target_scope=export_spec.target_scope,
        object_map=tuple(object_map),
        render_plan_hashes=tuple(item.render_plan_hash for item in resolved_plots),
        data_chains=cast(Any, tuple(data_chains)),
        resolver_versions=tuple(
            dict.fromkeys(item.plan.resolver_version for item in resolved_plots)
        ),
    )
    adapter_families = "+".join(dict.fromkeys(adapter.adapter_family for adapter in adapters))
    return OriginExportPlan(
        origin_plan_id=f"originplan:{export_spec.export_id.removeprefix('export:')}",
        origin_plan_version=1,
        export_spec_ref=ExportSpecRef(
            export_id=export_spec.export_id,
            export_version=export_spec.export_version,
            content_hash=canonical_hash(export_spec),
        ),
        render_plan_hash=export_spec.render_plan_hash,
        adapter_id=f"plotagent.origin.registry.{adapter_families}",
        adapter_version="1.0.0",
        origin_version=OriginExactVersion(
            version=DECLARED_ORIGIN_DISPLAY_VERSION,
            build=f"{DECLARED_ORIGIN_RUNTIME_VERSION:.6f}",
        ),
        template=OriginTemplateRef(
            template_resource=ResourceRef(
                resource_id=f"resource:{ORIGIN_TEMPLATE_ID.replace('-', '_')}",
                resource_kind="authorized_file",
            ),
            template_hash=ORIGIN_TEMPLATE_SHA256,
            signature_hash=ORIGIN_TEMPLATE_SHA256,
        ),
        data_objects=tuple(data_objects),
        graph_objects=tuple(graph_objects),
        manifest=manifest,
    )
