from pathlib import Path

import pytest

from plotagent.evaluation.suite import load_migrated_seq70_suite

REPOSITORY = Path(__file__).resolve().parents[2]
OVERLAY = REPOSITORY / "tests" / "fixtures" / "evaluation" / "agent-foundation-v2-suite.json"


def test_migrates_all_24_seq70_cases_to_versioned_eval_contracts() -> None:
    cases = load_migrated_seq70_suite(REPOSITORY, OVERLAY)
    assert len(cases) == 24
    assert len({case.eval_case_id for case in cases}) == 24
    assert sum(case.layer == "E3" for case in cases) == 18
    assert sum(case.layer == "E2" for case in cases) == 6
    assert all(case.blocks_release for case in cases)
    assert all(case.trial_count == (3 if case.layer == "E3" else 1) for case in cases)
    assert all(len(case.graders) == 2 for case in cases)


def test_refuses_silent_changes_to_the_frozen_legacy_source(tmp_path: Path) -> None:
    overlay = tmp_path / "suite.json"
    overlay.write_bytes(OVERLAY.read_bytes())
    repository = tmp_path / "repo"
    target = repository / "tests" / "fixtures" / "seq70"
    target.mkdir(parents=True)
    (target / "workflow_tasks.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="byte length changed"):
        load_migrated_seq70_suite(repository, overlay)
