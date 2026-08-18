"""Public, agent-neutral contracts for the PlotAgent plotting engine.

The plotting engine is a tool surface that can be consumed by any agent.  It
does not import the bundled Agent, a renderer, or a backend-specific plan.  A
``PlotDocument`` records data identity, semantic bindings and explicit user
actions; it is not a scene graph and must never describe every native object in
an Origin graph.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import (
    FieldId,
    FiniteNumber,
    RowId,
    SafeOutputName,
    Sha256,
    StrictModel,
    Token,
    VersionId,
)

PlotId = Annotated[
    str,
    StringConstraints(pattern=r"^plot:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
ActionId = Annotated[
    str,
    StringConstraints(pattern=r"^action:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
SemanticObjectId = Annotated[
    str,
    StringConstraints(
        pattern=r"^(plot|axis|series|legend|annotation|panel):[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        strict=True,
    ),
]
ColorHex = Annotated[
    str,
    StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$", strict=True),
]
FontFamily = Literal[
    "auto",
    "Arial",
    "Calibri",
    "Times New Roman",
    "Segoe UI",
    "Microsoft YaHei",
    "SimSun",
]
FontWeight = Literal["normal", "bold"]
LineStyle = Literal["solid", "dash", "dot", "dash_dot", "none"]
MarkerShape = Literal[
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
MarkerInterior = Literal["solid", "open", "hollow"]
PaletteName = Literal[
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


class EngineDataRef(StrictModel):
    """Immutable data revision consumed by a plot document."""

    kind: Literal["source", "prepared", "calculated"]
    dataset_id: Token
    version: VersionId
    content_hash: Sha256


class FieldBinding(StrictModel):
    """Semantic chart role bound to one immutable field."""

    role: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$", strict=True),
    ]
    field_id: FieldId


EngineScalar = bool | int | float | str | date | datetime | None


class EngineField(StrictModel):
    """Renderer-neutral field metadata exposed by the data layer."""

    field_id: FieldId
    name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    logical_type: Literal["numeric", "categorical", "datetime", "boolean", "text"]
    unit_label: Annotated[str, StringConstraints(max_length=128, strict=True)] | None = None


class EngineColumn(StrictModel):
    """One immutable field and its ordered values."""

    field: EngineField
    values: tuple[EngineScalar, ...]


class EngineDataView(StrictModel):
    """A bounded materialization shared by every plotting backend.

    Importers and preparation services own parsing and transformations.  The
    plotting engine receives only the requested immutable fields in row order.
    """

    data: EngineDataRef
    row_ids: Annotated[tuple[RowId, ...], Field(min_length=1)]
    columns: Annotated[tuple[EngineColumn, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def rectangular_unique_data(self) -> EngineDataView:
        field_ids = tuple(column.field.field_id for column in self.columns)
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("engine data fields must be unique")
        if len(self.row_ids) != len(set(self.row_ids)):
            raise ValueError("engine data row ids must be unique")
        if any(len(column.values) != len(self.row_ids) for column in self.columns):
            raise ValueError("engine data columns must match the row count")
        return self


class PlotDocumentRef(StrictModel):
    plot_id: PlotId
    plot_version: VersionId
    content_hash: Sha256


class PlotDocument(StrictModel):
    """Minimal, renderer-neutral state for one plotted data revision.

    Visual defaults belong to the selected engine profile (for Origin, the
    official template).  Only explicit user/agent actions are journaled here.
    """

    schema_version: Literal["2.0"] = "2.0"
    plot_id: PlotId
    plot_version: VersionId
    parent_version: VersionId | None = None
    profile_id: Token
    data: EngineDataRef
    bindings: Annotated[tuple[FieldBinding, ...], Field(min_length=1)]
    applied_action_ids: tuple[ActionId, ...] = ()

    @model_validator(mode="after")
    def unique_roles_and_linear_history(self) -> PlotDocument:
        roles = tuple(binding.role for binding in self.bindings)
        if len(roles) != len(set(roles)):
            raise ValueError("plot document bindings must have unique roles")
        if len(self.applied_action_ids) != len(set(self.applied_action_ids)):
            raise ValueError("plot document action ids must be unique")
        if self.plot_version == 1 and self.parent_version is not None:
            raise ValueError("the first plot document version cannot have a parent")
        if self.plot_version > 1 and self.parent_version != self.plot_version - 1:
            raise ValueError("plot document versions must form a linear history")
        return self


class CreatePlot(StrictModel):
    operation: Literal["create_plot"] = "create_plot"
    action_id: ActionId
    plot_id: PlotId
    profile_id: Token
    data: EngineDataRef
    bindings: Annotated[tuple[FieldBinding, ...], Field(min_length=1)]


class VersionedPlotAction(StrictModel):
    """Mutation/export request pinned to one explicit plot version.

    Semantic object ids identify what to edit; the version guard identifies
    which immutable document the caller observed.  Agent requests therefore
    cannot drift onto a newer plot after a delayed model response.
    """

    expected_plot_version: VersionId


class BindFields(VersionedPlotAction):
    operation: Literal["bind_fields"] = "bind_fields"
    action_id: ActionId
    target: SemanticObjectId
    data: EngineDataRef
    bindings: Annotated[tuple[FieldBinding, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def plot_target_and_unique_roles(self) -> BindFields:
        if not self.target.startswith("plot:"):
            raise ValueError("bind_fields requires a plot target")
        roles = tuple(binding.role for binding in self.bindings)
        if len(roles) != len(set(roles)):
            raise ValueError("bind_fields roles must be unique")
        return self


class SetTitle(VersionedPlotAction):
    operation: Literal["set_title"] = "set_title"
    action_id: ActionId
    target: SemanticObjectId
    text: Annotated[str, StringConstraints(max_length=512, strict=True)] | None = None
    font_family: FontFamily | None = None
    font_size_pt: Annotated[float, Field(ge=5, le=72, allow_inf_nan=False)] | None = None
    font_weight: FontWeight | None = None
    italic: bool | None = None
    color: ColorHex | None = None

    @model_validator(mode="after")
    def valid_title_edit(self) -> SetTitle:
        if not self.target.startswith("plot:"):
            raise ValueError("set_title requires a plot target")
        if all(
            value is None
            for value in (
                self.text,
                self.font_family,
                self.font_size_pt,
                self.font_weight,
                self.italic,
                self.color,
            )
        ):
            raise ValueError("set_title requires at least one explicit change")
        return self


class SetAxis(VersionedPlotAction):
    operation: Literal["set_axis"] = "set_axis"
    action_id: ActionId
    target: SemanticObjectId
    label: Annotated[str, StringConstraints(max_length=256, strict=True)] | None = None
    scale: Literal["linear", "log10", "datetime", "categorical"] | None = None
    minimum: FiniteNumber | None = None
    maximum: FiniteNumber | None = None
    reverse: bool | None = None
    title_font_family: FontFamily | None = None
    title_font_size_pt: Annotated[float, Field(ge=5, le=72, allow_inf_nan=False)] | None = None
    title_font_weight: FontWeight | None = None
    title_italic: bool | None = None
    title_color: ColorHex | None = None
    major_tick_step: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None
    minor_tick_count: Annotated[int, Field(ge=0, le=20)] | None = None
    tick_format: Literal["auto", "decimal", "scientific", "percent", "date", "time"] | None = None
    tick_rotation_deg: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)] | None = None
    tick_font_family: FontFamily | None = None
    tick_font_size_pt: Annotated[float, Field(ge=5, le=72, allow_inf_nan=False)] | None = None
    tick_color: ColorHex | None = None
    axis_line_color: ColorHex | None = None
    axis_line_width_pt: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)] | None = None
    major_grid_visible: bool | None = None
    minor_grid_visible: bool | None = None
    grid_color: ColorHex | None = None
    grid_line_width_pt: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)] | None = None
    grid_line_style: LineStyle | None = None

    @model_validator(mode="after")
    def valid_axis_edit(self) -> SetAxis:
        if not self.target.startswith("axis:"):
            raise ValueError("set_axis requires an axis target")
        if (self.minimum is None) != (self.maximum is None):
            raise ValueError("axis bounds must both be fixed or both be automatic")
        if self.minimum is not None and self.maximum is not None and self.minimum >= self.maximum:
            raise ValueError("axis minimum must be lower than maximum")
        if all(
            value is None
            for value in (
                self.label,
                self.scale,
                self.minimum,
                self.maximum,
                self.reverse,
                self.title_font_family,
                self.title_font_size_pt,
                self.title_font_weight,
                self.title_italic,
                self.title_color,
                self.major_tick_step,
                self.minor_tick_count,
                self.tick_format,
                self.tick_rotation_deg,
                self.tick_font_family,
                self.tick_font_size_pt,
                self.tick_color,
                self.axis_line_color,
                self.axis_line_width_pt,
                self.major_grid_visible,
                self.minor_grid_visible,
                self.grid_color,
                self.grid_line_width_pt,
                self.grid_line_style,
            )
        ):
            raise ValueError("set_axis requires at least one explicit change")
        return self


class SetSeriesStyle(VersionedPlotAction):
    operation: Literal["set_series_style"] = "set_series_style"
    action_id: ActionId
    target: SemanticObjectId
    line_stroke_color: ColorHex | None = None
    line_width_pt: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)] | None = None
    line_style: LineStyle | None = None
    line_opacity: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    marker_shape: MarkerShape | None = None
    marker_size_pt: Annotated[float, Field(gt=0, le=72, allow_inf_nan=False)] | None = None
    marker_interior: MarkerInterior | None = None
    marker_fill_color: ColorHex | None = None
    marker_stroke_color: ColorHex | None = None
    marker_stroke_width_pt: Annotated[
        float, Field(ge=0, le=20, allow_inf_nan=False)
    ] | None = None
    marker_opacity: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    fill_color: ColorHex | None = None
    fill_opacity: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    fill_stroke_color: ColorHex | None = None
    fill_stroke_width_pt: Annotated[
        float, Field(ge=0, le=20, allow_inf_nan=False)
    ] | None = None
    fill_stroke_style: LineStyle | None = None

    @model_validator(mode="after")
    def valid_series_edit(self) -> SetSeriesStyle:
        if not self.target.startswith("series:"):
            raise ValueError("set_series_style requires a series target")
        if all(
            value is None
            for value in (
                self.line_stroke_color,
                self.line_width_pt,
                self.line_style,
                self.line_opacity,
                self.marker_shape,
                self.marker_size_pt,
                self.marker_interior,
                self.marker_fill_color,
                self.marker_stroke_color,
                self.marker_stroke_width_pt,
                self.marker_opacity,
                self.fill_color,
                self.fill_opacity,
                self.fill_stroke_color,
                self.fill_stroke_width_pt,
                self.fill_stroke_style,
            )
        ):
            raise ValueError("set_series_style requires at least one explicit change")
        return self


class SetLegend(VersionedPlotAction):
    operation: Literal["set_legend"] = "set_legend"
    action_id: ActionId
    target: SemanticObjectId
    visible: bool | None = None
    anchor: Literal[
        "inside",
        "inside_top_left",
        "inside_top_right",
        "inside_bottom_left",
        "inside_bottom_right",
        "right",
        "bottom",
        "none",
    ] | None = None
    columns: Annotated[int, Field(ge=1, le=12)] | None = None
    title: Annotated[str, StringConstraints(max_length=256, strict=True)] | None = None
    font_family: FontFamily | None = None
    font_size_pt: Annotated[float, Field(ge=5, le=72, allow_inf_nan=False)] | None = None
    font_color: ColorHex | None = None
    frame_visible: bool | None = None
    frame_color: ColorHex | None = None
    frame_width_pt: Annotated[float, Field(ge=0, le=20, allow_inf_nan=False)] | None = None

    @model_validator(mode="after")
    def valid_legend_edit(self) -> SetLegend:
        if not self.target.startswith("legend:"):
            raise ValueError("set_legend requires a legend target")
        if all(
            value is None
            for value in (
                self.visible,
                self.anchor,
                self.columns,
                self.title,
                self.font_family,
                self.font_size_pt,
                self.font_color,
                self.frame_visible,
                self.frame_color,
                self.frame_width_pt,
            )
        ):
            raise ValueError("set_legend requires at least one explicit change")
        return self


class SetColorMap(VersionedPlotAction):
    operation: Literal["set_colormap"] = "set_colormap"
    action_id: ActionId
    target: SemanticObjectId
    palette: PaletteName | None = None
    reverse: bool | None = None
    minimum: FiniteNumber | None = None
    maximum: FiniteNumber | None = None
    midpoint: FiniteNumber | None = None
    mode: Literal["continuous", "discrete"] | None = None
    levels: Annotated[int, Field(ge=2, le=256)] | None = None
    missing_color: ColorHex | None = None
    colorbar_visible: bool | None = None
    colorbar_anchor: Literal["right", "bottom"] | None = None
    colorbar_title: Annotated[str, StringConstraints(max_length=256, strict=True)] | None = None
    colorbar_tick_format: Literal["auto", "decimal", "scientific", "percent"] | None = None

    @model_validator(mode="after")
    def valid_colormap_edit(self) -> SetColorMap:
        if not self.target.startswith("series:"):
            raise ValueError("set_colormap requires a series target")
        if (self.minimum is None) != (self.maximum is None):
            raise ValueError("colormap bounds must both be fixed or both be automatic")
        if self.midpoint is not None and self.minimum is None:
            raise ValueError("colormap midpoint requires fixed minimum and maximum")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum >= self.maximum:
                raise ValueError("colormap minimum must be lower than maximum")
            if self.midpoint is not None and not self.minimum < self.midpoint < self.maximum:
                raise ValueError("colormap midpoint must lie inside fixed bounds")
        metadata = {"operation", "action_id", "target", "expected_plot_version"}
        if all(value is None for name, value in self if name not in metadata):
            raise ValueError("set_colormap requires at least one explicit change")
        return self


class SetErrorStyle(VersionedPlotAction):
    operation: Literal["set_error_style"] = "set_error_style"
    action_id: ActionId
    target: SemanticObjectId
    bar_color: ColorHex | None = None
    bar_width_pt: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)] | None = None
    cap_size_pt: Annotated[float, Field(ge=0, le=72, allow_inf_nan=False)] | None = None
    bar_opacity: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    band_fill_color: ColorHex | None = None
    band_fill_opacity: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    band_stroke_color: ColorHex | None = None
    band_stroke_width_pt: Annotated[
        float, Field(ge=0, le=20, allow_inf_nan=False)
    ] | None = None

    @model_validator(mode="after")
    def valid_error_edit(self) -> SetErrorStyle:
        if not self.target.startswith("series:"):
            raise ValueError("set_error_style requires a series target")
        metadata = {"operation", "action_id", "target", "expected_plot_version"}
        if all(value is None for name, value in self if name not in metadata):
            raise ValueError("set_error_style requires at least one explicit change")
        return self


class SetDataLabels(VersionedPlotAction):
    operation: Literal["set_data_labels"] = "set_data_labels"
    action_id: ActionId
    target: SemanticObjectId
    visible: bool | None = None
    value_format: Literal["auto", "decimal", "scientific", "percent"] | None = None
    prefix: Annotated[str, StringConstraints(max_length=32, strict=True)] | None = None
    suffix: Annotated[str, StringConstraints(max_length=32, strict=True)] | None = None
    position: Literal["auto", "above", "below", "left", "right", "center"] | None = None
    rotation_deg: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)] | None = None
    font_family: FontFamily | None = None
    font_size_pt: Annotated[float, Field(ge=5, le=72, allow_inf_nan=False)] | None = None
    font_weight: FontWeight | None = None
    font_color: ColorHex | None = None

    @model_validator(mode="after")
    def valid_label_edit(self) -> SetDataLabels:
        if not self.target.startswith("series:"):
            raise ValueError("set_data_labels requires a series target")
        metadata = {"operation", "action_id", "target", "expected_plot_version"}
        if all(value is None for name, value in self if name not in metadata):
            raise ValueError("set_data_labels requires at least one explicit change")
        return self


class SetChartParameter(VersionedPlotAction):
    operation: Literal["set_chart_parameter"] = "set_chart_parameter"
    action_id: ActionId
    target: SemanticObjectId
    parameter: Token
    value: str | int | float | bool


class AddAnnotation(VersionedPlotAction):
    operation: Literal["add_annotation"] = "add_annotation"
    action_id: ActionId
    target: SemanticObjectId
    annotation_id: SemanticObjectId
    text: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]
    x: FiniteNumber
    y: FiniteNumber
    coordinate_system: Literal["data", "axes", "page"] = "data"
    font_family: FontFamily | None = None
    font_size_pt: Annotated[float, Field(ge=5, le=72, allow_inf_nan=False)] | None = None
    font_weight: FontWeight | None = None
    italic: bool | None = None
    color: ColorHex | None = None
    rotation_deg: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)] | None = None

    @model_validator(mode="after")
    def annotation_target_kind(self) -> AddAnnotation:
        if not self.annotation_id.startswith("annotation:"):
            raise ValueError("annotation_id must identify an annotation")
        return self


class ExportPlot(VersionedPlotAction):
    operation: Literal["export_plot"] = "export_plot"
    action_id: ActionId
    target: SemanticObjectId
    format: Literal["png", "svg", "opju"]
    output_name: SafeOutputName


PlotEngineAction = Annotated[
    CreatePlot
    | BindFields
    | SetTitle
    | SetAxis
    | SetSeriesStyle
    | SetLegend
    | SetColorMap
    | SetErrorStyle
    | SetDataLabels
    | SetChartParameter
    | AddAnnotation
    | ExportPlot,
    Field(discriminator="operation"),
]


class AppliedAction(StrictModel):
    action: PlotEngineAction
    document_before: PlotDocumentRef | None
    document_after: PlotDocumentRef
    applied_at: Annotated[str, StringConstraints(min_length=1, max_length=64, strict=True)]


class EngineCapability(StrictModel):
    operation: Literal[
        "create_plot",
        "bind_fields",
        "set_title",
        "set_axis",
        "set_series_style",
        "set_legend",
        "set_colormap",
        "set_error_style",
        "set_data_labels",
        "set_chart_parameter",
        "add_annotation",
        "export_plot",
    ]
    parameters: tuple[Token, ...] = ()


class EngineObjectTemplate(StrictModel):
    """Stable model-facing alias for one profile-owned semantic object."""

    object_alias: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$", strict=True),
    ]
    object_kind: Literal["axis", "series", "legend", "panel"]
    object_key: Token

    def instantiate(self, plot_id: PlotId) -> SemanticObjectId:
        token = plot_id.removeprefix("plot:")
        return f"{self.object_kind}:{token}.{self.object_key}"


class EngineRepeatableObjectTemplate(StrictModel):
    """Bounded alias pattern for data-dependent semantic objects.

    The model sees aliases such as ``series_1`` rather than native plot ids.
    The local client converts the positive ordinal to a stable semantic id;
    the profile backend remains responsible for rejecting an ordinal that is
    outside the materialized data.
    """

    object_alias_prefix: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z][a-z0-9]{0,31}$", strict=True),
    ]
    object_kind: Literal["series", "panel"]
    object_key_prefix: Token

    def instantiate(self, plot_id: PlotId, ordinal: int) -> SemanticObjectId:
        if ordinal < 1:
            raise ValueError("repeatable object ordinals start at one")
        token = plot_id.removeprefix("plot:")
        return f"{self.object_kind}:{token}.{self.object_key_prefix}_{ordinal}"


class EngineProfile(StrictModel):
    """One chart profile exposed to agents by the engine catalog."""

    profile_id: Token
    display_name: Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]
    required_roles: Annotated[tuple[Token, ...], Field(min_length=1)]
    optional_roles: tuple[Token, ...] = ()
    repeatable_role_prefixes: tuple[Token, ...] = ()
    role_field_types: dict[
        Token,
        tuple[Literal["numeric", "categorical", "datetime", "boolean", "text"], ...],
    ] = Field(default_factory=dict)
    objects: tuple[EngineObjectTemplate, ...] = ()
    repeatable_objects: tuple[EngineRepeatableObjectTemplate, ...] = ()
    capabilities: Annotated[tuple[EngineCapability, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_profile_contract(self) -> EngineProfile:
        roles = self.required_roles + self.optional_roles
        if len(roles) != len(set(roles)):
            raise ValueError("engine profile roles must be unique")
        if len(self.repeatable_role_prefixes) != len(set(self.repeatable_role_prefixes)):
            raise ValueError("repeatable role prefixes must be unique")
        if set(self.repeatable_role_prefixes) & set(roles):
            raise ValueError("repeatable role prefixes cannot also be fixed roles")
        allowed_role_contracts = set(roles + self.repeatable_role_prefixes)
        if not set(self.role_field_types) <= allowed_role_contracts:
            raise ValueError("field type contracts must refer to profile roles")
        if any(
            not accepted or len(accepted) != len(set(accepted))
            for accepted in self.role_field_types.values()
        ):
            raise ValueError("field type contracts must be non-empty and unique")
        object_aliases = tuple(item.object_alias for item in self.objects)
        if len(object_aliases) != len(set(object_aliases)):
            raise ValueError("engine profile object aliases must be unique")
        repeatable_prefixes = tuple(item.object_alias_prefix for item in self.repeatable_objects)
        if len(repeatable_prefixes) != len(set(repeatable_prefixes)):
            raise ValueError("engine profile repeatable object prefixes must be unique")
        if any(
            alias == prefix or alias.startswith(prefix + "_")
            for alias in object_aliases
            for prefix in repeatable_prefixes
        ):
            raise ValueError("fixed object aliases cannot overlap repeatable aliases")
        operations = tuple(capability.operation for capability in self.capabilities)
        if len(operations) != len(set(operations)):
            raise ValueError("engine profile capabilities must be unique")
        return self
