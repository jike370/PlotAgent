from __future__ import annotations

import math
from collections.abc import Sequence
from typing import cast

import pytest

from plotagent.contracts.base import PreparedDatasetRef
from plotagent.contracts.calculations import (
    CalculationResultBase,
    ConfusionCountSpec,
    DensityKDESpec,
    ECDFSpec,
    HistogramBinningSpec,
    MatrixProjectionSpec,
    PercentStackSpec,
    SummaryErrorSpec,
    TukeyBoxSpec,
    ViolinKDESpec,
)
from plotagent.contracts.canonical import canonical_hash
from plotagent.plot_calculations import (
    ALGORITHM_VERSION,
    PlotCalculationError,
    PlotCalculationInput,
    calculate_plot,
    deterministic_jitter,
)

BUILD_HASH = "f" * 64
PREPARED_HASH = "a" * 64


def prepared_ref() -> PreparedDatasetRef:
    return PreparedDatasetRef(
        prepared_dataset_id="prepared:golden",
        prepared_version=1,
        content_hash=PREPARED_HASH,
    )


def row_ids(count: int) -> tuple[str, ...]:
    return tuple(f"row:{index + 1}" for index in range(count))


def data(
    columns: dict[str, Sequence[object]], *, matrix: Sequence[Sequence[object]] | None = None
) -> PlotCalculationInput:
    count = len(next(iter(columns.values()))) if columns else len(matrix or ())
    return PlotCalculationInput(row_ids=row_ids(count), columns=columns, matrix=matrix)


def records(result: CalculationResultBase) -> list[dict[str, object]]:
    return [
        dict(zip(result.output_table.field_ids, row, strict=True))
        for row in result.output_table.rows
    ]


def test_histogram_fd_sturges_and_constant_goldens() -> None:
    fd_spec = HistogramBinningSpec(
        calculation_id="plotcalc:hist-fd",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        value_field="field:value",
    )
    fd = calculate_plot(
        fd_spec,
        data({"field:value": tuple(range(8))}),
        producer_build_hash=BUILD_HASH,
    )
    assert fd.binning_rule == "freedman_diaconis"
    assert fd.bin_count == 2
    assert fd.output_table.rows == (
        (0, 0.0, 3.5, 1.75, 4, 4),
        (1, 3.5, 7.0, 5.25, 4, 4),
    )

    sturges = calculate_plot(
        fd_spec.model_copy(update={"calculation_id": "plotcalc:hist-sturges"}),
        data({"field:value": (0, 0, 0, 0, 1)}),
        producer_build_hash=BUILD_HASH,
    )
    assert sturges.binning_rule == "sturges"
    assert sturges.bin_count == 4
    assert [row[4] for row in sturges.output_table.rows] == [4, 0, 0, 1]
    assert [row[1] for row in sturges.output_table.rows] == [0.0, 0.25, 0.5, 0.75]

    constant = calculate_plot(
        fd_spec.model_copy(update={"calculation_id": "plotcalc:hist-constant"}),
        data({"field:value": (5, 5, 5)}),
        producer_build_hash=BUILD_HASH,
    )
    assert constant.binning_rule == "constant"
    assert constant.output_table.rows == ((0, 4.5, 5.5, 5.0, 3, 3),)


def test_histogram_density_missing_report_and_log10_block() -> None:
    spec = HistogramBinningSpec(
        calculation_id="plotcalc:hist-missing",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="exclude_with_report",
        value_field="field:value",
        normalization="density",
    )
    result = calculate_plot(
        spec,
        data({"field:value": (0, None, float("nan"), float("inf"), float("-inf"), 1)}),
        producer_build_hash=BUILD_HASH,
    )
    assert result.included_row_ids == ("row:1", "row:6")
    assert tuple((item.row_id, item.reason) for item in result.exclusions) == (
        ("row:2", "missing"),
        ("row:3", "nan"),
        ("row:4", "positive_inf"),
        ("row:5", "negative_inf"),
    )
    assert result.nonfinite_counts.model_dump() == {
        "missing": 1,
        "nan": 1,
        "positive_inf": 1,
        "negative_inf": 1,
    }
    assert sum(
        cast(float, row[5]) * (cast(float, row[2]) - cast(float, row[1]))
        for row in result.output_table.rows
    ) == pytest.approx(1.0)

    log_spec = spec.model_copy(update={"log10_fields": ("field:value",)})
    with pytest.raises(PlotCalculationError) as raised:
        calculate_plot(
            log_spec,
            data({"field:value": (1, 0, 10)}),
            producer_build_hash=BUILD_HASH,
        )
    assert raised.value.code == "PLOTSPEC_CALCULATION_LOG10_NONPOSITIVE"


def test_tukey_linear_quantile_whiskers_and_outlier_row_reference() -> None:
    spec = TukeyBoxSpec(
        calculation_id="plotcalc:box",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        value_field="field:value",
    )
    result = calculate_plot(
        spec,
        data({"field:value": (1, 2, 3, 4, 100)}),
        producer_build_hash=BUILD_HASH,
    )
    summary, outlier = result.output_table.rows
    assert summary == (
        "summary",
        0,
        None,
        5,
        2.0,
        3.0,
        4.0,
        2.0,
        -1.0,
        7.0,
        1.0,
        4.0,
        None,
        None,
    )
    assert outlier[-2:] == (100.0, "row:5")
    assert result.included_row_count == 5
    assert result.excluded_row_count == 0


def test_tukey_group_order_is_first_seen_and_invalid_numeric_type_blocks() -> None:
    spec = TukeyBoxSpec(
        calculation_id="plotcalc:box-groups",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        value_field="field:value",
        group_field="field:group",
    )
    result = calculate_plot(
        spec,
        data({"field:value": (10, 1, 11, 2), "field:group": ("B", "A", "B", "A")}),
        producer_build_hash=BUILD_HASH,
    )
    summaries = [row for row in result.output_table.rows if row[0] == "summary"]
    assert [row[2] for row in summaries] == ["B", "A"]
    with pytest.raises(PlotCalculationError) as raised:
        calculate_plot(
            spec,
            data({"field:value": (1, "bad"), "field:group": ("A", "A")}),
            producer_build_hash=BUILD_HASH,
        )
    assert raised.value.code == "PLOTSPEC_CALCULATION_SHAPE_INVALID"


@pytest.mark.parametrize("kind", ["violin", "density"])
def test_kde_gaussian_scott_grid_and_density_golden(kind: str) -> None:
    common = {
        "calculation_id": f"plotcalc:{kind}",
        "calculation_version": 1,
        "prepared_dataset_ref": prepared_ref(),
        "algorithm_version": ALGORITHM_VERSION,
        "missing_policy": "fail",
        "value_field": "field:value",
    }
    spec = ViolinKDESpec(**common) if kind == "violin" else DensityKDESpec(**common)
    result = calculate_plot(
        spec,
        data({"field:value": (0, 2)}),
        producer_build_hash=BUILD_HASH,
    )
    bandwidth = math.sqrt(2.0) * 2.0 ** (-0.2)
    expected_at_zero = (1.0 + math.exp(-0.5 * (2.0 / bandwidth) ** 2)) / (
        2.0 * bandwidth * math.sqrt(2.0 * math.pi)
    )
    assert result.bandwidths == pytest.approx((bandwidth,))
    assert len(result.output_table.rows) == 256
    first = result.output_table.rows[0]
    last = result.output_table.rows[-1]
    if kind == "violin":
        assert first[3] == 0.0
        assert last[3] == 2.0
        assert first[4] == pytest.approx(expected_at_zero, rel=1e-14)
        assert last[4] == pytest.approx(expected_at_zero, rel=1e-14)
    else:
        assert first[3] == pytest.approx(-3.0 * bandwidth)
        assert last[3] == pytest.approx(2.0 + 3.0 * bandwidth)


@pytest.mark.parametrize("kind", ["violin", "density"])
def test_kde_constant_or_singleton_groups_block(kind: str) -> None:
    common = {
        "calculation_id": f"plotcalc:{kind}-invalid",
        "calculation_version": 1,
        "prepared_dataset_ref": prepared_ref(),
        "algorithm_version": ALGORITHM_VERSION,
        "missing_policy": "fail",
        "value_field": "field:value",
    }
    spec = ViolinKDESpec(**common) if kind == "violin" else DensityKDESpec(**common)
    values = (1, 1) if kind == "violin" else (1,)
    expected = (
        "PLOTSPEC_CALCULATION_DOMAIN_INVALID"
        if kind == "violin"
        else "PLOTSPEC_CALCULATION_INSUFFICIENT_DATA"
    )
    with pytest.raises(PlotCalculationError) as raised:
        calculate_plot(spec, data({"field:value": values}), producer_build_hash=BUILD_HASH)
    assert raised.value.code == expected


def test_ecdf_and_ccdf_ties_use_frozen_cumulative_definitions() -> None:
    spec = ECDFSpec(
        calculation_id="plotcalc:ecdf",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        value_field="field:value",
    )
    source = data({"field:value": (1, 1, 2, 4)})
    ecdf = calculate_plot(spec, source, producer_build_hash=BUILD_HASH)
    assert ecdf.output_table.rows == (
        (0, 1.0, 2, 0.5),
        (1, 2.0, 3, 0.75),
        (2, 4.0, 4, 1.0),
    )
    ccdf = calculate_plot(
        spec.model_copy(update={"calculation_id": "plotcalc:ccdf", "mode": "ccdf"}),
        source,
        producer_build_hash=BUILD_HASH,
    )
    assert ccdf.output_table.rows == (
        (0, 1.0, 4, 1.0),
        (1, 2.0, 2, 0.5),
        (2, 4.0, 1, 0.25),
    )


@pytest.mark.parametrize(
    ("method", "expected"),
    (
        ("mean_sd", (2.5, 1.2090055512641944, 3.7909944487358054)),
        ("mean_sem", (2.5, 1.8545027756320973, 3.1454972243679027)),
        ("mean_95_t_ci", (2.5, 0.445739743239121, 4.554260256760879)),
        ("median_iqr", (2.5, 1.75, 3.25)),
        ("median_range", (2.5, 1.0, 4.0)),
    ),
)
def test_computed_summary_goldens(method: str, expected: tuple[float, float, float]) -> None:
    spec = SummaryErrorSpec(
        calculation_id=f"plotcalc:{method}",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        method=cast(object, method),
        value_field="field:value",
    )
    result = calculate_plot(
        spec,
        data({"field:value": (1, 2, 3, 4)}),
        producer_build_hash=BUILD_HASH,
    )
    row = result.output_table.rows[0]
    assert row[3:6] == pytest.approx(expected)
    assert row[2] == 4


def test_direct_summary_bounds_and_symmetric_error_are_not_aggregated() -> None:
    source = data(
        {
            "field:group": ("A", "B"),
            "field:center": (5, 10),
            "field:lower": (4, 8),
            "field:upper": (8, 11),
            "field:error": (2, 1),
        }
    )
    bounds_spec = SummaryErrorSpec(
        calculation_id="plotcalc:direct-bounds",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        method="direct_bounds",
        group_fields=("field:group",),
        center_field="field:center",
        lower_field="field:lower",
        upper_field="field:upper",
    )
    bounds = calculate_plot(bounds_spec, source, producer_build_hash=BUILD_HASH)
    assert bounds.output_table.rows[0] == (0, "A", "row:1", 1, 5.0, 4.0, 8.0, 1.0, 3.0)

    symmetric_spec = SummaryErrorSpec(
        calculation_id="plotcalc:direct-symmetric",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        method="direct_symmetric_error",
        group_fields=("field:group",),
        center_field="field:center",
        symmetric_error_field="field:error",
    )
    symmetric = calculate_plot(symmetric_spec, source, producer_build_hash=BUILD_HASH)
    assert symmetric.output_table.rows[0] == (0, "A", "row:1", 1, 5.0, 3.0, 7.0, 2.0, 2.0)


def test_summary_requires_two_values_and_valid_direct_semantics() -> None:
    computed = SummaryErrorSpec(
        calculation_id="plotcalc:summary-small",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        method="mean_sd",
        value_field="field:value",
    )
    with pytest.raises(PlotCalculationError) as raised:
        calculate_plot(
            computed,
            data({"field:value": (1,)}),
            producer_build_hash=BUILD_HASH,
        )
    assert raised.value.code == "PLOTSPEC_CALCULATION_INSUFFICIENT_DATA"

    direct = SummaryErrorSpec(
        calculation_id="plotcalc:summary-bad-error",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        method="direct_symmetric_error",
        center_field="field:center",
        symmetric_error_field="field:error",
    )
    with pytest.raises(PlotCalculationError) as raised:
        calculate_plot(
            direct,
            data({"field:center": (2,), "field:error": (-1,)}),
            producer_build_hash=BUILD_HASH,
        )
    assert raised.value.code == "PLOTSPEC_CALCULATION_DOMAIN_INVALID"


def test_percent_stack_preserves_originals_totals_and_zero_components() -> None:
    spec = PercentStackSpec(
        calculation_id="plotcalc:stack",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        category_field="field:category",
        component_field="field:component",
        value_field="field:value",
    )
    result = calculate_plot(
        spec,
        data(
            {
                "field:category": ("A", "A", "B", "B"),
                "field:component": ("x", "y", "x", "y"),
                "field:value": (2, 1, 0, 4),
            }
        ),
        producer_build_hash=BUILD_HASH,
    )
    assert result.category_count == 2
    assert result.component_count == 2
    expected_rows = (
        (0, "A", 0, "x", "row:1", 2.0, 3.0, 2.0 / 3.0, 200.0 / 3.0),
        (0, "A", 1, "y", "row:2", 1.0, 3.0, 1.0 / 3.0, 100.0 / 3.0),
        (1, "B", 0, "x", "row:3", 0.0, 4.0, 0.0, 0.0),
        (1, "B", 1, "y", "row:4", 4.0, 4.0, 1.0, 100.0),
    )
    for actual, expected in zip(result.output_table.rows, expected_rows, strict=True):
        assert actual[:7] == expected[:7]
        assert actual[7:] == pytest.approx(expected[7:])


@pytest.mark.parametrize(
    ("categories", "components", "values", "code"),
    (
        (("A",), ("x",), (-1,), "PLOTSPEC_CALCULATION_DOMAIN_INVALID"),
        (("A", "A"), ("x", "y"), (0, 0), "PLOTSPEC_CALCULATION_DOMAIN_INVALID"),
        (("A", "A"), ("x", "x"), (1, 2), "PLOTSPEC_CALCULATION_DUPLICATE_CELL"),
    ),
)
def test_percent_stack_invalid_domains_block(
    categories: tuple[str, ...],
    components: tuple[str, ...],
    values: tuple[int, ...],
    code: str,
) -> None:
    spec = PercentStackSpec(
        calculation_id="plotcalc:stack-invalid",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        category_field="field:category",
        component_field="field:component",
        value_field="field:value",
    )
    with pytest.raises(PlotCalculationError) as raised:
        calculate_plot(
            spec,
            data(
                {
                    "field:category": categories,
                    "field:component": components,
                    "field:value": values,
                }
            ),
            producer_build_hash=BUILD_HASH,
        )
    assert raised.value.code == code


def test_regular_matrix_and_unique_xy_projection_goldens() -> None:
    regular_spec = MatrixProjectionSpec(
        calculation_id="plotcalc:matrix-regular",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        input_mode="regular_matrix",
        matrix_value_fields=("field:c1", "field:c2"),
    )
    regular = calculate_plot(
        regular_spec,
        PlotCalculationInput(row_ids=row_ids(2), columns={}, matrix=((1, 2), (3, 4))),
        producer_build_hash=BUILD_HASH,
    )
    assert regular.complete_grid is True
    assert (regular.matrix_rows, regular.matrix_columns) == (2, 2)
    assert regular.output_table.rows == (
        (0, 0, "row:1", "field:c1", 1.0),
        (0, 1, "row:1", "field:c2", 2.0),
        (1, 0, "row:2", "field:c1", 3.0),
        (1, 1, "row:2", "field:c2", 4.0),
    )

    xy_spec = MatrixProjectionSpec(
        calculation_id="plotcalc:matrix-xy",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        input_mode="unique_xy",
        x_field="field:x",
        y_field="field:y",
        z_field="field:z",
    )
    xy = calculate_plot(
        xy_spec,
        data({"field:x": (1, 0, 1), "field:y": (1, 0, 0), "field:z": (4, 1, 2)}),
        producer_build_hash=BUILD_HASH,
    )
    assert xy.complete_grid is False
    assert (xy.matrix_rows, xy.matrix_columns) == (2, 2)
    assert xy.output_table.rows == (
        (0, 0, 0.0, 0.0, 1.0, "row:2"),
        (0, 1, 1.0, 0.0, 2.0, "row:3"),
        (1, 1, 1.0, 1.0, 4.0, "row:1"),
    )


def test_matrix_duplicate_xy_blocks_without_aggregation() -> None:
    spec = MatrixProjectionSpec(
        calculation_id="plotcalc:matrix-duplicate",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        input_mode="unique_xy",
        x_field="field:x",
        y_field="field:y",
        z_field="field:z",
    )
    with pytest.raises(PlotCalculationError) as raised:
        calculate_plot(
            spec,
            data({"field:x": (0, 0), "field:y": (1, 1), "field:z": (2, 3)}),
            producer_build_hash=BUILD_HASH,
        )
    assert raised.value.code == "PLOTSPEC_CALCULATION_DUPLICATE_COORDINATE"


@pytest.mark.parametrize(
    ("normalization", "expected"),
    (
        ("count", (2, 1, 1, 1)),
        ("true_class", (2 / 3, 1 / 3, 1 / 2, 1 / 2)),
        ("predicted_class", (2 / 3, 1 / 2, 1 / 3, 1 / 2)),
    ),
)
def test_confusion_count_and_row_column_normalization_goldens(
    normalization: str,
    expected: tuple[float, ...],
) -> None:
    spec = ConfusionCountSpec(
        calculation_id=f"plotcalc:confusion-{normalization}",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        actual_field="field:actual",
        predicted_field="field:predicted",
        normalization=cast(object, normalization),
        category_order=("cat", "dog"),
    )
    result = calculate_plot(
        spec,
        data(
            {
                "field:actual": ("cat", "cat", "cat", "dog", "dog"),
                "field:predicted": ("cat", "cat", "dog", "cat", "dog"),
            }
        ),
        producer_build_hash=BUILD_HASH,
    )
    assert result.category_order == ("cat", "dog")
    assert [row[7] for row in result.output_table.rows] == pytest.approx(expected)
    assert [row[4] for row in result.output_table.rows] == [2, 1, 1, 1]


def test_confusion_fixed_input_order_zero_denominator_and_invalid_order() -> None:
    source = data({"field:actual": (False, True, False), "field:predicted": (True, True, False)})
    implicit = ConfusionCountSpec(
        calculation_id="plotcalc:confusion-implicit",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        actual_field="field:actual",
        predicted_field="field:predicted",
    )
    implicit_result = calculate_plot(implicit, source, producer_build_hash=BUILD_HASH)
    assert implicit_result.category_order == ("false", "true")

    explicit = implicit.model_copy(
        update={
            "calculation_id": "plotcalc:confusion-empty-category",
            "normalization": "true_class",
            "category_order": ("false", "true", "unused"),
        }
    )
    explicit_result = calculate_plot(explicit, source, producer_build_hash=BUILD_HASH)
    assert explicit_result.category_count == 3
    assert explicit_result.warnings[0].warning_id == "plotcalc.zero_normalization_denominator"
    assert [row[7] for row in explicit_result.output_table.rows[-3:]] == [0.0, 0.0, 0.0]

    invalid = implicit.model_copy(update={"category_order": ("false",)})
    with pytest.raises(PlotCalculationError) as raised:
        calculate_plot(invalid, source, producer_build_hash=BUILD_HASH)
    assert raised.value.code == "PLOTSPEC_CALCULATION_DOMAIN_INVALID"


def test_confusion_count_accepts_valid_preaggregated_counts() -> None:
    spec = ConfusionCountSpec(
        calculation_id="plotcalc:confusion-preaggregated",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        actual_field="field:actual",
        predicted_field="field:predicted",
        count_field="field:count",
        category_order=("cat", "dog"),
    )
    result = calculate_plot(
        spec,
        data(
            {
                "field:actual": ("cat", "cat", "dog", "dog"),
                "field:predicted": ("cat", "dog", "cat", "dog"),
                "field:count": (12, 2, 1, 10),
            }
        ),
        producer_build_hash=BUILD_HASH,
    )

    assert [row[4] for row in result.output_table.rows] == [12, 2, 1, 10]
    assert [row[7] for row in result.output_table.rows] == [12, 2, 1, 10]


@pytest.mark.parametrize("count", (-1, 1.5))
def test_confusion_count_rejects_invalid_preaggregated_counts(count: float) -> None:
    spec = ConfusionCountSpec(
        calculation_id="plotcalc:confusion-invalid-preaggregated",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        actual_field="field:actual",
        predicted_field="field:predicted",
        count_field="field:count",
    )

    with pytest.raises(PlotCalculationError) as raised:
        calculate_plot(
            spec,
            data(
                {
                    "field:actual": ("cat",),
                    "field:predicted": ("dog",),
                    "field:count": (count,),
                }
            ),
            producer_build_hash=BUILD_HASH,
        )

    assert raised.value.code == "PLOTSPEC_CALCULATION_DOMAIN_INVALID"


def test_fail_policy_algorithm_version_and_empty_input_have_stable_errors() -> None:
    spec = ECDFSpec(
        calculation_id="plotcalc:ecdf-invalid",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        value_field="field:value",
    )
    with pytest.raises(PlotCalculationError) as raised:
        calculate_plot(
            spec,
            data({"field:value": (1, None)}),
            producer_build_hash=BUILD_HASH,
        )
    assert raised.value.code == "PLOTSPEC_CALCULATION_NONFINITE"

    with pytest.raises(PlotCalculationError) as raised:
        calculate_plot(
            spec.model_copy(update={"algorithm_version": "2.0.0"}),
            data({"field:value": (1, 2)}),
            producer_build_hash=BUILD_HASH,
        )
    assert raised.value.code == "PLOTSPEC_CALCULATION_VERSION_UNSUPPORTED"

    with pytest.raises(PlotCalculationError) as raised:
        calculate_plot(
            spec,
            PlotCalculationInput(row_ids=(), columns={"field:value": ()}),
            producer_build_hash=BUILD_HASH,
        )
    assert raised.value.code == "PLOTSPEC_CALCULATION_INSUFFICIENT_DATA"


def test_result_and_jitter_are_cross_run_deterministic() -> None:
    spec = ECDFSpec(
        calculation_id="plotcalc:stable-hash",
        calculation_version=1,
        prepared_dataset_ref=prepared_ref(),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        value_field="field:value",
        fixed_seed=1729,
    )
    source = data({"field:value": (3, 1, 3, 2)})
    first = calculate_plot(spec, source, producer_build_hash=BUILD_HASH)
    second = calculate_plot(spec, source, producer_build_hash=BUILD_HASH)
    assert first.output_hash == second.output_hash
    assert canonical_hash(first) == canonical_hash(second)
    assert first.input_hash == "504ddbae11fd9c12e7fed064c0acb12b8fbe7ceb08a4dca46ea1659c9096af0e"
    assert first.output_hash == "d3a2ec283067edcac8c91eaf592ba9f2da74b986f0aef70f24693a6f8127e76c"
    assert (
        canonical_hash(first) == "8fdbccd59981145c6c83476df7843aa902950edc9d134ca635adb90e36b6f2e8"
    )
    assert first.fixed_seed == 1729

    first_jitter = deterministic_jitter(row_ids(3), seed=1729, half_width=0.25)
    second_jitter = deterministic_jitter(row_ids(3), seed=1729, half_width=0.25)
    assert first_jitter == second_jitter
    assert first_jitter == pytest.approx(
        (0.24440411868554796, -0.09336014377909244, -0.20232137407415052)
    )
    assert all(-0.25 <= offset <= 0.25 for offset in first_jitter)
