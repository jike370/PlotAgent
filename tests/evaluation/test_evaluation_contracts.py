from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from plotagent.evaluation.contracts import (
    EvalBudget,
    EvalCase,
    EvalPolicy,
    EvalSelection,
    EvalTrial,
    EvidenceArtifact,
    EvidenceManifest,
    EvidenceRequirement,
    FixtureAsset,
    GraderResult,
    GraderSpec,
    MetricThreshold,
)
from plotagent.evaluation.runner import (
    aggregate_evaluation,
    verify_evidence_files,
    write_evaluation_report,
)

SHA = "a" * 64
NOW = datetime(2026, 8, 18, tzinfo=UTC)


def budget() -> EvalBudget:
    return EvalBudget(
        max_wall_time_seconds=30,
        max_model_turns=4,
        max_tool_calls=8,
        max_repairs=1,
        max_input_tokens=10_000,
        max_output_tokens=2_000,
        max_estimated_cost=0.1,
    )


def case(*, layer: str = "E2", trials: int | None = 1) -> EvalCase:
    fixture = FixtureAsset(
        fixture_id="fixture:xy",
        path="fixtures/xy.csv",
        sha256=SHA,
        byte_length=10,
    )
    return EvalCase(
        eval_case_id="case:durable",
        suite_id="suite:foundation",
        suite_version=1,
        layer=layer,
        suite_kind="regression",
        claim="确认前项目版本不变化，确认后只产生一个已验证图形版本。",
        instruction="用 K01 绘制这张表。",
        fixtures=(fixture,),
        selection=EvalSelection(
            source_fixture_ids=(fixture.fixture_id,),
            profile_ids=("K01",),
        ),
        budget=budget(),
        required_outcomes=("一个 completed_verified durable task",),
        forbidden_outcomes=("确认前写入项目", "重复图形版本"),
        graders=(GraderSpec(
            grader_id="grader:checkpoint",
            kind="deterministic",
            claim="检查 durable checkpoint 与项目 revision。",
        ),),
        evidence_requirements=(EvidenceRequirement(
            requirement_id="evidence:checkpoint",
            artifact_kind="task_checkpoint",
            description="保存最终 durable task checkpoint。",
        ),),
        trial_count=trials,
    )


def policy() -> EvalPolicy:
    return EvalPolicy(
        policy_id="policy:release",
        suite_id="suite:foundation",
        suite_version=1,
        frozen_at=NOW,
        required_layers=("E2",),
        trials_by_layer={"E2": 1},
        thresholds=(MetricThreshold(
            metric="confirmation_no_side_effect_rate",
            direction="minimum",
            value=1.0,
        ),),
    )


def evidence() -> EvidenceManifest:
    return EvidenceManifest(
        manifest_id="manifest:one",
        eval_case_id="case:durable",
        trial_id="trial:one",
        git_commit=SHA,
        generated_at=NOW,
        artifacts=(EvidenceArtifact(
            artifact_id="artifact:checkpoint",
            kind="task_checkpoint",
            path="evidence/checkpoint.json",
            sha256=SHA,
            byte_length=10,
        ),),
        environment={"platform": "win32"},
    )


def trial(status: str = "PASS") -> EvalTrial:
    return EvalTrial(
        trial_id="trial:one",
        eval_case_id="case:durable",
        trial_index=1,
        status=status,
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=1),
        git_commit=SHA,
        evidence_manifest_id="manifest:one",
        grader_results=(GraderResult(
            grader_id="grader:checkpoint",
            kind="deterministic",
            status=status,
            summary="项目 revision 与 checkpoint 已核验。",
        ),),
        metrics={"confirmation_no_side_effect_rate": 1.0},
        **({} if status == "PASS" else {"failure_message": "observed failure"}),
    )


def test_rejects_selected_fixture_that_is_not_frozen() -> None:
    value = case().model_dump(mode="python")
    value["selection"] = EvalSelection(source_fixture_ids=("fixture:missing",))
    with pytest.raises(ValidationError, match="fixture manifest"):
        EvalCase.model_validate(value)


def test_missing_trial_is_unverified_and_blocks_release() -> None:
    result = aggregate_evaluation(
        run_id="run:missing",
        git_commit=SHA,
        cases=(case(trials=3),),
        policy=policy(),
        trials=(trial(),),
        evidence=(evidence(),),
        generated_at=NOW,
    )
    assert result.decision == "NO_GO"
    assert result.case_results[0].status == "UNVERIFIED"
    assert "blocking case case:durable is UNVERIFIED" in result.gate_failures


def test_mismatched_evidence_is_eval_invalid() -> None:
    broken = evidence().model_copy(update={"trial_id": "trial:other"})
    result = aggregate_evaluation(
        run_id="run:invalid",
        git_commit=SHA,
        cases=(case(),),
        policy=policy(),
        trials=(trial(),),
        evidence=(broken,),
        generated_at=NOW,
    )
    assert result.decision == "EVAL_INVALID"
    assert any("evidence identity mismatch" in item for item in result.gate_failures)


def test_complete_trial_and_evidence_produce_go_and_required_reports(tmp_path: Path) -> None:
    result = aggregate_evaluation(
        run_id="run:go",
        git_commit=SHA,
        cases=(case(),),
        policy=policy(),
        trials=(trial(),),
        evidence=(evidence(),),
        generated_at=NOW,
    )
    assert result.decision == "GO"
    write_evaluation_report(
        tmp_path,
        result,
        policy=policy(),
        cases=(case(),),
        trials=(trial(),),
        evidence=(evidence(),),
    )
    assert {
        "run-metadata.json",
        "fixture-manifest.json",
        "eval-policy.json",
        "case-results.csv",
        "report.json",
        "REPORT.md",
    }.issubset(path.name for path in tmp_path.iterdir())


def test_evidence_hashes_are_recomputed_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "evidence" / "checkpoint.json"
    path.parent.mkdir()
    path.write_bytes(b"0123456789")
    assert verify_evidence_files(tmp_path, evidence()) == (
        "artifact:checkpoint: SHA-256 mismatch",
    )
