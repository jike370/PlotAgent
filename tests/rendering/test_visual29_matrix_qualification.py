from __future__ import annotations

import hashlib
import json
from pathlib import Path

from plotagent.rendering import PlotResolver
from scripts import build_visual29_matrix as matrix
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
QUALIFIED = ("K04", "K12", "K19", "K22", "K21", "S21", "S31", "S34")
SYNTHETIC = ("K21", "S21", "S31", "S34")
GAPS: tuple[str, ...] = ()


def test_matrix_next_render_has_no_legacy_evidence_gap_blocker() -> None:
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
    assert qualification["blocking_observations"] == []


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_visual29_matrix_frozen_same_source_manifest() -> None:
    manifest_path = FIXTURES / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["stage"] == "VISUAL-29"
    assert manifest["lane"] == "matrix-specialist"
    assert manifest["rules"]["same_source_required"] is True
    assert manifest["rules"]["synthetic_allowed"] is True
    assert manifest["rules"]["grade_d_chart_type_ids"] == list(SYNTHETIC)
    assert manifest["rules"]["grade_d_cannot_be_relabelled_as_official"] is True
    assert tuple(item["chart_type_id"] for item in manifest["cases"]) == QUALIFIED
    assert tuple(item["chart_type_id"] for item in manifest["evidence_gaps"]) == GAPS
    assert tuple(item["chart_type_id"] for item in GAP_BLOCKING_OBSERVATIONS) == GAPS
    assert set(manifest["exports"]) == {"default", "edited"}
    assert all(item["fresh_reopen_identical"] for item in manifest["exports"].values())

    for case in manifest["cases"]:
        assert case["same_source_data"] is True
        if case["chart_type_id"] in SYNTHETIC:
            assert case["synthetic"] is True
            assert case["evidence_grade"] == "D"
            assert case["official_origin_evidence"] is False
            assert case["source_path"] is None
            assert case["source_sha256"] is None
            assert case["synthetic_label"] == "D-grade synthetic data + Origin-generated reference"
            assert case["synthetic_generation"]["frozen_before_reference"] is True
            construction = case["reference_construction"]
            assert construction["construction_path"] == "independent_origin_native"
            assert construction["plotagent_renderer_used"] is False
            assert construction["fresh_reopen_verified"] is True
            assert len(construction["reference_opju_sha256"]) == 64
        else:
            assert case["synthetic"] is False
            assert case["official_origin_evidence"] is True
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

    assert manifest["qualification"]["human_visual_signature"]["status"] == "reviewed"
    assert manifest["qualification"]["decision"] == "GO"
    qualification = manifest["qualification"]
    identity = qualification["source_build_identity"]
    assert identity["scope_version"] == "visual29-matrix-rendering-v2"
    assert identity["digest_algorithm"] == "git-blob-framed-sha256-v1"
    blockers = qualification["blocking_observations"]
    assert qualification["evidence_status"] == "qualified_after_visual_review"
    assert blockers == []
    assert "invalidation" not in qualification
    assert "automated P0 blockers closed" in manifest["audit_conclusion"]
    assert "visual qualification passed" in manifest["audit_conclusion"]


def test_visual29_matrix_gap_register_is_empty_after_explicit_d_admission() -> None:
    gap_path = FIXTURES / "evidence-gaps.json"
    assert gap_path.is_file()
    document = json.loads(gap_path.read_text(encoding="utf-8"))
    assert tuple(item["chart_type_id"] for item in document["gaps"]) == GAPS
    assert document["rules"]["synthetic_evidence_grade"] == "D"
    assert document["rules"]["synthetic_must_be_explicit"] is True
    assert document["gaps"] == []


def test_matrix_grade_d_generators_and_resolver_are_shape_driven() -> None:
    cases = {case.chart_id: case for case in matrix.SYNTHETIC_CASES}

    for chart_id, case in cases.items():
        first = matrix._synthetic_frame(case)
        second = matrix._synthetic_frame(case)
        assert first.equals(second), f"{chart_id} generator is not deterministic"

    for dimension in (3, 8):
        frame = matrix._synthetic_frame(cases["K21"], dimension=dimension, observations=40)
        assert len(frame) == dimension * dimension
        plot, store = matrix._build_plot(cases["K21"], frame, edited=True)
        resolved = PlotResolver().resolve(plot, store)
        axes = {axis.orientation: axis for axis in resolved.plan.axes}
        assert len(axes["x"].ticks) == len(axes["y"].ticks) == dimension
        palette = resolved.plan.layers[0].palette_spec
        assert palette is not None
        assert palette.palette_id == "OrangeNavy"

    for studies in (3, 11):
        frame = matrix._synthetic_frame(cases["S21"], studies=studies)
        assert (frame["lower"] < frame["effect"]).all()
        assert (frame["effect"] < frame["upper"]).all()
        plot, store = matrix._build_plot(cases["S21"], frame, edited=True)
        resolved = PlotResolver().resolve(plot, store)
        assert len(resolved.plan.layers) == 1
        y_axis = next(axis for axis in resolved.plan.axes if axis.orientation == "y")
        assert len(y_axis.ticks) == studies

    for chart_id, overrides, expected_series in (
        ("S31", {"series": 1, "points": 37}, 1),
        ("S31", {"series": 4, "points": 143}, 4),
        ("S34", {"series": 1, "points": 12}, 1),
        ("S34", {"series": 5, "points": 31}, 5),
    ):
        frame = matrix._synthetic_frame(cases[chart_id], **overrides)
        plot, store = matrix._build_plot(cases[chart_id], frame, edited=True)
        resolved = PlotResolver().resolve(plot, store)
        assert frame["series"].nunique() == expected_series
        assert len(plot.series) == len(resolved.plan.layers) == expected_series
        assert all(
            layer.data_ref.row_count == overrides["points"]
            for layer in resolved.plan.layers
        )
