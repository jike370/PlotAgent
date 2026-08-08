from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, cast

import pandas as pd

from plotagent.origin import build_origin_export_spec, compile_origin_plan
from plotagent.rendering.matplotlib.adapter import MatplotlibRenderer
from scripts.build_visual29_structural_synthetic import (
    CASES,
    FIXTURES,
    GENERATOR_ID,
    GENERATOR_VERSION,
    SEED,
    SOURCE_SCOPE,
    SOURCE_SCOPE_VERSION,
    build_resolved,
    generate_frame,
)
from scripts.visual_source_identity import source_build_identity

REPOSITORY = Path(__file__).resolve().parents[2]
OUTPUT = REPOSITORY / "build" / "visual-audit" / "visual29-structural-synthetic"
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _no_panel_overlap(resolved: object) -> bool:
    panels = resolved.plan.panels  # type: ignore[attr-defined]
    for index, first in enumerate(panels):
        for second in panels[index + 1 :]:
            separated = (
                first.left.value + first.width.value <= second.left.value
                or second.left.value + second.width.value <= first.left.value
                or first.top.value + first.height.value <= second.top.value
                or second.top.value + second.height.value <= first.top.value
            )
            if not separated:
                return False
    return True


def _artist_overlaps(first: object, second: object, renderer: Any) -> bool:
    first_box = first.get_window_extent(renderer)  # type: ignore[attr-defined]
    second_box = second.get_window_extent(renderer)  # type: ignore[attr-defined]
    return bool(
        first_box.x0 < second_box.x1
        and second_box.x0 < first_box.x1
        and first_box.y0 < second_box.y1
        and second_box.y0 < first_box.y1
    )


def test_d_grade_synthetic_inputs_are_frozen_and_never_claim_official_admission() -> None:
    for case in CASES:
        case_dir = FIXTURES / case.case_id
        provenance = json.loads((case_dir / "provenance.json").read_text(encoding="utf-8"))
        assert provenance["chart_type_id"] == case.chart_id
        assert provenance["evidence_grade"] == "D"
        assert provenance["synthetic"] is True
        assert provenance["same_source_data"] is True
        assert provenance["origin_official_same_source_admission"] is False
        assert provenance["generator"] == {
            "id": GENERATOR_ID,
            "version": GENERATOR_VERSION,
            "seed": SEED,
            "algorithm": (
                "closed-form deterministic synthetic generator; "
                "no fitted or inferred values"
            ),
        }
        assert provenance["reference_generation"]["plotagent_renderer_used"] is False
        assert provenance["reference_generation"]["raw_csv_embedded"] is True
        assert provenance["reference_generation"]["raw_worksheet"] == (
            f"DRef{case.chart_id}Raw"
        )
        assert Path(provenance["reference_generation"]["origin_template"]).is_file()
        assert provenance["data_sha256"] == _sha256(case_dir / "data.csv")


def test_synthetic_generators_are_deterministic() -> None:
    for chart_id, group_count, point_count in (
        ("K24", 5, 13),
        ("K25", 4, 9),
        ("S01", 4, 12),
    ):
        first = generate_frame(chart_id, group_count=group_count, point_count=point_count)
        second = generate_frame(chart_id, group_count=group_count, point_count=point_count)
        pd.testing.assert_frame_equal(first, second)


def test_k24_facets_generalise_across_group_count_and_range() -> None:
    for facet_count, point_count in ((2, 7), (3, 9), (5, 13)):
        frame = generate_frame("K24", group_count=facet_count, point_count=point_count)
        for edited in (False, True):
            resolved = build_resolved("K24", frame, edited=edited)
            assert len(resolved.plan.panels) == facet_count
            assert len(resolved.plan.layers) == facet_count
            assert resolved.plan.data_integrity.visible_rows == facet_count * point_count
            assert _no_panel_overlap(resolved)
            assert all(layer.geometry == "facet.xy" for layer in resolved.plan.layers)


def test_k25_explicit_child_plans_generalise_from_two_to_four_panels() -> None:
    for panel_count, point_count in ((2, 7), (3, 11), (4, 9)):
        frame = generate_frame("K25", group_count=panel_count, point_count=point_count)
        for edited in (False, True):
            resolved = build_resolved("K25", frame, edited=edited)
            assert len(resolved.plan.panels) == panel_count
            assert len(resolved.plan.layers) == panel_count
            assert resolved.plan.data_integrity.visible_rows == panel_count * point_count
            assert _no_panel_overlap(resolved)
            assert {layer.data_source_kind for layer in resolved.plan.layers} == {"panel_plan"}
            assert len({layer.panel_id for layer in resolved.plan.layers}) == panel_count


def test_s01_precomputed_structure_generalises_without_survival_analysis() -> None:
    for group_count, point_count in ((1, 7), (2, 9), (4, 12)):
        frame = generate_frame("S01", group_count=group_count, point_count=point_count)
        for _group, selected in frame.groupby("group", sort=False):
            survival = selected["survival"].tolist()
            assert survival == sorted(survival, reverse=True)
            assert (selected["lower"] <= selected["survival"]).all()
            assert (selected["survival"] <= selected["upper"]).all()
            assert selected["risk_count"].tolist() == sorted(
                selected["risk_count"].tolist(), reverse=True
            )
        for edited in (False, True):
            resolved = build_resolved("S01", frame, edited=edited)
            assert len(resolved.plan.panels) == 2
            assert len(resolved.plan.layers) == group_count * 3
            assert resolved.plan.data_integrity.visible_rows == group_count * point_count * 3
            assert _no_panel_overlap(resolved)
            assert {layer.geometry for layer in resolved.plan.layers} == {
                "special.survival_step",
                "special.survival_band",
                "special.risk_table",
            }
            assert all(
                layer.panel_id == "panel:risk"
                for layer in resolved.plan.layers
                if layer.geometry == "special.risk_table"
            )
            for geometry in (
                "special.survival_step",
                "special.survival_band",
                "special.risk_table",
            ):
                colors = {
                    layer.color.value
                    for layer in resolved.plan.layers
                    if layer.geometry == geometry and layer.color is not None
                }
                assert len(colors) == group_count


def test_s01_rendered_risk_layout_generalises_without_text_collisions() -> None:
    risk_panel_heights: list[float] = []
    for group_count in (1, 2, 4):
        frame = generate_frame("S01", group_count=group_count, point_count=9)
        for edited in (False, True):
            resolved = build_resolved("S01", frame, edited=edited)
            risk_panel = next(
                panel for panel in resolved.plan.panels if panel.panel_id == "panel:risk"
            )
            if not edited:
                risk_panel_heights.append(risk_panel.height.value)
            figure = MatplotlibRenderer().build_figure(resolved)
            figure.canvas.draw()
            renderer = cast(Any, figure.canvas).get_renderer()
            main_axis = next(
                axis for axis in figure.axes if axis.get_label() == "panel:main"
            )
            risk_axis = next(
                axis for axis in figure.axes if axis.get_label() == "panel:risk"
            )
            row_text = tuple(
                item
                for item in risk_axis.texts
                if (item.get_gid() or "").startswith("plotagent-risk-row:")
            )
            assert len({item.get_gid() for item in row_text}) == group_count

            assert all(
                not _artist_overlaps(first, second, renderer)
                for index, first in enumerate(row_text)
                for second in row_text[index + 1 :]
                if first.get_gid() != second.get_gid()
            )
            visible_ticks = tuple(
                item
                for item in main_axis.get_xticklabels()
                if item.get_visible() and item.get_text()
            )
            assert all(
                not _artist_overlaps(tick, item, renderer)
                for tick in visible_ticks
                for item in row_text
            )
            assert main_axis.get_xlabel() == ""
            x_labels = tuple(
                item
                for item in risk_axis.texts
                if item.get_gid() == "plotagent-risk-x-label"
            )
            assert len(x_labels) == 1
            assert all(
                not _artist_overlaps(x_labels[0], item, renderer) for item in row_text
            )
    assert risk_panel_heights == sorted(risk_panel_heights)
    assert len(set(risk_panel_heights)) == 3


def test_s01_risk_panel_has_target_neutral_axes_and_compiles_to_origin() -> None:
    resolved = build_resolved("S01", generate_frame("S01"))
    risk_axes = tuple(axis for axis in resolved.plan.axes if axis.panel_id == "panel:risk")
    assert {axis.orientation for axis in risk_axes} == {"x", "y"}
    assert len(risk_axes) == 2
    origin_plan = compile_origin_plan(
        (resolved,), build_origin_export_spec((resolved,), export_id="export:test.s01.risk")
    )
    risk_layer = next(
        layer for layer in origin_plan.graph_objects[0].layers if layer.panel_id == "panel:risk"
    )
    assert {axis.orientation for axis in risk_layer.axes} == {"x", "y"}
    assert risk_layer.plots


def test_rendered_d_grade_manifest_has_independent_reference_and_two_native_states() -> None:
    manifest_path = FIXTURES / "manifest.json"
    assert manifest_path.is_file(), "run the structural synthetic audit after Origin is available"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["stage"] == "VISUAL29-STRUCTURAL-SYNTHETIC-D"
    assert manifest["lane_chart_type_ids"] == ["K24", "K25", "S01"]
    assert manifest["rules"]["evidence_grade"] == "D"
    assert manifest["rules"]["origin_official_same_source_admission"] is False
    assert manifest["rules"]["independent_origin_reference_required"] is True
    assert manifest["evidence_gaps"] == []
    assert manifest["qualification"]["blocking_observations"] == []
    assert manifest["qualification"]["human_visual_signature"]["status"] == "pending"
    assert manifest["qualification"]["decision"] == "NO-GO"
    source_identity = manifest["qualification"]["source_build_identity"]
    assert source_identity["scope_version"] == SOURCE_SCOPE_VERSION
    assert source_identity["digest_algorithm"] == "git-blob-framed-sha256-v1"
    assert _GIT_COMMIT.fullmatch(source_identity["git_commit"]) is not None
    assert _SHA256.fullmatch(source_identity["source_sha256"]) is not None
    assert source_identity == source_build_identity(
        REPOSITORY,
        SOURCE_SCOPE,
        scope_version=SOURCE_SCOPE_VERSION,
    )
    for case in manifest["cases"]:
        case_dir = OUTPUT / case["case_id"]
        fixture_dir = FIXTURES / case["case_id"]
        assert case["evidence_grade"] == "D"
        assert case["reference_generation"]["plotagent_renderer_used"] is False
        assert case["reference_fresh_reopen"] is True
        assert case["reference_sha256"] == _sha256(fixture_dir / "reference.png")
        assert set(case["states"]) == {"default", "edited"}
        for state in case["states"].values():
            assert state["origin_export_status"] == "success"
            assert state["fresh_reopen_identical"] is True
            assert state["origin_opju_size"] > 0
        assert case["per_chart_opju"]["fresh_reopen_identical"] is True
        assert (case_dir / f"{case['chart_type_id']}.opju").is_file()
        assert (case_dir / "comparison-default.png").is_file()
        assert (case_dir / "comparison-edited.png").is_file()
