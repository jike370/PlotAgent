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
    PlotCalculationSpecRef,
    PlotSpecRef,
    PrecomputedKind,
    PreparationSpecRef,
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
from plotagent.contracts.styles import LineStyle, PaletteId, ResolvedPalette, SymbolStyle

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


class SpecialFamily(StrictModel):
    kind: Literal["special"] = "special"
    geometry: Annotated[
        tuple[
            Literal[
                "step",
                "lollipop",
                "dumbbell",
                "beeswarm",
                "ridgeline",
                "floating_bar",
                "bridge",
                "bullet",
                "pyramid",
                "scatter_matrix",
                "density2d",
                "marginal",
                "probability",
                "agreement",
                "dual_axis",
                "y_offset",
                "volcano",
            ],
            ...,
        ],
        Field(min_length=1),
    ]


PlotFamily = Annotated[
    XYFamily
    | CategoricalFamily
    | DistributionFamily
    | MatrixFamily
    | SurvivalFamily
    | DoseResponseFamily
    | ForestFamily
    | FacetFamily
    | SpecialFamily,
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


class SeriesStyleSpec(StrictModel):
    color: ColorValue | None = None
    category_colors: dict[str, ColorValue] = Field(default_factory=dict)
    line_width: PhysicalLength | None = None
    marker_size: PhysicalLength | None = None
    line_style: LineStyle = "solid"
    symbol: SymbolStyle = SymbolStyle()
    palette: ResolvedPalette | None = None


class SeriesSpec(StrictModel):
    series_id: Annotated[
        str,
        StringConstraints(pattern=r"^series:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    geometry: AllGeometryKind
    data: SeriesData
    label: SafeRichText | None = None
    style: SeriesStyleSpec = SeriesStyleSpec()


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


class LegendSpec(StrictModel):
    visible: bool | None = None
    placement: Literal["inside", "outside_right", "outside_bottom"] = "inside"
    anchor_x: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 1.0
    anchor_y: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 1.0


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
    legend: LegendSpec = LegendSpec()
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
    line_style: LineStyle | None = None
    symbol: SymbolStyle | None = None

    @model_validator(mode="after")
    def has_style_change(self) -> SetSeriesStylePatch:
        if all(
            value is None
            for value in (
                self.color,
                self.line_width,
                self.marker_size,
                self.line_style,
                self.symbol,
            )
        ):
            raise ValueError("set_series_style requires at least one style value")
        return self


class SetPalettePatch(PatchBase):
    operation: Literal["set_palette"] = "set_palette"
    palette_id: PaletteId
    reverse: bool = False


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
    | SetPalettePatch
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


class BatchExecutionSignature(StrictModel):
    """Source-independent identity for one strictly isomorphic batch fan-out."""

    dataset_signature: DatasetSignature
    field_mapping_hash: Sha256
    preparation_spec_hash: Sha256
    plot_calculation_spec_hash: Sha256 | None = None
    chart_type_id: ChartTypeId
    plot_template_hash: Sha256
    style_hash: Sha256
    content_hash: Sha256

    @model_validator(mode="after")
    def canonical_content_hash(self) -> BatchExecutionSignature:
        from plotagent.contracts.canonical import canonical_hash

        payload = self.model_dump(mode="json", exclude={"content_hash"})
        if canonical_hash(payload) != self.content_hash:
            raise ValueError("batch execution signature hash is not canonical")
        return self


class BatchPlotOverride(StrictModel):
    item_id: Token
    prepared_dataset_ref: PreparedDatasetRef
    patches: tuple[PlotPatch, ...] = ()


class BatchItemState(StrictModel):
    item_id: Token
    state: Literal[
        "pending",
        "queued",
        "preparing",
        "running",
        "committing",
        "succeeded",
        "failed",
        "cancelled",
    ]
    error_code: Token | None = None
    plot_version_ref: PlotSpecRef | None = None
    review_state: Literal["unconfirmed", "confirmed", "excluded"] = "unconfirmed"

    @model_validator(mode="after")
    def terminal_payload(self) -> BatchItemState:
        if self.state == "succeeded":
            if self.plot_version_ref is None or self.error_code is not None:
                raise ValueError("succeeded batch items require only a plot version reference")
        elif self.plot_version_ref is not None:
            raise ValueError("only succeeded batch items may reference a plot version")
        if self.state == "failed" and self.error_code is None:
            raise ValueError("failed batch items require a stable error code")
        if self.state != "failed" and self.error_code is not None:
            raise ValueError("only failed batch items may carry an error code")
        return self


class BatchSpec(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    batch_id: Annotated[
        str,
        StringConstraints(pattern=r"^batch:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    batch_version: VersionId
    dataset_signature: DatasetSignature
    execution_signature: BatchExecutionSignature
    dataset_version_refs: Annotated[tuple[PreparedDatasetRef, ...], Field(min_length=1)]
    shared_field_mapping: FieldMappingRef
    shared_preparation: PreparationSpecRef
    shared_plot_calculation: PlotCalculationSpecRef | None = None
    plot_template_ref: PlotSpecRef
    shared_style: ResolvedStyleSnapshot
    axis_policy: Literal["per_plot", "unified"] = "per_plot"
    plot_overrides: tuple[BatchPlotOverride, ...] = ()
    item_states: Annotated[tuple[BatchItemState, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_items(self) -> BatchSpec:
        from plotagent.contracts.canonical import canonical_hash

        item_ids = tuple(item.item_id for item in self.item_states)
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("batch item ids must be unique")
        if any(item.item_id not in set(item_ids) for item in self.plot_overrides):
            raise ValueError("batch overrides must reference declared items")
        signature = self.execution_signature
        if signature.dataset_signature != self.dataset_signature:
            raise ValueError("batch dataset signature must match the execution signature")
        if signature.field_mapping_hash != self.shared_field_mapping.content_hash:
            raise ValueError("batch field mapping must match the execution signature")
        if signature.preparation_spec_hash != self.shared_preparation.content_hash:
            raise ValueError("batch preparation must match the execution signature")
        calculation_hash = (
            None
            if self.shared_plot_calculation is None
            else self.shared_plot_calculation.content_hash
        )
        if signature.plot_calculation_spec_hash != calculation_hash:
            raise ValueError("batch plot calculation must match the execution signature")
        if signature.plot_template_hash != self.plot_template_ref.content_hash:
            raise ValueError("batch plot template must match the execution signature")
        if signature.style_hash != canonical_hash(self.shared_style):
            raise ValueError("batch style must match the execution signature")
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
    layout: Literal["1x2", "1x3", "1x4", "2x1", "2x2", "2x3", "3x1"]
    panels: Annotated[tuple[FigurePanel, ...], Field(min_length=2, max_length=6)]
    alignment: Literal["independent", "align_x", "align_y", "align_both"] = "align_both"
    axis_policy: Literal["independent", "shared_x", "shared_y", "shared_both"] = "independent"
    common_legend: bool
    physical_size: PhysicalSize
    publication_profile: PublicationProfileSnapshot
    parent_figure_version: VersionId | None = None

    @model_validator(mode="after")
    def layout_capacity(self) -> FigureSpec:
        capacity = {
            "1x2": 2,
            "1x3": 3,
            "1x4": 4,
            "2x1": 2,
            "2x2": 4,
            "2x3": 6,
            "3x1": 3,
        }[self.layout]
        if len(self.panels) > capacity:
            raise ValueError("panel count exceeds fixed layout capacity")
        if len({panel.panel_id for panel in self.panels}) != len(self.panels):
            raise ValueError("panel ids must be unique")
        return self


class ArtifactNaming(StrictModel):
    output_name: SafeOutputName
    collision_policy: Literal["fail", "confirm_overwrite", "save_as"] = "fail"
