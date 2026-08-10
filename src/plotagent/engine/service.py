"""Local authority for agent-native plot commands.

Agents propose the public actions.  This service resolves a profile, validates
the request against engine capabilities and produces the next minimal
``PlotDocument`` version.  Backend execution is intentionally outside the
reducer so an Origin or Matplotlib implementation cannot redefine domain state.
"""

from __future__ import annotations

from dataclasses import dataclass

from plotagent.engine.contracts import (
    CreatePlot,
    EngineProfile,
    ExportPlot,
    PlotDocument,
    PlotEngineAction,
)
from plotagent.engine.repository import PlotDocumentRepository


class EngineCommandError(ValueError):
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
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise EngineCommandError(f"unknown engine profile: {profile_id}") from exc

    def validate_create(self, action: CreatePlot) -> EngineProfile:
        profile = self.get(action.profile_id)
        roles = tuple(binding.role for binding in action.bindings)
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
        self.require_operation(profile, action.operation)
        return profile

    @staticmethod
    def require_operation(profile: EngineProfile, operation: str) -> None:
        if operation not in {capability.operation for capability in profile.capabilities}:
            raise EngineCommandError(
                f"engine profile {profile.profile_id} does not support {operation}"
            )


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
        profile = self.catalog.get(stored.document.profile_id)
        self.catalog.require_operation(profile, action.operation)
        return PlotTransition(
            before=stored.document,
            after=stored.document.model_copy(
                update={
                    "plot_version": stored.document.plot_version + 1,
                    "parent_version": stored.document.plot_version,
                    "applied_action_ids": stored.document.applied_action_ids + (action.action_id,),
                }
            ),
            action=action,
        )

    def commit(self, transition: PlotTransition) -> PlotDocument:
        self.repository.commit(transition.after, transition.action)
        return transition.after

    def execute(self, action: PlotEngineAction) -> PlotDocument:
        """Validate and persist domain state; runtime backend execution is separate."""

        return self.commit(self.prepare(action))

    @staticmethod
    def _target_plot_id(action: PlotEngineAction) -> str:
        target = getattr(action, "target", None)
        if not isinstance(target, str):
            raise EngineCommandError(f"{action.operation} has no semantic target")
        if target.startswith("plot:"):
            return target
        # Nested semantic ids are globally stable and encode their owning plot
        # after the kind prefix: ``series:<plot-token>.<series-token>``.
        _, separator, value = target.partition(":")
        owner, dot, _child = value.partition(".")
        if not separator or not dot or not owner:
            raise EngineCommandError(
                "nested semantic targets must encode their owning plot as kind:<plot>.<object>"
            )
        return "plot:" + owner
