from __future__ import annotations

import inspect
import json

from plotagent.contracts.registry import PRODUCT_CHART_IDS
from scripts.probe_origin_official_templates import (
    _T2_PATCH_EXPECTATIONS,
    CHART_PROFILES_BY_ID,
    FROZEN_MANIFEST_PATH,
    _base_frame,
    _new_graph,
    _probe_source_sha256,
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


def test_each_t2_profile_has_explicit_bare_gap_evidence() -> None:
    patched_profiles = {
        chart_id: profile
        for chart_id, profile in CHART_PROFILES_BY_ID.items()
        if profile.origin.tier == "T2"
    }

    assert len(patched_profiles) == 10
    assert set(_T2_PATCH_EXPECTATIONS) == set(patched_profiles)
    for chart_id, profile in patched_profiles.items():
        assert tuple(_T2_PATCH_EXPECTATIONS[chart_id]) == profile.origin.declared_patch_ids
        assert all(_T2_PATCH_EXPECTATIONS[chart_id].values())


def test_originpro_uppercase_template_extension_is_normalized_without_copying() -> None:
    captured: dict[str, object] = {}

    class FakeOrigin:
        def new_graph(self, name: str, *, template: str, hidden: bool) -> object:
            captured.update(name=name, template=template, hidden=hidden)
            return object()

    profile = CHART_PROFILES_BY_ID["K03"]
    graph = _new_graph(FakeOrigin(), "Probe", profile)

    assert graph is not None
    assert str(captured["template"]).endswith("SCATTER.otp")
    assert captured["hidden"] is True


def test_frozen_bare_template_manifest_is_complete_current_and_not_a_visual_pass() -> None:
    manifest = json.loads(FROZEN_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["probe_source_sha256"] == _probe_source_sha256()
    assert manifest["summary"] == {
        "auto": 28,
        "build_passed": 38,
        "chart_count": 38,
        "declared_patch": 10,
        "fresh_reopen_passed": 38,
        "visual_status": "UNVERIFIED",
    }
    assert tuple(manifest["charts"]) == PRODUCT_CHART_IDS
    assert all(chart["fresh_reopen_identical"] for chart in manifest["charts"].values())
    assert all(chart["visual_status"] == "UNVERIFIED" for chart in manifest["charts"].values())
