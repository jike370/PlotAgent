"""Local authority for agent-native plot commands.

Agents propose the public actions.  This service resolves a profile, validates
the request against engine capabilities and produces the next minimal
``PlotDocument`` version.  Backend execution is intentionally outside the
reducer so an Origin or Matplotlib implementation cannot redefine domain state.
"""

from __future__ import annotations

from dataclasses import dataclass

from plotagent.engine.contracts import (
    AddAnnotation,
    BindFields,
    CreatePlot,
    EngineCapability,
    EngineProfile,
    ExportPlot,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetChartParameter,
    SetColorMap,
    SetDataLabels,
    SetErrorStyle,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.removed import (
    REMOVED_CHART_TYPE_ERROR_CODE,
    REMOVED_CHART_TYPE_IDS,
)
from plotagent.engine.repository import EngineRepositoryConflict, PlotDocumentRepository


class EngineCommandError(ValueError):
    pass


class RemovedChartTypeError(EngineCommandError):
    """Stable failure raised when an old project references a removed chart."""

    code = REMOVED_CHART_TYPE_ERROR_CODE


class EngineVersionConflict(EngineCommandError):
    pass


class EngineCatalog:
    def __init__(self, profiles: tuple[EngineProfile, ...]) -> None:
        identifiers = tuple(profile.profile_id for profile in profiles)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("engine profile ids must be unique")
        self._profiles = {profile.profile_id: profile for profile in profiles}

    def profiles(self) -> tuple[EngineProfile, ...]:
        return tuple(self._profiles.values())

    def get(self, profile_id: str) -> EngineProfile:
        if profile_id in REMOVED_CHART_TYPE_IDS:
            raise RemovedChartTypeError(
                f"{REMOVED_CHART_TYPE_ERROR_CODE}: {profile_id}"
            )
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise EngineCommandError(f"unknown engine profile: {profile_id}") from exc

    def validate_create(self, action: CreatePlot) -> EngineProfile:
        profile = self.get(action.profile_id)
        self.validate_bindings(profile, tuple(binding.role for binding in action.bindings))
        self.validate_action(profile, action)
        return profile

    def validate_bindings(self, profile: EngineProfile, roles: tuple[str, ...]) -> None:
        missing = set(profile.required_roles) - set(roles)
        if missing:
            raise EngineCommandError(f"missing required field roles: {sorted(missing)}")
        allowed = set(profile.required_roles) | set(profile.optional_roles)
        unsupported = {
            role
            for role in roles
            if role not in allowed
            and not any(
                role.startswith(prefix + "_") for prefix in profile.repeatable_role_prefixes
            )
        }
        if unsupported:
            raise EngineCommandError(f"unsupported field roles: {sorted(unsupported)}")

    @staticmethod
    def require_operation(profile: EngineProfile, operation: str) -> EngineCapability:
        capability = next(
            (item for item in profile.capabilities if item.operation == operation),
            None,
        )
        if capability is None:
            raise EngineCommandError(
                f"engine profile {profile.profile_id} does not support {operation}"
            )
        return capability

    @classmethod
    def validate_action(cls, profile: EngineProfile, action: PlotEngineAction) -> None:
        capability = cls.require_operation(profile, action.operation)
        used = cls._used_parameters(action)
        unsupported = used - set(capability.parameters)
        if unsupported:
            raise EngineCommandError(
                f"engine profile {profile.profile_id} does not support "
                f"{action.operation} parameters: {sorted(unsupported)}"
            )

    @staticmethod
    def _used_parameters(action: PlotEngineAction) -> set[str]:
        if isinstance(action, (CreatePlot, BindFields)):
            return set()
        if isinstance(action, SetTitle):
            return {
                name
                for name in (
                    "text",
                    "font_family",
                    "font_size_pt",
                    "font_weight",
                    "italic",
                    "color",
                )
                if getattr(action, name) is not None
            }
        if isinstance(action, SetAxis):
            used = {
                name
                for name in (
                    "label",
                    "scale",
                    "reverse",
                    "title_font_family",
                    "title_font_size_pt",
                    "title_font_weight",
                    "title_italic",
                    "title_color",
                    "major_tick_step",
                    "minor_tick_count",
                    "tick_format",
                    "tick_rotation_deg",
                    "tick_font_family",
                    "tick_font_size_pt",
                    "tick_color",
                    "tick_labels_visible",
                    "major_ticks_visible",
                    "minor_ticks_visible",
                    "tick_direction",
                    "axis_line_visible",
                    "axis_title_visible",
                    "axis_line_color",
                    "axis_line_width_pt",
                    "major_grid_visible",
                    "minor_grid_visible",
                    "grid_color",
                    "grid_line_width_pt",
                    "grid_line_style",
                )
                if getattr(action, name) is not None
            }
            if action.minimum is not None:
                used.add("bounds")
            return used
        if isinstance(action, SetSeriesStyle):
            return {
                name
                for name in (
                    "visible",
                    "line_stroke_color",
                    "line_width_pt",
                    "line_style",
                    "line_opacity",
                    "marker_shape",
                    "marker_size_pt",
                    "marker_interior",
                    "marker_fill_color",
                    "marker_stroke_color",
                    "marker_stroke_width_pt",
                    "marker_opacity",
                    "fill_color",
                    "fill_opacity",
                    "fill_stroke_color",
                    "fill_stroke_width_pt",
                    "fill_stroke_style",
                )
                if getattr(action, name) is not None
            }
        if isinstance(action, SetLegend):
            return {
                name
                for name in (
                    "visible",
                    "anchor",
                    "columns",
                    "title",
                    "font_family",
                    "font_size_pt",
                    "font_color",
                    "frame_visible",
                    "frame_color",
                    "frame_width_pt",
                )
                if getattr(action, name) is not None
            }
        if isinstance(action, (SetColorMap, SetErrorStyle, SetDataLabels)):
            return {
                name
                for name, value in action
                if name
                not in {"operation", "action_id", "target", "expected_plot_version"}
                and value is not None
            }
        if isinstance(action, SetChartParameter):
            return {action.parameter}
        if isinstance(action, AddAnnotation):
            return {
                "text",
                "x",
                "y",
                "coordinate_system",
                *(
                    name
                    for name in (
                        "font_family",
                        "font_size_pt",
                        "font_weight",
                        "italic",
                        "color",
                        "rotation_deg",
                    )
                    if getattr(action, name) is not None
                ),
            }
        if isinstance(action, ExportPlot):
            return {action.format}
        raise AssertionError(f"unhandled engine action {action.operation}")


@dataclass(frozen=True, slots=True)
class PlotTransition:
    before: PlotDocument | None
    after: PlotDocument
    action: PlotEngineAction


class PlotEngineService:
    """Agent-independent command validator and plot-document authority."""

    def __init__(self, catalog: EngineCatalog, repository: PlotDocumentRepository) -> None:
        self.catalog = catalog
        self.repository = repository

    def prepare(self, action: PlotEngineAction) -> PlotTransition:
        if isinstance(action, ExportPlot):
            raise EngineCommandError("export_plot is non-mutating and must use the export service")
        if isinstance(action, CreatePlot):
            self.catalog.validate_create(action)
            if self.repository.latest_version(action.plot_id) is not None:
                raise EngineCommandError(f"plot document already exists: {action.plot_id}")
            return PlotTransition(
                before=None,
                after=PlotDocument(
                    plot_id=action.plot_id,
                    plot_version=1,
                    profile_id=action.profile_id,
                    data=action.data,
                    bindings=action.bindings,
                    applied_action_ids=(action.action_id,),
                ),
                action=action,
            )

        target_plot_id = self._target_plot_id(action)
        stored = self.repository.get(target_plot_id)
        if action.expected_plot_version != stored.document.plot_version:
            raise EngineVersionConflict(
                f"plot document version is stale: expected {action.expected_plot_version}, "
                f"latest is {stored.document.plot_version}"
            )
        profile = self.catalog.get(stored.document.profile_id)
        self.catalog.validate_action(profile, action)
        updates: dict[str, object] = {}
        if isinstance(action, BindFields):
            self.catalog.validate_bindings(
                profile,
                tuple(binding.role for binding in action.bindings),
            )
            updates.update(data=action.data, bindings=action.bindings)
        return PlotTransition(
            before=stored.document,
            after=stored.document.model_copy(
                update={
                    **updates,
                    "plot_version": stored.document.plot_version + 1,
                    "parent_version": stored.document.plot_version,
                    "applied_action_ids": stored.document.applied_action_ids + (action.action_id,),
                }
            ),
            action=action,
        )

    def commit(
        self,
        transition: PlotTransition,
        *,
        expected_project_revision: int | None = None,
    ) -> PlotDocument:
        try:
            self.repository.commit(
                transition.after,
                transition.action,
                expected_project_revision=expected_project_revision,
            )
        except EngineRepositoryConflict as error:
            raise EngineVersionConflict(str(error)) from None
        return transition.after

    def execute(
        self,
        action: PlotEngineAction,
        *,
        expected_project_revision: int | None = None,
    ) -> PlotDocument:
        """Validate and persist domain state; runtime backend execution is separate."""

        return self.commit(
            self.prepare(action),
            expected_project_revision=expected_project_revision,
        )

    def replay(self, action: PlotEngineAction) -> PlotDocument | None:
        """Return an already committed action without executing it twice."""

        applied = self.repository.find_action(action.action_id)
        if applied is None:
            return None
        if applied.action != action:
            raise EngineCommandError("action id is already bound to different arguments")
        return self.repository.get(
            applied.document_after.plot_id,
            applied.document_after.plot_version,
        ).document

    @staticmethod
    def _target_plot_id(action: PlotEngineAction) -> str:
        target = getattr(action, "target", None)
        if not isinstance(target, str):
            raise EngineCommandError(f"{action.operation} has no semantic target")
        if target.startswith("plot:"):
            return target
        # Nested semantic ids are globally stable and encode their owning plot
        # after the kind prefix: ``series:<plot-token>.<series-token>``. Plot
        # tokens may themselves contain dots (Agent-created ids intentionally
        # use namespaced tokens), while semantic object keys never do. Split
        # from the right so ``axis:agent.line_temp_response.1.y`` resolves to
        # ``plot:agent.line_temp_response.1`` rather than ``plot:agent``.
        _, separator, value = target.partition(":")
        owner, dot, _child = value.rpartition(".")
        if not separator or not dot or not owner:
            raise EngineCommandError(
                "nested semantic targets must encode their owning plot as kind:<plot>.<object>"
            )
        return "plot:" + owner
