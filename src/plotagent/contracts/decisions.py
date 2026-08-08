"""The only four model-visible AgentDecision variants."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import (
    SCHEMA_VERSION,
    ChartTypeId,
    ColorValue,
    FiniteNumber,
    PhysicalSize,
    SafeOutputName,
    SchemaVersion,
    SemanticAlias,
    StrictModel,
)
from plotagent.contracts.plots import (
    BarAreaEditSpec,
    ChartParameterEditSpec,
    ColorbarEditSpec,
    DualYAxisEditSpec,
    FacetEditSpec,
    UncertaintyEditSpec,
    YOffsetEditSpec,
)
from plotagent.contracts.styles import (
    LineStyle,
    PaletteId,
    SymbolInterior,
    SymbolShape,
)

ActionType = Literal[
    "create_plot",
    "patch_plot",
    "create_batch",
    "patch_batch",
    "create_figure",
    "patch_figure",
    "export_artifact",
]
PatchOperation = Literal[
    "set_plot_title",
    "set_axis_range",
    "set_axis_scale",
    "set_axis_label",
    "set_axis_reverse",
    "set_axis_ticks",
    "set_font_size",
    "set_bar_area_style",
    "set_uncertainty_style",
    "set_colorbar_style",
    "set_dual_y_style",
    "set_facet_style",
    "set_y_offset_style",
    "set_chart_parameters",
    "set_series_style",
    "set_category_color",
    "set_palette",
    "set_legend_visibility",
    "move_legend",
    "apply_publication_profile",
    "set_canvas_size",
    "add_annotation",
]

ActionId = Annotated[
    str,
    StringConstraints(pattern=r"^action:[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", strict=True),
]


class SemanticFieldSelection(StrictModel):
    role: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$", strict=True),
    ]
    context_field_alias: SemanticAlias


class ActionBase(StrictModel):
    action_id: ActionId
    depends_on: tuple[ActionId, ...] = ()


class CreatePlotAction(ActionBase):
    action_type: Literal["create_plot"] = "create_plot"
    target_alias: SemanticAlias
    chart_type_id: ChartTypeId
    field_selections: Annotated[tuple[SemanticFieldSelection, ...], Field(min_length=1)]


class AxisRangeIntent(StrictModel):
    operation: Literal["set_axis_range"] = "set_axis_range"
    target_alias: SemanticAlias
    minimum: FiniteNumber | None = None
    maximum: FiniteNumber | None = None

    @model_validator(mode="after")
    def ordered(self) -> AxisRangeIntent:
        if (self.minimum is None) != (self.maximum is None):
            raise ValueError("axis bounds must both be fixed or both be automatic")
        if self.minimum is not None and self.maximum is not None and self.minimum >= self.maximum:
            raise ValueError("axis minimum must be lower than maximum")
        return self


class PlotTitleIntent(StrictModel):
    operation: Literal["set_plot_title"] = "set_plot_title"
    target_alias: SemanticAlias
    title: Annotated[str, StringConstraints(max_length=256, strict=True)] | None = None


class AxisScaleIntent(StrictModel):
    operation: Literal["set_axis_scale"] = "set_axis_scale"
    target_alias: SemanticAlias
    scale: Literal["linear", "log10", "datetime", "categorical"]


class AxisLabelIntent(StrictModel):
    operation: Literal["set_axis_label"] = "set_axis_label"
    target_alias: SemanticAlias
    label: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]


class AxisReverseIntent(StrictModel):
    operation: Literal["set_axis_reverse"] = "set_axis_reverse"
    target_alias: SemanticAlias
    reverse: bool


class AxisTicksIntent(StrictModel):
    operation: Literal["set_axis_ticks"] = "set_axis_ticks"
    target_alias: SemanticAlias
    major_interval: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None
    number_format: Literal["auto", "fixed", "scientific"] = "auto"
    decimal_places: Annotated[int, Field(ge=0, le=12)] = 3


class FontSizeIntent(StrictModel):
    operation: Literal["set_font_size"] = "set_font_size"
    target_alias: SemanticAlias
    size_pt: Annotated[float, Field(ge=5, le=72, allow_inf_nan=False)]


class BarAreaStyleIntent(StrictModel):
    operation: Literal["set_bar_area_style"] = "set_bar_area_style"
    target_alias: SemanticAlias
    style: BarAreaEditSpec


class UncertaintyStyleIntent(StrictModel):
    operation: Literal["set_uncertainty_style"] = "set_uncertainty_style"
    target_alias: SemanticAlias
    style: UncertaintyEditSpec


class ColorbarStyleIntent(StrictModel):
    operation: Literal["set_colorbar_style"] = "set_colorbar_style"
    target_alias: SemanticAlias
    style: ColorbarEditSpec


class DualYAxisStyleIntent(StrictModel):
    operation: Literal["set_dual_y_style"] = "set_dual_y_style"
    target_alias: SemanticAlias
    style: DualYAxisEditSpec


class FacetStyleIntent(StrictModel):
    operation: Literal["set_facet_style"] = "set_facet_style"
    target_alias: SemanticAlias
    style: FacetEditSpec


class YOffsetStyleIntent(StrictModel):
    operation: Literal["set_y_offset_style"] = "set_y_offset_style"
    target_alias: SemanticAlias
    style: YOffsetEditSpec


class ChartParametersIntent(StrictModel):
    operation: Literal["set_chart_parameters"] = "set_chart_parameters"
    target_alias: SemanticAlias
    parameters: ChartParameterEditSpec


class SeriesStyleIntent(StrictModel):
    operation: Literal["set_series_style"] = "set_series_style"
    target_alias: SemanticAlias
    color: ColorValue | None = None
    line_width_pt: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)] | None = None
    marker_size_pt: Annotated[float, Field(gt=0, le=72, allow_inf_nan=False)] | None = None
    line_style: LineStyle | None = None
    symbol_shape: SymbolShape | None = None
    symbol_interior: SymbolInterior | None = None

    @model_validator(mode="after")
    def has_style_change(self) -> SeriesStyleIntent:
        if all(
            value is None
            for value in (
                self.color,
                self.line_width_pt,
                self.marker_size_pt,
                self.line_style,
                self.symbol_shape,
                self.symbol_interior,
            )
        ):
            raise ValueError("set_series_style requires at least one style value")
        return self


class PaletteIntent(StrictModel):
    operation: Literal["set_palette"] = "set_palette"
    target_alias: SemanticAlias
    palette_id: PaletteId
    reverse: bool = False


class CategoryColorIntent(StrictModel):
    operation: Literal["set_category_color"] = "set_category_color"
    target_alias: SemanticAlias
    category: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    color: ColorValue


class LegendVisibilityIntent(StrictModel):
    operation: Literal["set_legend_visibility"] = "set_legend_visibility"
    target_alias: SemanticAlias
    visible: bool


class LegendPlacementIntent(StrictModel):
    operation: Literal["move_legend"] = "move_legend"
    target_alias: SemanticAlias
    placement: Literal["inside", "outside_right", "outside_bottom"]


class PublicationProfileIntent(StrictModel):
    operation: Literal["apply_publication_profile"] = "apply_publication_profile"
    target_alias: SemanticAlias
    profile_alias: SemanticAlias


class CanvasSizeIntent(StrictModel):
    operation: Literal["set_canvas_size"] = "set_canvas_size"
    target_alias: SemanticAlias
    physical_size: PhysicalSize


class AddAnnotationIntent(StrictModel):
    operation: Literal["add_annotation"] = "add_annotation"
    target_alias: SemanticAlias
    kind: Literal["text", "reference_line", "reference_band"]
    text: Annotated[str, StringConstraints(max_length=256, strict=True)] | None = None
    x: FiniteNumber | None = None
    y: FiniteNumber | None = None
    x2: FiniteNumber | None = None
    y2: FiniteNumber | None = None
    affect_range: bool = False

    @model_validator(mode="after")
    def valid_shape(self) -> AddAnnotationIntent:
        if self.kind == "text" and (self.text is None or not self.text.strip()):
            raise ValueError("text annotation requires text")
        if self.kind == "reference_line" and (self.x is None) == (self.y is None):
            raise ValueError("reference line requires exactly one of x or y")
        if self.kind == "reference_band":
            vertical = self.x is not None and self.x2 is not None and self.y is self.y2 is None
            horizontal = self.y is not None and self.y2 is not None and self.x is self.x2 is None
            if not (vertical or horizontal):
                raise ValueError("reference band requires one x or y interval")
            start, end = (self.x, self.x2) if vertical else (self.y, self.y2)
            if start is not None and end is not None and start >= end:
                raise ValueError("reference band start must be lower than end")
        return self


PatchIntent = Annotated[
    PlotTitleIntent
    | AxisRangeIntent
    | AxisScaleIntent
    | AxisLabelIntent
    | AxisReverseIntent
    | AxisTicksIntent
    | FontSizeIntent
    | BarAreaStyleIntent
    | UncertaintyStyleIntent
    | ColorbarStyleIntent
    | DualYAxisStyleIntent
    | FacetStyleIntent
    | YOffsetStyleIntent
    | ChartParametersIntent
    | SeriesStyleIntent
    | CategoryColorIntent
    | PaletteIntent
    | LegendVisibilityIntent
    | LegendPlacementIntent
    | PublicationProfileIntent
    | CanvasSizeIntent
    | AddAnnotationIntent,
    Field(discriminator="operation"),
]


class PatchPlotAction(ActionBase):
    action_type: Literal["patch_plot"] = "patch_plot"
    target_alias: SemanticAlias
    patches: Annotated[tuple[PatchIntent, ...], Field(min_length=1)]


class CreateBatchAction(ActionBase):
    action_type: Literal["create_batch"] = "create_batch"
    target_alias: SemanticAlias
    chart_type_id: ChartTypeId
    field_selections: Annotated[tuple[SemanticFieldSelection, ...], Field(min_length=1)]
    axis_policy: Literal["per_plot", "unified"] = "per_plot"


class PatchBatchAction(ActionBase):
    action_type: Literal["patch_batch"] = "patch_batch"
    target_alias: SemanticAlias
    axis_policy: Literal["per_plot", "unified"]


class CreateFigureAction(ActionBase):
    action_type: Literal["create_figure"] = "create_figure"
    target_alias: SemanticAlias
    plot_aliases: Annotated[tuple[SemanticAlias, ...], Field(min_length=2, max_length=4)]
    layout: Literal["1x2", "2x1", "2x2"]


class PatchFigureAction(ActionBase):
    action_type: Literal["patch_figure"] = "patch_figure"
    target_alias: SemanticAlias
    panel_alias: SemanticAlias
    replacement_plot_alias: SemanticAlias


class ExportArtifactAction(ActionBase):
    action_type: Literal["export_artifact"] = "export_artifact"
    target_alias: SemanticAlias
    format: Literal["png", "svg", "opju"]
    target_scope: Literal["current_plot", "selected_plots", "batch", "figure"]
    output_name: SafeOutputName


BusinessAction = Annotated[
    CreatePlotAction
    | PatchPlotAction
    | CreateBatchAction
    | PatchBatchAction
    | CreateFigureAction
    | PatchFigureAction
    | ExportArtifactAction,
    Field(discriminator="action_type"),
]


class PlanWarning(StrictModel):
    category: Literal["scientific", "compatibility", "scope"]
    message: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]


class ActionPlan(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    decision_type: Literal["action_plan"] = "action_plan"
    plan_id: Annotated[
        str,
        StringConstraints(pattern=r"^plan:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    target_alias: SemanticAlias
    actions: Annotated[tuple[BusinessAction, ...], Field(min_length=1, max_length=64)]
    warnings: tuple[PlanWarning, ...] = ()
    confirmation: Literal["not_required", "required"] = "not_required"

    @model_validator(mode="after")
    def ordered_acyclic_dependencies(self) -> ActionPlan:
        seen: set[str] = set()
        for action in self.actions:
            if action.action_id in seen:
                raise ValueError("action ids must be unique")
            if any(dependency not in seen for dependency in action.depends_on):
                raise ValueError("actions may depend only on earlier actions in the same plan")
            seen.add(action.action_id)
        return self


class InputChoice(StrictModel):
    value: SemanticAlias
    label: Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]


class InputQuestion(StrictModel):
    question_key: SemanticAlias
    prompt: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]
    input_kind: Literal["single_choice", "multiple_choice", "number", "text"]
    choices: tuple[InputChoice, ...] = ()

    @model_validator(mode="after")
    def choices_match_kind(self) -> InputQuestion:
        choice_kind = self.input_kind in {"single_choice", "multiple_choice"}
        if choice_kind != bool(self.choices):
            raise ValueError("choice inputs require choices and other inputs forbid them")
        return self


class DataRequest(StrictModel):
    """A bounded request for explicitly authorized additional context.

    Provider-visible aliases are resolved to authoritative object/field ids and
    versions locally.  The model never supplies a table id or storage location.
    """

    dataset_alias: SemanticAlias
    expected_version: Annotated[int, Field(ge=1)]
    field_aliases: Annotated[tuple[SemanticAlias, ...], Field(min_length=1, max_length=12)]
    requested_categories: Annotated[
        tuple[Literal["field_metadata", "statistics", "sample"], ...],
        Field(min_length=1),
    ]
    estimated_field_count: Annotated[int, Field(ge=1, le=12)]
    estimated_row_count: Annotated[int, Field(ge=0, le=20)]
    estimated_scalar_count: Annotated[int, Field(ge=0, le=200)]
    purpose: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    default_context_insufficient_reason: Annotated[
        str,
        StringConstraints(min_length=1, max_length=256, strict=True),
    ]
    smaller_scope_possible: bool
    authorization_scope: Literal["this_run", "this_conversation_similar"]

    @model_validator(mode="after")
    def counts_are_consistent(self) -> DataRequest:
        if self.estimated_field_count != len(self.field_aliases):
            raise ValueError("estimated_field_count must match field_aliases")
        if self.estimated_scalar_count > self.estimated_field_count * self.estimated_row_count:
            raise ValueError("estimated scalar count exceeds the requested field/row product")
        if len(set(self.requested_categories)) != len(self.requested_categories):
            raise ValueError("requested data categories must be unique")
        return self


class NeedsInput(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    decision_type: Literal["needs_input"] = "needs_input"
    target_alias: SemanticAlias
    questions: Annotated[tuple[InputQuestion, ...], Field(max_length=3)] = ()
    data_request: DataRequest | None = None

    @model_validator(mode="after")
    def has_question_or_data_request(self) -> NeedsInput:
        if not self.questions and self.data_request is None:
            raise ValueError("needs_input requires questions or a data request")
        return self


class Unsupported(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    decision_type: Literal["unsupported"] = "unsupported"
    target_alias: SemanticAlias
    category: Literal["v1_scope", "provider_capability", "chart_capability"]
    explanation: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]


class NoChange(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    decision_type: Literal["no_change"] = "no_change"
    target_alias: SemanticAlias
    explanation: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]


AgentDecision = Annotated[
    ActionPlan | NeedsInput | Unsupported | NoChange,
    Field(discriminator="decision_type"),
]
