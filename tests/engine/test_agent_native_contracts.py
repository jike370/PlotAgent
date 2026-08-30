from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from plotagent.engine import (
    AddCallout,
    AddReferenceLine,
    BindFields,
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetCanvas,
    SetLegend,
    SetObservationOverlay,
    SetSeriesStyle,
)
from plotagent.engine.profiles import ENGINE_PROFILES
from plotagent.engine.service import EngineCatalog, EngineCommandError

HASH = "a" * 64


def _data() -> EngineDataRef:
    return EngineDataRef(kind="source", dataset_id="dataset.demo", version=1, content_hash=HASH)


def _bindings() -> tuple[FieldBinding, ...]:
    return (
        FieldBinding(role="x", field_id="field:x"),
        FieldBinding(role="y", field_id="field:y"),
    )


def test_plot_document_is_minimal_and_has_no_renderer_plan() -> None:
    document = PlotDocument(
        plot_id="plot:demo",
        plot_version=1,
        profile_id="profile.line",
        data=_data(),
        bindings=_bindings(),
    )

    assert set(document.model_dump()) == {
        "schema_version",
        "plot_id",
        "plot_version",
        "parent_version",
        "profile_id",
        "data",
        "bindings",
        "applied_action_ids",
    }
    serialized = document.model_dump_json()
    assert "origin" not in serialized.lower()
    assert "matplotlib" not in serialized.lower()
    assert "layer" not in serialized.lower()
    assert "renderer" not in serialized.lower()


def test_actions_are_agent_neutral_and_discriminated() -> None:
    adapter = TypeAdapter(PlotEngineAction)
    action = adapter.validate_python(
        {
            "operation": "create_plot",
            "action_id": "action:create",
            "plot_id": "plot:demo",
            "profile_id": "profile.line",
            "data": _data().model_dump(mode="json"),
            "bindings": tuple(item.model_dump(mode="json") for item in _bindings()),
        }
    )

    assert isinstance(action, CreatePlot)

    rebound = adapter.validate_python(
        {
            "operation": "bind_fields",
            "action_id": "action:rebind",
            "target": "plot:demo",
            "expected_plot_version": 1,
            "data": _data().model_dump(mode="json"),
            "bindings": tuple(item.model_dump(mode="json") for item in _bindings()),
        }
    )
    assert isinstance(rebound, BindFields)


@pytest.mark.parametrize(
    "action",
    [
        SetAxis(
            action_id="action:axis",
            target="axis:y",
            expected_plot_version=1,
            scale="log10",
        ),
        SetSeriesStyle(
            action_id="action:series",
            target="series:signal",
            expected_plot_version=1,
            line_stroke_color="#0055AA",
        ),
        SetLegend(
            action_id="action:legend",
            target="legend:main",
            expected_plot_version=1,
            visible=False,
        ),
        AddReferenceLine(
            action_id="action:threshold",
            target="axis:demo.y",
            expected_plot_version=1,
            reference_line_id="reference_line:demo.threshold",
            value=2.5,
            line_style="dash",
        ),
    ],
)
def test_common_actions_address_semantic_objects(action: PlotEngineAction) -> None:
    assert action.target.split(":", 1)[0] in {"axis", "series", "legend"}


def test_backend_specific_or_empty_edits_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SetAxis(
            action_id="action:bad-axis",
            target="series:y",
            expected_plot_version=1,
            scale="linear",
        )


def test_visibility_and_tick_direction_are_typed_common_actions() -> None:
    axis = SetAxis(
        action_id="action:axis-visibility",
        target="axis:demo.x",
        expected_plot_version=1,
        tick_labels_visible=False,
        major_ticks_visible=True,
        minor_ticks_visible=False,
        tick_direction="inout",
        axis_line_visible=True,
        axis_title_visible=False,
    )
    series = SetSeriesStyle(
        action_id="action:series-visibility",
        target="series:demo.primary",
        expected_plot_version=1,
        visible=False,
    )

    assert axis.tick_direction == "inout"
    assert series.visible is False
    for profile in ENGINE_PROFILES:
        axis_capability = next(
            capability for capability in profile.capabilities if capability.operation == "set_axis"
        )
        assert {
            "tick_labels_visible",
            "major_ticks_visible",
            "minor_ticks_visible",
            "tick_direction",
            "axis_line_visible",
            "axis_title_visible",
        } <= set(axis_capability.parameters)
        has_series = any(
            object_.object_kind == "series"
            for object_ in (*profile.objects, *profile.repeatable_objects)
        )
        series_capability = next(
            (
                capability
                for capability in profile.capabilities
                if capability.operation == "set_series_style"
            ),
            None,
        )
        assert (series_capability is not None) is has_series
        if series_capability is not None:
            if profile.profile_id == "K09":
                assert series_capability.parameters == ("fill_color",)
            else:
                assert "visible" in series_capability.parameters
    with pytest.raises(ValidationError):
        SetSeriesStyle(
            action_id="action:empty-series",
            target="series:y",
            expected_plot_version=1,
        )
    with pytest.raises(ValidationError):
        TypeAdapter(PlotEngineAction).validate_python(
            {
                "operation": "execute_labtalk",
                "action_id": "action:unsafe",
                "script": "run.section(foo)",
            }
        )


def test_canvas_is_a_typed_public_action_for_every_profile() -> None:
    action = SetCanvas(
        action_id="action:wide-page",
        target="plot:demo",
        expected_plot_version=1,
        aspect_ratio=2.4,
    )

    assert action.aspect_ratio == 2.4
    for profile in ENGINE_PROFILES:
        capability = next(
            item for item in profile.capabilities if item.operation == "set_canvas"
        )
        assert set(capability.parameters) == {"width_mm", "height_mm", "aspect_ratio"}

    with pytest.raises(ValidationError, match="one canvas dimension requires"):
        SetCanvas(
            action_id="action:incomplete-page",
            target="plot:demo",
            expected_plot_version=1,
            width_mm=180,
        )


def test_k13_observation_overlay_is_closed_to_same_bound_rows() -> None:
    action = SetObservationOverlay(
        action_id="action:k13-observations",
        target="observation_overlay:demo.raw",
        expected_plot_version=1,
        jitter_fraction=0.2,
        marker_shape="triangle_down",
    )
    catalog = EngineCatalog(ENGINE_PROFILES)
    catalog.validate_action(catalog.get("K13"), action)

    k13 = catalog.get("K13")
    assert next(
        item for item in k13.objects if item.object_alias == "observations"
    ).instantiate("plot:demo") == "observation_overlay:demo.raw"
    assert sum(
        capability.operation == "set_observation_overlay"
        for profile in ENGINE_PROFILES
        for capability in profile.capabilities
    ) == 1

    with pytest.raises(EngineCommandError, match="does not support"):
        catalog.validate_action(catalog.get("K14"), action)
    with pytest.raises(ValidationError):
        TypeAdapter(PlotEngineAction).validate_python(
            {
                **action.model_dump(mode="python"),
                "field_id": "field:second-data",
            }
        )
    with pytest.raises(ValidationError, match="disagree"):
        SetCanvas(
            action_id="action:conflicting-page",
            target="plot:demo",
            expected_plot_version=1,
            width_mm=180,
            height_mm=100,
            aspect_ratio=3,
        )


def test_reference_line_is_public_only_where_profiles_have_numeric_axes() -> None:
    supported = {
        profile.profile_id
        for profile in ENGINE_PROFILES
        if any(item.operation == "add_reference_line" for item in profile.capabilities)
    }
    assert supported == {profile.profile_id for profile in ENGINE_PROFILES} - {
        "K20",
        "K21",
        "K24",
        "S61",
    }
    for profile in ENGINE_PROFILES:
        capability = next(
            (item for item in profile.capabilities if item.operation == "add_reference_line"),
            None,
        )
        if capability is not None:
            assert set(capability.parameters) == {
                "value",
                "label",
                "line_color",
                "line_width_pt",
                "line_style",
            }

    with pytest.raises(ValidationError, match="requires an axis target"):
        AddReferenceLine(
            action_id="action:bad-reference-target",
            target="plot:demo",
            expected_plot_version=1,
            reference_line_id="reference_line:demo.threshold",
            value=1,
        )
    with pytest.raises(ValidationError, match="cannot be none"):
        AddReferenceLine(
            action_id="action:hidden-reference",
            target="axis:demo.y",
            expected_plot_version=1,
            reference_line_id="reference_line:demo.threshold",
            value=1,
            line_style="none",
        )


def test_callout_contract_is_reference_line_bound_and_uses_separate_coordinate_names() -> None:
    action = AddCallout(
        action_id="action:eu-mean-callout",
        target="reference_line:demo.eu_mean",
        expected_plot_version=2,
        callout_id="callout:demo.eu_mean",
        text="Mean total content across EU",
        anchor_fraction=0.55,
        text_x_fraction=0.52,
        text_y_fraction=0.82,
        arrow_head="filled",
    )

    assert action.target == "reference_line:demo.eu_mean"
    assert action.anchor_fraction == 0.55
    assert TypeAdapter(PlotEngineAction).validate_python(action.model_dump()) == action
    supported = {
        profile.profile_id
        for profile in ENGINE_PROFILES
        if any(item.operation == "add_callout" for item in profile.capabilities)
    }
    assert supported == {profile.profile_id for profile in ENGINE_PROFILES} - {
        "K20",
        "K21",
        "K24",
        "S61",
    }
    for profile in ENGINE_PROFILES:
        callout = next(
            (item for item in profile.capabilities if item.operation == "add_callout"),
            None,
        )
        reference_line = next(
            (item for item in profile.capabilities if item.operation == "add_reference_line"),
            None,
        )
        assert (callout is not None) == (reference_line is not None)
        if callout is not None:
            assert set(callout.parameters) == {
                "text",
                "anchor_fraction",
                "text_x_fraction",
                "text_y_fraction",
                "arrow_color",
                "arrow_width_pt",
                "arrow_head",
                "font_family",
                "font_size_pt",
                "font_weight",
                "italic",
                "text_color",
            }

    with pytest.raises(ValidationError, match="requires a reference_line target"):
        AddCallout(
            action_id="action:bad-callout-target",
            target="axis:demo.y",
            expected_plot_version=1,
            callout_id="callout:demo.bad",
            text="Bad target",
            text_x_fraction=0.5,
            text_y_fraction=0.5,
        )


def test_engine_data_view_is_rectangular_and_renderer_neutral() -> None:
    data = _data()
    view = EngineDataView(
        data=data,
        row_ids=("row:1", "row:2"),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:x",
                    name="Time",
                    logical_type="numeric",
                    unit_label="s",
                ),
                values=(0.0, 1.0),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:y",
                    name="Signal",
                    logical_type="numeric",
                ),
                values=(2.0, 3.0),
            ),
        ),
    )

    assert view.data.content_hash == HASH
    assert tuple(column.field.name for column in view.columns) == ("Time", "Signal")
    serialized = view.model_dump_json().casefold()
    assert "origin" not in serialized
    assert "matplotlib" not in serialized


def test_engine_data_view_rejects_jagged_or_duplicate_data() -> None:
    field = EngineField(field_id="field:x", name="X", logical_type="numeric")
    with pytest.raises(ValidationError, match="row count"):
        EngineDataView(
            data=_data(),
            row_ids=("row:1", "row:2"),
            columns=(EngineColumn(field=field, values=(1.0,)),),
        )
    with pytest.raises(ValidationError, match="fields must be unique"):
        EngineDataView(
            data=_data(),
            row_ids=("row:1",),
            columns=(
                EngineColumn(field=field, values=(1.0,)),
                EngineColumn(field=field, values=(2.0,)),
            ),
        )
