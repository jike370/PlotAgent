from __future__ import annotations

from pathlib import Path

from scripts.run_release_operational_matrix import (
    BATCH_NODEIDS,
    _import_case,
    _write_large_csv,
)


def test_operational_matrix_freezes_batch_and_recovery_cases() -> None:
    assert len(BATCH_NODEIDS) == 6
    assert len(set(BATCH_NODEIDS)) == 6
    assert any("confirmed_batch" in nodeid for nodeid in BATCH_NODEIDS)
    assert any("partially" in nodeid or "partial" in nodeid for nodeid in BATCH_NODEIDS)
    assert any("restart" in nodeid for nodeid in BATCH_NODEIDS)
    assert any("cancellation" in nodeid for nodeid in BATCH_NODEIDS)


def test_large_import_probe_uses_real_csv_and_reports_a_committed_dataset(
    tmp_path: Path,
) -> None:
    source = tmp_path / "large.csv"
    _write_large_csv(source, rows=1000)

    result = _import_case(
        tmp_path / "evidence",
        case_id="IMPORT-CSV-1K",
        source=source,
        expected_datasets=1,
        expected_rows=1000,
    )

    assert result.status == "PASS"
    assert "datasets=1" in result.observation
    assert "rows=[1000]" in result.observation
    assert result.duration_ms > 0
    assert result.peak_python_mb is not None and result.peak_python_mb > 0
    assert not (tmp_path / "evidence" / "workspaces" / "IMPORT-CSV-1K").exists()
