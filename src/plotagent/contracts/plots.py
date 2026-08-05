"""Plot, patch, batch, and fixed-layout figure contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import (
    SCHEMA_VERSION,
    ChartTypeId,
    ColorValue,
    FieldId,
    FieldMappingRef,
    FiniteNumber,
    ObjectVersionRef,
    PhysicalLength,
    PhysicalSize,
    PlotCalculationResultRef,
    PlotSpecRef,
    PrecomputedKind,
    PreparedDatasetRef,
    SafeOutputName,
    SchemaVersion,
    SemanticTargetId,
    Sha256,
    StrictModel,
    Token,
    VersionId,
)
from plotagent.contracts.registry import CHARTS_BY_ID, GeometryKind

AxisScaleKind = Literal["linear", "log10", "datetime", "categorical"]
AllGeometryKind = GeometryKind


class SafeTextNode(StrictModel):
    kind: Literal["plain", "newline", "sub", "sup", "bold", "italic", "fraction"]
    text: Annotated[str, StringConstraints(max_length=512, strict=True)] = ""
    denominator: Annotated[str, StringConstraints(max_length=128, strict=True)] | None = None

    @model_validator(mode="after")
    def fraction_shape(self) -> SafeTextNode:
        if self.kind == "fraction" and self.denominator is None:
            raise ValueError("fraction text requires a denominator")
        if self.kind != "fraction" and self.denominator is not None:
            raise ValueError("only fraction text accepts a denominator")
        return self


class SafeRichText(StrictModel):
    nodes: Annotated[tuple[SafeTextNode, ...], Field(min_length=1)]


class XYFamily(StrictModel):
    kind: Literal["xy"] = "xy"
    geometry: Annotated[
        tuple[Literal["line", "symbol", "error_bar", "band", "area"], ...],
        Field(min_length=1),
    ]


class CategoricalFamily(StrictModel):
    kind: Literal["categorical"] = "categorical"
    geometry: Annotated[tuple[Literal["bar"], ...], Field(min_length=1)]


class DistributionFamily(StrictModel):
    kind: Literal["distribution"] = "distribution"
    geometry: Annotated[
        tuple[Literal["strip", "box", "violin", "histogram", "density", "step"], ...],
        Field(min_length=1),
    ]


class MatrixFamily(StrictModel):
    kind: Literal["matrix"] = "matrix"
    geometry: Annotated[tuple[Literal["heatmap", "contour"], ...], Field(min_length=1)]


class SurvivalFamily(StrictModel):
    kind: Literal["survival"] = "survival"
    geometry: Annotated[tuple[Literal["step", "band", "risk_table"], ...], Field(min_length=1)]


class DoseResponseFamily(StrictModel):
    kind: Literal["dose_response"] = "dose_response"
    geometry: Annotated[tuple[Literal["symbol", "line", "band"], ...], Field(min_length=1)]


class ForestFamily(StrictModel):
    kind: Literal["forest"] = "forest"
    geometry: Annotated[tuple[Literal["interval", "symbol"], ...], Field(min_length=1)]


class FacetFamily(StrictModel):
    kind: Literal["facet"] = "facet"
    geometry: Annotated[tuple[Literal["panel"], ...], Field(min_length=1)]


PlotFamily = Annotated[
    XYFamily
    | CategoricalFamily
    | DistributionFamily
    | MatrixFamily
    | SurvivalFamily
    | DoseResponseFamily
    | ForestFamily
    | FacetFamily,
    Field(discriminator="kind"),
]


class PrecomputedDataRef(StrictModel):
    precomputed_id: Annotated[
        str,
        StringConstraints(pattern=r"^precomputed:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    precomputed_version: VersionId
    precomputed_kind: PrecomputedKind
    content_hash: Sha256
    data_ref_hash: Sha256
    field_ids: Annotated[tuple[FieldId, ...], Field(min_length=1)]
    provenance: Literal["user_provided_precomputed"] = "user_provided_precomputed"


class AxisRange(StrictModel):
    minimum: FiniteNumber | None = None
    maximum: FiniteNumber | None = None
    reverse: bool = False

    @model_validator(mode="after")
    def ordered_if_fixed(self) -> AxisRange:
        if self.minimum is not None and self.maximum is not None and self.minimum >= self.maximum:
            raise ValueError("axis minimum must be lower than maximum")
        return self


class ScaleSpec(StrictModel):
    scale_id: Annotated[
        str,
        StringConstraints(pattern=r"^scale:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    kind: AxisScaleKind
    axis_range: AxisRange = AxisRange()


class AxisSpec(StrictModel):
    axis_id: Annotated[
        str,
        StringConstraints(pattern=r"^axis:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    scale_id: Annotated[
        str,
        StringConstraints(pattern=r"^scale:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    orientation: Literal["x", "y", "color"]
    position: Literal["bottom", "top", "left", "right", "none"]
    label: SafeRichText


class PreparedSeriesData(StrictModel):
    kind: Literal["prepared"] = "prepared"
    prepared_dataset_ref: PreparedDatasetRef
    role_fields: Annotated[tuple[FieldId, ...], Field(min_length=1)]


class CalculatedSeriesData(StrictModel):
    kind: Literal["calculated"] = "calculated"
    calculation_result_ref: PlotCalculationResultRef
    role_fields: Annotated[tuple[FieldId, ...], Field(min_length=1)]


class PrecomputedSeriesData(StrictModel):
    kind: Literal["precomputed"] = "precomputed"
    precomputed_data_ref: PrecomputedDataRef
    role_fields: Annotated[tuple[FieldId, ...], Field(min_length=1)]


SeriesData = Annotated[
    PreparedSeriesData | CalculatedSeriesData | PrecomputedSeriesData,
    Field(discriminator="kind"),
]


class SeriesSpec(StrictModel):
    series_id: Annotated[
        str,
        StringConstraints(pattern=r"^series:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    geometry: AllGeometryKind
    data: SeriesData
    label: SafeRichText | None = None


class AnnotationSpec(StrictModel):
    annotation_id: Annotated[
        str,
        StringConstraints(pattern=r"^annotation:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    kind: Literal[
        "text",
        "arrow",
        "line",
        "rectangle",
        "reference_line",
        "reference_band",
        "peak_label",
        "significance_bracket",
        "panel_label",
    ]
    text: SafeRichText | None = None
    x: FiniteNumber | None = None
    y: FiniteNumber | None = None
    affect_range: bool = False


class StyleSourceRef(StrictModel):
    source_kind: Literal["project", "batch", "plot", "publication_profile"]
    source_id: Token
    source_version: VersionId
    content_hash: Sha256


class ResolvedStyleSnapshot(StrictModel):
    font_family: Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]
    font_size: PhysicalLength
    line_width: PhysicalLength
    marker_size: PhysicalLength
    colors: Annotated[tuple[ColorValue, ...], Field(min_length=1)]


class PublicationProfileSnapshot(StrictModel):
    profile_id: Token
    profile_version: VersionId
    content_hash: Sha256
    physical_size: PhysicalSize
    dpi: Annotated[int, Field(ge=72, le=2400)]
    color_space: Literal["sRGB"] = "sRGB"


class PlotProvenance(StrictModel):
    origin: Literal["manual", "agent_plan"]
    parent_plot_ref: PlotSpecRef | None = None
    plan_id: (
        Annotated[
            str,
            StringConstraints(pattern=r"^plan:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
        ]
        | None
    ) = None
    user_instruction_hash: Sha256 | None = None
    engine_build_hash: Sha256


class PlotSpec(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    plot_id: Annotated[
        str,
        StringConstraints(pattern=r"^plot:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    plot_version: VersionId
    chart_type_id: ChartTypeId
    family: PlotFamily
    prepared_data_refs: Annotated[tuple[PreparedDatasetRef, ...], Field(min_length=1)]
    precomputed_data_refs: tuple[PrecomputedDataRef, ...] = ()
    plot_calculation_refs: tuple[PlotCalculationResultRef, ...] = ()
    scales: Annotated[tuple[ScaleSpec, ...], Field(min_length=1)]
    axes: Annotated[tuple[AxisSpec, ...], Field(min_length=1)]
    series: Annotated[tuple[SeriesSpec, ...], Field(min_length=1)]
    annotations: tuple[AnnotationSpec, ...] = ()
    style_sources: Annotated[tuple[StyleSourceRef, ...], Field(min_length=1)]
    resolved_style: ResolvedStyleSnapshot
    publication_profile: PublicationProfileSnapshot
    provenance: PlotProvenance

    @model_validator(mode="after")
    def registry_contract(self) -> PlotSpec:
        registration = CHARTS_BY_ID[self.chart_type_id]
        if self.family.kind != registration.family:
            raise ValueError("chart family does not match the v1 registry")
        if not set(self.family.geometry).issubset(registration.geometries):
            raise ValueError("geometry is not allowed by the v1 registry")

        calculation_kinds = {ref.calculation_kind for ref in self.plot_calculation_refs}
        if not calculation_kinds.issubset(registration.allowed_calculations):
            raise ValueError("plot calculation is not allowed for this chart")
        if not set(registration.required_calculations).issubset(calculation_kinds):
            raise ValueError("required plot calculation is missing")

        precomputed_kinds = {ref.precomputed_kind for ref in self.precomputed_data_refs}
        if not set(registration.required_precomputed).issubset(precomputed_kinds):
            raise ValueError("required precomputed input is missing")

        if len({scale.scale_id for scale in self.scales}) != len(self.scales):
            raise ValueError("scale ids must be unique")
        if len({axis.axis_id for axis in self.axes}) != len(self.axes):
            raise ValueError("axis ids must be unique")
        if len({series.series_id for series in self.series}) != len(self.series):
            raise ValueError("series ids must be unique")
        scale_ids = {scale.scale_id for scale in self.scales}
        if any(axis.scale_id not in scale_ids for axis in self.axes):
            raise ValueError("every axis must reference a declared scale")
        return self


class PatchBase(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    target_id: SemanticTargetId
    expected_plot_version: VersionId


class SetAxisRangePatch(PatchBase):
    operation: Literal["set_axis_range"] = "set_axis_range"
    minimum: FiniteNumber
    maximum: FiniteNumber

    @model_validator(mode="after")
    def ordered(self) -> SetAxisRangePatch:
        if self.minimum >= self.maximum:
            raise ValueError("axis minimum must be lower than maximum")
        return self


class SetAxisScalePatch(PatchBase):
    operation: Literal["set_axis_scale"] = "set_axis_scale"
    scale: AxisScaleKind


class SetAxisLabelPatch(PatchBase):
    operation: Literal["set_axis_label"] = "set_axis_label"
    label: SafeRichText


class SetSeriesStylePatch(PatchBase):
    operation: Literal["set_series_style"] = "set_series_style"
    color: ColorValue | None = None
    line_width: PhysicalLength | None = None
    marker_size: PhysicalLength | None = None


class SetCategoryColorPatch(PatchBase):
    operation: Literal["set_category_color"] = "set_category_color"
    category: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    color: ColorValue


class MoveLegendPatch(PatchBase):
    operation: Literal["move_legend"] = "move_legend"
    placement: Literal["inside", "outside_right", "outside_bottom"]
    anchor_x: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    anchor_y: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class SetLegendVisibilityPatch(PatchBase):
    operation: Literal["set_legend_visibility"] = "set_legend_visibility"
    visible: bool


class AddAnnotationPatch(PatchBase):
    operation: Literal["add_annotation"] = "add_annotation"
    annotation: AnnotationSpec


class UpdateAnnotationPatch(PatchBase):
    operation: Literal["update_annotation"] = "update_annotation"
    annotation: AnnotationSpec


class RemoveAnnotationPatch(PatchBase):
    operation: Literal["remove_annotation"] = "remove_annotation"
    annotation_id: Annotated[
        str,
        StringConstraints(pattern=r"^annotation:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]


class ApplyPublicationProfilePatch(PatchBase):
    operation: Literal["apply_publication_profile"] = "apply_publication_profile"
    profile: PublicationProfileSnapshot


class SetCanvasSizePatch(PatchBase):
    operation: Literal["set_canvas_size"] = "set_canvas_size"
    physical_size: PhysicalSize


class SetBatchAxisPolicyPatch(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    operation: Literal["set_batch_axis_policy"] = "set_batch_axis_policy"
    target_id: Annotated[
        str,
        StringConstraints(pattern=r"^batch:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    expected_batch_version: VersionId
    axis_policy: Literal["per_plot", "unified"]


PlotPatch = Annotated[
    SetAxisRangePatch
    | SetAxisScalePatch
    | SetAxisLabelPatch
    | SetSeriesStylePatch
    | SetCategoryColorPatch
    | MoveLegendPatch
    | SetLegendVisibilityPatch
    | AddAnnotationPatch
    | UpdateAnnotationPatch
    | RemoveAnnotationPatch
    | ApplyPublicationProfilePatch
    | SetCanvasSizePatch
    | SetBatchAxisPolicyPatch,
    Field(discriminator="operation"),
]


class PatchTransaction(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    transaction_id: Token
    project_id: Annotated[
        str,
        StringConstraints(pattern=r"^project:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    expected_versions: Annotated[tuple[ObjectVersionRef, ...], Field(min_length=1)]
    patches: Annotated[tuple[PlotPatch, ...], Field(min_length=1)]
    scope: Literal["plot", "selected_plots", "batch"]


class DatasetFieldSignature(StrictModel):
    field_id: FieldId
    logical_type: Literal["numeric", "categorical", "datetime", "boolean", "text"]
    unit_hash: Sha256
    semantic_role: Token


class DatasetSignature(StrictModel):
    fields: Annotated[tuple[DatasetFieldSignature, ...], Field(min_length=1)]
    semantic_hash: Sha256


class BatchPlotOverride(StrictModel):
    item_id: Token
    prepared_dataset_ref: PreparedDatasetRef
    patches: tuple[PlotPatch, ...] = ()


class BatchItemState(StrictModel):
    item_id: Token
    state: Literal["pending", "succeeded", "failed", "excluded"]
    error_code: Token | None = None


class BatchSpec(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    batch_id: Annotated[
        str,
        StringConstraints(pattern=r"^batch:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    batch_version: VersionId
    dataset_signature: DatasetSignature
    dataset_version_refs: Annotated[tuple[PreparedDatasetRef, ...], Field(min_length=1)]
    shared_field_mapping: FieldMappingRef
    plot_template_ref: PlotSpecRef
    shared_style: ResolvedStyleSnapshot
    axis_policy: Literal["per_plot", "unified"] = "per_plot"
    plot_overrides: tuple[BatchPlotOverride, ...] = ()
    item_states: Annotated[tuple[BatchItemState, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_items(self) -> BatchSpec:
        item_ids = tuple(item.item_id for item in self.item_states)
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("batch item ids must be unique")
        if any(item.item_id not in set(item_ids) for item in self.plot_overrides):
            raise ValueError("batch overrides must reference declared items")
        return self


class FigurePanel(StrictModel):
    panel_id: Annotated[
        str,
        StringConstraints(pattern=r"^panel:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    plot_version_ref: PlotSpecRef
    panel_label: SafeRichText


class FigureSpec(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    figure_id: Annotated[
        str,
        StringConstraints(pattern=r"^figure:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    figure_version: VersionId
    layout: Literal["1x2", "2x1", "2x2"]
    panels: Annotated[tuple[FigurePanel, ...], Field(min_length=2, max_length=4)]
    common_legend: bool
    physical_size: PhysicalSize
    publication_profile: PublicationProfileSnapshot

    @model_validator(mode="after")
    def layout_capacity(self) -> FigureSpec:
        capacity = {"1x2": 2, "2x1": 2, "2x2": 4}[self.layout]
        if len(self.panels) > capacity:
            raise ValueError("panel count exceeds fixed layout capacity")
        if len({panel.panel_id for panel in self.panels}) != len(self.panels):
            raise ValueError("panel ids must be unique")
        return self


class ArtifactNaming(StrictModel):
    output_name: SafeOutputName
    collision_policy: Literal["fail", "confirm_overwrite", "save_as"] = "fail"
