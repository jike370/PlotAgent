from __future__ import annotations

from pathlib import Path

from scripts.run_release_data_stress_matrix import STRESS_CASE_IDS, execute


def test_release_data_stress_matrix_freezes_every_required_domain() -> None:
    assert STRESS_CASE_IDS == (
        "LARGE-K01-100K-RENDER",
        "MISSING-K01-GAPS",
        "MISSING-K20-HEATMAP",
        "EXTREME-K01-LINE",
        "EXTREME-K08-COLUMN",
        "DYNAMIC-X03-2-4-2",
        "DYNAMIC-X38-1-4-2",
        "DYNAMIC-X39-2-5-2",
    )
    assert len(set(STRESS_CASE_IDS)) == 8


def test_release_data_stress_matrix_executes_without_a_model(tmp_path: Path) -> None:
    output = tmp_path / "data-stress"

    results = execute(output, large_rows=1_000)

    assert tuple(item.case_id for item in results) == STRESS_CASE_IDS
    assert all(item.status == "PASS" for item in results)
    assert {item.domain for item in results} == {
        "large_render",
        "missing_values",
        "finite_extremes",
        "dynamic_series",
    }
    assert len(tuple((output / "artifacts").rglob("*.png"))) == 14
    assert (output / "matrix-results.csv").is_file()
    assert (output / "run-metadata.json").is_file()
    assert (output / "REPORT.md").is_file()
