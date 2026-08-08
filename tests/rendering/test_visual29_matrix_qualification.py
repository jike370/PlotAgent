from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.build_visual29_matrix import GAP_BLOCKING_OBSERVATIONS
from scripts.build_visual29_matrix import (
    _fresh_qualification as matrix_fresh_qualification,
)

FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "visual_regression"
    / "visual29-matrix"
)
QUALIFIED = ("K04", "K12", "K19", "K22")
GAPS = ("K21", "S21", "S31", "S34")


def test_matrix_next_render_qualification_only_blocks_evidence_gaps() -> None:
    qualification = matrix_fresh_qualification(
        {
            "scope_version": "test",
            "git_commit": "a" * 40,
            "source_sha256": "b" * 64,
        }
    )

    assert qualification["evidence_status"] == "fresh_render_pending_human"
    assert qualification["decision"] == "NO-GO"
    assert qualification["human_visual_signature"]["status"] == "pending"
    assert tuple(
        item["chart_type_id"] for item in qualification["blocking_observations"]
    ) == GAPS


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_visual29_matrix_frozen_same_source_manifest() -> None:
    manifest_path = FIXTURES / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["stage"] == "VISUAL-29"
    assert manifest["lane"] == "matrix-specialist"
    assert manifest["rules"]["same_source_required"] is True
    assert manifest["rules"]["synthetic_allowed"] is False
    assert tuple(item["chart_type_id"] for item in manifest["cases"]) == QUALIFIED
    assert tuple(item["chart_type_id"] for item in manifest["evidence_gaps"]) == GAPS
    assert tuple(item["chart_type_id"] for item in GAP_BLOCKING_OBSERVATIONS) == GAPS
    assert set(manifest["exports"]) == {"default", "edited"}
    assert all(item["fresh_reopen_identical"] for item in manifest["exports"].values())

    for case in manifest["cases"]:
        assert case["same_source_data"] is True
        assert case["synthetic"] is False
        assert case["evidence_grade"] in {"A", "C"}
        fixture_dir = next(FIXTURES.glob(f"{case['chart_type_id']}_*"))
        assert _sha256(fixture_dir / "data.csv") == case["data_sha256"]
        assert _sha256(fixture_dir / "reference.png") == case["reference_sha256"]
        assert set(case["states"]) == {"default", "edited"}
        for state in case["states"].values():
            assert len(state["plot_spec_sha256"]) == 64
            assert len(state["render_plan_sha256"]) == 64
            assert len(state["matplotlib_png_sha256"]) == 64
            assert len(state["origin_fresh_png_sha256"]) == 64

    assert manifest["qualification"]["human_visual_signature"]["status"] == "pending"
    assert manifest["qualification"]["decision"] == "NO-GO"
    qualification = manifest["qualification"]
    identity = qualification["source_build_identity"]
    assert identity["scope_version"] == "visual29-matrix-rendering-v2"
    assert identity["digest_algorithm"] == "git-blob-framed-sha256-v1"
    blockers = qualification["blocking_observations"]
    assert qualification["evidence_status"] == "fresh_render_pending_human"
    assert {item["chart_type_id"] for item in blockers} == set(GAPS)
    assert {item["code"] for item in blockers} == {"SAME_SOURCE_EVIDENCE_MISSING"}
    assert {item["backend"] for item in blockers} == {"evidence"}
    assert all(item["status"] == "open" for item in blockers)
    assert "invalidation" not in qualification
    assert "automated P0 blockers closed" in manifest["audit_conclusion"]
    assert "visual qualification not passed" in manifest["audit_conclusion"]


def test_visual29_matrix_gaps_are_not_rendered_or_claimed() -> None:
    gap_path = FIXTURES / "evidence-gaps.json"
    assert gap_path.is_file()
    document = json.loads(gap_path.read_text(encoding="utf-8"))
    assert tuple(item["chart_type_id"] for item in document["gaps"]) == GAPS
    assert all(
        item["status"] == "not_tested_missing_same_source_evidence"
        for item in document["gaps"]
    )
    assert all(item["rendered"] is False for item in document["gaps"])
    assert all(item["qualification_claimed"] is False for item in document["gaps"])
    assert all(not tuple(FIXTURES.glob(f"{chart_id}_*")) for chart_id in GAPS)
