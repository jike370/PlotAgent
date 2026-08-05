"""Export, resolved-render, and typed Origin-plan contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import (
    SCHEMA_VERSION,
    ChartTypeId,
    ColorValue,
    ContentTableRef,
    ExportSpecRef,
    FieldId,
    FiniteNumber,
    NonNegativeInt,
    ObjectVersionRef,
    PhysicalLength,
    PhysicalSize,
    ResourceRef,
    SafeOutputName,
    SchemaVersion,
    SemanticTargetId,
    Sha256,
    StrictModel,
    Token,
    VersionId,
    WarningRecord,
)
from plotagent.contracts.plots import SafeRichText

RenderPlanHash = Sha256


class ExportValidationRequirements(StrictModel):
    validate_structure: Literal[True] = True
    validate_dimensions: Literal[True] = True
    validate_content: Literal[True] = True
    require_fresh_reopen: bool = False


class ExportSpec(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    export_id: Annotated[
        str,
        StringConstraints(pattern=r"^export:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    export_version: VersionId
    format: Literal["png", "svg", "opju"]
    target_scope: Literal["current_plot", "selected_plots", "batch", "figure"]
    target_refs: Annotated[tuple[ObjectVersionRef, ...], Field(min_length=1)]
    target_resource: ResourceRef
    output_name: SafeOutputName
    render_plan_hash: RenderPlanHash
    validation: ExportValidationRequirements = ExportValidationRequirements()

    @model_validator(mode="after")
    def opju_reopens(self) -> ExportSpec:
        if self.format == "opju" and not self.validation.require_fresh_reopen:
            raise ValueError("OPJU export requires fresh-reopen validation")
        return self


class ResolvedTick(StrictModel):
    value: FiniteNumber
    label: SafeRichText


class ResolvedAxis(StrictModel):
    axis_id: Annotated[
        str,
        StringConstraints(pattern=r"^axis:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    panel_id: Annotated[
        str,
        StringConstraints(pattern=r"^panel:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ] = "panel:main"
    orientation: Literal["x", "y", "color"] = "x"
    position: Literal["bottom", "top", "left", "right", "none"] = "bottom"
    scale: Literal["linear", "log10", "datetime", "categorical"]
    minimum: FiniteNumber | None = None
    maximum: FiniteNumber | None = None
    reverse: bool = False
    ticks: tuple[ResolvedTick, ...] = ()
    exponent: int = 0
    precision: NonNegativeInt = 0
    label: SafeRichText

    @model_validator(mode="after")
    def fixed_range_order(self) -> ResolvedAxis:
        if self.minimum is not None and self.maximum is not None and self.minimum >= self.maximum:
            raise ValueError("resolved axis minimum must be lower than maximum")
        return self


class ResolvedFont(StrictModel):
    family: Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]
    file_hash: Sha256
    size: PhysicalLength


class ResolvedPanel(StrictModel):
    panel_id: Annotated[
        str,
        StringConstraints(pattern=r"^panel:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    left: PhysicalLength
    top: PhysicalLength
    width: PhysicalLength
    height: PhysicalLength


class ResolvedFieldBinding(StrictModel):
    role: Token
    field_id: FieldId


class ResolvedLayer(StrictModel):
    layer_id: Token
    target_id: SemanticTargetId
    panel_id: Annotated[
        str,
        StringConstraints(pattern=r"^panel:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ] = "panel:main"
    geometry: Token
    data_source_kind: Literal["direct", "fixed", "user_precomputed", "panel_plan"] = "direct"
    data_ref: ContentTableRef
    field_ids: Annotated[tuple[str, ...], Field(min_length=1)]
    field_bindings: tuple[ResolvedFieldBinding, ...] = ()
    full_row_count: NonNegativeInt = 0
    displayed_row_count: NonNegativeInt = 0
    z_order: int
    label: SafeRichText | None = None
    color: ColorValue | None = None
    palette: tuple[ColorValue, ...] = ()
    levels: tuple[FiniteNumber, ...] = ()
    color_minimum: FiniteNumber | None = None
    color_maximum: FiniteNumber | None = None
    line_width: PhysicalLength | None = None
    marker_size: PhysicalLength | None = None

    @model_validator(mode="after")
    def valid_resolved_data(self) -> ResolvedLayer:
        if self.full_row_count and self.displayed_row_count > self.full_row_count:
            raise ValueError("displayed rows cannot exceed full rows")
        if self.displayed_row_count and self.displayed_row_count != self.data_ref.row_count:
            raise ValueError("displayed rows must match the resolved data reference")
        if self.field_bindings:
            binding_fields = tuple(item.field_id for item in self.field_bindings)
            if binding_fields != self.field_ids:
                raise ValueError("field bindings must preserve the resolved field order")
            if len({item.role for item in self.field_bindings}) != len(self.field_bindings):
                raise ValueError("resolved field roles must be unique")
        return self


class ResolvedLegend(StrictModel):
    visible: bool = False
    placement: Literal["inside", "outside_right", "outside_bottom"] = "inside"
    anchor_x: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 1.0
    anchor_y: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 1.0


class ResolvedAnnotation(StrictModel):
    annotation_id: Annotated[
        str,
        StringConstraints(pattern=r"^annotation:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    panel_id: Annotated[
        str,
        StringConstraints(pattern=r"^panel:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ] = "panel:main"
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


class DataIntegritySnapshot(StrictModel):
    total_rows: NonNegativeInt
    visible_rows: NonNegativeInt
    excluded_rows: NonNegativeInt
    nonfinite_values: NonNegativeInt
    simplification_applied: bool
    full_data_hash: Sha256

    @model_validator(mode="after")
    def valid_counts(self) -> DataIntegritySnapshot:
        if self.visible_rows + self.excluded_rows > self.total_rows:
            raise ValueError("visible and excluded rows cannot exceed total rows")
        return self


class ResolvedRenderPlan(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    render_plan_id: Annotated[
        str,
        StringConstraints(pattern=r"^renderplan:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    render_plan_version: VersionId
    chart_type_id: ChartTypeId | None = None
    resolver_version: Token
    source_refs: Annotated[tuple[ObjectVersionRef, ...], Field(min_length=1)]
    source_content_hashes: Annotated[tuple[Sha256, ...], Field(min_length=1)]
    quality_tier: Literal["thumbnail", "interactive", "formal"]
    canvas: PhysicalSize
    dpi: Annotated[int, Field(ge=72, le=2400)] = 300
    background: ColorValue = ColorValue(value="#FFFFFF")
    color_space: Literal["sRGB"] = "sRGB"
    svg_text_mode: Literal["text_to_path", "editable_text"] = "text_to_path"
    panels: Annotated[tuple[ResolvedPanel, ...], Field(min_length=1)]
    axes: Annotated[tuple[ResolvedAxis, ...], Field(min_length=1)]
    layers: Annotated[tuple[ResolvedLayer, ...], Field(min_length=1)]
    fonts: Annotated[tuple[ResolvedFont, ...], Field(min_length=1)]
    legend: ResolvedLegend = ResolvedLegend()
    annotations: tuple[ResolvedAnnotation, ...] = ()
    data_integrity: DataIntegritySnapshot
    warnings: tuple[WarningRecord, ...] = ()

    @model_validator(mode="after")
    def unique_resolved_ids(self) -> ResolvedRenderPlan:
        if len({panel.panel_id for panel in self.panels}) != len(self.panels):
            raise ValueError("resolved panel ids must be unique")
        if len({axis.axis_id for axis in self.axes}) != len(self.axes):
            raise ValueError("resolved axis ids must be unique")
        if len({layer.layer_id for layer in self.layers}) != len(self.layers):
            raise ValueError("resolved layer ids must be unique")
        if self.quality_tier == "formal" and self.data_integrity.simplification_applied:
            raise ValueError("formal render plans cannot use visual simplification")
        return self


class OriginExactVersion(StrictModel):
    version: Token
    build: Token
    bitness: Literal["x64"] = "x64"


class OriginTemplateRef(StrictModel):
    template_resource: ResourceRef
    template_hash: Sha256
    signature_hash: Sha256


class OriginDataObject(StrictModel):
    object_id: Token
    object_kind: Literal["worksheet", "matrixbook"]
    folder: Literal["Data", "Analysis"]
    internal_name: Annotated[
        str,
        StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$", strict=True),
    ]
    long_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    data_ref: ContentTableRef


class OriginGraphObject(StrictModel):
    graph_id: Token
    folder: Literal["Graphs"] = "Graphs"
    internal_name: Annotated[
        str,
        StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$", strict=True),
    ]
    long_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    layer_ids: Annotated[tuple[Token, ...], Field(min_length=1)]
    data_object_ids: Annotated[tuple[Token, ...], Field(min_length=1)]


OriginNumericPropertyName = Literal[
    "page.width_mm",
    "page.height_mm",
    "layer.left_mm",
    "layer.top_mm",
    "layer.width_mm",
    "layer.height_mm",
    "axis.minimum",
    "axis.maximum",
    "plot.line_width_pt",
    "plot.marker_size_pt",
]
OriginBooleanPropertyName = Literal[
    "axis.reverse",
    "legend.visible",
]


class OriginNumericProperty(StrictModel):
    value_kind: Literal["number"] = "number"
    target_id: Token
    property_name: OriginNumericPropertyName
    value: FiniteNumber


class OriginBooleanProperty(StrictModel):
    value_kind: Literal["boolean"] = "boolean"
    target_id: Token
    property_name: OriginBooleanPropertyName
    value: bool


class OriginScaleProperty(StrictModel):
    value_kind: Literal["scale"] = "scale"
    target_id: Token
    property_name: Literal["axis.scale"] = "axis.scale"
    value: Literal["linear", "log10", "datetime", "categorical"]


class OriginColorProperty(StrictModel):
    value_kind: Literal["color"] = "color"
    target_id: Token
    property_name: Literal["plot.color"] = "plot.color"
    value: ColorValue


OriginPropertyAssignment = Annotated[
    OriginNumericProperty | OriginBooleanProperty | OriginScaleProperty | OriginColorProperty,
    Field(discriminator="value_kind"),
]


class OriginValidationPlan(StrictModel):
    live_structural_validation: Literal[True] = True
    fresh_reopen_validation: Literal[True] = True
    require_no_external_links: Literal[True] = True
    require_atomic_publish: Literal[True] = True


class OriginExportPlan(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    origin_plan_id: Annotated[
        str,
        StringConstraints(pattern=r"^originplan:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    origin_plan_version: VersionId
    export_spec_ref: ExportSpecRef
    render_plan_hash: RenderPlanHash
    adapter_id: Token
    adapter_version: Token
    capability: Literal["O1"] = "O1"
    origin_version: OriginExactVersion
    template: OriginTemplateRef
    project_folders: Literal["Data/Analysis/Graphs/Metadata"] = "Data/Analysis/Graphs/Metadata"
    data_objects: Annotated[tuple[OriginDataObject, ...], Field(min_length=1)]
    graph_objects: Annotated[tuple[OriginGraphObject, ...], Field(min_length=1)]
    property_assignments: tuple[OriginPropertyAssignment, ...] = ()
    validation: OriginValidationPlan = OriginValidationPlan()

    @model_validator(mode="after")
    def valid_origin_links(self) -> OriginExportPlan:
        data_ids = {item.object_id for item in self.data_objects}
        if len(data_ids) != len(self.data_objects):
            raise ValueError("Origin data object ids must be unique")
        if len({item.graph_id for item in self.graph_objects}) != len(self.graph_objects):
            raise ValueError("Origin graph ids must be unique")
        if any(not set(graph.data_object_ids).issubset(data_ids) for graph in self.graph_objects):
            raise ValueError("Origin graphs must reference declared data objects")
        return self
