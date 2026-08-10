from __future__ import annotations

import json

from plotagent.contracts.registry import PRODUCT_CHART_IDS
from scripts import build_template_first_visual_review as review


def test_review_inventory_has_all_product_charts_and_one_representative_per_family() -> None:
    records = review._records()

    assert [record["chart_id"] for record in records] == list(PRODUCT_CHART_IDS)
    family_ids = {record["family_id"] for record in records}
    representatives = [record for record in records if record["family_representative"]]
    assert len(family_ids) == len(representatives)
    assert {record["family_id"] for record in representatives} == family_ids


def test_frozen_review_manifest_never_claims_visual_pass() -> None:
    if not review.FROZEN_MANIFEST.is_file():
        return

    manifest = json.loads(review.FROZEN_MANIFEST.read_text(encoding="utf-8"))
    assert set(manifest["charts"]) == set(PRODUCT_CHART_IDS)
    assert manifest["summary"]["chart_count"] == 38
    assert manifest["summary"]["mechanical_pass"] == 38
    assert manifest["summary"]["visual_unverified"] == 38
    assert all(chart["mechanical_status"] == "PASS" for chart in manifest["charts"].values())
    assert all(chart["visual_status"] == "UNVERIFIED" for chart in manifest["charts"].values())
    assert all(
        family["manual_edit_status"] == "UNVERIFIED" for family in manifest["families"].values()
    )


def test_review_page_keeps_visual_status_unverified() -> None:
    if not (review.OUTPUT / "index.html").is_file():
        return

    source = (review.OUTPUT / "index.html").read_text(encoding="utf-8")
    assert "视觉 UNVERIFIED" in source
    assert "机械 PASS" in source
    assert "视觉 PASS" not in source
    assert source.count('class="chart-card"') == 38
