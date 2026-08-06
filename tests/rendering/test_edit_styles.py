from __future__ import annotations

import pytest

from plotagent.contracts.base import ColorValue, PhysicalLength
from plotagent.contracts.plots import (
    SetCategoryColorPatch,
    SetPalettePatch,
    SetSeriesStylePatch,
)
from plotagent.contracts.styles import SymbolStyle, resolve_palette
from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from plotagent.plots.validation import PlotValidationError, validate_plot_patch
from plotagent.rendering import PlotResolver
from tests.rendering.fixture_factory import build_plot_and_store
from tests.rendering.test_generalization import Variant, _grouped_bar_variant, resolve_variant


def test_chart_profile_rejects_undeclared_style_field_with_stable_error() -> None:
    plot, _store = build_plot_and_store("K01")
    patch = SetSeriesStylePatch(
        target_id=plot.series[0].series_id,
        expected_plot_version=plot.plot_version,
        marker_size=PhysicalLength(value=7, unit="pt"),
    )
    with pytest.raises(PlotValidationError) as error:
        validate_plot_patch(plot, patch)
    assert error.value.code == "PATCH_CAPABILITY_NOT_SUPPORTED"


def test_resolver_carries_symbol_line_and_color_from_the_target_series() -> None:
    plot, store = build_plot_and_store("K02")
    symbol_series = plot.series[1]
    styled_series = symbol_series.model_copy(
        update={
            "style": symbol_series.style.model_copy(
                update={
                    "color": ColorValue(value="#123456"),
                    "marker_size": PhysicalLength(value=8, unit="pt"),
                    "symbol": SymbolStyle(shape="diamond", interior="hollow"),
                }
            )
        }
    )
    styled_plot = plot.model_copy(update={"series": (plot.series[0], styled_series)})

    resolved = PlotResolver().resolve(styled_plot, store)
    layer = next(item for item in resolved.plan.layers if item.target_id == symbol_series.series_id)
    assert layer.color.value == "#123456"
    assert layer.marker_size == PhysicalLength(value=8, unit="pt")
    assert layer.symbol == SymbolStyle(shape="diamond", interior="hollow")
    origin = compile_origin_plan((resolved,), build_origin_export_spec((resolved,)))
    origin_plot = next(
        item
        for graph in origin.graph_objects
        for origin_layer in graph.layers
        for item in origin_layer.plots
        if item.source_layer_id == layer.layer_id
    )
    assert origin_plot.color == ColorValue(value="#123456")
    assert origin_plot.symbol == SymbolStyle(shape="diamond", interior="hollow")


def test_palette_patch_is_compact_and_resolves_once_before_rendering() -> None:
    plot, store = build_plot_and_store("K20")
    patch = SetPalettePatch(
        target_id=plot.series[0].series_id,
        expected_plot_version=plot.plot_version,
        palette_id="Magma",
        reverse=True,
    )
    validate_plot_patch(plot, patch)
    palette = resolve_palette(patch.palette_id, reverse=patch.reverse)
    series = plot.series[0]
    styled = plot.model_copy(
        update={
            "series": (
                series.model_copy(
                    update={"style": series.style.model_copy(update={"palette": palette})}
                ),
            )
        }
    )
    layer = PlotResolver().resolve(styled, store).plan.layers[0]
    assert layer.palette_spec == palette
    assert layer.palette == palette.colors
    resolved = PlotResolver().resolve(styled, store)
    origin = compile_origin_plan((resolved,), build_origin_export_spec((resolved,)))
    assert origin.graph_objects[0].layers[0].plots[0].palette_spec == palette


def test_category_color_patch_changes_only_the_named_category_identity() -> None:
    plot, store = build_plot_and_store("K09")
    patch = SetCategoryColorPatch(
        target_id=plot.series[0].series_id,
        expected_plot_version=plot.plot_version,
        category="G2",
        color=ColorValue(value="#112233"),
    )
    validate_plot_patch(plot, patch)
    series = plot.series[0]
    styled = plot.model_copy(
        update={
            "series": (
                series.model_copy(
                    update={
                        "style": series.style.model_copy(
                            update={"category_colors": {patch.category: patch.color}}
                        )
                    }
                ),
            )
        }
    )

    layers = PlotResolver().resolve(styled, store).plan.layers
    colors_by_label = {
        "".join(node.text for node in layer.label.nodes): layer.color.value
        for layer in layers
        if layer.label is not None
    }

    assert colors_by_label["G2"] == "#112233"
    assert colors_by_label["G1"] != "#112233"


def test_category_encoding_extends_to_the_frozen_15_color_origin_list_without_recycling() -> None:
    resolved = resolve_variant(_grouped_bar_variant(15, category_count=1))
    encodings = tuple((layer.color.value, layer.symbol.shape) for layer in resolved.plan.layers)

    assert len({color for color, _shape in encodings}) == 15
    assert len({shape for _color, shape in encodings}) == 1
    assert {warning.warning_id for warning in resolved.plan.warnings} == {
        "style.category_palette_extended"
    }


def test_category_encoding_uses_unique_color_symbol_pairs_after_15_categories() -> None:
    resolved = resolve_variant(_grouped_bar_variant(16, category_count=1))
    encodings = tuple((layer.color.value, layer.symbol.shape) for layer in resolved.plan.layers)

    assert len(set(encodings)) == 16
    assert len({shape for _color, shape in encodings}) == 2
    assert {warning.warning_id for warning in resolved.plan.warnings} == {
        "style.category_color_symbol_fallback"
    }


def test_category_encoding_fails_instead_of_recycling_after_the_joint_capacity() -> None:
    with pytest.raises(PlotValidationError, match="capacity is 180") as error:
        resolve_variant(_grouped_bar_variant(181, category_count=1))

    assert error.value.code == "STYLE_CATEGORY_CAPACITY_EXCEEDED"


def _sixteen_category_variant(chart_id: str) -> Variant:
    groups = tuple(f"Group {index + 1}" for index in range(16))
    if chart_id in {"X05", "K12"}:
        columns = {"value": tuple(float(index) for index in range(16)), "group": groups}
    elif chart_id == "K14":
        columns = {
            "group": tuple(group for group in groups for _value in range(3)),
            "grid": tuple(value for _group in groups for value in (0.0, 1.0, 2.0)),
            "density": (0.1, 0.8, 0.1) * len(groups),
        }
    elif chart_id == "X38":
        columns = {
            "x": tuple(value for _group in groups for value in (0.0, 1.0)),
            "y": tuple(value for _group in groups for value in (0.0, 1.0)),
            "series": tuple(group for group in groups for _value in range(2)),
        }
    else:
        raise AssertionError(f"unsupported test chart {chart_id}")
    return Variant(f"{chart_id}.categories-16", chart_id, (columns,))


@pytest.mark.parametrize("chart_id", ("X05", "K12", "K14", "X38"))
def test_category_encoding_policy_is_shared_by_non_bar_grouped_geometries(
    chart_id: str,
) -> None:
    resolved = resolve_variant(_sixteen_category_variant(chart_id))
    encoded_layers = tuple(
        layer
        for layer in resolved.plan.layers
        if layer.label is not None and not layer.geometry.endswith("threshold")
    )
    encodings = {(layer.color.value, layer.symbol.shape) for layer in encoded_layers}

    assert len(encoded_layers) == 16
    assert len(encodings) == 16
    assert {warning.warning_id for warning in resolved.plan.warnings} == {
        "style.category_color_symbol_fallback"
    }
