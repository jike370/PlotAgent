from __future__ import annotations

import csv
import json
from pathlib import Path

from plotagent.engine.profiles import ENGINE_PROFILES
from scripts.release_matrix_cases import RELEASE_CASES
from scripts.run_release_matrix import execute_offline_matrix
from scripts.run_release_origin_matrix import (
    _edited_history,
    _load_offline_rows,
    _request,
)


def test_release_cases_freeze_all_public_profiles_and_three_variants() -> None:
    public_ids = {str(profile.profile_id) for profile in ENGINE_PROFILES}

    assert len(RELEASE_CASES) == 102
    assert {case.profile_id for case in RELEASE_CASES} == public_ids
    for profile_id in public_ids:
        cases = [case for case in RELEASE_CASES if case.profile_id == profile_id]
        assert {case.variant for case in cases} == {
            "minimal",
            "representative",
            "edge_error",
        }
        for case in cases:
            assert len(case.view.row_ids) > 0
            assert all(len(column.values) == len(case.view.row_ids) for column in case.view.columns)
            assert tuple(binding.field_id for binding in case.create.bindings) == tuple(
                column.field.field_id for column in case.view.columns
            )


def test_offline_release_matrix_executes_306_unique_keys(tmp_path: Path) -> None:
    output = tmp_path / "offline-matrix"

    rows = execute_offline_matrix(output, repository=Path(__file__).resolve().parents[2])

    assert len(rows) == 306
    assert len({row.matrix_key for row in rows}) == 306
    assert sum(row.status == "PASS" for row in rows) == 272
    assert sum(row.status == "FAIL" for row in rows) == 0
    assert sum(row.status == "UNVERIFIED" for row in rows) == 34
    assert {row.profile_id for row in rows if row.status == "UNVERIFIED"} == {
        str(profile.profile_id) for profile in ENGINE_PROFILES
    }
    assert all(
        row.variant == "representative" and row.format == "opju"
        for row in rows
        if row.status == "UNVERIFIED"
    )

    metadata = json.loads((output / "run-metadata.json").read_text(encoding="utf-8"))
    assert metadata["matrix_key_count"] == 306
    assert metadata["phase"] == "offline"
    with (output / "matrix-results.csv").open(encoding="utf-8-sig", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    assert len(csv_rows) == 306
    assert (output / "REPORT.md").is_file()
    assert len(tuple((output / "artifacts").glob("*/*/plot.png"))) == 68
    assert len(tuple((output / "artifacts").glob("*/*/plot.svg"))) == 68


def test_representative_origin_history_uses_a_fresh_linear_edit_version(
    tmp_path: Path,
) -> None:
    case = next(
        item
        for item in RELEASE_CASES
        if item.profile_id == "K01" and item.variant == "representative"
    )
    title, document = _edited_history(case)
    default = _request(
        case,
        install_dir=tmp_path,
        output=tmp_path / "default.opju",
        previous=None,
    )
    edited = _request(
        case,
        install_dir=tmp_path,
        output=tmp_path / "edited.opju",
        previous=tmp_path / "default.opju",
        title=title,
        document=document,
    )

    assert default.document.plot_version == 1
    assert default.previous_opju is None
    assert document.plot_version == 2
    assert document.parent_version == 1
    assert title.expected_plot_version == 1
    assert edited.previous_opju == str(tmp_path / "default.opju")
    assert tuple(action.action_id for action in edited.actions) == document.applied_action_ids


def test_origin_matrix_rebases_offline_artifacts_to_merged_report(
    tmp_path: Path,
) -> None:
    offline = tmp_path / "offline"
    output = tmp_path / "origin"
    rows = execute_offline_matrix(
        offline,
        repository=Path(__file__).resolve().parents[2],
    )
    output.mkdir()

    rebased = _load_offline_rows(offline, output)

    source = next(row for row in rows if row.artifact is not None)
    merged = next(row for row in rebased if row.matrix_key == source.matrix_key)
    assert merged.artifact is not None
    assert (output / merged.artifact).resolve() == (offline / source.artifact).resolve()
