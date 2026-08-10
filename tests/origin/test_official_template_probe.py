from __future__ import annotations

import inspect

from plotagent.contracts.registry import PRODUCT_CHART_IDS
from scripts.probe_origin_official_templates import (
    CHART_PROFILES_BY_ID,
    _base_frame,
    probe_variants,
)


def test_bare_template_probe_covers_every_product_chart_without_renderer_fallback() -> None:
    source = inspect.getsource(
        __import__("scripts.probe_origin_official_templates", fromlist=["*"])
    )

    assert set(CHART_PROFILES_BY_ID) == set(PRODUCT_CHART_IDS)
    assert "MatplotlibRenderer" not in source
    assert "compile_origin_plan" not in source
    assert "resolve_chart" not in source
    assert "plotagent.rendering" not in source
    assert "plotagent.origin.planner" not in source


def test_bare_template_probe_has_dynamic_and_edit_variants_for_all_38_charts() -> None:
    for chart_id in PRODUCT_CHART_IDS:
        variants = {
            variant.name: variant for variant in probe_variants(chart_id, _base_frame(chart_id))
        }
        assert {"default", "rows_min", "rows_large", "range_cross_zero", "missing_middle"} <= set(
            variants
        )
        assert variants["edited"].edited is True
        assert all(not variant.frame.empty for variant in variants.values())


def test_bare_template_probe_keeps_visual_status_out_of_mechanical_conclusions() -> None:
    source = inspect.getsource(
        __import__("scripts.probe_origin_official_templates", fromlist=["*"])
    )

    assert '"visual_status": "UNVERIFIED"' in source
    assert '"visual_pass_allowed": False' in source
    assert "contact_sheet" in source
