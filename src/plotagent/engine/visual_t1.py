"""Closed, renderer-neutral T1 visual action vocabulary."""

from __future__ import annotations

from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import (
    AddAnnotation,
    BindFields,
    PlotEngineAction,
    SetAxis,
    SetColorMap,
    SetDataLabels,
    SetErrorStyle,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineReadback

VISUAL_ACTION_TYPES = (
    SetTitle,
    SetAxis,
    SetSeriesStyle,
    SetLegend,
    SetColorMap,
    SetErrorStyle,
    SetDataLabels,
    AddAnnotation,
)
DATA_DERIVED_VISUAL_TYPES = (SetSeriesStyle, SetColorMap, SetErrorStyle, SetDataLabels)


def split_visual_actions(
    actions: tuple[PlotEngineAction, ...],
) -> tuple[tuple[PlotEngineAction, ...], tuple[PlotEngineAction, ...]]:
    structural: list[PlotEngineAction] = []
    visual: list[PlotEngineAction] = []
    for action in actions:
        if isinstance(action, BindFields):
            structural.append(action)
            visual = [item for item in visual if not isinstance(item, DATA_DERIVED_VISUAL_TYPES)]
        elif isinstance(action, VISUAL_ACTION_TYPES):
            visual.append(action)
        else:
            structural.append(action)
    return tuple(structural), tuple(visual)


def visual_style_hash(readback: EngineReadback, actions: tuple[PlotEngineAction, ...]) -> str:
    return canonical_hash(
        {
            "profile_style_hash": readback.style_hash,
            "t1_visual_actions": [action.model_dump(mode="json") for action in actions],
        }
    )
