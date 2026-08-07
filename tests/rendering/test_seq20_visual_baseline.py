from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "visual_regression" / "seq20"
EXPECTED_BATCHES = {
    1: ("K01", "K02", "K03", "K08", "K18"),
    2: ("X01", "X02", "X09", "K05", "K09"),
    3: ("K10", "S05", "S25", "X03"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("batch", (1, 2, 3))
def test_seq20_frozen_same_source_manifest(batch: int) -> None:
    manifest_path = FIXTURES / f"batch-{batch}.manifest.json"
    if not manifest_path.is_file():
        pytest.skip(f"SEQ-20 batch {batch} has not been frozen yet")
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
