from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
FIXTURES = REPOSITORY / "tests" / "fixtures" / "visual_regression" / "visual29-structural"
EXPECTED_CASES = ("X05", "X13", "X23", "X35", "X36", "X38")
EXPECTED_GAPS = ("K24", "K25", "S01")
EXPECTED_LANE = ("S01", "X05", "X13", "X38", "K24", "K25", "X23", "X35", "X36")
EXPECTED_BLOCKED = {"X05", "X23", "X35", "X36", "X38"}
EXPECTED_ORIGIN_FAILURES = {("X36", "edited"), ("X38", "edited")}
_SHA256 = re.compile(r"[0-9a-f]{64}")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_dir(chart_id: str) -> Path:
    matches = tuple(FIXTURES.glob(f"{chart_id}_*"))
    assert len(matches) == 1
    return matches[0]


def _manifest() -> dict[str, object]:
    path = FIXTURES / "manifest.json"
    assert path.is_file(), "run build_visual29_structural.py after the backend freeze"
    return json.loads(path.read_text(encoding="utf-8"))


def test_structural_lane_frozen_anchors_are_same_source_and_non_synthetic() -> None:
    for chart_id in EXPECTED_CASES:
        fixture_dir = _fixture_dir(chart_id)
        provenance = json.loads((fixture_dir / "provenance.json").read_text(encoding="utf-8"))
        source = Path(provenance["source_path"])

        assert provenance["chart_type_id"] == chart_id
        assert provenance["evidence_grade"] in {"A", "C"}
        assert provenance["same_source_data"] is True
        assert provenance["synthetic"] is False
        assert source.is_file()
        assert _sha256(source) == provenance["source_sha256"]
        assert _sha256(fixture_dir / "data.csv") == provenance["data_sha256"]
        assert _sha256(fixture_dir / "reference.png") == provenance["reference_sha256"]


def test_structural_lane_manifest_covers_every_assigned_chart_without_substitution() -> None:
    manifest = _manifest()
    cases = manifest["cases"]
    gaps = manifest["gaps"]

    assert manifest["stage"] == "VISUAL29-STRUCTURAL"
    assert tuple(manifest["lane_chart_type_ids"]) == EXPECTED_LANE
    assert tuple(item["chart_type_id"] for item in cases) == EXPECTED_CASES
    assert tuple(item["chart_type_id"] for item in gaps) == EXPECTED_GAPS
    assert {item["chart_type_id"] for item in cases}.isdisjoint(
        {item["chart_type_id"] for item in gaps}
    )
    assert {item["chart_type_id"] for item in cases + gaps} == set(EXPECTED_LANE)
    assert manifest["rules"]["same_source_required"] is True
    assert manifest["rules"]["synthetic_allowed"] is False
    assert all(item["status"] == "not_tested" for item in gaps)
    assert all(item["reason"] for item in gaps)
    assert all(not tuple(FIXTURES.glob(f"{item['chart_type_id']}_*")) for item in gaps)


def test_structural_lane_default_and_edited_evidence_is_fresh_reopened() -> None:
    manifest = _manifest()
    for case in manifest["cases"]:
        assert case["same_source_data"] is True
        assert case["synthetic"] is False
        assert set(case["states"]) == {"default", "edited"}
        for state_name, state in case["states"].items():
            if (case["chart_type_id"], state_name) in EXPECTED_ORIGIN_FAILURES:
                assert state["origin_export_status"] == "failed"
                assert state["fresh_reopen_identical"] is False
                assert state["origin_error"]["error"]["code"] == "BUILD_FAILURE"
                continue
            assert state["origin_export_status"] == "success"
            assert state["fresh_reopen_identical"] is True
            assert state["origin_opju_size"] > 0
            for key in (
                "plot_spec_sha256",
                "render_plan_sha256",
                "matplotlib_png_sha256",
                "origin_plan_sha256",
                "origin_opju_sha256",
                "origin_fresh_png_sha256",
            ):
                assert _SHA256.fullmatch(state[key]) is not None
            report_hash = state["validation_report_sha256"]
            assert report_hash is None or _SHA256.fullmatch(report_hash) is not None


def test_structural_lane_is_bound_to_source_and_waits_for_human_signature() -> None:
    manifest = _manifest()
    qualification = manifest["qualification"]
    identity = qualification["source_build_identity"]

    assert identity["scope_version"] == "visual29-structural-rendering-v1"
    assert _GIT_COMMIT.fullmatch(identity["git_commit"]) is not None
    assert _SHA256.fullmatch(identity["source_sha256"]) is not None
    blockers = qualification["blocking_observations"]
    assert {item["chart_type_id"] for item in blockers} == EXPECTED_BLOCKED
    assert {item["code"] for item in blockers} == {
        "LEGEND_DATA_OVERLAP",
        "CATEGORY_LABEL_OVERLAP",
        "BUILD_FAILURE",
    }
    assert all(item["status"] == "open" for item in blockers)
    assert qualification["human_visual_signature"]["status"] == "pending"
    assert qualification["evidence_status"] == "first_round_stale"
    assert qualification["invalidation"]["code"] == "AUDIT_AXIS_LABEL_CONTRACT_UPDATED"
    assert qualification["decision"] == "NO-GO"
    assert "visual qualification not passed" in manifest["audit_conclusion"]
