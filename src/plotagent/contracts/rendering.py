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
from plotagent.contracts.styles import LineStyle, ResolvedPalette, SymbolStyle

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
    color: ColorValue = ColorValue(value="#000000")
    line_width: PhysicalLength = PhysicalLength(value=0.8, unit="pt")
    cross_at: FiniteNumber | None = None

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
    label: SafeRichText | None = None


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
    line_style: LineStyle = "solid"
    symbol: SymbolStyle = SymbolStyle()
    palette_spec: ResolvedPalette | None = None
    fill_color: ColorValue | None = None
    edge_color: ColorValue | None = None
    edge_width: PhysicalLength | None = None
    width_ratio: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)] = 0.8
    alpha: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)] = 1.0
    uncertainty_color: ColorValue | None = None
    uncertainty_line_width: PhysicalLength | None = None
    cap_size: PhysicalLength | None = None
    band_alpha: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)] = 0.25
    step_where: Literal["pre", "mid", "post"] = "post"

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
    common: bool = False


class ResolvedColorbar(StrictModel):
    visible: bool = False
    title: SafeRichText | None = None
    minimum: FiniteNumber | None = None
    maximum: FiniteNumber | None = None
    levels: Annotated[int, Field(ge=2, le=64)] = 7


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
    x2: FiniteNumber | None = None
    y2: FiniteNumber | None = None
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
    title: SafeRichText | None = None
    color_space: Literal["sRGB"] = "sRGB"
    svg_text_mode: Literal["text_to_path", "editable_text"] = "text_to_path"
    panels: Annotated[tuple[ResolvedPanel, ...], Field(min_length=1)]
    axes: Annotated[tuple[ResolvedAxis, ...], Field(min_length=1)]
    layers: Annotated[tuple[ResolvedLayer, ...], Field(min_length=1)]
    fonts: Annotated[tuple[ResolvedFont, ...], Field(min_length=1)]
    legend: ResolvedLegend = ResolvedLegend()
    colorbar: ResolvedColorbar = ResolvedColorbar()
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


type OriginScalar = str | int | float | bool | None


class OriginColumnPlan(StrictModel):
    """One persisted worksheet column with no formula or executable property surface."""

    field_id: FieldId
    role: Token
    designation: Literal["X", "Y", "Z", "XError", "YError", "Label", "Group", "None"]
    logical_type: Literal["numeric", "categorical", "datetime", "text"]
    long_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    units: Annotated[str, StringConstraints(max_length=128, strict=True)] = ""
    comments: Annotated[str, StringConstraints(max_length=512, strict=True)] = ""
    values: tuple[OriginScalar, ...]


class OriginMatrixPlan(StrictModel):
    """Native matrix values and coordinate mapping; raster payloads are impossible by type."""

    row_count: NonNegativeInt
    column_count: NonNegativeInt
    x_coordinates: tuple[FiniteNumber, ...]
    y_coordinates: tuple[FiniteNumber, ...]
    x_labels: tuple[str, ...] = ()
    y_labels: tuple[str, ...] = ()
    values: tuple[tuple[FiniteNumber | None, ...], ...]
    units: Annotated[str, StringConstraints(max_length=128, strict=True)] = ""

    @model_validator(mode="after")
    def valid_matrix_shape(self) -> OriginMatrixPlan:
        if len(self.x_coordinates) != self.column_count:
            raise ValueError("Origin matrix X coordinates must match the column count")
        if len(self.y_coordinates) != self.row_count:
            raise ValueError("Origin matrix Y coordinates must match the row count")
        if len(self.values) != self.row_count or any(
            len(row) != self.column_count for row in self.values
        ):
            raise ValueError("Origin matrix values must match the declared shape")
        if self.x_labels and len(self.x_labels) != self.column_count:
            raise ValueError("Origin matrix X labels must match the column count")
        if self.y_labels and len(self.y_labels) != self.row_count:
            raise ValueError("Origin matrix Y labels must match the row count")
        return self


class OriginDataObject(StrictModel):
    object_id: Token
    object_kind: Literal["worksheet", "matrixbook"]
    folder: Literal["Data", "Analysis"]
    internal_name: Annotated[
        str,
        StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$", strict=True),
    ]
    long_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    data_chain: Literal["direct", "fixed_plot_calculation", "user_provided_precomputed"]
    data_ref: ContentTableRef
    columns: tuple[OriginColumnPlan, ...] = ()
    matrix: OriginMatrixPlan | None = None

    @model_validator(mode="after")
    def valid_data_layout(self) -> OriginDataObject:
        if self.object_kind == "worksheet":
            if not self.columns or self.matrix is not None:
                raise ValueError("Origin worksheets require columns and cannot contain a matrix")
            row_counts = {len(column.values) for column in self.columns}
            if row_counts != {self.data_ref.row_count}:
                raise ValueError("Origin worksheet column rows must match the content table")
            if tuple(column.field_id for column in self.columns) != self.data_ref.field_ids:
                raise ValueError("Origin worksheet columns must preserve content-table field order")
        elif self.matrix is None or self.columns:
            raise ValueError("Origin matrixbooks require one matrix and cannot contain columns")
        return self


class OriginTickPlan(StrictModel):
    value: FiniteNumber
    label: Annotated[str, StringConstraints(max_length=256, strict=True)]


class OriginAxisPlan(StrictModel):
    axis_id: Token
    orientation: Literal["x", "y"]
    position: Literal["bottom", "top", "left", "right", "none"] = "bottom"
    scale: Literal["linear", "log10", "datetime", "categorical"]
    minimum: FiniteNumber
    maximum: FiniteNumber
    reverse: bool = False
    ticks: Annotated[tuple[OriginTickPlan, ...], Field(min_length=1)]
    title: Annotated[str, StringConstraints(max_length=512, strict=True)] = ""
    color: ColorValue = ColorValue(value="#000000")
    line_width_pt: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 0.8
    cross_at: FiniteNumber | None = None

    @model_validator(mode="after")
    def valid_axis(self) -> OriginAxisPlan:
        if self.minimum >= self.maximum:
            raise ValueError("Origin axis minimum must be lower than maximum")
        tick_values = tuple(tick.value for tick in self.ticks)
        if tuple(sorted(tick_values)) != tick_values or len(set(tick_values)) != len(tick_values):
            raise ValueError("Origin axis ticks must be strictly increasing")
        return self


class OriginRoleColumn(StrictModel):
    role: Token
    field_id: FieldId


class OriginPlotPlan(StrictModel):
    plot_id: Token
    source_layer_id: Token
    native_kind: Literal[
        "line",
        "line_symbol",
        "scatter",
        "bubble",
        "error_bar",
        "band",
        "area",
        "bar",
        "grouped_bar",
        "stacked_bar",
        "floating_bar",
        "lollipop",
        "percent_bar",
        "horizontal_bar",
        "strip",
        "box",
        "violin",
        "histogram",
        "density",
        "step",
        "heatmap",
        "contour",
        "survival_step",
        "survival_band",
        "risk_table",
        "forest_interval",
        "forest_symbol",
        "spectrum",
        "nyquist",
        "facet_line",
    ]
    data_object_id: Token
    role_columns: Annotated[tuple[OriginRoleColumn, ...], Field(min_length=1)]
    z_order: int
    label: Annotated[str, StringConstraints(max_length=512, strict=True)] = ""
    color: ColorValue | None = None
    palette: tuple[ColorValue, ...] = ()
    levels: tuple[FiniteNumber, ...] = ()
    line_width_pt: FiniteNumber | None = None
    marker_size_pt: FiniteNumber | None = None
    line_style: LineStyle = "solid"
    symbol: SymbolStyle = SymbolStyle()
    palette_spec: ResolvedPalette | None = None
    alpha: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 1.0
    fill_color: ColorValue | None = None
    edge_color: ColorValue | None = None
    edge_width_pt: FiniteNumber | None = None
    width_ratio: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)] = 0.8
    uncertainty_color: ColorValue | None = None
    uncertainty_line_width_pt: FiniteNumber | None = None
    cap_size_pt: FiniteNumber | None = None
    band_alpha: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)] = 0.25
    step_where: Literal["pre", "mid", "post"] = "post"


class OriginLayerPlan(StrictModel):
    layer_id: Token
    panel_id: Token
    left_mm: FiniteNumber
    top_mm: FiniteNumber
    width_mm: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    height_mm: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    axes: Annotated[tuple[OriginAxisPlan, ...], Field(min_length=2, max_length=2)]
    plots: Annotated[tuple[OriginPlotPlan, ...], Field(min_length=1)]
    label: Annotated[str, StringConstraints(max_length=256, strict=True)] = ""


class OriginGraphObject(StrictModel):
    graph_id: Token
    folder: Literal["Graphs"] = "Graphs"
    internal_name: Annotated[
        str,
        StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$", strict=True),
    ]
    long_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    page_width_mm: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    page_height_mm: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    font_family: Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]
    font_size_pt: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    title: Annotated[str, StringConstraints(max_length=512, strict=True)] = ""
    legend_visible: bool
    legend_anchor_x: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 1.0
    legend_anchor_y: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 1.0
    layers: Annotated[tuple[OriginLayerPlan, ...], Field(min_length=1)]
    data_object_ids: Annotated[tuple[Token, ...], Field(min_length=1)]
    annotations: tuple[ResolvedAnnotation, ...] = ()
    colorbar: ResolvedColorbar = ResolvedColorbar()

    @model_validator(mode="after")
    def unique_graph_parts(self) -> OriginGraphObject:
        if len({layer.layer_id for layer in self.layers}) != len(self.layers):
            raise ValueError("Origin graph layer ids must be unique")
        plot_ids = [plot.plot_id for layer in self.layers for plot in layer.plots]
        if len(set(plot_ids)) != len(plot_ids):
            raise ValueError("Origin graph plot ids must be unique")
        return self


class OriginObjectMapEntry(StrictModel):
    plotagent_object_id: Token
    origin_object_ref: Annotated[
        str,
        StringConstraints(pattern=r"^(Data|Analysis|Graphs|Metadata)/[A-Za-z0-9_/]+$", strict=True),
    ]


class OriginManifestPlan(StrictModel):
    chart_type_ids: Annotated[tuple[ChartTypeId, ...], Field(min_length=1)]
    target_scope: Literal["current_plot", "selected_plots", "batch", "figure"]
    object_map: Annotated[tuple[OriginObjectMapEntry, ...], Field(min_length=1)]
    render_plan_hashes: Annotated[tuple[RenderPlanHash, ...], Field(min_length=1)]
    data_chains: Annotated[
        tuple[Literal["direct", "fixed_plot_calculation", "user_provided_precomputed"], ...],
        Field(min_length=1),
    ]
    resolver_versions: Annotated[tuple[Token, ...], Field(min_length=1)]
    raw_data_triggers_plotagent_recalculation: Literal[False] = False
    external_links: Literal[False] = False
    known_differences: tuple[str, ...] = ()


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
    manifest: OriginManifestPlan
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
        plot_ids = {
            plot.plot_id
            for graph in self.graph_objects
            for layer in graph.layers
            for plot in layer.plots
        }
        if any(
            plot.data_object_id not in data_ids
            for graph in self.graph_objects
            for layer in graph.layers
            for plot in layer.plots
        ):
            raise ValueError("Origin plots must reference declared data objects")
        mapped = {entry.plotagent_object_id for entry in self.manifest.object_map}
        required = data_ids | {graph.graph_id for graph in self.graph_objects} | plot_ids
        if not required.issubset(mapped):
            raise ValueError("Origin manifest must map every data, graph, and plot object")
        if self.capability == "O1" and self.manifest.known_differences:
            raise ValueError("O1 Origin plans cannot declare known differences")
        return self
