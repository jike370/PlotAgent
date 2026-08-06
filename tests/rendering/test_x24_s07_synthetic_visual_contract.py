from __future__ import annotations

import math
from typing import Any

import pytest

from scripts.build_x24_s07_synthetic_audit import (
    _assert_axis_coverage,
    _assert_chart_semantics,
    _assert_dynamic_pairs,
    _assert_finite_geometry,
    _load_case,
    _load_manifest,
    _matplotlib_checks,
    _resolved,
)


@pytest.mark.parametrize("case", _load_manifest()["cases"], ids=lambda item: item["case_id"])
def test_frozen_x24_s07_synthetic_cases_are_deterministic_and_visible(
    case: dict[str, Any],
) -> None:
    frame = _load_case(case)
    _, resolved = _resolved(case, frame)
    _, repeated = _resolved(case, frame)

    assert resolved.render_plan_hash == repeated.render_plan_hash
    _assert_finite_geometry(resolved)
    _assert_axis_coverage(resolved)
    checks = _assert_chart_semantics(case, frame, resolved)
    matplotlib_checks = _matplotlib_checks(resolved)

    assert checks["input_rows"] == case["expected"]["row_count"]
    assert matplotlib_checks["visible_text_clipped"] is False
    assert matplotlib_checks["x_tick_overlap"] is False


def test_frozen_x24_s07_pairs_exercise_dynamic_category_count_and_range() -> None:
    results: list[dict[str, object]] = []
    for case in _load_manifest()["cases"]:
        frame = _load_case(case)
        _, resolved = _resolved(case, frame)
        results.append(
            {
                "case_id": case["case_id"],
                "chart_checks": _assert_chart_semantics(case, frame, resolved),
            }
        )

    checks = _assert_dynamic_pairs(results)

    assert set(checks) == {"X24", "S07"}


def test_x24_formal_layout_reserves_right_axis_margin_and_coincident_panels() -> None:
    case = next(item for item in _load_manifest()["cases"] if item["case_id"] == "X24_expanded")
    frame = _load_case(case)
    _, resolved = _resolved(case, frame)
    left, right = resolved.plan.panels

    assert left.left == right.left
    assert left.top == right.top
    assert left.width == right.width
    assert left.height == right.height
    right_margin = resolved.plan.canvas.width.value - left.left.value - left.width.value
    assert math.isclose(right_margin, 12.0, rel_tol=0.0, abs_tol=1e-12)
