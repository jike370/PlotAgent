from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from plotagent.contracts.calculations import PlotCalculationResult, PlotCalculationSpec

from .helpers import HASH_A, HASH_B, HASH_C, prepared_ref

SPEC_CASES: tuple[tuple[str, dict[str, object]], ...] = (
    ("histogram_binning", {"value_field": "field:value", "normalization": "count"}),
    ("tukey_box", {"value_field": "field:value"}),
    ("violin_kde", {"value_field": "field:value", "grid_points": 256}),
    ("density_kde", {"value_field": "field:value", "grid_points": 256}),
    ("ecdf", {"value_field": "field:value", "mode": "ccdf"}),
    ("summary_error", {"method": "mean_sd", "value_field": "field:value"}),
    (
        "percent_stack",
        {
            "category_field": "field:category",
            "component_field": "field:component",
            "value_field": "field:value",
        },
    ),
    (
        "matrix_projection",
        {
            "input_mode": "unique_xy",
            "x_field": "field:x",
            "y_field": "field:y",
            "z_field": "field:z",
        },
    ),
    (
        "confusion_count",
        {
            "actual_field": "field:actual",
            "predicted_field": "field:predicted",
            "normalization": "count",
        },
    ),
)

ALGORITHMS = {
    "histogram_binning": "freedman_diaconis_sturges",
    "tukey_box": "linear_quantile_tukey_1_5_iqr",
    "violin_kde": "gaussian_scott_observed_range",
    "density_kde": "gaussian_scott_three_bandwidth",
    "ecdf": "right_continuous_empirical_cdf",
    "summary_error": "fixed_summary_error",
    "percent_stack": "category_nonnegative_percent",
    "matrix_projection": "regular_or_unique_xy_projection",
    "confusion_count": "fixed_confusion_count",
}


def spec_payload(kind: str, specific: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "calculation_id": f"plotcalc:{kind}",
        "calculation_version": 1,
        "prepared_dataset_ref": prepared_ref().model_dump(mode="json"),
        "algorithm_version": "algorithm.v1",
        "missing_policy": "fail",
        "kind": kind,
        "algorithm_id": ALGORITHMS[kind],
        **specific,
    }


@pytest.mark.parametrize(("kind", "specific"), SPEC_CASES)
def test_nine_calculation_specs_accept_only_their_closed_shape(
    kind: str, specific: dict[str, object]
) -> None:
    adapter = TypeAdapter(PlotCalculationSpec)
    payload = spec_payload(kind, specific)
    assert adapter.validate_json(json.dumps(payload)).kind == kind
    with pytest.raises(ValidationError):
        adapter.validate_json(json.dumps({**payload, "expression": "x + 1"}))


@pytest.mark.parametrize(
    ("kind", "specific"),
    (
        ("histogram_binning", {"bin_count": 3, "normalization": "count"}),
        ("tukey_box", {"group_count": 1}),
        ("violin_kde", {"group_count": 1, "grid_points": 256}),
        ("density_kde", {"group_count": 1, "grid_points": 256}),
        ("ecdf", {"mode": "ecdf"}),
        ("summary_error", {"method": "mean_sd", "group_count": 1}),
        ("percent_stack", {"category_count": 2}),
        ("matrix_projection", {"matrix_rows": 2, "matrix_columns": 2}),
        ("confusion_count", {"normalization": "count", "category_count": 2}),
    ),
)
def test_nine_calculation_results_are_hash_bound(kind: str, specific: dict[str, object]) -> None:
    payload = {
        "schema_version": "1.0",
        "calculation_id": f"plotcalc:{kind}",
        "result_version": 1,
        "spec_ref": {
            "calculation_id": f"plotcalc:{kind}",
            "calculation_version": 1,
            "calculation_kind": kind,
            "content_hash": HASH_A,
        },
        "prepared_dataset_ref": prepared_ref().model_dump(mode="json"),
        "algorithm_version": "algorithm.v1",
        "missing_policy": "fail",
        "input_hash": HASH_A,
        "output_hash": HASH_B,
        "output_data_ref": {
            "object_hash": HASH_B,
            "row_count": 2,
            "field_ids": ["field:result"],
        },
        "total_row_count": 4,
        "included_row_count": 4,
        "excluded_row_count": 0,
        "producer_build_hash": HASH_C,
        "kind": kind,
        "algorithm_id": ALGORITHMS[kind],
        **specific,
    }
    adapter = TypeAdapter(PlotCalculationResult)
    assert adapter.validate_json(json.dumps(payload)).kind == kind
    with pytest.raises(ValidationError):
        adapter.validate_json(json.dumps({**payload, "output_hash": HASH_C}))
    with pytest.raises(ValidationError):
        mismatch_kind = "ecdf" if kind != "ecdf" else "tukey_box"
        spec_ref = dict(payload["spec_ref"])  # type: ignore[arg-type]
        adapter.validate_json(
            json.dumps(
                {
                    **payload,
                    "spec_ref": {**spec_ref, "calculation_kind": mismatch_kind},
                }
            )
        )


def test_summary_and_matrix_conditional_fields_are_enforced() -> None:
    adapter = TypeAdapter(PlotCalculationSpec)
    with pytest.raises(ValidationError, match="direct_bounds"):
        adapter.validate_json(
            json.dumps(spec_payload("summary_error", {"method": "direct_bounds"}))
        )
    with pytest.raises(ValidationError, match="unique_xy"):
        adapter.validate_json(
            json.dumps(spec_payload("matrix_projection", {"input_mode": "unique_xy"}))
        )
