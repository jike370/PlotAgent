"""Cost-aware workflow contracts for PlotAgent's goal-driven task interface.

These types are the only planning surface shared with the bundled Agent.  The
Agent may propose a :class:`TaskDraft`; only the local compiler can resolve it
to a :class:`TaskPlan`.  No renderer object, filesystem path, SQL statement or
executable expression is representable here.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import (
    FieldId,
    FiniteNumber,
    Sha256,
    StrictModel,
    Token,
    VersionId,
)

WorkflowRunId = Annotated[
    str,
    StringConstraints(pattern=r"^workflow:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
TaskDraftId = Annotated[
    str,
    StringConstraints(pattern=r"^draft:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
TaskPlanId = Annotated[
    str,
    StringConstraints(pattern=r"^plan:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
TaskItemId = Annotated[
    str,
    StringConstraints(pattern=r"^item:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
WorkflowRecipeId = Annotated[
    str,
    StringConstraints(pattern=r"^recipe:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
WorkflowAlias = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$", strict=True),
]
WorkflowDisplayLabel = Annotated[
    str,
    StringConstraints(min_length=1, max_length=256, strict=True),
]
InstructionText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=4_096, strip_whitespace=True, strict=True),
]
WorkflowColor = Annotated[
    str,
    StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$", strict=True),
]
WorkflowFontFamily = Literal[
    "auto",
    "Arial",
    "Calibri",
    "Times New Roman",
    "Segoe UI",
    "Microsoft YaHei",
    "SimSun",
]
WorkflowFontWeight = Literal["normal", "bold"]
WorkflowLineStyle = Literal["solid", "dash", "dot", "dash_dot", "none"]
WorkflowMarkerShape = Literal[
    "circle",
    "square",
    "triangle_up",
    "triangle_down",
    "triangle_left",
    "triangle_right",
    "diamond",
    "plus",
    "cross",
    "hexagon",
    "star",
    "pentagon",
    "none",
]
WorkflowMarkerInterior = Literal["solid", "open", "hollow"]
WorkflowPalette = Literal[
    "viridis",
    "plasma",
    "inferno",
    "magma",
    "cividis",
    "turbo",
    "blue_orange",
    "red_white_blue",
    "blue_white_red",
    "gray_scale",
    "fire",
    "rainbow_modified",
    "cool_warm",
    "spectral",
    "terrain",
    "ocean",
]

WorkflowRoute = Literal[
    "agent",
    "recipe_replay",
    "direct",
]


class WorkflowBudget(StrictModel):
    """Hard ceilings selected by Core before any model call."""

    max_agent_turns: Annotated[int, Field(ge=0, le=10)] = 2
    max_tool_calls: Annotated[int, Field(ge=0, le=24)] = 8
    max_preview_rows: Annotated[int, Field(ge=0, le=200)] = 40
    max_profiled_fields: Annotated[int, Field(ge=0, le=128)] = 24
    max_disclosed_scalars: Annotated[int, Field(ge=0, le=20_000)] = 2_000


class WorkflowSource(StrictModel):
    source_alias: WorkflowAlias
    source_dataset_id: Token
    source_version: VersionId
    content_hash: Sha256
    display_name: WorkflowDisplayLabel
    row_count: Annotated[int, Field(ge=0)]


class WorkflowField(StrictModel):
    field_alias: WorkflowAlias
    source_alias: WorkflowAlias
    field_id: FieldId
    name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    logical_type: Literal["numeric", "categorical", "datetime", "boolean", "text"]
    unit_label: Annotated[str, StringConstraints(max_length=128, strict=True)] | None = None
    unit_evidence: Literal["none", "declared", "suffix_candidate"] = "none"


class WorkflowPlot(StrictModel):
    plot_alias: WorkflowAlias
    plot_id: Token
    plot_version: VersionId
    profile_id: Token


class WorkflowContext(StrictModel):
    schema_version: Literal["workflow-context.v1"] = "workflow-context.v1"
    workflow_run_id: WorkflowRunId
    project_id: Token
    project_revision: Annotated[int, Field(ge=0)]
    instruction: InstructionText
    locale: Literal["zh-CN", "en-US"] = "zh-CN"
    sources: Annotated[tuple[WorkflowSource, ...], Field(max_length=64)] = ()
    fields: Annotated[tuple[WorkflowField, ...], Field(max_length=512)] = ()
    plots: Annotated[tuple[WorkflowPlot, ...], Field(max_length=64)] = ()
    selected_source_aliases: Annotated[tuple[WorkflowAlias, ...], Field(max_length=8)] = ()
    selected_plot_aliases: Annotated[tuple[WorkflowAlias, ...], Field(max_length=8)] = ()
    selected_profile_ids: Annotated[tuple[Token, ...], Field(max_length=64)] = ()
    allowed_profile_ids: Annotated[tuple[Token, ...], Field(min_length=1)]
    budget: WorkflowBudget

    @model_validator(mode="after")
    def valid_alias_graph(self) -> WorkflowContext:
        source_aliases = tuple(item.source_alias for item in self.sources)
        plot_aliases = tuple(item.plot_alias for item in self.plots)
        field_aliases = tuple(item.field_alias for item in self.fields)
        if len(source_aliases) != len(set(source_aliases)):
            raise ValueError("workflow source aliases must be unique")
        if len(plot_aliases) != len(set(plot_aliases)):
            raise ValueError("workflow plot aliases must be unique")
        if len(field_aliases) != len(set(field_aliases)):
            raise ValueError("workflow field aliases must be unique")
        source_set = set(source_aliases)
        plot_set = set(plot_aliases)
        if any(field.source_alias not in source_set for field in self.fields):
            raise ValueError("workflow fields must belong to an exposed source")
        if not set(self.selected_source_aliases) <= source_set:
            raise ValueError("selected source aliases must be exposed")
        if not set(self.selected_plot_aliases) <= plot_set:
            raise ValueError("selected plot aliases must be exposed")
        if not set(self.selected_profile_ids) <= set(self.allowed_profile_ids):
            raise ValueError("selected profiles must be allowed")
        return self


class SourceInspection(StrictModel):
    source_alias: WorkflowAlias
    display_name: str
    row_count: Annotated[int, Field(ge=0)]
    fields: tuple[WorkflowField, ...]
    metadata_keys: tuple[Token, ...] = ()


class SourceList(StrictModel):
    sources: Annotated[tuple[WorkflowSource, ...], Field(max_length=64)]


WorkflowScalar = bool | int | float | str | date | datetime | None


class RowPage(StrictModel):
    source_alias: WorkflowAlias
    field_aliases: Annotated[tuple[WorkflowAlias, ...], Field(min_length=1, max_length=24)]
    offset: Annotated[int, Field(ge=0)]
    rows: Annotated[tuple[tuple[WorkflowScalar, ...], ...], Field(max_length=40)]
    has_more: bool

    @model_validator(mode="after")
    def rectangular(self) -> RowPage:
        width = len(self.field_aliases)
        if any(len(row) != width for row in self.rows):
            raise ValueError("row preview must be rectangular")
        return self


class FieldProfile(StrictModel):
    source_alias: WorkflowAlias
    field_alias: WorkflowAlias
    valid_count: Annotated[int, Field(ge=0)]
    missing_count: Annotated[int, Field(ge=0)]
    distinct_count: Annotated[int, Field(ge=0)]
    numeric_minimum: FiniteNumber | None = None
    numeric_maximum: FiniteNumber | None = None
    examples: Annotated[tuple[WorkflowScalar, ...], Field(max_length=8)] = ()


class ValueSearchMatch(StrictModel):
    row_offset: Annotated[int, Field(ge=0)]
    value: WorkflowScalar


class ValueSearchResult(StrictModel):
    source_alias: WorkflowAlias
    field_alias: WorkflowAlias
    mode: Literal["equal", "contains", "prefix"]
    query: WorkflowScalar
    matches: Annotated[tuple[ValueSearchMatch, ...], Field(max_length=40)]
    truncated: bool = False


class InstrumentMetadata(StrictModel):
    source_alias: WorkflowAlias
    values: dict[Token, Annotated[str, StringConstraints(max_length=512, strict=True)]]


class SchemaComparison(StrictModel):
    source_aliases: Annotated[tuple[WorkflowAlias, ...], Field(min_length=2, max_length=8)]
    common_field_names: tuple[str, ...]
    only_by_source: dict[WorkflowAlias, tuple[str, ...]]
    isomorphic: bool


class InspectionAudit(StrictModel):
    workflow_run_id: WorkflowRunId
    tool_name: Literal[
        "list_sources",
        "inspect_source",
        "preview_rows",
        "sample_rows",
        "profile_field",
        "search_values",
        "compare_schemas",
        "inspect_instrument_metadata",
        "preview_data_operation",
    ]
    source_aliases: Annotated[tuple[WorkflowAlias, ...], Field(min_length=1, max_length=8)]
    disclosed_field_count: Annotated[int, Field(ge=0)]
    disclosed_row_count: Annotated[int, Field(ge=0)]
    disclosed_scalar_count: Annotated[int, Field(ge=0)]


class SelectFields(StrictModel):
    operation: Literal["select_fields"] = "select_fields"
    source_alias: WorkflowAlias
    field_aliases: Annotated[tuple[WorkflowAlias, ...], Field(min_length=1, max_length=128)]


class FilterPredicate(StrictModel):
    field_alias: WorkflowAlias
    operator: Literal[
        "equal",
        "not_equal",
        "less_than",
        "less_or_equal",
        "greater_than",
        "greater_or_equal",
        "is_missing",
        "is_not_missing",
        "in_values",
    ]
    value: WorkflowScalar | tuple[WorkflowScalar, ...] = None

    @model_validator(mode="after")
    def operator_value_match(self) -> FilterPredicate:
        if self.operator in {"is_missing", "is_not_missing"}:
            if self.value is not None:
                raise ValueError("missing predicates do not accept a value")
        elif self.operator == "in_values":
            if not isinstance(self.value, tuple) or not self.value:
                raise ValueError("in_values requires a non-empty tuple")
        elif self.value is None or isinstance(self.value, tuple):
            raise ValueError("comparison predicates require one scalar value")
        return self


class FilterRows(StrictModel):
    operation: Literal["filter_rows"] = "filter_rows"
    source_alias: WorkflowAlias
    predicates: Annotated[tuple[FilterPredicate, ...], Field(min_length=1, max_length=16)]
    combine: Literal["all", "any"] = "all"


class SortKey(StrictModel):
    field_alias: WorkflowAlias
    direction: Literal["ascending", "descending"] = "ascending"
    missing: Literal["first", "last"] = "last"


class SortRows(StrictModel):
    operation: Literal["sort_rows"] = "sort_rows"
    source_alias: WorkflowAlias
    keys: Annotated[tuple[SortKey, ...], Field(min_length=1, max_length=8)]


class ExcludeRows(StrictModel):
    operation: Literal["exclude_rows"] = "exclude_rows"
    source_alias: WorkflowAlias
    row_indices: Annotated[
        tuple[Annotated[int, Field(ge=0)], ...], Field(min_length=1, max_length=256)
    ]

    @model_validator(mode="after")
    def unique_rows(self) -> ExcludeRows:
        if len(self.row_indices) != len(set(self.row_indices)):
            raise ValueError("excluded row indices must be unique")
        return self


class DropEmptyFields(StrictModel):
    operation: Literal["drop_empty_fields"] = "drop_empty_fields"
    source_alias: WorkflowAlias
    field_aliases: Annotated[tuple[WorkflowAlias, ...], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def unique_fields(self) -> DropEmptyFields:
        if len(self.field_aliases) != len(set(self.field_aliases)):
            raise ValueError("empty field aliases must be unique")
        return self


class ConvertType(StrictModel):
    operation: Literal["convert_type"] = "convert_type"
    source_alias: WorkflowAlias
    field_alias: WorkflowAlias
    target_type: Literal["numeric", "categorical", "datetime", "boolean", "text"]
    output_field_alias: WorkflowAlias
    output_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    decimal_separator: Literal[".", ","] = "."
    thousands_separator: Literal[",", ".", " "] | None = None
    datetime_format: (
        Annotated[str, StringConstraints(min_length=1, max_length=64, strict=True)] | None
    ) = None
    true_values: Annotated[tuple[str, ...], Field(max_length=32)] = ()
    false_values: Annotated[tuple[str, ...], Field(max_length=32)] = ()
    case_sensitive: bool = False

    @model_validator(mode="after")
    def conversion_options_match_target(self) -> ConvertType:
        if self.output_field_alias == self.field_alias:
            raise ValueError("type conversion must create a new field alias")
        if self.decimal_separator == self.thousands_separator:
            raise ValueError("decimal and thousands separators must differ")
        if self.target_type == "datetime" and self.datetime_format is None:
            raise ValueError("datetime conversion requires an explicit format")
        if self.target_type == "boolean":
            if not self.true_values or not self.false_values:
                raise ValueError("boolean conversion requires true and false values")
            true_values = {
                value if self.case_sensitive else value.casefold() for value in self.true_values
            }
            false_values = {
                value if self.case_sensitive else value.casefold() for value in self.false_values
            }
            if true_values & false_values:
                raise ValueError("boolean true and false values must not overlap")
        elif self.true_values or self.false_values:
            raise ValueError("boolean labels are only valid for boolean conversion")
        return self


class WorkflowOutputField(StrictModel):
    field_alias: WorkflowAlias
    name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]


class ReshapeLongToWide(StrictModel):
    operation: Literal["reshape_long_to_wide"] = "reshape_long_to_wide"
    source_alias: WorkflowAlias
    index_field_aliases: Annotated[tuple[WorkflowAlias, ...], Field(min_length=1, max_length=8)]
    name_field_alias: WorkflowAlias
    value_field_alias: WorkflowAlias
    output_fields: Annotated[tuple[WorkflowOutputField, ...], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def unique_outputs(self) -> ReshapeLongToWide:
        aliases = tuple(item.field_alias for item in self.output_fields)
        names = tuple(item.name for item in self.output_fields)
        if len(aliases) != len(set(aliases)) or len(names) != len(set(names)):
            raise ValueError("long-to-wide output aliases and names must be unique")
        return self


class ReshapeWideToLong(StrictModel):
    operation: Literal["reshape_wide_to_long"] = "reshape_wide_to_long"
    source_alias: WorkflowAlias
    id_field_aliases: Annotated[tuple[WorkflowAlias, ...], Field(max_length=8)] = ()
    value_field_aliases: Annotated[tuple[WorkflowAlias, ...], Field(min_length=2, max_length=64)]
    output_name: WorkflowAlias
    output_value: WorkflowAlias


class ConcatenateSources(StrictModel):
    operation: Literal["concatenate_sources"] = "concatenate_sources"
    source_aliases: Annotated[
        tuple[WorkflowAlias, ...],
        Field(
            min_length=2,
            max_length=8,
            description="Exact opaque Core source aliases copied from the current context.",
        ),
    ]
    source_label_field: Annotated[
        WorkflowAlias,
        Field(
            description=(
                "New output field alias declared by this operation; downstream bindings must "
                "copy this exact alias."
            )
        ),
    ] = "source_group"
    source_labels: Annotated[tuple[WorkflowDisplayLabel, ...], Field(max_length=8)] = ()

    @model_validator(mode="after")
    def unique_sources(self) -> ConcatenateSources:
        if len(self.source_aliases) != len(set(self.source_aliases)):
            raise ValueError("concatenated sources must be unique")
        if self.source_labels and len(self.source_labels) != len(self.source_aliases):
            raise ValueError("source labels must match concatenated sources")
        normalized = tuple(label.strip().casefold() for label in self.source_labels)
        if len(normalized) != len(set(normalized)):
            raise ValueError("source labels must be unique")
        return self


class AlignSourcesOnX(StrictModel):
    """Build one wide table from independent series sharing an ordered X domain."""

    operation: Literal["align_sources_on_x"] = "align_sources_on_x"
    source_aliases: Annotated[tuple[WorkflowAlias, ...], Field(min_length=2, max_length=8)]
    x_field_aliases: Annotated[tuple[WorkflowAlias, ...], Field(min_length=2, max_length=8)]
    value_field_aliases: Annotated[tuple[WorkflowAlias, ...], Field(min_length=2, max_length=8)]
    output_x_field_alias: WorkflowAlias
    output_x_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    output_series_fields: Annotated[
        tuple[WorkflowOutputField, ...], Field(min_length=2, max_length=8)
    ]
    numeric_tolerance: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0

    @model_validator(mode="after")
    def aligned_dimensions_match(self) -> AlignSourcesOnX:
        size = len(self.source_aliases)
        if len(set(self.source_aliases)) != size:
            raise ValueError("aligned sources must be unique")
        if not (
            len(self.x_field_aliases)
            == len(self.value_field_aliases)
            == len(self.output_series_fields)
            == size
        ):
            raise ValueError("each aligned source requires one X, value, and output series")
        output_aliases = (
            self.output_x_field_alias,
            *(field.field_alias for field in self.output_series_fields),
        )
        if len(output_aliases) != len(set(output_aliases)):
            raise ValueError("aligned output field aliases must be unique")
        normalized_names = tuple(
            field.name.strip().casefold() for field in self.output_series_fields
        )
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("aligned output series names must be unique")
        return self


class RenameField(StrictModel):
    operation: Literal["rename_field"] = "rename_field"
    source_alias: WorkflowAlias
    field_alias: WorkflowAlias
    output_field_alias: WorkflowAlias
    output_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]


class DeriveColumn(StrictModel):
    operation: Literal["derive_column"] = "derive_column"
    source_alias: WorkflowAlias
    input_field_aliases: Annotated[tuple[WorkflowAlias, ...], Field(min_length=1, max_length=2)]
    operator: Literal[
        "add", "subtract", "multiply", "divide", "absolute", "negate", "log10", "ln", "sqrt"
    ]
    scalar: FiniteNumber | None = None
    output_field_alias: WorkflowAlias
    output_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]

    @model_validator(mode="after")
    def operands_match_operator(self) -> DeriveColumn:
        unary = self.operator in {"absolute", "negate", "log10", "ln", "sqrt"}
        if unary and (len(self.input_field_aliases) != 1 or self.scalar is not None):
            raise ValueError("unary derived columns require exactly one field")
        if not unary:
            has_two_fields = len(self.input_field_aliases) == 2 and self.scalar is None
            has_field_scalar = len(self.input_field_aliases) == 1 and self.scalar is not None
            if not (has_two_fields or has_field_scalar):
                raise ValueError(
                    "binary derived columns require two fields or one field and scalar"
                )
        return self


class ConvertUnit(StrictModel):
    operation: Literal["convert_unit"] = "convert_unit"
    source_alias: WorkflowAlias
    field_alias: WorkflowAlias
    target_unit: Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]
    output_field_alias: WorkflowAlias
    output_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]


class BucketizeNumeric(StrictModel):
    """Create a categorical field from explicit ordered numeric boundaries."""

    operation: Literal["bucketize_numeric"] = "bucketize_numeric"
    source_alias: WorkflowAlias
    field_alias: WorkflowAlias
    boundaries: Annotated[tuple[FiniteNumber, ...], Field(min_length=1, max_length=32)]
    labels: Annotated[
        tuple[WorkflowDisplayLabel, ...],
        Field(min_length=2, max_length=33),
    ]
    output_field_alias: WorkflowAlias
    output_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]

    @model_validator(mode="after")
    def ordered_bins(self) -> BucketizeNumeric:
        if len(self.labels) != len(self.boundaries) + 1:
            raise ValueError("bucket labels must have exactly one more value than boundaries")
        if any(
            left >= right
            for left, right in zip(self.boundaries, self.boundaries[1:], strict=False)
        ):
            raise ValueError("bucket boundaries must be strictly increasing")
        normalized = tuple(label.strip().casefold() for label in self.labels)
        if len(normalized) != len(set(normalized)):
            raise ValueError("bucket labels must be unique")
        return self


DataOperation = Annotated[
    SelectFields
    | FilterRows
    | SortRows
    | ExcludeRows
    | DropEmptyFields
    | ConvertType
    | ReshapeLongToWide
    | ReshapeWideToLong
    | ConcatenateSources
    | AlignSourcesOnX
    | RenameField
    | DeriveColumn
    | ConvertUnit
    | BucketizeNumeric,
    Field(discriminator="operation"),
]


class DraftFieldBinding(StrictModel):
    role: Token
    source_alias: Annotated[
        WorkflowAlias,
        Field(
            description=(
                "Exact opaque Core source alias copied from the current context; never a "
                "display name."
            )
        ),
    ]
    field_alias: Annotated[
        WorkflowAlias,
        Field(
            description=(
                "Exact opaque Core field alias from the current context, or the exact output "
                "alias declared by a preceding data operation; never a display name."
            )
        ),
    ]


class DraftSetTitle(StrictModel):
    operation: Literal["set_title"] = "set_title"
    target_alias: WorkflowAlias = "plot"
    text: Annotated[str, StringConstraints(max_length=512, strict=True)] | None = None
    font_family: WorkflowFontFamily | None = None
    font_size_pt: Annotated[float, Field(ge=5, le=72, allow_inf_nan=False)] | None = None
    font_weight: WorkflowFontWeight | None = None
    italic: bool | None = None
    color: WorkflowColor | None = None

    @model_validator(mode="after")
    def has_change(self) -> DraftSetTitle:
        if all(value is None for name, value in self if name not in {"operation", "target_alias"}):
            raise ValueError("title edit needs at least one change")
        return self


class DraftSetAxis(StrictModel):
    operation: Literal["set_axis"] = "set_axis"
    target_alias: WorkflowAlias
    label: Annotated[str, StringConstraints(max_length=256, strict=True)] | None = None
    scale: Literal["linear", "log10", "datetime", "categorical"] | None = None
    minimum: FiniteNumber | None = None
    maximum: FiniteNumber | None = None
    reverse: bool | None = None
    title_font_family: WorkflowFontFamily | None = None
    title_font_size_pt: Annotated[float, Field(ge=5, le=72, allow_inf_nan=False)] | None = None
    title_font_weight: WorkflowFontWeight | None = None
    title_italic: bool | None = None
    title_color: WorkflowColor | None = None
    major_tick_step: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None
    minor_tick_count: Annotated[int, Field(ge=0, le=20)] | None = None
    tick_format: Literal["auto", "decimal", "scientific", "percent", "date", "time"] | None = None
    tick_rotation_deg: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)] | None = None
    tick_font_family: WorkflowFontFamily | None = None
    tick_font_size_pt: Annotated[float, Field(ge=5, le=72, allow_inf_nan=False)] | None = None
    tick_color: WorkflowColor | None = None
    axis_line_color: WorkflowColor | None = None
    axis_line_width_pt: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)] | None = None
    major_grid_visible: bool | None = None
    minor_grid_visible: bool | None = None
    grid_color: WorkflowColor | None = None
    grid_line_width_pt: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)] | None = None
    grid_line_style: WorkflowLineStyle | None = None

    @model_validator(mode="after")
    def valid_edit(self) -> DraftSetAxis:
        if (self.minimum is None) != (self.maximum is None):
            raise ValueError("axis bounds must be both fixed or both automatic")
        if self.minimum is not None and self.maximum is not None and self.minimum >= self.maximum:
            raise ValueError("axis minimum must be lower than maximum")
        if all(value is None for name, value in self if name not in {"operation", "target_alias"}):
            raise ValueError("axis edit needs at least one change")
        return self


class DraftSetSeriesStyle(StrictModel):
    operation: Literal["set_series_style"] = "set_series_style"
    target_alias: WorkflowAlias
    line_stroke_color: WorkflowColor | None = None
    line_width_pt: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)] | None = None
    line_style: WorkflowLineStyle | None = None
    line_opacity: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    marker_shape: WorkflowMarkerShape | None = None
    marker_size_pt: Annotated[float, Field(gt=0, le=72, allow_inf_nan=False)] | None = None
    marker_interior: WorkflowMarkerInterior | None = None
    marker_fill_color: WorkflowColor | None = None
    marker_stroke_color: WorkflowColor | None = None
    marker_opacity: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    fill_color: WorkflowColor | None = None
    fill_opacity: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    fill_stroke_color: WorkflowColor | None = None
    fill_stroke_width_pt: Annotated[float, Field(ge=0, le=20, allow_inf_nan=False)] | None = None
    fill_stroke_style: WorkflowLineStyle | None = None

    @model_validator(mode="after")
    def has_change(self) -> DraftSetSeriesStyle:
        if all(value is None for name, value in self if name not in {"operation", "target_alias"}):
            raise ValueError("series style needs at least one change")
        return self


class DraftSetLegend(StrictModel):
    operation: Literal["set_legend"] = "set_legend"
    target_alias: WorkflowAlias = "legend"
    visible: bool | None = None
    anchor: (
        Literal[
            "inside",
            "inside_top_left",
            "inside_top_right",
            "inside_bottom_left",
            "inside_bottom_right",
            "right",
            "bottom",
            "none",
        ]
        | None
    ) = None
    columns: Annotated[int, Field(ge=1, le=12)] | None = None
    title: Annotated[str, StringConstraints(max_length=256, strict=True)] | None = None
    font_family: WorkflowFontFamily | None = None
    font_size_pt: Annotated[float, Field(ge=5, le=72, allow_inf_nan=False)] | None = None
    font_color: WorkflowColor | None = None
    frame_visible: bool | None = None
    frame_color: WorkflowColor | None = None
    frame_width_pt: Annotated[float, Field(ge=0, le=20, allow_inf_nan=False)] | None = None

    @model_validator(mode="after")
    def has_change(self) -> DraftSetLegend:
        if all(value is None for name, value in self if name not in {"operation", "target_alias"}):
            raise ValueError("legend edit needs at least one change")
        return self


class DraftSetColorMap(StrictModel):
    operation: Literal["set_colormap"] = "set_colormap"
    target_alias: WorkflowAlias
    palette: WorkflowPalette | None = None
    reverse: bool | None = None
    minimum: FiniteNumber | None = None
    maximum: FiniteNumber | None = None
    midpoint: FiniteNumber | None = None
    mode: Literal["continuous", "discrete"] | None = None
    levels: Annotated[int, Field(ge=2, le=256)] | None = None
    missing_color: WorkflowColor | None = None
    colorbar_visible: bool | None = None
    colorbar_anchor: Literal["right", "bottom"] | None = None
    colorbar_title: Annotated[str, StringConstraints(max_length=256, strict=True)] | None = None
    colorbar_tick_format: Literal["auto", "decimal", "scientific", "percent"] | None = None

    @model_validator(mode="after")
    def valid_edit(self) -> DraftSetColorMap:
        if (self.minimum is None) != (self.maximum is None):
            raise ValueError("colormap bounds must both be fixed or both automatic")
        if self.midpoint is not None and self.minimum is None:
            raise ValueError("colormap midpoint requires fixed minimum and maximum")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum >= self.maximum:
                raise ValueError("colormap minimum must be lower than maximum")
            if self.midpoint is not None and not self.minimum < self.midpoint < self.maximum:
                raise ValueError("colormap midpoint must lie inside fixed bounds")
        if all(value is None for name, value in self if name not in {"operation", "target_alias"}):
            raise ValueError("colormap edit needs at least one change")
        return self


class DraftSetErrorStyle(StrictModel):
    operation: Literal["set_error_style"] = "set_error_style"
    target_alias: WorkflowAlias
    bar_color: WorkflowColor | None = None
    bar_width_pt: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)] | None = None
    cap_size_pt: Annotated[float, Field(ge=0, le=72, allow_inf_nan=False)] | None = None
    bar_opacity: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    band_fill_color: WorkflowColor | None = None
    band_fill_opacity: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    band_stroke_color: WorkflowColor | None = None
    band_stroke_width_pt: Annotated[float, Field(ge=0, le=20, allow_inf_nan=False)] | None = None

    @model_validator(mode="after")
    def has_change(self) -> DraftSetErrorStyle:
        if all(value is None for name, value in self if name not in {"operation", "target_alias"}):
            raise ValueError("error style needs at least one change")
        return self


class DraftSetDataLabels(StrictModel):
    operation: Literal["set_data_labels"] = "set_data_labels"
    target_alias: WorkflowAlias
    visible: bool | None = None
    value_format: Literal["auto", "decimal", "scientific", "percent"] | None = None
    prefix: Annotated[str, StringConstraints(max_length=32, strict=True)] | None = None
    suffix: Annotated[str, StringConstraints(max_length=32, strict=True)] | None = None
    position: Literal["auto", "above", "below", "left", "right", "center"] | None = None
    rotation_deg: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)] | None = None
    font_family: WorkflowFontFamily | None = None
    font_size_pt: Annotated[float, Field(ge=5, le=72, allow_inf_nan=False)] | None = None
    font_weight: WorkflowFontWeight | None = None
    font_color: WorkflowColor | None = None

    @model_validator(mode="after")
    def has_change(self) -> DraftSetDataLabels:
        if all(value is None for name, value in self if name not in {"operation", "target_alias"}):
            raise ValueError("data label edit needs at least one change")
        return self


class DraftSetChartParameter(StrictModel):
    operation: Literal["set_chart_parameter"] = "set_chart_parameter"
    target_alias: WorkflowAlias = "plot"
    parameter: Token
    value: str | int | float | bool


class DraftAddAnnotation(StrictModel):
    operation: Literal["add_annotation"] = "add_annotation"
    target_alias: WorkflowAlias = "plot"
    annotation_alias: WorkflowAlias
    text: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]
    x: FiniteNumber
    y: FiniteNumber
    coordinate_system: Literal["data", "axes", "page"] = "data"
    font_family: WorkflowFontFamily | None = None
    font_size_pt: Annotated[float, Field(ge=5, le=72, allow_inf_nan=False)] | None = None
    font_weight: WorkflowFontWeight | None = None
    italic: bool | None = None
    color: WorkflowColor | None = None
    rotation_deg: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)] | None = None


DraftVisualAction = Annotated[
    DraftSetTitle
    | DraftSetAxis
    | DraftSetSeriesStyle
    | DraftSetLegend
    | DraftSetColorMap
    | DraftSetErrorStyle
    | DraftSetDataLabels
    | DraftSetChartParameter
    | DraftAddAnnotation,
    Field(discriminator="operation"),
]


class TaskDraftItem(StrictModel):
    task_kind: Literal["create", "edit", "update_data"]
    item_id: TaskItemId
    plot_alias: WorkflowAlias
    profile_id: Token
    target_plot_alias: WorkflowAlias | None = None
    source_aliases: Annotated[tuple[WorkflowAlias, ...], Field(max_length=8)] = ()
    data_operations: Annotated[tuple[DataOperation, ...], Field(max_length=32)] = ()
    bindings: Annotated[tuple[DraftFieldBinding, ...], Field(max_length=128)] = ()
    visual_actions: Annotated[tuple[DraftVisualAction, ...], Field(max_length=64)] = ()

    @model_validator(mode="after")
    def unique_item_contract(self) -> TaskDraftItem:
        if self.task_kind == "create":
            if self.target_plot_alias is not None or not self.source_aliases or not self.bindings:
                raise ValueError("create tasks need sources and bindings, not an existing plot")
        elif self.task_kind == "edit" and (
            self.target_plot_alias is None
            or self.source_aliases
            or self.data_operations
            or self.bindings
            or not self.visual_actions
        ):
            raise ValueError("edit tasks accept only a target plot and visual actions")
        elif self.task_kind == "update_data" and (
            self.target_plot_alias is None or not self.source_aliases or not self.bindings
        ):
            raise ValueError("update_data tasks need a target plot, sources and bindings")
        if len(self.source_aliases) != len(set(self.source_aliases)):
            raise ValueError("task item source aliases must be unique")
        roles = tuple(binding.role for binding in self.bindings)
        if len(roles) != len(set(roles)):
            raise ValueError("task item roles must be unique")
        if any(binding.source_alias not in self.source_aliases for binding in self.bindings):
            raise ValueError("task bindings must use an item source")
        return self


class TaskDraft(StrictModel):
    schema_version: Literal["task-draft.v1"] = "task-draft.v1"
    draft_id: TaskDraftId
    workflow_run_id: WorkflowRunId
    route: Literal["agent", "recipe_replay", "direct"]
    summary: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]
    items: Annotated[tuple[TaskDraftItem, ...], Field(min_length=1, max_length=64)]
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    hard_constraints: Annotated[tuple[str, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def unique_items(self) -> TaskDraft:
        ids = tuple(item.item_id for item in self.items)
        aliases = tuple(item.plot_alias for item in self.items)
        if len(ids) != len(set(ids)) or len(aliases) != len(set(aliases)):
            raise ValueError("task draft item ids and plot aliases must be unique")
        return self


class InputQuestion(StrictModel):
    question_key: Token
    prompt: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]
    answer_kind: Literal["text", "single_choice", "multi_choice", "field", "profile"]
    choices: Annotated[tuple[str, ...], Field(max_length=24)] = ()
    required: bool = True


class WorkflowNeedsInput(StrictModel):
    outcome: Literal["needs_input"] = "needs_input"
    workflow_run_id: WorkflowRunId
    questions: Annotated[tuple[InputQuestion, ...], Field(min_length=1, max_length=4)]


class WorkflowUnsupported(StrictModel):
    outcome: Literal["unsupported"] = "unsupported"
    workflow_run_id: WorkflowRunId
    reason_code: Token
    message: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]


class WorkflowDraftReady(StrictModel):
    outcome: Literal["draft_ready"] = "draft_ready"
    draft: TaskDraft


WorkflowDecision = Annotated[
    WorkflowNeedsInput | WorkflowUnsupported | WorkflowDraftReady,
    Field(discriminator="outcome"),
]


class ResolvedFieldBinding(StrictModel):
    role: Token
    source_alias: WorkflowAlias
    field_id: FieldId


class ResolvedWorkflowField(StrictModel):
    field_alias: WorkflowAlias
    source_alias: WorkflowAlias
    field_id: FieldId
    name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    logical_type: Literal["numeric", "categorical", "datetime", "boolean", "text"]
    unit_label: Annotated[str, StringConstraints(max_length=128, strict=True)] | None = None


class CompiledTaskItem(StrictModel):
    task_kind: Literal["create", "edit", "update_data"]
    item_id: TaskItemId
    plot_alias: WorkflowAlias
    plot_id: Token
    profile_id: Token
    target_plot_id: Token | None = None
    target_plot_version: VersionId | None = None
    sources: Annotated[tuple[WorkflowSource, ...], Field(max_length=8)] = ()
    resolved_fields: tuple[ResolvedWorkflowField, ...] = ()
    data_operations: tuple[DataOperation, ...]
    bindings: tuple[ResolvedFieldBinding, ...] = ()
    visual_actions: tuple[DraftVisualAction, ...]
    depends_on: tuple[TaskItemId, ...] = ()
    idempotency_key: Token

    @model_validator(mode="after")
    def valid_task_kind(self) -> CompiledTaskItem:
        if self.task_kind == "create":
            if self.target_plot_id is not None or not self.sources or not self.bindings:
                raise ValueError("compiled create task is incomplete")
        elif self.task_kind == "edit" and (
            self.target_plot_id is None
            or self.target_plot_version is None
            or self.sources
            or self.resolved_fields
            or self.data_operations
            or self.bindings
            or not self.visual_actions
        ):
            raise ValueError("compiled edit task is incomplete")
        elif self.task_kind == "update_data" and (
            self.target_plot_id is None
            or self.target_plot_version is None
            or not self.sources
            or not self.bindings
        ):
            raise ValueError("compiled update_data task is incomplete")
        return self


class TaskPlan(StrictModel):
    schema_version: Literal["task-plan.v1"] = "task-plan.v1"
    plan_id: TaskPlanId
    workflow_run_id: WorkflowRunId
    draft_hash: Sha256
    expected_project_revision: Annotated[int, Field(ge=0)]
    items: Annotated[tuple[CompiledTaskItem, ...], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def valid_dependencies(self) -> TaskPlan:
        ids = tuple(item.item_id for item in self.items)
        if len(ids) != len(set(ids)):
            raise ValueError("compiled task item ids must be unique")
        known: set[str] = set()
        for item in self.items:
            if not set(item.depends_on) <= known:
                raise ValueError("task dependencies must refer to earlier items")
            known.add(item.item_id)
        return self


class TaskItemProgress(StrictModel):
    item_id: TaskItemId
    state: Literal[
        "pending",
        "running",
        "succeeded",
        "failed",
        "blocked",
        "cancelled",
    ]
    attempt_count: Annotated[int, Field(ge=0, le=32)] = 0
    error_code: Token | None = None
    error_message: (
        Annotated[
            str,
            StringConstraints(min_length=1, max_length=512, strip_whitespace=True, strict=True),
        ]
        | None
    ) = None
    error_retryable: bool | None = None
    output_plot_id: Token | None = None
    output_plot_version: VersionId | None = None

    @model_validator(mode="after")
    def failure_metadata_matches_state(self) -> TaskItemProgress:
        failure_values = (self.error_code, self.error_message, self.error_retryable)
        if self.state in {"failed", "blocked"}:
            if any(value is None for value in failure_values):
                raise ValueError("failed task progress requires complete failure metadata")
        elif any(value is not None for value in failure_values):
            raise ValueError("non-failed task progress cannot retain failure metadata")
        return self


class TaskPlanSnapshot(StrictModel):
    plan: TaskPlan
    state: Literal[
        "awaiting_confirmation",
        "ready",
        "running",
        "partially_succeeded",
        "succeeded",
        "failed",
        "rejected",
        "cancelled",
    ]
    current_project_revision: Annotated[int, Field(ge=0)]
    item_progress: Annotated[tuple[TaskItemProgress, ...], Field(min_length=1)]
    created_at: Annotated[str, StringConstraints(min_length=1, max_length=64, strict=True)]
    updated_at: Annotated[str, StringConstraints(min_length=1, max_length=64, strict=True)]

    @model_validator(mode="after")
    def progress_matches_plan(self) -> TaskPlanSnapshot:
        if tuple(item.item_id for item in self.plan.items) != tuple(
            item.item_id for item in self.item_progress
        ):
            raise ValueError("task item progress must match plan order")
        return self


class WorkflowRunSnapshot(StrictModel):
    workflow_run_id: WorkflowRunId
    project_id: Token
    state: Literal[
        "routing",
        "agent",
        "recipe_replay",
        "direct",
        "needs_input",
        "draft_ready",
        "awaiting_confirmation",
        "executing",
        "completed",
        "partially_succeeded",
        "failed",
        "cancelled",
    ]
    route: WorkflowRoute | None = None
    context_hash: Sha256 | None = None
    draft_id: TaskDraftId | None = None
    plan_id: TaskPlanId | None = None
    model_turn_count: Annotated[int, Field(ge=0, le=6)] = 0
    tool_call_count: Annotated[int, Field(ge=0, le=24)] = 0
    input_token_count: Annotated[int, Field(ge=0)] = 0
    output_token_count: Annotated[int, Field(ge=0)] = 0
    estimated_cost: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0
    created_at: Annotated[str, StringConstraints(min_length=1, max_length=64, strict=True)]
    updated_at: Annotated[str, StringConstraints(min_length=1, max_length=64, strict=True)]


class WorkflowRecipe(StrictModel):
    schema_version: Literal["workflow-recipe.v1"] = "workflow-recipe.v1"
    recipe_id: WorkflowRecipeId
    recipe_version: VersionId
    display_name: Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]
    structure_fingerprint: Sha256
    draft_template: TaskDraft
    engine_profile_hash: Sha256
    renderer_contract_hash: Sha256
    created_from_workflow_run_id: WorkflowRunId
    created_from_plan_id: TaskPlanId
    created_from_export_hash: Sha256
    archived: bool = False
