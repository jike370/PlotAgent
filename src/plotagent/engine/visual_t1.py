"""Closed, renderer-neutral T1 visual action vocabulary."""

from __future__ import annotations

from dataclasses import replace

from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import (
    AddAnnotation,
    AddCallout,
    AddReferenceLine,
    BindFields,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetCanvas,
    SetChartParameter,
    SetColorMap,
    SetDataLabels,
    SetErrorStyle,
    SetLegend,
    SetObservationOverlay,
    SetPointMarkerMap,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineReadback
from plotagent.engine.product_style import (
    K06_POINT_ERROR_STYLE,
    K07_ERROR_RIBBON_STYLE,
    K09_GROUPED_COLUMN_STYLE,
    K22_FILLED_CONTOUR_STYLE,
    X40_BEFORE_AFTER_STYLE,
    K09GroupedColumnStyle,
)

VISUAL_ACTION_TYPES = (
    SetTitle,
    SetAxis,
    SetSeriesStyle,
    SetLegend,
    SetColorMap,
    SetErrorStyle,
    SetDataLabels,
    SetCanvas,
    AddAnnotation,
    AddReferenceLine,
    AddCallout,
)
DATA_DERIVED_VISUAL_TYPES = (SetSeriesStyle, SetColorMap, SetErrorStyle, SetDataLabels)
K09_VISUAL_CHART_PARAMETERS = frozenset(
    {
        "bar_border_visible",
        "within_group_gap_percent",
        "between_group_gap_percent",
    }
)


def product_default_visual_actions(
    document: PlotDocument,
) -> tuple[PlotEngineAction, ...]:
    """Return renderer-neutral defaults that official templates must materialize.

    These internal actions are prepended before user actions, so the normal
    last-write-wins reducer preserves every explicit edit. They are not public
    TaskPlan operations and do not expand a profile's capability surface.
    """

    token = document.plot_id.removeprefix("plot:")
    if document.profile_id == "X40":
        style = X40_BEFORE_AFTER_STYLE
        return (
            SetSeriesStyle(
                action_id=f"action:product-default-{token}-before",
                target=f"series:{token}.column_1",
                expected_plot_version=document.plot_version,
                marker_shape=style.before_marker_shape,
                marker_size_pt=style.marker_size_pt,
                marker_interior="solid",
                marker_fill_color=style.before_color,
                marker_stroke_color=style.before_color,
            ),
            SetSeriesStyle(
                action_id=f"action:product-default-{token}-after",
                target=f"series:{token}.column_2",
                expected_plot_version=document.plot_version,
                marker_shape=style.after_marker_shape,
                marker_size_pt=style.marker_size_pt,
                marker_interior="solid",
                marker_fill_color=style.after_color,
                marker_stroke_color=style.after_color,
            ),
            SetSeriesStyle(
                action_id=f"action:product-default-{token}-connector",
                target=f"series:{token}.connector",
                expected_plot_version=document.plot_version,
                visible=True,
                line_stroke_color=style.connector_color,
                line_width_pt=style.connector_width_pt,
                line_style="solid",
            ),
            SetAxis(
                action_id=f"action:product-default-{token}-x-axis",
                target=f"axis:{token}.x",
                expected_plot_version=document.plot_version,
                axis_title_visible=style.x_axis_title_visible,
            ),
            SetAxis(
                action_id=f"action:product-default-{token}-y-axis",
                target=f"axis:{token}.y",
                expected_plot_version=document.plot_version,
                label=style.y_axis_label,
            ),
            SetLegend(
                action_id=f"action:product-default-{token}-legend",
                target=f"legend:{token}.main",
                expected_plot_version=document.plot_version,
                visible=style.legend_visible,
            ),
        )
    if document.profile_id == "K07":
        target = f"series:{token}.primary"
        style = K07_ERROR_RIBBON_STYLE
        return (
            SetSeriesStyle(
                action_id=f"action:product-default-{token}-series",
                target=target,
                expected_plot_version=document.plot_version,
                line_stroke_color=style.color,
                line_width_pt=style.line_width_pt,
                line_style=style.line_style,
            ),
            SetErrorStyle(
                action_id=f"action:product-default-{token}-band",
                target=target,
                expected_plot_version=document.plot_version,
                band_fill_color=style.color,
                band_fill_opacity=style.band_fill_opacity,
                band_stroke_color=style.color,
                band_stroke_width_pt=style.band_stroke_width_pt,
            ),
            SetLegend(
                action_id=f"action:product-default-{token}-legend",
                target=f"legend:{token}.main",
                expected_plot_version=document.plot_version,
                visible=style.legend_visible,
            ),
        )
    if document.profile_id == "K22":
        style = K22_FILLED_CONTOUR_STYLE
        return (
            SetColorMap(
                action_id=f"action:product-default-{token}-colormap",
                target=f"series:{token}.matrix",
                expected_plot_version=document.plot_version,
                palette=style.palette,
                reverse=style.reverse,
                colorbar_visible=style.colorbar_visible,
                colorbar_anchor=style.colorbar_anchor,
                colorbar_tick_format=style.colorbar_tick_format,
            ),
        )
    if document.profile_id != "K06":
        return ()
    target = f"series:{token}.primary"
    style = K06_POINT_ERROR_STYLE
    return (
        SetSeriesStyle(
            action_id=f"action:product-default-{token}-series",
            target=target,
            expected_plot_version=document.plot_version,
            marker_shape=style.marker_shape,
            marker_size_pt=style.marker_size_pt,
            marker_interior="solid",
            marker_fill_color=style.color,
            marker_stroke_color=style.color,
        ),
        SetErrorStyle(
            action_id=f"action:product-default-{token}-errors",
            target=target,
            expected_plot_version=document.plot_version,
            bar_color=style.color,
            bar_width_pt=style.error_width_pt,
            cap_size_pt=style.cap_size_pt,
            bar_opacity=1.0,
        ),
        SetLegend(
            action_id=f"action:product-default-{token}-legend",
            target=f"legend:{token}.main",
            expected_plot_version=document.plot_version,
            visible=style.legend_visible,
        ),
    )


def resolve_k09_grouped_column_style(
    document: PlotDocument,
    actions: tuple[PlotEngineAction, ...],
) -> K09GroupedColumnStyle:
    """Resolve and validate K09's three public whole-plot style controls."""

    style = K09_GROUPED_COLUMN_STYLE
    for action in actions:
        if not isinstance(action, SetChartParameter):
            continue
        if action.parameter not in K09_VISUAL_CHART_PARAMETERS:
            continue
        if document.profile_id != "K09" or action.target != document.plot_id:
            raise ValueError("K09 grouped-column parameters require the K09 plot target")
        if action.parameter == "bar_border_visible":
            if not isinstance(action.value, bool):
                raise ValueError("K09 bar_border_visible must be boolean")
            style = replace(style, bar_border_visible=action.value)
            continue
        if isinstance(action.value, bool) or not isinstance(action.value, (int, float)):
            raise ValueError(f"K09 {action.parameter} must be numeric")
        value = float(action.value)
        if not 0.0 <= value < 100.0:
            raise ValueError(f"K09 {action.parameter} must be from 0 up to but not including 100")
        style = replace(style, **{action.parameter: value})
    return style


def resolve_canvas_inches(
    current_width: float,
    current_height: float,
    action: SetCanvas,
) -> tuple[float, float]:
    """Resolve one page edit against the current native page size."""

    width = current_width if action.width_mm is None else action.width_mm / 25.4
    height = current_height if action.height_mm is None else action.height_mm / 25.4
    if action.aspect_ratio is not None:
        if action.width_mm is not None and action.height_mm is None:
            height = width / action.aspect_ratio
        elif action.width_mm is None:
            width = height * action.aspect_ratio
    return width, height


def _belongs_to_plot(target: str, plot_target: str) -> bool:
    """Match a child semantic ID to the complete plot ID, including dots."""

    plot_token = plot_target.removeprefix("plot:")
    return target.partition(":")[2].startswith(plot_token + ".")


def _with_colorbar_visibility(action: SetColorMap, visible: bool) -> SetColorMap:
    """Normalize the overlapping color-scale visibility edit.

    ``SetChartParameter(color_scale_visible=...)`` and
    ``SetColorMap(colorbar_visible=...)`` intentionally expose the same user
    state through structural and visual vocabularies.  Structural renderers run
    before the shared visual pass, so the shared pass must carry the same final
    value rather than replaying an earlier one.  Other colormap properties stay
    latent while hidden and are applied if a later action shows the scale.
    """

    payload = action.model_dump(mode="python")
    payload["colorbar_visible"] = visible
    return SetColorMap.model_validate(payload)


def _supersede_colorbar_visibility(
    visual: list[PlotEngineAction], chart_action: SetChartParameter
) -> list[PlotEngineAction]:
    if chart_action.parameter != "color_scale_visible":
        return visual
    if not isinstance(chart_action.value, bool):
        raise ValueError("color_scale_visible must be boolean")
    normalized: list[PlotEngineAction] = []
    for item in visual:
        if (
            isinstance(item, SetColorMap)
            and item.colorbar_visible is not None
            and _belongs_to_plot(item.target, chart_action.target)
        ):
            normalized.append(_with_colorbar_visibility(item, chart_action.value))
        else:
            normalized.append(item)
    return normalized


def split_visual_actions(
    actions: tuple[PlotEngineAction, ...],
) -> tuple[tuple[PlotEngineAction, ...], tuple[PlotEngineAction, ...]]:
    structural: list[PlotEngineAction] = []
    visual: list[PlotEngineAction] = []
    for action in actions:
        if isinstance(action, BindFields):
            structural = [item for item in structural if not isinstance(item, SetPointMarkerMap)]
            structural.append(action)
            visual = [item for item in visual if not isinstance(item, DATA_DERIVED_VISUAL_TYPES)]
        elif isinstance(action, SetPointMarkerMap):
            structural = [
                item
                for item in structural
                if not (isinstance(item, SetPointMarkerMap) and item.target == action.target)
            ]
            structural.append(action)
            normalized_visual: list[PlotEngineAction] = []
            for item in visual:
                if (
                    isinstance(item, SetSeriesStyle)
                    and item.target == action.target
                    and item.marker_shape is not None
                ):
                    payload = item.model_dump(
                        exclude={
                            "operation",
                            "action_id",
                            "target",
                            "expected_plot_version",
                        },
                        exclude_none=True,
                    )
                    payload.pop("marker_shape", None)
                    if payload:
                        normalized_visual.append(item.model_copy(update={"marker_shape": None}))
                else:
                    normalized_visual.append(item)
            visual = normalized_visual
        elif isinstance(action, SetObservationOverlay):
            structural = [
                item
                for item in structural
                if not (isinstance(item, SetObservationOverlay) and item.target == action.target)
            ]
            structural.append(action)
        elif (
            isinstance(action, SetChartParameter)
            and action.parameter in K09_VISUAL_CHART_PARAMETERS
        ):
            # K09's official indexed-column binder creates one native DataPlot.
            # Border and spacing are persistent presentation properties on that
            # object, so both backends apply them in the shared visual pass.
            visual.append(action)
        elif isinstance(action, VISUAL_ACTION_TYPES):
            if isinstance(action, SetSeriesStyle) and action.marker_shape is not None:
                structural = [
                    item
                    for item in structural
                    if not (isinstance(item, SetPointMarkerMap) and item.target == action.target)
                ]
            visual.append(action)
        else:
            structural.append(action)
            if isinstance(action, SetChartParameter):
                visual = _supersede_colorbar_visibility(visual, action)
    return tuple(structural), tuple(visual)


def effective_visual_actions(
    actions: tuple[PlotEngineAction, ...],
) -> tuple[PlotEngineAction, ...]:
    """Collapse cumulative state edits property-by-property.

    Applying every historical value is normally harmless for persistent native
    objects, but it is incorrect for state whose temporary value removes an
    object (for example a hidden Matplotlib colorbar).  Both backends therefore
    consume the same final state per action type and target.  Annotations remain
    independent addressable objects.
    """

    stateful = (
        SetTitle,
        SetAxis,
        SetSeriesStyle,
        SetLegend,
        SetColorMap,
        SetErrorStyle,
        SetDataLabels,
        SetChartParameter,
    )
    merged: dict[tuple[object, ...], PlotEngineAction] = {}
    last_positions: dict[tuple[object, ...], int] = {}

    def state_key(action: PlotEngineAction) -> tuple[object, ...]:
        if isinstance(action, SetChartParameter):
            return type(action), action.target, action.parameter
        return type(action), action.target

    last_canvas_position = max(
        (index for index, action in enumerate(actions) if isinstance(action, SetCanvas)),
        default=-1,
    )
    last_reference_line_positions = {
        action.reference_line_id: index
        for index, action in enumerate(actions)
        if isinstance(action, AddReferenceLine)
    }
    last_callout_positions = {
        action.callout_id: index
        for index, action in enumerate(actions)
        if isinstance(action, AddCallout)
    }
    for index, action in enumerate(actions):
        if not isinstance(action, stateful):
            continue
        key = state_key(action)
        previous = merged.get(key)
        update = action.model_dump(exclude_none=True)
        if isinstance(action, SetAxis):
            if action.bounds_mode == "automatic":
                # Resetting to automatic bounds must remove earlier fixed limits
                # from the cumulative action state.
                update["minimum"] = None
                update["maximum"] = None
            elif action.minimum is not None and action.maximum is not None:
                # A later fixed pair supersedes an earlier automatic reset even
                # when callers use the backwards-compatible implicit fixed mode.
                update["bounds_mode"] = "fixed"
        merged[key] = action if previous is None else previous.model_copy(update=update)
        last_positions[key] = index

    result: list[PlotEngineAction] = []
    for index, action in enumerate(actions):
        if isinstance(action, SetCanvas):
            if index == last_canvas_position:
                result.append(action)
            continue
        if isinstance(action, AddReferenceLine):
            if last_reference_line_positions[action.reference_line_id] == index:
                result.append(action)
            continue
        if isinstance(action, AddCallout):
            if last_callout_positions[action.callout_id] == index:
                result.append(action)
            continue
        if not isinstance(action, stateful):
            result.append(action)
            continue
        key = state_key(action)
        if last_positions[key] == index:
            result.append(merged[key])
    return tuple(result)


def visual_style_hash(readback: EngineReadback, actions: tuple[PlotEngineAction, ...]) -> str:
    return canonical_hash(
        {
            "profile_style_hash": readback.style_hash,
            "t1_visual_actions": [action.model_dump(mode="json") for action in actions],
        }
    )
