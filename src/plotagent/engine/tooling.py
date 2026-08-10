"""Portable tool description and decoding for any Agent client."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import TypeAdapter, ValidationError

from plotagent.engine.contracts import PlotEngineAction
from plotagent.engine.service import EngineCatalog, EngineCommandError

_ACTION_ADAPTER: TypeAdapter[PlotEngineAction] = TypeAdapter(PlotEngineAction)


class EngineActionCodec:
    """Expose one closed tool schema and decode untrusted Agent arguments.

    This class has no dependency on PlotAgent's bundled Agent.  A different
    Agent runtime can discover the same profiles and submit the same typed
    actions without receiving access to Python, Origin script, or Matplotlib
    code execution.
    """

    tool_name = "plot_engine_action"

    def __init__(self, catalog: EngineCatalog) -> None:
        self._catalog = catalog

    def input_schema(self) -> dict[str, Any]:
        return _ACTION_ADAPTER.json_schema()

    def profile_manifest(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "profile_id": profile.profile_id,
                "display_name": profile.display_name,
                "required_roles": profile.required_roles,
                "optional_roles": profile.optional_roles,
                "repeatable_role_prefixes": profile.repeatable_role_prefixes,
                "objects": tuple(
                    {
                        "object_alias": item.object_alias,
                        "object_kind": item.object_kind,
                        "object_key": item.object_key,
                    }
                    for item in profile.objects
                ),
                "capabilities": tuple(
                    {
                        "operation": capability.operation,
                        "parameters": capability.parameters,
                    }
                    for capability in profile.capabilities
                ),
            }
            for profile in self._catalog.profiles()
        )

    def decode(self, arguments: Mapping[str, object]) -> PlotEngineAction:
        try:
            action = _ACTION_ADAPTER.validate_python(dict(arguments))
        except ValidationError as exc:
            raise EngineCommandError("invalid plot engine action arguments") from exc
        if action.operation == "create_plot":
            self._catalog.validate_create(action)
        return action
