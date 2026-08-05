"""Business validation that complements the strict W0 Pydantic contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import ValidationError

from plotagent.charts.registry import get_chart
from plotagent.charts.series_rules import get_series_rule
from plotagent.contracts.plots import (
    AddAnnotationPatch,
    ApplyPublicationProfilePatch,
    MoveLegendPatch,
    PlotPatch,
    PlotSpec,
    RemoveAnnotationPatch,
    SafeRichText,
    SetAxisLabelPatch,
    SetAxisRangePatch,
    SetAxisScalePatch,
    SetBatchAxisPolicyPatch,
    SetCanvasSizePatch,
    SetCategoryColorPatch,
    SetLegendVisibilityPatch,
    SetSeriesStylePatch,
    UpdateAnnotationPatch,
)

if TYPE_CHECKING:
    from plotagent.rendering.data import RenderDataStore

_UNSAFE_TEXT = re.compile(
    r"(?:<\s*/?\s*(?:script|style|iframe|svg|math|html)\b|"
    r"javascript\s*:|on(?:load|error|click)\s*=|"
    r"\\(?:begin|end|frac|input|include|write|href)\b|\$[^$]*\$)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class PlotValidationError(ValueError):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def validate_safe_text(value: SafeRichText) -> None:
    total_length = 0
    for node in value.nodes:
        total_length += len(node.text) + len(node.denominator or "")
        if _UNSAFE_TEXT.search(node.text) or (
            node.denominator is not None and _UNSAFE_TEXT.search(node.denominator)
        ):
            raise PlotValidationError(
                "PLOTSPEC_SAFE_TEXT_INVALID",
                "safe chart text cannot contain renderer markup, scripts, or LaTeX commands",
            )
    if total_length > 2048:
        raise PlotValidationError("PLOTSPEC_SAFE_TEXT_INVALID", "safe chart text is too long")


def _binding_hash(plot: PlotSpec, series_index: int) -> str:
    data = plot.series[series_index].data
    if data.kind == "prepared":
        return data.prepared_dataset_ref.content_hash
    if data.kind == "calculated":
        return data.calculation_result_ref.content_hash
    return data.precomputed_data_ref.data_ref_hash


def validate_plot_spec(
    plot: PlotSpec,
    data_store: RenderDataStore,
    *,
    allow_panel_plan_placeholder: bool = False,
) -> PlotSpec:
    """Validate local fields, bindings, text, and chart-specific geometry roles."""

    try:
        PlotSpec.model_validate(plot.model_dump())
    except ValidationError as error:
        raise PlotValidationError("PLOTSPEC_FAMILY_MISMATCH", str(error)) from error
    registration = get_chart(plot.chart_type_id)
    if registration.adapter_family == "facet" and plot.chart_type_id == "K25":
        if not allow_panel_plan_placeholder:
            raise PlotValidationError(
                "PLOTSPEC_PANEL_PLANS_REQUIRED",
                "K25 must be resolved from explicit child plans and placements",
            )
        return plot

    for axis in plot.axes:
        validate_safe_text(axis.label)
    for series in plot.series:
        if series.label is not None:
            validate_safe_text(series.label)
    for annotation in plot.annotations:
        if annotation.text is not None:
            validate_safe_text(annotation.text)

    for index, series in enumerate(plot.series):
        try:
            rule = get_series_rule(plot.chart_type_id, series.geometry)
            roles = rule.roles_for_count(len(series.data.role_fields))
        except ValueError as error:
            raise PlotValidationError("PLOTSPEC_FAMILY_MISMATCH", str(error)) from error
        if series.data.kind not in rule.data_kinds:
            raise PlotValidationError(
                "PLOTSPEC_DATA_CHAIN_MISMATCH",
                f"{series.series_id} cannot consume {series.data.kind} data",
            )
        try:
            table = data_store.get(_binding_hash(plot, index))
        except KeyError as error:
            raise PlotValidationError("PLOTSPEC_DATA_BINDING_MISSING", str(error)) from error
        missing_fields = set(series.data.role_fields) - set(table.field_ids)
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise PlotValidationError(
                "PLOTSPEC_FIELD_MISSING",
                f"{series.series_id} references fields not present in its table: {missing}",
            )
        role_to_field = dict(zip(roles, series.data.role_fields, strict=True))
        if "lower" in role_to_field and "upper" in role_to_field:
            lower = table.column(role_to_field["lower"])
            upper = table.column(role_to_field["upper"])
            for row_index, (low, high) in enumerate(zip(lower, upper, strict=True)):
                if isinstance(low, (int, float)) and isinstance(high, (int, float)) and low > high:
                    raise PlotValidationError(
                        "PLOTSPEC_INTERVAL_INVALID",
                        f"lower exceeds upper in {series.series_id} row {row_index}",
                    )
    return plot


def validate_plot_patch(plot: PlotSpec, patch: PlotPatch) -> PlotPatch:
    """Validate target existence and expected version before a patch transaction."""

    if isinstance(patch, SetBatchAxisPolicyPatch):
        raise PlotValidationError("PATCH_TARGET_INVALID", "a batch patch cannot target a PlotSpec")
    if patch.expected_plot_version != plot.plot_version:
        raise PlotValidationError("PATCH_VERSION_CONFLICT", "patch expected version is stale")

    axes = {axis.axis_id: axis for axis in plot.axes}
    series_ids = {series.series_id for series in plot.series}
    annotation_ids = {annotation.annotation_id for annotation in plot.annotations}

    if isinstance(patch, (SetAxisRangePatch, SetAxisScalePatch, SetAxisLabelPatch)):
        if patch.target_id not in axes:
            raise PlotValidationError("PATCH_TARGET_INVALID", "axis target does not exist")
        if isinstance(patch, SetAxisRangePatch):
            scale = next(
                scale for scale in plot.scales if scale.scale_id == axes[patch.target_id].scale_id
            )
            if scale.kind == "log10" and (patch.minimum <= 0 or patch.maximum <= 0):
                raise PlotValidationError("AXIS_LOG_NONPOSITIVE", "Log10 bounds must be positive")
        if isinstance(patch, SetAxisLabelPatch):
            validate_safe_text(patch.label)
    elif isinstance(patch, (SetSeriesStylePatch, SetCategoryColorPatch)):
        if patch.target_id not in series_ids:
            raise PlotValidationError("PATCH_TARGET_INVALID", "series target does not exist")
    elif isinstance(patch, (MoveLegendPatch, SetLegendVisibilityPatch)):
        if patch.target_id != "legend:main":
            raise PlotValidationError("PATCH_TARGET_INVALID", "legend target does not exist")
    elif isinstance(patch, AddAnnotationPatch):
        if patch.annotation.annotation_id in annotation_ids:
            raise PlotValidationError("PATCH_TARGET_INVALID", "annotation id already exists")
        if patch.annotation.text is not None:
            validate_safe_text(patch.annotation.text)
    elif isinstance(patch, UpdateAnnotationPatch):
        if patch.annotation.annotation_id not in annotation_ids:
            raise PlotValidationError("PATCH_TARGET_INVALID", "annotation target does not exist")
        if patch.annotation.text is not None:
            validate_safe_text(patch.annotation.text)
    elif isinstance(patch, RemoveAnnotationPatch):
        if patch.annotation_id not in annotation_ids:
            raise PlotValidationError("PATCH_TARGET_INVALID", "annotation target does not exist")
    elif isinstance(patch, (ApplyPublicationProfilePatch, SetCanvasSizePatch)):
        if not patch.target_id.startswith("panel:"):
            raise PlotValidationError("PATCH_TARGET_INVALID", "canvas patch must target a panel")
    return patch
