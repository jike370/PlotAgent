"""Deterministic generalization gates for the existing v1 rendering pipeline.

The case data and expected structural invariants in this module are independent
of resolver output.  Do not derive these cases from resolved geometry: changing
the resolver must not silently rewrite its own oracle.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from matplotlib.figure import Figure

from plotagent.charts.registry import CHARTS, ChartAdapterRegistration
from plotagent.contracts.base import ColorValue
from plotagent.contracts.plots import (
    CalculatedSeriesData,
    PlotSpec,
    PrecomputedSeriesData,
    PreparedSeriesData,
    SeriesData,
)
from plotagent.exports import export_png, export_svg
from plotagent.rendering import PlotResolver, RenderDataStore, RenderTable, ResolvedPlot
from plotagent.rendering.data import Scalar
from plotagent.rendering.matplotlib.adapter import MatplotlibRenderer
from tests.rendering.fixture_factory import build_plot_and_store, resolve_chart

# Frozen for reproducibility.  The current generators are arithmetic rather than
# stochastic; retaining an explicit seed prevents future randomization from being
# introduced without changing the test-data contract.
GENERALIZATION_SEED = 20260806


@dataclass(frozen=True, slots=True)
class Variant:
    case_id: str
    chart_id: str
    series_columns: tuple[Mapping[str, Sequence[object]], ...]


def _binding_hash(data: SeriesData) -> str:
    if isinstance(data, PreparedSeriesData):
        return data.prepared_dataset_ref.content_hash
    if isinstance(data, CalculatedSeriesData):
        return data.calculation_result_ref.content_hash
    assert isinstance(data, PrecomputedSeriesData)
    return data.precomputed_data_ref.data_ref_hash


def _replace_series_table(
    plot: PlotSpec,
    series_index: int,
    columns: Mapping[str, Sequence[object]],
) -> tuple[PlotSpec, str, RenderTable]:
    series = plot.series[series_index]
    field_ids = tuple(
        f"field:generalization.{plot.chart_type_id.lower()}.{series_index}.{role}"
        for role in columns
    )
    table = RenderTable.from_columns(dict(zip(field_ids, columns.values(), strict=True)))
    data = series.data

    prepared_replacements: dict[str, object] = {}
    calculation_replacements: dict[str, object] = {}
    precomputed_replacements: dict[str, object] = {}
    if isinstance(data, PreparedSeriesData):
        old_ref = data.prepared_dataset_ref
        new_ref = old_ref.model_copy(update={"content_hash": table.object_hash})
        updated_data: SeriesData = data.model_copy(
            update={"prepared_dataset_ref": new_ref, "role_fields": field_ids}
        )
        prepared_replacements[old_ref.prepared_dataset_id] = new_ref
    elif isinstance(data, CalculatedSeriesData):
        old_ref = data.calculation_result_ref
        new_ref = old_ref.model_copy(update={"content_hash": table.object_hash})
        updated_data = data.model_copy(
            update={"calculation_result_ref": new_ref, "role_fields": field_ids}
        )
        calculation_replacements[old_ref.calculation_id] = new_ref
    else:
        old_ref = data.precomputed_data_ref
        new_ref = old_ref.model_copy(
            update={"data_ref_hash": table.object_hash, "field_ids": field_ids}
        )
        updated_data = data.model_copy(
            update={"precomputed_data_ref": new_ref, "role_fields": field_ids}
        )
        precomputed_replacements[old_ref.precomputed_id] = new_ref

    updated_series = list(plot.series)
    updated_series[series_index] = series.model_copy(update={"data": updated_data})
    updated_plot = plot.model_copy(
        update={
            "series": tuple(updated_series),
            "prepared_data_refs": tuple(
                prepared_replacements.get(ref.prepared_dataset_id, ref)
                for ref in plot.prepared_data_refs
            ),
            "plot_calculation_refs": tuple(
                calculation_replacements.get(ref.calculation_id, ref)
                for ref in plot.plot_calculation_refs
            ),
            "precomputed_data_refs": tuple(
                precomputed_replacements.get(ref.precomputed_id, ref)
                for ref in plot.precomputed_data_refs
            ),
        }
    )
    return updated_plot, _binding_hash(updated_data), table


def resolve_variant(variant: Variant) -> ResolvedPlot:
    plot, base_store = build_plot_and_store(variant.chart_id)
    if len(variant.series_columns) != len(plot.series):
        raise AssertionError(f"{variant.case_id} does not supply every series")
    tables = dict(base_store.tables)
    for index, columns in enumerate(variant.series_columns):
        old_hash = _binding_hash(plot.series[index].data)
        plot, new_hash, table = _replace_series_table(plot, index, columns)
        tables.pop(old_hash, None)
        tables[new_hash] = table
    return PlotResolver().resolve(plot, RenderDataStore(tables))


def _grouped_bar_variant(group_count: int, category_count: int = 4) -> Variant:
    categories = tuple(f"Category {index + 1}" for index in range(category_count))
    groups = tuple(f"Group {index + 1}" for index in range(group_count))
    category_column = tuple(category for category in categories for _group in groups)
    group_column = groups * category_count
    values = tuple(
        float((category_index + 1) * 3 + group_index - 2)
        for category_index in range(category_count)
        for group_index in range(group_count)
    )
    return Variant(
        case_id=f"K09.groups-{group_count}.categories-{category_count}",
        chart_id="K09",
        series_columns=(
            {"category": category_column, "group": group_column, "value": values},
        ),
    )


GROUPED_BAR_VARIANTS = tuple(_grouped_bar_variant(count) for count in (1, 2, 3, 5)) + (
    _grouped_bar_variant(3, 1),
    _grouped_bar_variant(3, 12),
)


def _stack_variant(component_count: int) -> Variant:
    categories = ("Alpha", "Beta", "Gamma")
    components = tuple(f"Part {index + 1}" for index in range(component_count))
    # Frozen values alternate sign and intentionally arrive category-major.  The
    # expected accumulator below is separately specified as positive/negative.
    values = tuple(
        float((category_index + 2) * (component_index + 1))
        * (-1.0 if component_index % 3 == 1 else 1.0)
        for category_index in range(len(categories))
        for component_index in range(component_count)
    )
    return Variant(
        case_id=f"K10.components-{component_count}.cross-zero",
        chart_id="K10",
        series_columns=(
            {
                "category": tuple(category for category in categories for _ in components),
                "component": components * len(categories),
                "value": values,
            },
        ),
    )


STACK_VARIANTS = tuple(_stack_variant(count) for count in (1, 2, 3, 5))


def _percent_stack_variant(component_count: int) -> Variant:
    categories = ("Alpha", "Beta", "Gamma")
    components = tuple(f"Part {index + 1}" for index in range(component_count))
    weights = tuple(float(index + 1) for index in range(component_count))
    total = sum(weights)
    fractions = tuple(value / total for value in weights)
    return Variant(
        case_id=f"K11.components-{component_count}",
        chart_id="K11",
        series_columns=(
            {
                "category": tuple(category for category in categories for _ in components),
                "component": components * len(categories),
                "value": fractions * len(categories),
            },
        ),
    )


PERCENT_STACK_VARIANTS = tuple(_percent_stack_variant(count) for count in (1, 2, 3, 5))


ERROR_VARIANTS = (
    Variant(
        "K08.error-zero",
        "K08",
        (
            {
                "category": ("A", "B", "C"),
                "value": (0.0, 4.0, -3.0),
                "lower": (0.0, 4.0, -3.0),
                "upper": (0.0, 4.0, -3.0),
            },
        ),
    ),
    Variant(
        "K08.error-symmetric",
        "K08",
        (
            {
                "category": ("A", "B", "C"),
                "value": (-10.0, 0.0, 25.0),
                "lower": (-12.0, -1.5, 20.0),
                "upper": (-8.0, 1.5, 30.0),
            },
        ),
    ),
    Variant(
        "K08.error-asymmetric",
        "K08",
        (
            {
                "category": ("A", "B", "C"),
                "value": (-1_000_000.0, 2_000_000.0, 5_000_000.0),
                "lower": (-1_600_000.0, 1_900_000.0, 2_000_000.0),
                "upper": (-900_000.0, 3_000_000.0, 8_500_000.0),
            },
        ),
    ),
)


AFFINE_LINE_VARIANTS = (
    Variant("K01.points-1", "K01", ({"x": (0.0,), "y": (-7.0,)},)),
    Variant("K01.points-2", "K01", ({"x": (-2.0, 8.0), "y": (-5.0, 10.0)},)),
    Variant(
        "K01.points-101.small-scale",
        "K01",
        (
            {
                "x": tuple(index * 1e-7 for index in range(101)),
                "y": tuple(-2e-6 + index * 4e-8 for index in range(101)),
            },
        ),
    ),
    Variant(
        "K01.points-101.large-offset",
        "K01",
        (
            {
                "x": tuple(1e9 + index * 1e5 for index in range(101)),
                "y": tuple(-8e11 + index * 2e9 for index in range(101)),
            },
        ),
    ),
)


OPTIONAL_ROLE_VARIANTS = (
    Variant(
        "K04.xy-only",
        "K04",
        ({"x": (-1.0, 0.0, 1.0), "y": (2.0, -3.0, 4.0)},),
    ),
    Variant(
        "K04.with-size",
        "K04",
        ({"x": (-1.0, 0.0, 1.0), "y": (2.0, -3.0, 4.0), "size": (0.0, 2.0, 9.0)},),
    ),
    Variant(
        "K06.symmetric-error",
        "K06",
        ({"x": (1.0, 2.0, 3.0), "center": (-2.0, 0.0, 5.0), "error": (0.0, 1.0, 2.5)},),
    ),
    Variant(
        "K12.no-group",
        "K12",
        ({"value": (-4.0, -1.0, 0.0, 3.0, 9.0)},),
    ),
    Variant(
        "K13.no-group",
        "K13",
        (
            {
                "q1": (-3.0,),
                "median": (-1.0,),
                "q3": (2.0,),
                "whisker_low": (-7.0,),
                "whisker_high": (6.0,),
            },
        ),
    ),
    Variant(
        "K14.no-group",
        "K14",
        ({"grid": (-3.0, -1.0, 1.0, 3.0), "density": (0.0, 0.8, 0.8, 0.0)},),
    ),
    Variant(
        "K16.with-three-groups",
        "K16",
        (
            {
                "grid": (0.0, 1.0, 2.0) * 3,
                "density": (0.1, 0.8, 0.1, 0.2, 0.6, 0.2, 0.3, 0.4, 0.3),
                "group": ("G1",) * 3 + ("G2",) * 3 + ("G3",) * 3,
            },
        ),
    ),
    Variant(
        "K17.with-five-groups",
        "K17",
        (
            {
                "x": tuple(float(index) for _group in range(5) for index in range(4)),
                "probability": (0.25, 0.5, 0.75, 1.0) * 5,
                "group": tuple(f"G{group + 1}" for group in range(5) for _ in range(4)),
            },
        ),
    ),
)


LONG_LABEL_VARIANT = Variant(
    "K09.long-labels",
    "K09",
    (
        {
            "category": (
                "Untreated control sample",
                "Untreated control sample",
                "Low-dose treatment cohort",
                "Low-dose treatment cohort",
                "High-dose treatment cohort",
                "High-dose treatment cohort",
            ),
            "group": ("Baseline", "Follow-up") * 3,
            "value": (2.0, 2.4, 3.0, 3.8, 5.0, 4.2),
        },
    ),
)


def _matrix_variant(chart_id: str, row_count: int, column_count: int) -> Variant:
    rows = tuple(f"Row {index + 1}" for index in range(row_count))
    columns = tuple(f"Column {index + 1}" for index in range(column_count))
    if chart_id == "K20":
        role_columns: Mapping[str, Sequence[object]] = {
            "row": tuple(row for row in rows for _ in columns),
            "column": columns * len(rows),
            "value": tuple(
                float((row_index - 1) * 10 + column_index)
                for row_index in range(row_count)
                for column_index in range(column_count)
            ),
        }
    else:
        x = tuple(float(index) for index in range(column_count))
        y = tuple(float(index) for index in range(row_count))
        role_columns = {
            "x": tuple(value for _y in y for value in x),
            "y": tuple(value for value in y for _x in x),
            "z": tuple(
                float((row_index - 1) ** 2 - column_index * 0.5)
                for row_index in range(row_count)
                for column_index in range(column_count)
            ),
        }
    return Variant(
        case_id=f"{chart_id}.grid-{row_count}x{column_count}",
        chart_id=chart_id,
        series_columns=(role_columns,),
    )


MATRIX_VARIANTS = (
    _matrix_variant("K20", 1, 1),
    _matrix_variant("K20", 3, 5),
    _matrix_variant("K20", 10, 12),
    _matrix_variant("K22", 2, 2),
    _matrix_variant("K22", 4, 5),
)


def _variadic_series_variant(
    chart_id: str,
    series_count: int,
    *,
    row_count: int = 5,
) -> Variant:
    columns: dict[str, Sequence[object]] = {}
    if chart_id == "X03":
        columns["category"] = tuple(f"Sample {index + 1}" for index in range(row_count))
    for series_index in range(series_count):
        columns[f"series_{series_index + 1}"] = tuple(
            float((row_index + 1) * (series_index + 2) + (series_index % 2) * 0.5)
            for row_index in range(row_count)
        )
    return Variant(
        case_id=f"{chart_id}.series-{series_count}.rows-{row_count}",
        chart_id=chart_id,
        series_columns=(columns,),
    )


VARIADIC_SERIES_VARIANTS = (
    _variadic_series_variant("X03", 2),
    _variadic_series_variant("X03", 4, row_count=7),
    _variadic_series_variant("X39", 2),
    _variadic_series_variant("X39", 5, row_count=7),
    _variadic_series_variant("X40", 2),
    _variadic_series_variant("X40", 4, row_count=7),
    _variadic_series_variant("X40", 5),
)


def _roles(resolved: ResolvedPlot, layer_index: int) -> dict[str, tuple[Scalar, ...]]:
    layer = resolved.plan.layers[layer_index]
    table = resolved.table_for(layer)
    return {
        binding.role: table.column(binding.field_id) for binding in layer.field_bindings
    }


def _float_values(values: Sequence[Scalar]) -> tuple[float, ...]:
    return tuple(float(value) for value in values)


def _assert_matplotlib_draws(resolved: ResolvedPlot) -> Figure:
    figure = MatplotlibRenderer().build_figure(resolved)
    figure.canvas.draw()
    assert figure.axes
    assert all(
        math.isfinite(value)
        for axis in figure.axes
        for value in (*axis.get_xlim(), *axis.get_ylim())
    )
    return figure


def _axis_for(resolved: ResolvedPlot, panel_id: str, orientation: str) -> tuple[float, float]:
    axis = next(
        item
        for item in resolved.plan.axes
        if item.panel_id == panel_id and item.orientation == orientation
    )
    return cast(float, axis.minimum), cast(float, axis.maximum)


def _visible_extents(
    geometry: str, roles: Mapping[str, tuple[Scalar, ...]]
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    if geometry.startswith(("xy.", "facet.")):
        x_role = next(
            role
            for role in ("x", "time", "dose", "spectral_axis", "angle", "z_real")
            if role in roles
        )
        y_roles = tuple(
            role
            for role in (
                "y",
                "center",
                "value",
                "response",
                "intensity",
                "z_imaginary",
                "lower",
                "upper",
            )
            if role in roles
        )
        return _float_values(roles[x_role]), tuple(
            value for role in y_roles for value in _float_values(roles[role])
        )
    if geometry == "bar.horizontal":
        half_heights = tuple(value / 2 for value in _float_values(roles["height"]))
        y = _float_values(roles["y"])
        return (
            _float_values(roles["left"]) + _float_values(roles["right"]),
            tuple(value - half for value, half in zip(y, half_heights, strict=True))
            + tuple(value + half for value, half in zip(y, half_heights, strict=True)),
        )
    if geometry.startswith("bar."):
        x = _float_values(roles["x"])
        half_width = tuple(value / 2 for value in _float_values(roles["width"]))
        x_extents = tuple(value - half for value, half in zip(x, half_width, strict=True)) + tuple(
            value + half for value, half in zip(x, half_width, strict=True)
        )
        y_roles = tuple(role for role in ("bottom", "top", "lower", "upper") if role in roles)
        return x_extents, tuple(
            value for role in y_roles for value in _float_values(roles[role])
        )
    if geometry == "distribution.strip":
        return _float_values(roles["x"]), _float_values(roles["y"])
    if geometry == "distribution.box":
        return _float_values(roles["group"]), tuple(
            value
            for role in ("q1", "median", "q3", "whisker_low", "whisker_high")
            for value in _float_values(roles[role])
        )
    if geometry == "distribution.violin":
        x = _float_values(roles["x"])
        half_width = _float_values(roles["half_width"])
        return (
            tuple(value - half for value, half in zip(x, half_width, strict=True))
            + tuple(value + half for value, half in zip(x, half_width, strict=True)),
            _float_values(roles["y"]),
        )
    if geometry == "distribution.histogram":
        return (
            _float_values(roles["left"]) + _float_values(roles["right"]),
            (0.0,) + _float_values(roles["height"]),
        )
    if geometry == "distribution.density":
        return _float_values(roles["grid"]), _float_values(roles["density"])
    if geometry == "distribution.step":
        return _float_values(roles["x"]), _float_values(roles["probability"])
    if geometry.startswith("matrix."):
        x_role = next(
            role for role in ("column", "column_label", "x", "predicted") if role in roles
        )
        y_role = next(role for role in ("row", "row_label", "y", "actual") if role in roles)
        return _float_values(roles[x_role]), _float_values(roles[y_role])
    if geometry == "special.drop_line":
        return _float_values(roles["x"]), _float_values(roles["y"])
    if geometry == "special.lollipop":
        value_roles = tuple(role for role in roles if role.startswith("series_"))
        return (
            tuple(value for role in value_roles for value in _float_values(roles[role])),
            tuple(float(index) for index, _ in enumerate(roles["category"])),
        )
    if geometry in {"special.survival_step", "special.survival_band"}:
        y_roles = tuple(role for role in ("survival", "lower", "upper") if role in roles)
        return _float_values(roles["time"]), tuple(
            value for role in y_roles for value in _float_values(roles[role])
        )
    if geometry in {"special.forest_interval", "special.forest_symbol"}:
        x_roles = tuple(role for role in ("effect", "lower", "upper") if role in roles)
        return (
            tuple(value for role in x_roles for value in _float_values(roles[role])),
            _float_values(roles["label"]),
        )
    if geometry == "special.risk_table":
        return (), ()
    raise AssertionError(f"missing test extent rules for {geometry}")


@pytest.mark.parametrize("entry", CHARTS, ids=lambda entry: entry.chart_type_id)
def test_every_chart_resolves_deterministically_with_finite_geometry(
    entry: ChartAdapterRegistration,
) -> None:
    chart_id = cast(str, entry.chart_type_id)
    first = resolve_chart(chart_id)
    second = resolve_chart(chart_id)

    assert first.render_plan_hash == second.render_plan_hash
    assert first.plan == second.plan
    assert first.plan.data_integrity.nonfinite_values == 0
    for table in first.tables.values():
        for column in table.columns.values():
            assert all(not isinstance(value, float) or math.isfinite(value) for value in column)
    _assert_matplotlib_draws(first)


@pytest.mark.parametrize("entry", CHARTS, ids=lambda entry: entry.chart_type_id)
def test_every_chart_axis_range_covers_all_visible_data_geometry(
    entry: ChartAdapterRegistration,
) -> None:
    resolved = resolve_chart(cast(str, entry.chart_type_id))
    for layer_index, layer in enumerate(resolved.plan.layers):
        x_values, y_values = _visible_extents(layer.geometry, _roles(resolved, layer_index))
        if not x_values and not y_values:
            continue
        x_minimum, x_maximum = _axis_for(resolved, layer.panel_id, "x")
        y_minimum, y_maximum = _axis_for(resolved, layer.panel_id, "y")
        assert x_minimum <= min(x_values) <= max(x_values) <= x_maximum
        assert y_minimum <= min(y_values) <= max(y_values) <= y_maximum


@pytest.mark.parametrize("variant", AFFINE_LINE_VARIANTS, ids=lambda item: item.case_id)
def test_line_affine_and_point_count_variants_are_finite_and_in_range(variant: Variant) -> None:
    resolved = resolve_variant(variant)
    roles = _roles(resolved, 0)
    x_axis, y_axis = resolved.plan.axes

    assert min(_float_values(roles["x"])) >= cast(float, x_axis.minimum)
    assert max(_float_values(roles["x"])) <= cast(float, x_axis.maximum)
    assert min(_float_values(roles["y"])) >= cast(float, y_axis.minimum)
    assert max(_float_values(roles["y"])) <= cast(float, y_axis.maximum)
    _assert_matplotlib_draws(resolved)


@pytest.mark.parametrize("variant", GROUPED_BAR_VARIANTS, ids=lambda item: item.case_id)
def test_grouped_bar_intervals_never_overlap(variant: Variant) -> None:
    resolved = resolve_variant(variant)
    intervals_by_category: dict[int, list[tuple[float, float]]] = {}
    for layer_index, layer in enumerate(resolved.plan.layers):
        roles = _roles(resolved, layer_index)
        assert layer.geometry == "bar.grouped"
        for x, width in zip(_float_values(roles["x"]), _float_values(roles["width"]), strict=True):
            category = round(x)
            intervals_by_category.setdefault(category, []).append((x - width / 2, x + width / 2))

    expected_group_count = len({str(value) for value in variant.series_columns[0]["group"]})
    assert len(resolved.plan.layers) == expected_group_count
    assert resolved.plan.legend.visible is (expected_group_count > 1)
    for intervals in intervals_by_category.values():
        ordered = sorted(intervals)
        assert len(ordered) == expected_group_count
        assert all(
            left[1] <= right[0] + 1e-12
            for left, right in zip(ordered, ordered[1:], strict=False)
        )
    _assert_matplotlib_draws(resolved)


def test_grouped_bar_colors_are_stable_when_more_groups_are_added() -> None:
    expected = ("#2A6FDB", "#D64545", "#2A9D6F", "#E69F00", "#7B61A8")
    for variant in GROUPED_BAR_VARIANTS[:4]:
        resolved = resolve_variant(variant)
        group_count = len(resolved.plan.layers)
        actual = tuple(cast(ColorValue, layer.color).value for layer in resolved.plan.layers)
        assert actual == expected[:group_count]


@pytest.mark.parametrize("variant", STACK_VARIANTS, ids=lambda item: item.case_id)
def test_stacked_bar_uses_independent_positive_and_negative_accumulators(
    variant: Variant,
) -> None:
    resolved = resolve_variant(variant)
    positive: dict[int, float] = {}
    negative: dict[int, float] = {}

    for layer_index, layer in enumerate(resolved.plan.layers):
        roles = _roles(resolved, layer_index)
        assert layer.geometry == "bar.stacked"
        for x, height, bottom, top in zip(
            _float_values(roles["x"]),
            _float_values(roles["height"]),
            _float_values(roles["bottom"]),
            _float_values(roles["top"]),
            strict=True,
        ):
            category = round(x)
            expected_bottom = (
                positive.get(category, 0.0) if height >= 0 else negative.get(category, 0.0)
            )
            assert bottom == pytest.approx(expected_bottom)
            assert top == pytest.approx(bottom + height)
            if height >= 0:
                positive[category] = top
            else:
                negative[category] = top

    y_axis = next(axis for axis in resolved.plan.axes if axis.orientation == "y")
    assert cast(float, y_axis.minimum) <= min((0.0, *negative.values()))
    assert cast(float, y_axis.maximum) >= max((0.0, *positive.values()))
    _assert_matplotlib_draws(resolved)


@pytest.mark.parametrize("variant", PERCENT_STACK_VARIANTS, ids=lambda item: item.case_id)
def test_percent_stacks_end_at_one_for_every_category(variant: Variant) -> None:
    resolved = resolve_variant(variant)
    totals: dict[int, float] = {}
    for layer_index, layer in enumerate(resolved.plan.layers):
        roles = _roles(resolved, layer_index)
        assert layer.geometry == "bar.percent"
        for x, height, bottom, top in zip(
            _float_values(roles["x"]),
            _float_values(roles["height"]),
            _float_values(roles["bottom"]),
            _float_values(roles["top"]),
            strict=True,
        ):
            category = round(x)
            assert bottom == pytest.approx(totals.get(category, 0.0))
            assert top == pytest.approx(bottom + height)
            totals[category] = top
    assert totals
    assert all(total == pytest.approx(1.0) for total in totals.values())
    _assert_matplotlib_draws(resolved)


@pytest.mark.parametrize("variant", ERROR_VARIANTS, ids=lambda item: item.case_id)
def test_bar_error_bounds_are_attached_and_included_in_axis_range(variant: Variant) -> None:
    resolved = resolve_variant(variant)
    roles = _roles(resolved, 0)
    center = tuple(
        bottom + height
        for bottom, height in zip(
            _float_values(roles["bottom"]), _float_values(roles["height"]), strict=True
        )
    )
    lower = _float_values(roles["lower"])
    upper = _float_values(roles["upper"])
    y_axis = next(axis for axis in resolved.plan.axes if axis.orientation == "y")

    assert all(low <= value <= high for low, value, high in zip(lower, center, upper, strict=True))
    assert cast(float, y_axis.minimum) <= min(0.0, *lower)
    assert cast(float, y_axis.maximum) >= max(0.0, *upper)
    _assert_matplotlib_draws(resolved)


@pytest.mark.parametrize("variant", MATRIX_VARIANTS, ids=lambda item: item.case_id)
def test_matrix_grid_dimensions_and_palette_range_are_data_driven(variant: Variant) -> None:
    resolved = resolve_variant(variant)
    layer = resolved.plan.layers[0]
    roles = _roles(resolved, 0)
    x_role = "column" if variant.chart_id == "K20" else "x"
    y_role = "row" if variant.chart_id == "K20" else "y"
    value_role = "value" if variant.chart_id == "K20" else "z"
    x = _float_values(roles[x_role])
    y = _float_values(roles[y_role])
    values = _float_values(roles[value_role])

    assert len(x) == len(set(x)) * len(set(y))
    assert len(set(zip(x, y, strict=True))) == len(x)
    assert layer.color_minimum == min(values)
    assert layer.color_maximum == max(values)
    assert len(layer.palette) >= 5
    if variant.chart_id == "K22":
        assert len(layer.levels) == 7
    _assert_matplotlib_draws(resolved)


@pytest.mark.parametrize(
    "variant",
    VARIADIC_SERIES_VARIANTS,
    ids=lambda item: item.case_id,
)
def test_variadic_series_geometry_tracks_rows_columns_and_pairs(variant: Variant) -> None:
    resolved = resolve_variant(variant)
    columns = variant.series_columns[0]
    value_roles = tuple(role for role in columns if role.startswith("series_"))
    row_count = len(columns[value_roles[0]])
    lines = [layer for layer in resolved.plan.layers if layer.geometry == "xy.line"]
    symbols = [layer for layer in resolved.plan.layers if layer.geometry == "xy.symbol"]

    assert len(symbols) == len(value_roles)
    assert len({layer.layer_id for layer in symbols}) == len(value_roles)
    assert all(layer.label is not None for layer in symbols)
    if variant.chart_id in {"X03", "X39"}:
        assert len(lines) == row_count
        expected_points_per_line = len(value_roles)
    else:
        assert len(lines) == row_count * (len(value_roles) // 2)
        expected_points_per_line = 2

    for layer_index, layer in enumerate(resolved.plan.layers):
        if layer.geometry != "xy.line":
            continue
        roles = _roles(resolved, layer_index)
        assert len(roles["x"]) == expected_points_per_line
        assert len(roles["y"]) == expected_points_per_line
    if variant.chart_id == "X40" and len(value_roles) % 2:
        # The unmatched last column is intentionally displayed as symbols only.
        assert symbols[-1].label is not None

    _assert_matplotlib_draws(resolved)


@pytest.mark.parametrize("variant", OPTIONAL_ROLE_VARIANTS, ids=lambda item: item.case_id)
def test_optional_field_signatures_resolve_and_render(variant: Variant) -> None:
    resolved = resolve_variant(variant)

    assert resolved.plan.layers
    assert resolved.plan.data_integrity.excluded_rows == 0
    _assert_matplotlib_draws(resolved)


def test_symmetric_error_is_resolved_to_explicit_lower_and_upper_bounds() -> None:
    variant = next(item for item in OPTIONAL_ROLE_VARIANTS if item.case_id == "K06.symmetric-error")
    resolved = resolve_variant(variant)
    roles = _roles(resolved, 0)

    assert "error" not in roles
    assert _float_values(roles["lower"]) == pytest.approx((-2.0, -1.0, 2.5))
    assert _float_values(roles["upper"]) == pytest.approx((-2.0, 1.0, 7.5))


def test_missing_rows_are_excluded_before_axis_and_renderer_resolution() -> None:
    variant = Variant(
        "K01.missing-rows",
        "K01",
        (
            {
                "x": (0.0, 1.0, None, 3.0, 4.0),
                "y": (1.0, None, 3.0, 4.0, 5.0),
            },
        ),
    )
    resolved = resolve_variant(variant)
    roles = _roles(resolved, 0)

    assert roles["x"] == (0.0, 3.0, 4.0)
    assert roles["y"] == (1.0, 4.0, 5.0)
    assert resolved.plan.data_integrity.total_rows == 5
    assert resolved.plan.data_integrity.visible_rows == 3
    assert resolved.plan.data_integrity.excluded_rows == 2
    _assert_matplotlib_draws(resolved)


@pytest.mark.parametrize("value", (math.nan, math.inf, -math.inf))
def test_nonfinite_values_cannot_enter_content_addressed_render_tables(value: float) -> None:
    with pytest.raises(ValueError, match="Out of range float values"):
        RenderTable.from_columns({"field:x": (0.0, value)})


def test_long_categorical_labels_are_preserved_and_trigger_readable_rotation() -> None:
    resolved = resolve_variant(LONG_LABEL_VARIANT)
    x_axis = next(axis for axis in resolved.plan.axes if axis.orientation == "x")
    expected = tuple(
        dict.fromkeys(
            str(value) for value in LONG_LABEL_VARIANT.series_columns[0]["category"]
        )
    )
    actual = tuple("".join(node.text for node in tick.label.nodes) for tick in x_axis.ticks)
    figure = _assert_matplotlib_draws(resolved)

    assert actual == expected
    assert all(
        label.get_rotation() == pytest.approx(30.0)
        for label in figure.axes[0].get_xticklabels()
    )


@pytest.mark.parametrize(
    "variant",
    (GROUPED_BAR_VARIANTS[0], GROUPED_BAR_VARIANTS[2], GROUPED_BAR_VARIANTS[3])
    + STACK_VARIANTS[1:]
    + ERROR_VARIANTS
    + (LONG_LABEL_VARIANT,),
    ids=lambda item: item.case_id,
)
def test_representative_generalizations_export_png_and_svg(
    variant: Variant, tmp_path: Path
) -> None:
    resolved = resolve_variant(variant)
    png_path = tmp_path / f"{variant.case_id}.png"
    svg_path = tmp_path / f"{variant.case_id}.svg"

    png = export_png(png_path, resolved)
    svg = export_svg(svg_path, resolved)

    assert png.render_plan_hash == svg.render_plan_hash == resolved.render_plan_hash
    assert svg.element_counts.get("image", 0) == 0
