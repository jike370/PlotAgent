from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.build_visual29_fixed import MECHANICAL_BLOCKERS

FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "visual_regression"
    / "visual29-fixed"
)
EXPECTED_ANCHORED = {
    "K06": "A",
    "K07": "A",
    "K11": "A",
    "K13": "A",
    "K14": "C",
    "K15": "A",
    "K16": "A",
    "K17": "C",
    "K20": "A",
    "S61": "C",
    "X24": "C",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fixed_visual_evidence_is_same_source_and_never_synthetic() -> None:
    index = json.loads((FIXTURES / "evidence-index.json").read_text(encoding="utf-8"))

    assert index["stage"] == "visual29-fixed"
    assert index["rules"] == {
        "same_source_required": True,
        "synthetic_allowed": False,
        "missing_data_is_not_rendered": True,
    }
    anchored = {item["chart_type_id"]: item for item in index["anchored_cases"]}
    grades = {chart_id: item["evidence_grade"] for chart_id, item in anchored.items()}
    assert grades == EXPECTED_ANCHORED
    for chart_id, item in anchored.items():
        assert item["same_source_data"] is True
        assert item["synthetic"] is False
        case_dir = next(FIXTURES.glob(f"{chart_id}_*"))
        assert _sha256(case_dir / "data.csv") == item["data_sha256"]
        assert _sha256(case_dir / "reference.png") == item["reference_sha256"]


def test_s07_missing_origin_same_source_data_is_an_explicit_no_go() -> None:
    gap_dir = FIXTURES / "S07_volcano"
    gap = json.loads((gap_dir / "evidence-gap.json").read_text(encoding="utf-8"))

    assert gap["chart_type_id"] == "S07"
    assert gap["blocking_code"] == "SAME_SOURCE_ORIGIN_DATA_MISSING"
    assert gap["rendered"] is False
    assert gap["tested"] is False
    assert gap["synthetic"] is False
    assert not (gap_dir / "data.csv").exists()
    assert not (gap_dir / "reference.png").exists()


def test_next_render_does_not_carry_first_pass_mechanical_blockers() -> None:
    assert MECHANICAL_BLOCKERS == ()


def test_fixed_calculation_tables_satisfy_structural_invariants() -> None:
    k06 = pd.read_csv(FIXTURES / "K06_point_error" / "data.csv")
    assert tuple(k06.columns) == (
        "x",
        "center",
        "x_lower",
        "x_upper",
        "lower",
        "upper",
    )
    assert (k06["x_lower"] <= k06["x"]).all()
    assert (k06["x"] <= k06["x_upper"]).all()
    assert (k06["lower"] <= k06["center"]).all()
    assert (k06["center"] <= k06["upper"]).all()

    k11 = pd.read_csv(FIXTURES / "K11_percent_stack" / "data.csv")
    assert np.allclose(k11.groupby("category")["value"].sum().to_numpy(), 1.0)

    k13 = pd.read_csv(FIXTURES / "K13_tukey_box" / "data.csv")
    assert (k13["whisker_low"] <= k13["q1"]).all()
    assert (k13["q1"] <= k13["median"]).all()
    assert (k13["median"] <= k13["q3"]).all()
    assert (k13["q3"] <= k13["whisker_high"]).all()

    k14 = pd.read_csv(FIXTURES / "K14_violin" / "data.csv")
    assert (k14["density"] >= 0).all()
    for _, group in k14.groupby("group"):
        integral = np.trapezoid(group["density"], group["grid"])
        assert 0.75 < integral < 1.0

    k15 = pd.read_csv(FIXTURES / "K15_histogram" / "data.csv")
    assert (k15["right"] > k15["left"]).all()
    assert (k15["left"].iloc[1:].to_numpy() >= k15["right"].iloc[:-1].to_numpy()).all()
    assert (k15["height"] >= 0).all()

    k16 = pd.read_csv(FIXTURES / "K16_density" / "data.csv")
    assert (k16["density"] >= 0).all()
    for _, group in k16.groupby("group"):
        np.testing.assert_allclose(np.trapezoid(group["density"], group["grid"]), 1.0, rtol=0.08)

    k17 = pd.read_csv(FIXTURES / "K17_ecdf" / "data.csv")
    assert k17["x"].is_monotonic_increasing
    assert k17["probability"].is_monotonic_increasing
    assert k17["probability"].iloc[-1] == 1.0

    for chart_id, rows, columns in (("K20", "row", "column"), ("S61", "actual", "predicted")):
        case_dir = next(FIXTURES.glob(f"{chart_id}_*"))
        frame = pd.read_csv(case_dir / "data.csv")
        assert len(frame) == frame[rows].nunique() * frame[columns].nunique()
        assert frame["value"].notna().all()


def test_render_manifest_keeps_human_signature_pending_and_gap_blocking() -> None:
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["stage"] == "visual29-fixed"
    assert manifest["rules"]["same_source_required"] is True
    assert manifest["rules"]["synthetic_allowed"] is False
    assert {item["chart_type_id"] for item in manifest["cases"]} == set(EXPECTED_ANCHORED)
    assert {item["chart_type_id"] for item in manifest["evidence_gaps"]} == {"S07"}
    assert set(manifest["exports"]) == {"default", "edited"}
    assert all(item["fresh_reopen_identical"] for item in manifest["exports"].values())
    for case in manifest["cases"]:
        assert set(case["states"]) == {"default", "edited"}
        for state in case["states"].values():
            assert len(state["plot_spec_sha256"]) == 64
            assert len(state["render_plan_sha256"]) == 64
            assert len(state["matplotlib_png_sha256"]) == 64
            assert len(state["origin_fresh_png_sha256"]) == 64
    qualification = manifest["qualification"]
    assert qualification["decision"] == "NO-GO"
    assert qualification["human_visual_signature"]["status"] == "pending"
    source_identity = qualification["source_build_identity"]
    assert source_identity["scope_version"] == "visual29-fixed-rendering-v2"
    assert source_identity["digest_algorithm"] == "git-blob-framed-sha256-v1"
    s61 = next(item for item in manifest["cases"] if item["chart_type_id"] == "S61")
    k06 = next(item for item in manifest["cases"] if item["chart_type_id"] == "K06")
    for state in k06["states"].values():
        matplotlib = state["matplotlib_point_interval_evidence"]
        origin = state["origin_point_interval_evidence"]
        assert matplotlib["consumed"] is True
        assert matplotlib["has_xerr"] is matplotlib["has_yerr"] is True
        assert matplotlib["center_marker_count"] == matplotlib["row_count"] > 0
        assert matplotlib["horizontal_interval_count"] == matplotlib["row_count"]
        assert matplotlib["vertical_interval_count"] == matplotlib["row_count"]
        assert matplotlib["cap_line_count"] == 4
        assert origin["consumed"] is True
        assert origin["fresh_reopen"] is True
        assert origin["center_symbol_plot_count"] == 1
        assert origin["endpoint_symbol_plot_count"] == 0
        assert origin["segments_per_observation"] == 6
        assert origin["horizontal_interval_count"] == origin["row_count"]
        assert origin["vertical_interval_count"] == origin["row_count"]
    s61_consumed = all(
        state.get("matplotlib_annotation_evidence", {}).get("consumed") is True
        and state.get("origin_annotation_evidence", {}).get("consumed") is True
        for state in s61["states"].values()
    )
    blocker_codes = {
        (item["chart_type_id"], item["code"])
        for item in qualification["blocking_observations"]
    }
    expected_blockers = {("S07", "SAME_SOURCE_ORIGIN_DATA_MISSING")}
    if not s61_consumed:
        expected_blockers.update(
            {
                ("K06", "NATIVE_ERROR_BAR_CONNECTOR_MISMATCH"),
                ("K20", "NATIVE_COLORBAR_TICK_LABEL_COLLISION"),
                ("S61", "CONFUSION_CELL_LABELS_MISSING"),
            }
        )
    assert blocker_codes == expected_blockers
    case_blockers = {
        (case["chart_type_id"], blocker["code"])
        for case in manifest["cases"]
        for blocker in case["blocking_observations"]
    }
    expected_case_blockers: set[tuple[str, str]] = set()
    if not s61_consumed:
        expected_case_blockers.update(
            {
                ("K06", "NATIVE_ERROR_BAR_CONNECTOR_MISMATCH"),
                ("K20", "NATIVE_COLORBAR_TICK_LABEL_COLLISION"),
                ("S61", "CONFUSION_CELL_LABELS_MISSING"),
            }
        )
    assert case_blockers == expected_case_blockers
    if s61_consumed:
        for state in s61["states"].values():
            matplotlib = state["matplotlib_annotation_evidence"]
            origin = state["origin_annotation_evidence"]
            assert matplotlib["expected_count"] == matplotlib["rendered_count"] > 0
            assert matplotlib["text_position_match"] is True
            assert matplotlib["color_match"] is True
            assert matplotlib["center_alignment"] is True
            assert origin["expected_count"] == origin["native_label_count"] > 0
            assert origin["text_match"] is True
            assert origin["color_match"] is True
            assert origin["fresh_reopen"] is True
            assert origin["plan_contract_match"] is True
            assert origin["build_validation_passed"] is True
            assert origin["reopen_validation_passed"] is True
            assert matplotlib["contract_sha256"] == origin["contract_sha256"]
