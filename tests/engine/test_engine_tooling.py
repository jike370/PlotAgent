from __future__ import annotations

import inspect

import pytest

from plotagent.engine import EngineActionCodec, EngineCatalog, EngineCommandError
from plotagent.engine.profiles import K01_LINE_PROFILE


def _codec() -> EngineActionCodec:
    return EngineActionCodec(EngineCatalog((K01_LINE_PROFILE,)))


def test_agent_neutral_tool_schema_is_closed_and_profile_discoverable() -> None:
    codec = _codec()
    schema = codec.input_schema()
    serialized = str(schema)

    assert codec.tool_name == "plot_engine_action"
    assert "create_plot" in serialized
    assert "bind_fields" in serialized
    assert "set_axis" in serialized
    assert "export_plot" in serialized
    assert codec.profile_manifest() == (
        {
            "profile_id": "K01",
            "display_name": "Line",
            "required_roles": ("x", "y"),
            "optional_roles": ("label",),
            "repeatable_role_prefixes": (),
            "capabilities": tuple(
                {
                    "operation": item.operation,
                    "parameters": item.parameters,
                }
                for item in K01_LINE_PROFILE.capabilities
            ),
        },
    )


def test_tool_decodes_a_typed_action_and_rejects_unknown_arguments() -> None:
    codec = _codec()
    action = codec.decode(
        {
            "operation": "set_axis",
            "action_id": "action:y-log",
            "target": "axis:demo.y",
            "expected_plot_version": 1,
            "scale": "log10",
        }
    )

    assert action.operation == "set_axis"
    assert action.target == "axis:demo.y"
    with pytest.raises(EngineCommandError, match="invalid plot engine action"):
        codec.decode(
            {
                "operation": "set_axis",
                "action_id": "action:unguarded",
                "target": "axis:demo.y",
                "scale": "log10",
            }
        )
    with pytest.raises(EngineCommandError, match="invalid plot engine action"):
        codec.decode(
            {
                "operation": "run_origin_script",
                "action_id": "action:unsafe",
                "script": "arbitrary()",
            }
        )


def test_tool_surface_does_not_import_the_bundled_agent() -> None:
    source = inspect.getsource(__import__(EngineActionCodec.__module__, fromlist=["*"]))
    assert "plotagent.agent" not in source
    assert "PlotSpec" not in source
