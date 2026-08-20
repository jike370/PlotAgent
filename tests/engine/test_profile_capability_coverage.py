"""Frozen product expectations for the public editing surface.

These assertions intentionally do not derive their expected exceptions from
the generated catalog.  They are the independent requirements trace that was
missing when a catalog omission made X38 reject a valid axis-range edit while
the Agent, compiler and UI all agreed with that same omission.
"""

from __future__ import annotations

import pytest

from plotagent.engine import EngineCatalog, EngineCommandError, SetErrorStyle
from plotagent.engine.profiles import ENGINE_PROFILES


def _capabilities(profile_id: str) -> dict[str, set[str]]:
    profile = next(item for item in ENGINE_PROFILES if item.profile_id == profile_id)
    return {
        capability.operation: set(capability.parameters)
        for capability in profile.capabilities
    }


def test_all_34_profiles_expose_the_common_editing_spine() -> None:
    assert len(ENGINE_PROFILES) == 34
    for profile in ENGINE_PROFILES:
        operations = {capability.operation for capability in profile.capabilities}
        assert {
            "create_plot",
            "bind_fields",
            "set_title",
            "set_axis",
            "set_series_style",
            "export_plot",
        } <= operations, profile.profile_id
        assert "add_annotation" not in operations, profile.profile_id


def test_axis_capability_exceptions_are_explicit_and_frozen() -> None:
    missing_bounds: set[str] = set()
    missing_scale: set[str] = set()
    missing_reverse: set[str] = set()
    required_visibility = {
        "tick_labels_visible",
        "major_ticks_visible",
        "minor_ticks_visible",
        "tick_direction",
        "axis_line_visible",
        "axis_title_visible",
    }

    for profile in ENGINE_PROFILES:
        axis = _capabilities(profile.profile_id)["set_axis"]
        assert "label" in axis, profile.profile_id
        assert required_visibility <= axis, profile.profile_id
        if "bounds" not in axis:
            missing_bounds.add(profile.profile_id)
        if "scale" not in axis:
            missing_scale.add(profile.profile_id)
        if "reverse" not in axis:
            missing_reverse.add(profile.profile_id)

    # Matrix/category axes have no meaningful numeric bounds.  X24 mixes a
    # categorical X, numeric left Y and fixed-percent right Y; the current
    # profile-wide contract cannot safely expose a target-specific bound.
    assert missing_bounds == {"K20", "K21", "S61", "X24"}
    assert missing_scale == {"K20", "K21", "K22", "S34", "S61", "X13", "X24"}
    assert missing_reverse == {"X24"}
    assert "bounds" in _capabilities("X38")["set_axis"]


def test_error_style_capabilities_match_each_native_error_shape() -> None:
    assert _capabilities("K06")["set_error_style"] == {
        "bar_color",
        "bar_width_pt",
        "cap_size_pt",
        "bar_opacity",
    }
    assert _capabilities("K07")["set_error_style"] == {
        "band_fill_color",
        "band_fill_opacity",
        "band_stroke_color",
        "band_stroke_width_pt",
    }
    assert {
        profile.profile_id
        for profile in ENGINE_PROFILES
        if "set_error_style" in _capabilities(profile.profile_id)
    } == {"K06", "K07"}


def test_engine_authority_enforces_the_error_shape_boundary() -> None:
    catalog = EngineCatalog(ENGINE_PROFILES)
    catalog.validate_action(
        catalog.get("K06"),
        SetErrorStyle(
            action_id="action:k06-bar",
            target="series:k06.primary",
            expected_plot_version=1,
            cap_size_pt=5,
        ),
    )
    catalog.validate_action(
        catalog.get("K07"),
        SetErrorStyle(
            action_id="action:k07-band",
            target="series:k07.primary",
            expected_plot_version=1,
            band_fill_opacity=0.25,
        ),
    )
    with pytest.raises(EngineCommandError, match="band_fill_opacity"):
        catalog.validate_action(
            catalog.get("K06"),
            SetErrorStyle(
                action_id="action:k06-invalid-band",
                target="series:k06.primary",
                expected_plot_version=1,
                band_fill_opacity=0.25,
            ),
        )
    with pytest.raises(EngineCommandError, match="cap_size_pt"):
        catalog.validate_action(
            catalog.get("K07"),
            SetErrorStyle(
                action_id="action:k07-invalid-bar",
                target="series:k07.primary",
                expected_plot_version=1,
                cap_size_pt=5,
            ),
        )


def test_legend_capability_matches_a_declared_legend_object() -> None:
    for profile in ENGINE_PROFILES:
        has_legend_object = any(item.object_kind == "legend" for item in profile.objects)
        has_legend_capability = "set_legend" in _capabilities(profile.profile_id)
        assert has_legend_capability is has_legend_object, profile.profile_id
