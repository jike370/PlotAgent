from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from plotagent.rendering import PlotResolver
from plotagent.rendering.matplotlib.adapter import MatplotlibRenderer
from scripts.build_seq20_visual_baseline import (
    BATCHES,
    InputSeries,
    _build_plot,
    _edited_color_indices,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "visual_regression" / "seq20"
EXPECTED_BATCHES = {
    1: ("K01", "K02", "K03", "K08", "K18"),
    2: ("X01", "X02", "X09", "K05", "K09"),
    3: ("K10", "S05", "S25", "X03"),
    4: ("X39", "X40"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_seq20_common_edit_keeps_line_and_symbol_one_logical_color() -> None:
    values = ((0.0, 1.0), (2.0, 3.0))
    inputs = (
        InputSeries("line", "prepared", ("x", "y"), values, "Signal"),
        InputSeries("symbol", "prepared", ("x", "y"), values, "Signal"),
        InputSeries("line", "prepared", ("x", "y"), ((0.0, 1.0), (4.0, 5.0)), "Other"),
        InputSeries("symbol", "prepared", ("x", "y"), ((0.0, 1.0), (4.0, 5.0)), "Other"),
    )

    assert _edited_color_indices(inputs) == (0, 0, 1, 1)


@pytest.mark.parametrize("edited", (False, True), ids=("default", "edited"))
def test_seq20_k02_has_one_same_color_legend_in_both_backends(edited: bool) -> None:
    case = next(item for item in BATCHES[1] if item.chart_id == "K02")
    frame = pd.read_csv(FIXTURES / case.case_id / "data.csv")
    plot, store = _build_plot(case, frame, edited=edited)
    resolved = PlotResolver().resolve(plot, store)
    line, symbol = resolved.plan.layers

    assert resolved.plan.legend.visible is True
    assert line.color == symbol.color
    assert [layer.label is not None for layer in resolved.plan.layers] == [True, False]

    figure = MatplotlibRenderer().build_figure(resolved)
    try:
        legend = figure.axes[0].get_legend()
        assert legend is not None
        assert [item.get_text() for item in legend.get_texts()] == ["Signal"]
    finally:
        plt.close(figure)

    origin = compile_origin_plan((resolved,), build_origin_export_spec((resolved,)))
    graph = origin.graph_objects[0]
    origin_line, origin_symbol = graph.layers[0].plots
    assert graph.legend_visible is True
    assert origin_line.color == origin_symbol.color
    assert [item.label for item in graph.layers[0].plots if item.label] == ["Signal"]

@pytest.mark.parametrize("batch", (1, 2, 3, 4))
def test_seq20_frozen_same_source_evidence_manifest(batch: int) -> None:
    manifest_path = FIXTURES / f"batch-{batch}.manifest.json"
    assert manifest_path.is_file(), f"missing frozen SEQ-20 evidence batch {batch}"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["stage"] == "SEQ-20"
    assert manifest["batch"] == batch
    assert manifest["rules"]["same_source_required"] is True
    assert manifest["rules"]["synthetic_allowed"] is False
    assert tuple(item["chart_type_id"] for item in manifest["cases"]) == EXPECTED_BATCHES[batch]
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

    qualification = manifest["qualification"]
    assert qualification["blocking_observations"] == []
    assert qualification["human_visual_signature"]["status"] == "pending"
    source_identity = qualification["source_build_identity"]
    assert source_identity["scope_version"] == "seq20-rendering-v2"
    assert source_identity["digest_algorithm"] == "git-blob-framed-sha256-v1"
    assert len(source_identity["source_sha256"]) == 64
    assert "automated P0 blockers closed" in manifest["audit_conclusion"]
    assert "visual qualification passed" not in manifest["audit_conclusion"]
