"""Bundled Agent client for the public Agent Native plotting engine.

The model works with bounded aliases from ``ProjectContextSnapshot``.  This
module is the local authority that binds those aliases to immutable data,
versioned plots and profile-owned semantic objects.  Other Agent clients may
skip this convenience layer and submit public ``PlotEngineAction`` values
directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.agent_context import ContextObjectRef
from plotagent.contracts.base import FiniteNumber, StrictModel, Token
from plotagent.contracts.decisions import NeedsInput, NoChange, Unsupported
from plotagent.contracts.project_context import ContextFieldBinding, ProjectContextSnapshot
from plotagent.engine import (
    AddAnnotation,
    BindFields,
    CreatePlot,
    EngineCatalog,
    EngineCommandError,
    EngineDataRef,
    ExportPlot,
    FieldBinding,
    PlotEngineAction,
    SetAxis,
    SetChartParameter,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)

AgentAlias = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$", strict=True),
]
AgentActionId = Annotated[
    str,
    StringConstraints(pattern=r"^action:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]


class AgentFieldBinding(StrictModel):
    role: Token
    field_alias: AgentAlias


class AgentCreatePlot(StrictModel):
    operation: Literal["create_plot"] = "create_plot"
    action_id: AgentActionId
    plot_alias: AgentAlias
    profile_id: Token
    source_alias: AgentAlias
    bindings: Annotated[tuple[AgentFieldBinding, ...], Field(min_length=1)]


class AgentBindFields(StrictModel):
    operation: Literal["bind_fields"] = "bind_fields"
    action_id: AgentActionId
    plot_alias: AgentAlias
    source_alias: AgentAlias
    bindings: Annotated[tuple[AgentFieldBinding, ...], Field(min_length=1)]


class AgentSetTitle(StrictModel):
    operation: Literal["set_title"] = "set_title"
    action_id: AgentActionId
    plot_alias: AgentAlias
    text: Annotated[str, StringConstraints(max_length=512, strict=True)]


class AgentSetAxis(StrictModel):
    operation: Literal["set_axis"] = "set_axis"
    action_id: AgentActionId
    plot_alias: AgentAlias
    axis_alias: AgentAlias
    label: Annotated[str, StringConstraints(max_length=256, strict=True)] | None = None
    scale: Literal["linear", "log10", "datetime", "categorical"] | None = None
    minimum: FiniteNumber | None = None
    maximum: FiniteNumber | None = None
    reverse: bool | None = None

    @model_validator(mode="after")
    def has_one_change(self) -> AgentSetAxis:
        if all(
            value is None
            for value in (self.label, self.scale, self.minimum, self.maximum, self.reverse)
        ):
            raise ValueError("set_axis requires at least one explicit change")
        if (self.minimum is None) != (self.maximum is None):
            raise ValueError("axis bounds must both be fixed or both be automatic")
        return self


class AgentSetSeriesStyle(StrictModel):
    operation: Literal["set_series_style"] = "set_series_style"
    action_id: AgentActionId
    plot_alias: AgentAlias
    series_alias: AgentAlias
    color: Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$", strict=True)] | None = (
        None
    )
    line_width_pt: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)] | None = None
    line_style: Literal["solid", "dash", "dot", "dash_dot", "none"] | None = None
    symbol: Token | None = None
    symbol_size_pt: Annotated[float, Field(gt=0, le=72, allow_inf_nan=False)] | None = None


class AgentSetLegend(StrictModel):
    operation: Literal["set_legend"] = "set_legend"
    action_id: AgentActionId
    plot_alias: AgentAlias
    visible: bool | None = None
    anchor: Literal["inside", "right", "bottom", "none"] | None = None


class AgentSetChartParameter(StrictModel):
    operation: Literal["set_chart_parameter"] = "set_chart_parameter"
    action_id: AgentActionId
    plot_alias: AgentAlias
    parameter: Token
    value: str | int | float | bool


class AgentAddAnnotation(StrictModel):
    operation: Literal["add_annotation"] = "add_annotation"
    action_id: AgentActionId
    plot_alias: AgentAlias
    annotation_alias: AgentAlias
    text: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]
    x: FiniteNumber
    y: FiniteNumber
    coordinate_system: Literal["data", "axes", "page"] = "data"


class AgentExportPlot(StrictModel):
    operation: Literal["export_plot"] = "export_plot"
    action_id: AgentActionId
    plot_alias: AgentAlias
    format: Literal["png", "svg", "opju"]
    output_name: Annotated[
        str,
        StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]


AgentEngineAction = Annotated[
    AgentCreatePlot
    | AgentBindFields
    | AgentSetTitle
    | AgentSetAxis
    | AgentSetSeriesStyle
    | AgentSetLegend
    | AgentSetChartParameter
    | AgentAddAnnotation
    | AgentExportPlot,
    Field(discriminator="operation"),
]


class EngineAgentPlan(StrictModel):
    schema_version: Literal["engine-agent.v1"] = "engine-agent.v1"
    decision_type: Literal["action_plan"] = "action_plan"
    plan_id: Annotated[
        str,
        StringConstraints(pattern=r"^plan:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    target_alias: AgentAlias
    actions: Annotated[tuple[AgentEngineAction, ...], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def unique_action_ids(self) -> EngineAgentPlan:
        ids = tuple(action.action_id for action in self.actions)
        if len(ids) != len(set(ids)):
            raise ValueError("agent engine action ids must be unique")
        return self


class BoundEnginePlan(StrictModel):
    plan_id: str
    expected_project_revision: int
    actions: tuple[PlotEngineAction, ...]


EngineAgentDecision = Annotated[
    EngineAgentPlan | NeedsInput | Unsupported | NoChange,
    Field(discriminator="decision_type"),
]


@dataclass(slots=True)
class _PlotBinding:
    plot_id: str
    version: int
    profile_id: str


class BundledEngineAgentBinder:
    """Bind one provider proposal to local ids, versions and capabilities."""

    def __init__(self, catalog: EngineCatalog) -> None:
        self._catalog = catalog

    def bind(
        self,
        plan: EngineAgentPlan,
        context: ProjectContextSnapshot,
        *,
        target_profiles: Mapping[str, str] | None = None,
    ) -> BoundEnginePlan:
        fields = {item.field_alias: item for item in context.field_bindings}
        objects = {
            item.object_alias: item
            for item in context.known_objects + context.recent_result_objects
        }
        objects[context.conversation_state.current_target.object_alias] = (
            context.conversation_state.current_target
        )
        plots: dict[str, _PlotBinding] = {}
        for alias, profile_id in (target_profiles or {}).items():
            target = objects.get(alias)
            if target is None or target.object_type != "plot":
                raise EngineCommandError(f"agent plot alias is unavailable: {alias}")
            plots[alias] = _PlotBinding(target.object_id, target.object_version, profile_id)

        bound: list[PlotEngineAction] = []
        for position, proposed in enumerate(plan.actions, start=1):
            action: PlotEngineAction
            if isinstance(proposed, AgentCreatePlot):
                if proposed.plot_alias in plots:
                    raise EngineCommandError("agent create_plot alias already exists")
                data, bindings = self._bind_data(
                    proposed.source_alias,
                    proposed.bindings,
                    objects,
                    fields,
                )
                plot_id = "plot:agent." + plan.plan_id.removeprefix("plan:") + f".{position}"
                action = CreatePlot(
                    action_id=proposed.action_id,
                    plot_id=plot_id,
                    profile_id=proposed.profile_id,
                    data=data,
                    bindings=bindings,
                )
                self._catalog.validate_create(action)
                plots[proposed.plot_alias] = _PlotBinding(plot_id, 1, proposed.profile_id)
            else:
                plot = self._plot(plots, proposed.plot_alias)
                action = self._bind_mutation(proposed, plot, objects, fields)
                profile = self._catalog.get(plot.profile_id)
                self._catalog.validate_action(profile, action)
                if not isinstance(action, ExportPlot):
                    plot.version += 1
            bound.append(action)
        return BoundEnginePlan(
            plan_id=plan.plan_id,
            expected_project_revision=context.project_revision,
            actions=tuple(bound),
        )

    def _bind_mutation(
        self,
        proposed: AgentEngineAction,
        plot: _PlotBinding,
        objects: Mapping[str, ContextObjectRef],
        fields: Mapping[str, ContextFieldBinding],
    ) -> PlotEngineAction:
        if isinstance(proposed, AgentBindFields):
            data, bindings = self._bind_data(
                proposed.source_alias,
                proposed.bindings,
                objects,
                fields,
            )
            return BindFields(
                action_id=proposed.action_id,
                target=plot.plot_id,
                expected_plot_version=plot.version,
                data=data,
                bindings=bindings,
            )
        if isinstance(proposed, AgentSetTitle):
            return SetTitle(
                action_id=proposed.action_id,
                target=plot.plot_id,
                expected_plot_version=plot.version,
                text=proposed.text,
            )
        if isinstance(proposed, AgentSetAxis):
            return SetAxis(
                target=self._semantic_target(plot, proposed.axis_alias, "axis"),
                action_id=proposed.action_id,
                expected_plot_version=plot.version,
                label=proposed.label,
                scale=proposed.scale,
                minimum=proposed.minimum,
                maximum=proposed.maximum,
                reverse=proposed.reverse,
            )
        if isinstance(proposed, AgentSetSeriesStyle):
            return SetSeriesStyle(
                target=self._semantic_target(plot, proposed.series_alias, "series"),
                action_id=proposed.action_id,
                expected_plot_version=plot.version,
                color=proposed.color,
                line_width_pt=proposed.line_width_pt,
                line_style=proposed.line_style,
                symbol=proposed.symbol,
                symbol_size_pt=proposed.symbol_size_pt,
            )
        if isinstance(proposed, AgentSetLegend):
            return SetLegend(
                target=self._semantic_target(plot, "legend", "legend"),
                action_id=proposed.action_id,
                expected_plot_version=plot.version,
                visible=proposed.visible,
                anchor=proposed.anchor,
            )
        if isinstance(proposed, AgentSetChartParameter):
            return SetChartParameter(
                target=plot.plot_id,
                action_id=proposed.action_id,
                expected_plot_version=plot.version,
                parameter=proposed.parameter,
                value=proposed.value,
            )
        if isinstance(proposed, AgentAddAnnotation):
            token = plot.plot_id.removeprefix("plot:")
            return AddAnnotation(
                target=plot.plot_id,
                action_id=proposed.action_id,
                expected_plot_version=plot.version,
                annotation_id=f"annotation:{token}.{proposed.annotation_alias}",
                text=proposed.text,
                x=proposed.x,
                y=proposed.y,
                coordinate_system=proposed.coordinate_system,
            )
        if isinstance(proposed, AgentExportPlot):
            return ExportPlot(
                target=plot.plot_id,
                action_id=proposed.action_id,
                expected_plot_version=plot.version,
                format=proposed.format,
                output_name=proposed.output_name,
            )
        raise AssertionError("create_plot is bound before mutation dispatch")

    def _semantic_target(
        self,
        plot: _PlotBinding,
        alias: str,
        expected_kind: str,
    ) -> str:
        profile = self._catalog.get(plot.profile_id)
        item = next(
            (candidate for candidate in profile.objects if candidate.object_alias == alias),
            None,
        )
        if item is not None:
            if item.object_kind != expected_kind:
                raise EngineCommandError(
                    f"profile {profile.profile_id} does not expose {expected_kind} alias {alias}"
                )
            return item.instantiate(plot.plot_id)
        for repeatable in profile.repeatable_objects:
            prefix = repeatable.object_alias_prefix + "_"
            if not alias.startswith(prefix):
                continue
            ordinal_text = alias.removeprefix(prefix)
            if (
                repeatable.object_kind == expected_kind
                and ordinal_text.isdigit()
                and int(ordinal_text) >= 1
                and ordinal_text == str(int(ordinal_text))
            ):
                return repeatable.instantiate(plot.plot_id, int(ordinal_text))
        raise EngineCommandError(
            f"profile {profile.profile_id} does not expose {expected_kind} alias {alias}"
        )

    @staticmethod
    def _plot(plots: Mapping[str, _PlotBinding], alias: str) -> _PlotBinding:
        try:
            return plots[alias]
        except KeyError as error:
            raise EngineCommandError(f"agent plot alias is unavailable: {alias}") from error

    @staticmethod
    def _bind_data(
        source_alias: str,
        proposed: tuple[AgentFieldBinding, ...],
        objects: Mapping[str, ContextObjectRef],
        fields: Mapping[str, ContextFieldBinding],
    ) -> tuple[EngineDataRef, tuple[FieldBinding, ...]]:
        source = objects.get(source_alias)
        if source is None or source.object_type != "source_dataset":
            raise EngineCommandError("agent source alias is unavailable")
        content_hash = source.content_hash
        if content_hash is None:
            raise EngineCommandError("agent source alias has no immutable content hash")
        bound_fields: list[FieldBinding] = []
        for item in proposed:
            field = fields.get(item.field_alias)
            if (
                field is None
                or field.source_dataset_id != source.object_id
                or field.source_version != source.object_version
            ):
                raise EngineCommandError("agent field alias is outside the selected source")
            bound_fields.append(FieldBinding(role=item.role, field_id=field.field_id))
        return (
            EngineDataRef(
                kind="source",
                dataset_id=source.object_id,
                version=source.object_version,
                content_hash=content_hash,
            ),
            tuple(bound_fields),
        )
