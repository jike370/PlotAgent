from __future__ import annotations

import json

import pytest

from plotagent.charts.registry import CHARTS, ChartRegistryError, get_chart
from plotagent.contracts.base import PhysicalLength
from plotagent.contracts.canonical import canonical_json
from plotagent.contracts.plots import (
    FacetFamily,
    PreparedSeriesData,
    SafeRichText,
    SafeTextNode,
    SeriesSpec,
    SetAxisRangePatch,
)
from plotagent.contracts.rendering import ResolvedLayer
from plotagent.plots.validation import PlotValidationError, validate_plot_patch
from plotagent.rendering import PanelPlan, PlotResolver, RenderDataStore, RenderTable
from plotagent.rendering.matplotlib.adapter import MatplotlibRenderer
from plotagent.rendering.resolver import INTERACTIVE_LIMIT
from tests.contracts.helpers import HASH_A, minimal_plot
from tests.rendering.fixture_factory import resolve_chart


def _line_data(count: int = 4) -> RenderTable:
    return RenderTable.from_columns(
        {
            "field:x": tuple(float(index) for index in range(count)),
            "field:y": tuple(float(index * index + 1) for index in range(count)),
        }
    )


def test_runtime_registry_is_explicit_exact_and_rejects_every_other_id() -> None:
    expected = {
        *(f"K{index:02d}" for index in range(1, 23)),
        "K24",
        "K25",
        "S01",
        "S05",
        "S21",
        "S25",
        "S31",
        "S34",
        "S61",
        "X01",
        "X02",
        "X03",
        "X05",
        "X07",
        "X09",
        "X11",
        "X12",
        "X13",
        "X15",
        "X16",
        "X17",
        "X18",
        "X19",
        "X23",
        "X24",
        "X35",
        "X36",
        "X37",
        "X38",
        "S07",
    }
    assert {entry.chart_type_id for entry in CHARTS} == expected
    assert all(entry.limitations for entry in CHARTS)
    assert all(
        entry.exports.png and entry.exports.svg and entry.exports.opju == "O1" for entry in CHARTS
    )
    assert get_chart("K11").data_modes == ("fixed",)
    assert get_chart("K21").data_modes == ("user_precomputed",)
    assert get_chart("K25").data_modes == ("panel_plans",)
    for rejected in ("K23", "S45", "X04", "K26", "unknown"):
        with pytest.raises(ChartRegistryError):
            get_chart(rejected)


def test_k01_resolved_plan_is_deterministic_and_origin_spike_stable() -> None:
    plot = minimal_plot()
    store = RenderDataStore({HASH_A: _line_data()})
    first = PlotResolver().resolve(plot, store)
    second = PlotResolver().resolve(plot, store)

    assert first.render_plan_hash == second.render_plan_hash
    assert canonical_json(first.plan) == canonical_json(second.plan)
    assert first.plan.chart_type_id == "K01"
    assert first.plan.render_plan_id == "renderplan:test.formal"
    assert first.plan.canvas.width.value == 89.0
    assert first.plan.dpi == 300
    assert [(axis.axis_id, axis.minimum, axis.maximum) for axis in first.plan.axes] == [
        ("axis:x", -0.15000000000000002, 3.15),
        ("axis:y", 0.55, 10.45),
    ]
    layer = first.plan.layers[0]
    assert layer.geometry == "xy.line"
    assert tuple(binding.role for binding in layer.field_bindings) == ("x", "y")
    assert layer.data_source_kind == "direct"
    assert layer.full_row_count == layer.displayed_row_count == 4
    assert first.plan.data_integrity.simplification_applied is False


def test_preview_simplification_keeps_full_data_axis_range_and_formal_count() -> None:
    count = INTERACTIVE_LIMIT + 17
    plot = minimal_plot()
    store = RenderDataStore({HASH_A: _line_data(count)})
    preview = PlotResolver().resolve(plot, store, quality_tier="interactive")
    formal = PlotResolver().resolve(plot, store, quality_tier="formal")

    assert preview.plan.layers[0].full_row_count == count
    assert preview.plan.layers[0].displayed_row_count == INTERACTIVE_LIMIT
    assert preview.plan.data_integrity.simplification_applied is True
    assert (
        formal.plan.layers[0].full_row_count == formal.plan.layers[0].displayed_row_count == count
    )
    assert formal.plan.data_integrity.simplification_applied is False
    assert [(axis.minimum, axis.maximum) for axis in preview.plan.axes] == [
        (axis.minimum, axis.maximum) for axis in formal.plan.axes
    ]


def test_x35_dual_y_columns_keep_explicit_side_by_side_coordinates() -> None:
    resolved = resolve_chart("X35")
    left, right = resolved.plan.layers

    assert left.geometry == right.geometry == "bar.floating"

    def x_values(layer: ResolvedLayer) -> tuple[float, ...]:
        binding = next(item for item in layer.field_bindings if item.role == "x")
        return tuple(float(value) for value in resolved.table_for(layer).column(binding.field_id))

    left_x = x_values(left)
    right_x = x_values(right)
    assert all(
        right_value - left_value == pytest.approx(0.38)
        for left_value, right_value in zip(left_x, right_x, strict=True)
    )


def test_x02_lollipop_stems_and_x_axis_stay_at_zero_when_range_changes() -> None:
    resolved = resolve_chart("X02")

    assert [layer.geometry for layer in resolved.plan.layers] == ["special.lollipop"]
    figure = MatplotlibRenderer().build_figure(resolved)
    axis = figure.axes[0]
    segments = axis.collections[0].get_segments()

    assert segments
    assert all(float(segment[0][1]) == pytest.approx(0.0) for segment in segments)
    assert axis.spines["bottom"].get_position() == ("data", 0.0)


@pytest.mark.parametrize("chart_id", ["X23", "X35", "X36"])
def test_dual_y_matplotlib_frame_does_not_double_paint_the_right_axis(
    chart_id: str,
) -> None:
    figure = MatplotlibRenderer().build_figure(resolve_chart(chart_id))
    left_axis, right_axis = figure.axes
    left_width = left_axis.spines["left"].get_linewidth()

    assert left_axis.spines["right"].get_visible() is False
    assert right_axis.spines["left"].get_visible() is False
    assert right_axis.spines["top"].get_visible() is False
    assert right_axis.spines["bottom"].get_visible() is False
    assert right_axis.spines["right"].get_linewidth() == pytest.approx(left_width)
    assert right_axis.yaxis.label.get_fontweight() == left_axis.yaxis.label.get_fontweight()
    assert all(
        tick.tick1line.get_markeredgewidth() == pytest.approx(left_width)
        for tick in right_axis.yaxis.get_major_ticks()
    )


def test_patch_validation_checks_version_target_log_and_safe_text() -> None:
    plot = minimal_plot()
    assert (
        validate_plot_patch(
            plot,
            SetAxisRangePatch(
                target_id="axis:y",
                expected_plot_version=1,
                minimum=0.0,
                maximum=5.0,
            ),
        ).operation
        == "set_axis_range"
    )
    with pytest.raises(PlotValidationError, match="PATCH_VERSION_CONFLICT"):
        validate_plot_patch(
            plot,
            SetAxisRangePatch(
                target_id="axis:y",
                expected_plot_version=2,
                minimum=0.0,
                maximum=5.0,
            ),
        )


def test_k25_requires_explicit_nonoverlapping_child_plans() -> None:
    child_plot = minimal_plot()
    child = PlotResolver().resolve(child_plot, RenderDataStore({HASH_A: _line_data()}))
    parent = child_plot.model_copy(
        update={
            "plot_id": "plot:k25",
            "chart_type_id": "K25",
            "family": FacetFamily(geometry=("panel",)),
            "series": (
                SeriesSpec(
                    series_id="series:panels",
                    geometry="panel",
                    data=PreparedSeriesData(
                        prepared_dataset_ref=child_plot.prepared_data_refs[0],
                        role_fields=("field:panel",),
                    ),
                ),
            ),
        }
    )
    label_a = SafeRichText(nodes=(SafeTextNode(kind="plain", text="A"),))
    label_b = SafeRichText(nodes=(SafeTextNode(kind="plain", text="B"),))
    resolved = PlotResolver().resolve_panel_plans(
        parent,
        (
            PanelPlan("panel:a", child, 0.1, 0.1, 42.9, 59.8, label_a),
            PanelPlan("panel:b", child, 46.0, 0.1, 42.9, 59.8, label_b),
        ),
    )
    assert resolved.plan.chart_type_id == "K25"
    assert tuple(panel.panel_id for panel in resolved.plan.panels) == ("panel:a", "panel:b")
    assert all(layer.data_source_kind == "panel_plan" for layer in resolved.plan.layers)
    assert len(resolved.plan.annotations) == 2

    with pytest.raises(PlotValidationError, match="cannot overlap"):
        PlotResolver().resolve_panel_plans(
            parent,
            (
                PanelPlan("panel:a", child, 0.1, 0.1, 50.0, 59.8, label_a),
                PanelPlan("panel:b", child, 40.0, 0.1, 48.9, 59.8, label_b),
            ),
        )


def test_resolved_plan_json_contains_no_renderer_commands_or_paths() -> None:
    resolved = PlotResolver().resolve(minimal_plot(), RenderDataStore({HASH_A: _line_data()}))
    payload = json.loads(resolved.plan.model_dump_json())
    assert payload["resolver_version"] == "resolver.v1"
    keys: list[str] = []

    def collect_keys(value: object) -> None:
        if isinstance(value, dict):
            keys.extend(str(key).lower() for key in value)
            for item in value.values():
                collect_keys(item)
        elif isinstance(value, list):
            for item in value:
                collect_keys(item)

    collect_keys(payload)
    assert "path" not in keys
    assert all(font["size"]["unit"] == "pt" for font in payload["fonts"])
    assert PhysicalLength(value=1.0, unit="mm").unit == "mm"
