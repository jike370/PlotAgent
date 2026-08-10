from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from plotagent.engine import (
    CreatePlot,
    EngineDataRef,
    FieldBinding,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetLegend,
    SetSeriesStyle,
)

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


@pytest.mark.parametrize(
    "action",
    [
        SetAxis(action_id="action:axis", target="axis:y", scale="log10"),
        SetSeriesStyle(action_id="action:series", target="series:signal", color="#0055AA"),
        SetLegend(action_id="action:legend", target="legend:main", visible=False),
    ],
)
def test_common_actions_address_semantic_objects(action: PlotEngineAction) -> None:
    assert action.target.split(":", 1)[0] in {"axis", "series", "legend"}


def test_backend_specific_or_empty_edits_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SetAxis(action_id="action:bad-axis", target="series:y", scale="linear")
    with pytest.raises(ValidationError):
        SetSeriesStyle(action_id="action:empty-series", target="series:y")
    with pytest.raises(ValidationError):
        TypeAdapter(PlotEngineAction).validate_python(
            {
                "operation": "execute_labtalk",
                "action_id": "action:unsafe",
                "script": "run.section(foo)",
            }
        )
