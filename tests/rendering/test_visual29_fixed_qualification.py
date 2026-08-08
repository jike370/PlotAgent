from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from plotagent.rendering import PlotResolver
from scripts import build_visual29_fixed as builder
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
    "S07": "D",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fixed_visual_evidence_separates_ac_same_source_from_d_synthetic() -> None:
    index = json.loads((FIXTURES / "evidence-index.json").read_text(encoding="utf-8"))

    assert index["stage"] == "visual29-fixed"
    assert index["rules"] == {
        "official_same_source_required_for_grades": ["A", "C"],
        "synthetic_origin_reference_allowed_for": ["S07"],
        "synthetic_evidence_grade": "D",
        "origin_official_same_source_admission_for_D": False,
        "missing_data_is_not_rendered": True,
    }
    anchored = {item["chart_type_id"]: item for item in index["anchored_cases"]}
    grades = {chart_id: item["evidence_grade"] for chart_id, item in anchored.items()}
    assert grades == EXPECTED_ANCHORED
    for chart_id, item in anchored.items():
        assert item["same_source_data"] is True
        assert item["synthetic"] is (chart_id == "S07")
        assert item["origin_official_same_source_admission"] is (chart_id != "S07")
        case_dir = next(FIXTURES.glob(f"{chart_id}_*"))
        assert _sha256(case_dir / "data.csv") == item["data_sha256"]
        assert _sha256(case_dir / "reference.png") == item["reference_sha256"]


def test_s07_is_explicit_d_grade_origin_generated_synthetic_evidence() -> None:
    case_dir = FIXTURES / "S07_volcano"
    provenance = json.loads((case_dir / "provenance.json").read_text(encoding="utf-8"))

    assert provenance["chart_type_id"] == "S07"
    assert provenance["evidence_status"] == "synthetic_origin_reference_anchored"
    assert provenance["evidence_grade"] == "D"
    assert provenance["admission_class"] == "D_synthetic_origin_reference"
    assert provenance["synthetic"] is True
    assert provenance["origin_official_same_source_admission"] is False
    assert provenance["reference_and_test_use_identical_csv"] is True
    assert provenance["synthetic_generator"] == {
        "name": builder.SYNTHETIC_GENERATOR_VERSION,
        "seed": builder.SYNTHETIC_SEED,
        "bit_generator": "PCG64",
        "row_count": 48,
        "rules": provenance["synthetic_generator"]["rules"],
    }
    reference = provenance["origin_reference"]
    assert reference["construction_path"] == "independent_origin_native"
    assert reference["plotagent_renderer_used"] is False
    assert reference["origin_template"] == "SCATTER"
    assert reference["origin_menu_equivalent"] == "Plot > Basic 2D > Scatter"
    assert reference["fresh_reopen"] is True
    assert reference["embedded_input_matches_csv"] is True
    assert reference["embedded_row_count"] == 48
    assert reference["native_plot_count"] == 6
    assert reference["native_plot_types"] == [
        "scatter", "scatter", "scatter", "line", "line", "line"
    ]
    assert reference["thresholds"] == {
        "absolute_log2_fold_change": 1.0,
        "pvalue": 0.05,
    }
    assert all(reference["class_counts"][label] > 0 for label in ("Down", "Not significant", "Up"))
    assert len(reference["reference_opju_sha256"]) == 64
    assert not (case_dir / "evidence-gap.json").exists()


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

    s07 = pd.read_csv(FIXTURES / "S07_volcano" / "data.csv")
    assert tuple(s07.columns) == ("feature", "log2fc", "pvalue")
    assert len(s07) == 48
    assert s07["feature"].is_unique
    assert np.isfinite(s07["log2fc"]).all()
    assert ((s07["pvalue"] > 0) & (s07["pvalue"] <= 1)).all()
    classes = np.select(
        (
            (s07["pvalue"] < 0.05) & (s07["log2fc"] <= -1.0),
            (s07["pvalue"] < 0.05) & (s07["log2fc"] >= 1.0),
        ),
        ("Down", "Up"),
        default="Not significant",
    )
    assert set(classes) == {"Down", "Not significant", "Up"}


def test_s07_resolution_generalizes_to_more_rows_and_wider_ranges() -> None:
    case = next(item for item in builder.CASES if item.chart_id == "S07")
    baseline = pd.read_csv(FIXTURES / case.case_id / "data.csv")
    expanded = baseline.copy()
    expanded["feature"] = expanded["feature"].map(lambda value: f"expanded_{value}")
    expanded["log2fc"] = expanded["log2fc"] * 1.8
    expanded["pvalue"] = np.maximum(expanded["pvalue"] * 0.1, 1e-12)
    expanded = pd.concat((baseline, expanded), ignore_index=True)

    for frame in (baseline.iloc[:24].reset_index(drop=True), baseline, expanded):
        for edited in (False, True):
            plot, store = builder._build_plot(case, frame, edited=edited)
            resolved = PlotResolver().resolve(plot, store)
            symbols = [item for item in resolved.plan.layers if item.geometry == "xy.symbol"]
            thresholds = [item for item in resolved.plan.layers if item.geometry == "xy.line"]
            assert sum(item.displayed_row_count for item in symbols) == len(frame)
            assert len({item.color.value for item in symbols if item.color is not None}) == 3
            assert len(thresholds) == 3
            x_axis = next(
                item
                for item in resolved.plan.axes
                if item.orientation == "x" and item.panel_id == "panel:main"
            )
            y_axis = next(
                item
                for item in resolved.plan.axes
                if item.orientation == "y" and item.panel_id == "panel:main"
            )
            assert x_axis.minimum is not None and x_axis.maximum is not None
            assert np.isclose(abs(x_axis.minimum), abs(x_axis.maximum))
            assert x_axis.minimum <= frame["log2fc"].min()
            assert x_axis.maximum >= frame["log2fc"].max()
            y_values = -np.log10(frame["pvalue"].to_numpy(dtype=float))
            assert y_axis.minimum is not None and y_axis.maximum is not None
            assert y_axis.minimum <= float(y_values.min())
            assert y_axis.maximum >= float(y_values.max())


def test_render_manifest_keeps_human_signature_pending_and_gap_blocking() -> None:
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["stage"] == "visual29-fixed"
    assert manifest["rules"]["official_same_source_required_for_grades"] == ["A", "C"]
    assert manifest["rules"]["synthetic_origin_reference_allowed_for"] == ["S07"]
    assert manifest["rules"]["synthetic_evidence_grade"] == "D"
    assert manifest["rules"]["origin_official_same_source_admission_for_D"] is False
    assert {item["chart_type_id"] for item in manifest["cases"]} == set(EXPECTED_ANCHORED)
    assert manifest["evidence_gaps"] == []
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
    current_identity = builder.source_build_identity(
        builder.REPOSITORY,
        builder.SOURCE_SCOPE,
        scope_version=builder.SOURCE_SCOPE_VERSION,
    )
    assert source_identity["source_sha256"] == current_identity["source_sha256"]
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
    expected_blockers: set[tuple[str, str]] = set()
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
