from __future__ import annotations

import inspect

import pytest

from plotagent.engine import EngineActionCodec, EngineCatalog, EngineCommandError
from plotagent.engine.profiles import (
    K01_LINE_PROFILE,
    K03_SCATTER_PROFILE,
    X40_BEFORE_AFTER_PROFILE,
)


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
    assert "restore_plot_version" not in serialized
    assert codec.profile_manifest() == (
        {
            "profile_id": "K01",
            "display_name": "Line",
            "required_roles": ("x", "y"),
            "optional_roles": ("group",),
            "repeatable_role_prefixes": (),
            "objects": tuple(
                {
                    "object_alias": item.object_alias,
                    "object_kind": item.object_kind,
                    "object_key": item.object_key,
                }
                for item in K01_LINE_PROFILE.objects
            ),
            "repeatable_objects": (
                {
                    "object_alias_pattern": "series_{ordinal}",
                    "object_kind": "series",
                    "object_key_prefix": "group",
                    "ordinal_minimum": 1,
                },
            ),
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
                "operation": "restore_plot_version",
                "action_id": "action:unsafe-history",
                "target": "plot:demo",
                "expected_plot_version": 2,
                "source_plot_version": 1,
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


def test_tool_decodes_json_array_fields_from_the_desktop_boundary() -> None:
    action = _codec().decode(
        {
            "operation": "create_plot",
            "action_id": "action:desktop-create",
            "plot_id": "plot:desktop-create",
            "profile_id": "K01",
            "data": {
                "kind": "source",
                "dataset_id": "source:desktop",
                "version": 1,
                "content_hash": "a" * 64,
            },
            "bindings": [
                {"role": "x", "field_id": "field:x"},
                {"role": "y", "field_id": "field:y"},
            ],
        }
    )

    assert tuple(binding.role for binding in action.bindings) == ("x", "y")


def test_tool_surface_does_not_import_the_bundled_agent() -> None:
    source = inspect.getsource(__import__(EngineActionCodec.__module__, fromlist=["*"]))
    assert "plotagent.agent" not in source
    assert "PlotSpec" not in source


def test_dynamic_profile_manifest_publishes_bounded_series_alias_pattern() -> None:
    codec = EngineActionCodec(EngineCatalog((K03_SCATTER_PROFILE,)))

    assert codec.profile_manifest()[0]["repeatable_objects"] == (
        {
            "object_alias_pattern": "series_{ordinal}",
            "object_kind": "series",
            "object_key_prefix": "group",
            "ordinal_minimum": 1,
        },
    )


def test_profile_manifest_publishes_x40_target_parameter_boundaries() -> None:
    codec = EngineActionCodec(EngineCatalog((X40_BEFORE_AFTER_PROFILE,)))
    capability = next(
        item
        for item in codec.profile_manifest()[0]["capabilities"]
        if item["operation"] == "set_series_style"
    )

    assert capability["target_parameters"] == (
        {
            "object_kind": "series",
            "object_key": "connector",
            "parameters": (
                "visible",
                "line_stroke_color",
                "line_width_pt",
                "line_style",
            ),
        },
        {
            "object_kind": "series",
            "object_key_prefix": "column",
            "parameters": (
                "marker_shape",
                "marker_size_pt",
                "marker_interior",
                "marker_fill_color",
                "marker_stroke_color",
            ),
        },
    )
