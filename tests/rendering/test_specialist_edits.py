from __future__ import annotations

import math

import matplotlib.pyplot as plt
import pytest

from plotagent.contracts.base import ColorValue, PhysicalLength
from plotagent.contracts.plots import (
    BarAreaEditSpec,
    ChartParameterEditSpec,
    ColorbarEditSpec,
    DualYAxisEditSpec,
    FacetEditSpec,
    FacetLabelEdit,
    SetBarAreaStylePatch,
    SetChartParametersPatch,
    SpecialistEditSpec,
    UncertaintyEditSpec,
    YOffsetEditSpec,
)
from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from plotagent.plots.validation import PlotValidationError, validate_plot_patch
from plotagent.rendering import PlotResolver
from plotagent.rendering.matplotlib.adapter import MatplotlibRenderer
from tests.rendering.fixture_factory import build_plot_and_store


def _resolve(chart_id: str, specialist: SpecialistEditSpec):
    plot, store = build_plot_and_store(chart_id)
    edited = plot.model_copy(update={"specialist": specialist})
    return edited, PlotResolver().resolve(edited, store)


def _roles(resolved, layer_index: int) -> dict[str, tuple[object, ...]]:
    layer = resolved.plan.layers[layer_index]
    table = resolved.table_for(layer)
    return {binding.role: table.column(binding.field_id) for binding in layer.field_bindings}


def test_bar_area_edit_is_data_driven_and_propagates_to_both_backends() -> None:
    specialist = SpecialistEditSpec(
        bar_area=BarAreaEditSpec(
            fill_color=ColorValue(value="#123456"),
            edge_color=ColorValue(value="#654321"),
            edge_width=PhysicalLength(value=1.2, unit="pt"),
            width_ratio=0.6,
            alpha=0.7,
        )
    )
    _plot, resolved = _resolve("K09", specialist)

    assert len(resolved.plan.layers) == 2
    assert all(layer.width_ratio == 0.6 for layer in resolved.plan.layers)
    assert all(set(_roles(resolved, index)["width"]) == {0.3} for index in range(2))
    assert all(layer.fill_color == ColorValue(value="#123456") for layer in resolved.plan.layers)
    figure = MatplotlibRenderer().build_figure(resolved)
    patches = figure.axes[0].patches
    assert patches and all(item.get_width() == pytest.approx(0.3) for item in patches)
    assert all(item.get_alpha() == pytest.approx(0.7) for item in patches)
    plt.close(figure)

    origin = compile_origin_plan((resolved,), build_origin_export_spec((resolved,)))
    origin_plots = origin.graph_objects[0].layers[0].plots
    assert all(item.width_ratio == 0.6 for item in origin_plots)
    assert all(item.fill_color == ColorValue(value="#123456") for item in origin_plots)


def test_uncertainty_and_colorbar_edits_are_typed_and_renderer_visible() -> None:
    uncertainty = UncertaintyEditSpec(
        color=ColorValue(value="#7C3AED"),
        line_width=PhysicalLength(value=1.4, unit="pt"),
        cap_size=PhysicalLength(value=6, unit="pt"),
        band_alpha=0.4,
    )
    _plot, band = _resolve("K07", SpecialistEditSpec(uncertainty=uncertainty))
    assert all(layer.uncertainty_color == ColorValue(value="#7C3AED") for layer in band.plan.layers)
    assert all(layer.band_alpha == 0.4 for layer in band.plan.layers)
    figure = MatplotlibRenderer().build_figure(band)
    assert figure.axes[0].collections
    plt.close(figure)

    colorbar = ColorbarEditSpec(
        minimum=-3,
        maximum=3,
        levels=5,
    )
    _plot, contour = _resolve("K22", SpecialistEditSpec(colorbar=colorbar))
    layer = contour.plan.layers[0]
    assert (layer.color_minimum, layer.color_maximum, len(layer.levels)) == (-3, 3, 5)
    assert contour.plan.colorbar.visible is True
    figure = MatplotlibRenderer().build_figure(contour)
    assert len(figure.axes) == 2
    plt.close(figure)
    origin = compile_origin_plan((contour,), build_origin_export_spec((contour,)))
    assert origin.graph_objects[0].colorbar.levels == 5


def test_dual_y_facet_and_offset_edits_change_structure_without_mutating_data() -> None:
    dual_style = DualYAxisEditSpec(
        left_color=ColorValue(value="#0F766E"),
        right_color=ColorValue(value="#BE123C"),
        axis_width=PhysicalLength(value=1.1, unit="pt"),
    )
    _plot, dual = _resolve("X23", SpecialistEditSpec(dual_y=dual_style))
    axes = {axis.panel_id: axis for axis in dual.plan.axes if axis.orientation == "y"}
    assert axes["panel:left"].color == ColorValue(value="#0F766E")
    assert axes["panel:right"].color == ColorValue(value="#BE123C")
    assert all(axis.line_width.value == 1.1 for axis in axes.values())

    facet_style = FacetEditSpec(
        order=("B", "A"),
        labels=(FacetLabelEdit(value="B", label="Treatment"),),
        gap=PhysicalLength(value=6, unit="mm"),
        shared_x=False,
        shared_y=False,
        common_legend=False,
    )
    _plot, facet = _resolve("K24", SpecialistEditSpec(facet=facet_style))
    assert [layer.label.nodes[0].text for layer in facet.plan.layers] == ["B", "A"]
    assert facet.plan.panels[0].label.nodes[0].text == "Treatment"
    assert facet.plan.legend.common is False
    first, second = facet.plan.panels
    assert second.left.value - (first.left.value + first.width.value) == pytest.approx(6)

    offset_style = YOffsetEditSpec(distance=10, order=("B", "A"))
    _plot, offset = _resolve("X38", SpecialistEditSpec(y_offset=offset_style))
    assert [layer.label.nodes[0].text for layer in offset.plan.layers] == ["B", "A"]
    first_y = tuple(float(value) for value in _roles(offset, 0)["y"])
    second_y = tuple(float(value) for value in _roles(offset, 1)["y"])
    assert max(second_y) - max(first_y) > 5


@pytest.mark.parametrize(
    ("chart_id", "parameters"),
    (
        ("X01", ChartParameterEditSpec(step_where="mid")),
        ("X02", ChartParameterEditSpec(lollipop_baseline=-2)),
        ("X24", ChartParameterEditSpec(pareto_reference_percent=75)),
        (
            "S07",
            ChartParameterEditSpec(
                volcano_absolute_log2_fold_change=2,
                volcano_pvalue=0.01,
            ),
        ),
    ),
)
def test_fixed_chart_parameters_have_explicit_resolved_geometry(
    chart_id: str,
    parameters: ChartParameterEditSpec,
) -> None:
    _plot, resolved = _resolve(
        chart_id,
        SpecialistEditSpec(chart_parameters=parameters),
    )
    if chart_id == "X01":
        assert resolved.plan.layers[0].step_where == "mid"
    elif chart_id == "X02":
        assert set(_roles(resolved, 0)["baseline"]) == {-2.0}
        x_axis = next(axis for axis in resolved.plan.axes if axis.orientation == "x")
        assert x_axis.cross_at == -2
    elif chart_id == "X24":
        reference = resolved.plan.layers[-1]
        assert set(_roles(resolved, len(resolved.plan.layers) - 1)["y"]) == {75.0}
        assert reference.geometry == "xy.line"
    else:
        guides = [
            _roles(resolved, index)
            for index, layer in enumerate(resolved.plan.layers)
            if layer.geometry == "xy.line"
        ]
        vertical_x = {tuple(float(value) for value in roles["x"]) for roles in guides}
        assert (-2.0, -2.0) in vertical_x and (2.0, 2.0) in vertical_x
        assert any(all(math.isclose(float(value), 2.0) for value in roles["y"]) for roles in guides)


def test_specialist_patch_capability_is_denied_outside_its_chart_profile() -> None:
    plot, _store = build_plot_and_store("K01")
    patch = SetBarAreaStylePatch(
        target_id=plot.plot_id,
        expected_plot_version=plot.plot_version,
        style=BarAreaEditSpec(width_ratio=0.5),
    )
    with pytest.raises(PlotValidationError) as error:
        validate_plot_patch(plot, patch)
    assert error.value.code == "PATCH_CAPABILITY_NOT_SUPPORTED"

    chart_patch = SetChartParametersPatch(
        target_id=plot.plot_id,
        expected_plot_version=plot.plot_version,
        parameters=ChartParameterEditSpec(),
    )
    with pytest.raises(PlotValidationError) as chart_error:
        validate_plot_patch(plot, chart_patch)
    assert chart_error.value.code == "PATCH_CAPABILITY_NOT_SUPPORTED"
