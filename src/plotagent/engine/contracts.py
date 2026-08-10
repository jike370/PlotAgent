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
    data: EngineDataRef | None = None
    bindings: tuple[FieldBinding, ...] = ()
    components: Annotated[tuple[PlotDocumentRef, ...], Field(max_length=4)] = ()
    applied_action_ids: tuple[ActionId, ...] = ()

    @model_validator(mode="after")
    def unique_roles_and_linear_history(self) -> PlotDocument:
        roles = tuple(binding.role for binding in self.bindings)
        if len(roles) != len(set(roles)):
            raise ValueError("plot document bindings must have unique roles")
        if len(self.applied_action_ids) != len(set(self.applied_action_ids)):
            raise ValueError("plot document action ids must be unique")
        has_data = self.data is not None
        has_components = bool(self.components)
        if has_data == has_components:
            raise ValueError("a plot document requires exactly one data or component source")
        if has_data and not self.bindings:
            raise ValueError("a data-backed plot document requires field bindings")
        if has_components and self.bindings:
            raise ValueError("a component-backed plot document cannot bind data fields")
        component_ids = tuple(item.plot_id for item in self.components)
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("plot document component plots must be unique")
        if self.plot_id in component_ids:
            raise ValueError("a plot document cannot contain itself")
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
    data: EngineDataRef | None = None
    bindings: tuple[FieldBinding, ...] = ()
    components: Annotated[tuple[PlotDocumentRef, ...], Field(max_length=4)] = ()

    @model_validator(mode="after")
    def one_plot_source(self) -> CreatePlot:
        has_data = self.data is not None
        has_components = bool(self.components)
        if has_data == has_components:
            raise ValueError("create_plot requires exactly one data or component source")
        if has_data and not self.bindings:
            raise ValueError("a data-backed create_plot requires field bindings")
        if has_components and self.bindings:
            raise ValueError("a component-backed create_plot cannot bind fields")
        component_ids = tuple(item.plot_id for item in self.components)
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("create_plot component plots must be unique")
        if self.plot_id in component_ids:
            raise ValueError("create_plot cannot contain its own plot id")
        return self


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
    text: Annotated[str, StringConstraints(max_length=512, strict=True)]


class SetAxis(VersionedPlotAction):
    operation: Literal["set_axis"] = "set_axis"
    action_id: ActionId
    target: SemanticObjectId
    label: Annotated[str, StringConstraints(max_length=256, strict=True)] | None = None
    scale: Literal["linear", "log10", "datetime", "categorical"] | None = None
    minimum: FiniteNumber | None = None
    maximum: FiniteNumber | None = None
    reverse: bool | None = None

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
            for value in (self.label, self.scale, self.minimum, self.maximum, self.reverse)
        ):
            raise ValueError("set_axis requires at least one explicit change")
        return self


class SetSeriesStyle(VersionedPlotAction):
    operation: Literal["set_series_style"] = "set_series_style"
    action_id: ActionId
    target: SemanticObjectId
    color: ColorHex | None = None
    line_width_pt: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)] | None = None
    line_style: Literal["solid", "dash", "dot", "dash_dot", "none"] | None = None
    symbol: Token | None = None
    symbol_size_pt: Annotated[float, Field(gt=0, le=72, allow_inf_nan=False)] | None = None

    @model_validator(mode="after")
    def valid_series_edit(self) -> SetSeriesStyle:
        if not self.target.startswith("series:"):
            raise ValueError("set_series_style requires a series target")
        if all(
            value is None
            for value in (
                self.color,
                self.line_width_pt,
                self.line_style,
                self.symbol,
                self.symbol_size_pt,
            )
        ):
            raise ValueError("set_series_style requires at least one explicit change")
        return self


class SetLegend(VersionedPlotAction):
    operation: Literal["set_legend"] = "set_legend"
    action_id: ActionId
    target: SemanticObjectId
    visible: bool | None = None
    anchor: Literal["inside", "right", "bottom", "none"] | None = None

    @model_validator(mode="after")
    def valid_legend_edit(self) -> SetLegend:
        if not self.target.startswith("legend:"):
            raise ValueError("set_legend requires a legend target")
        if self.visible is None and self.anchor is None:
            raise ValueError("set_legend requires at least one explicit change")
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
    source_kind: Literal["data", "plots"] = "data"
    required_roles: tuple[Token, ...] = ()
    optional_roles: tuple[Token, ...] = ()
    repeatable_role_prefixes: tuple[Token, ...] = ()
    minimum_components: Annotated[int, Field(ge=0, le=4)] = 0
    maximum_components: Annotated[int, Field(ge=0, le=4)] = 0
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
        if self.source_kind == "data":
            if not self.required_roles:
                raise ValueError("a data profile requires at least one field role")
            if self.minimum_components or self.maximum_components:
                raise ValueError("a data profile cannot declare component bounds")
        else:
            if roles or self.repeatable_role_prefixes:
                raise ValueError("a plot-composition profile cannot declare field roles")
            if self.minimum_components < 2:
                raise ValueError("a plot-composition profile requires at least two components")
            if self.maximum_components < self.minimum_components:
                raise ValueError("component maximum must not be lower than its minimum")
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
        if self.source_kind == "plots" and "bind_fields" in operations:
            raise ValueError("a plot-composition profile cannot expose bind_fields")
        return self
