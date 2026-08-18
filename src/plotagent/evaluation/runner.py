"""Deterministic aggregation and evidence writing for versioned eval suites."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from plotagent.evaluation.contracts import (
    EvalCase,
    EvalCaseResult,
    EvalPolicy,
    EvalRunReport,
    EvalStatus,
    EvalTrial,
    EvidenceManifest,
)


def _status_for_trials(trials: Sequence[EvalTrial], expected: int) -> EvalStatus:
    statuses = {trial.status for trial in trials}
    if "EVAL_INVALID" in statuses:
        return "EVAL_INVALID"
    if "FAIL" in statuses:
        return "FAIL"
    if "BLOCKED" in statuses:
        return "BLOCKED"
    if len(trials) != expected or "UNVERIFIED" in statuses:
        return "UNVERIFIED"
    if all(trial.status == "PASS" for trial in trials):
        return "PASS"
    return "UNVERIFIED"


def _threshold_passes(direction: str, observed: float, expected: float) -> bool:
    return observed >= expected if direction == "minimum" else observed <= expected


def verify_evidence_files(root: Path, manifest: EvidenceManifest) -> tuple[str, ...]:
    """Verify evidence using relative paths only; never trust a reported hash or size."""

    failures: list[str] = []
    resolved_root = root.resolve()
    for artifact in manifest.artifacts:
        path = (resolved_root / artifact.path).resolve()
        try:
            path.relative_to(resolved_root)
        except ValueError:
            failures.append(f"{artifact.artifact_id}: path escaped evidence root")
            continue
        if not path.is_file():
            failures.append(f"{artifact.artifact_id}: file is missing")
            continue
        payload = path.read_bytes()
        if len(payload) != artifact.byte_length:
            failures.append(f"{artifact.artifact_id}: byte length mismatch")
        if hashlib.sha256(payload).hexdigest() != artifact.sha256:
            failures.append(f"{artifact.artifact_id}: SHA-256 mismatch")
    return tuple(failures)


def aggregate_evaluation(
    *,
    run_id: str,
    git_commit: str,
    cases: Sequence[EvalCase],
    policy: EvalPolicy,
    trials: Sequence[EvalTrial],
    evidence: Sequence[EvidenceManifest],
    generated_at: datetime | None = None,
) -> EvalRunReport:
    """Aggregate immutable trials without mutating, dropping, or selectively rerunning failures."""

    failures: list[str] = []
    case_by_id = {case.eval_case_id: case for case in cases}
    if len(case_by_id) != len(cases):
        failures.append("eval case ids are not unique")
    if any(
        case.suite_id != policy.suite_id or case.suite_version != policy.suite_version
        for case in cases
    ):
        failures.append("case suite identity does not match the frozen policy")
    if any(trial.git_commit != git_commit for trial in trials):
        failures.append("trials were not produced from the frozen commit")

    trial_ids = tuple(trial.trial_id for trial in trials)
    if len(trial_ids) != len(set(trial_ids)):
        failures.append("trial ids are not unique")
    manifest_by_id = {manifest.manifest_id: manifest for manifest in evidence}
    if len(manifest_by_id) != len(evidence):
        failures.append("evidence manifest ids are not unique")
    for trial in trials:
        case = case_by_id.get(trial.eval_case_id)
        if case is None:
            failures.append(f"{trial.trial_id}: unknown eval case")
            continue
        manifest = manifest_by_id.get(trial.evidence_manifest_id)
        if manifest is None:
            failures.append(f"{trial.trial_id}: evidence manifest is missing")
            continue
        if manifest.eval_case_id != trial.eval_case_id or manifest.trial_id != trial.trial_id:
            failures.append(f"{trial.trial_id}: evidence identity mismatch")
        if manifest.git_commit != trial.git_commit:
            failures.append(f"{trial.trial_id}: evidence commit mismatch")
        grader_by_id = {result.grader_id: result for result in trial.grader_results}
        for grader in case.graders:
            if grader.required and grader.grader_id not in grader_by_id:
                failures.append(f"{trial.trial_id}: required grader {grader.grader_id} is missing")
        kinds = Counter(artifact.kind for artifact in manifest.artifacts)
        for requirement in case.evidence_requirements:
            if kinds[requirement.artifact_kind] < requirement.minimum_count:
                failures.append(
                    f"{trial.trial_id}: evidence {requirement.requirement_id} is incomplete"
                )

    trials_by_case: dict[str, list[EvalTrial]] = defaultdict(list)
    for trial in trials:
        trials_by_case[trial.eval_case_id].append(trial)
    case_results: list[EvalCaseResult] = []
    for case in cases:
        case_trials = sorted(
            trials_by_case.get(case.eval_case_id, []),
            key=lambda item: item.trial_index,
        )
        expected = case.trial_count or policy.trials_by_layer.get(case.layer, 1)
        indices = tuple(trial.trial_index for trial in case_trials)
        if len(indices) != len(set(indices)) or any(index > expected for index in indices):
            failures.append(f"{case.eval_case_id}: trial indices violate the frozen trial policy")
        status = _status_for_trials(case_trials, expected)
        passed = sum(trial.status == "PASS" for trial in case_trials)
        case_results.append(EvalCaseResult(
            eval_case_id=case.eval_case_id,
            layer=case.layer,
            status=status,
            passed_trials=passed,
            expected_trials=expected,
            observed_trials=len(case_trials),
            trial_ids=tuple(trial.trial_id for trial in case_trials),
            summary=f"{passed}/{expected} trials passed; observed {len(case_trials)}",
        ))

    metrics: dict[str, float] = {}
    for layer in policy.required_layers:
        selected = [result for result in case_results if result.layer == layer]
        metrics[f"{layer.lower()}_case_pass_rate"] = (
            sum(result.status == "PASS" for result in selected) / len(selected)
            if selected else 0.0
        )
    metric_values: dict[str, list[float]] = defaultdict(list)
    for trial in trials:
        for name, value in trial.metrics.items():
            metric_values[name].append(value)
    for name, values in metric_values.items():
        metrics[name] = sum(values) / len(values)

    for threshold in policy.thresholds:
        metric_observed = metrics.get(threshold.metric)
        if metric_observed is None:
            failures.append(f"metric {threshold.metric} is missing")
        elif not _threshold_passes(threshold.direction, metric_observed, threshold.value):
            operator = ">=" if threshold.direction == "minimum" else "<="
            failures.append(
                f"{threshold.metric}={metric_observed:.6f} does not satisfy "
                f"{operator}{threshold.value:.6f}"
            )
    for case, result in zip(cases, case_results, strict=True):
        if case.blocks_release and result.status != "PASS":
            failures.append(f"blocking case {case.eval_case_id} is {result.status}")
    for layer in ("E0", "E1", "E2"):
        if (
            layer in policy.required_layers
            and metrics.get(f"{layer.lower()}_case_pass_rate") != 1.0
        ):
            failures.append(f"{layer} deterministic release gate is not 100%")

    invalid = any(
        marker in failure
        for failure in failures
        for marker in (
            "not unique",
            "unknown eval case",
            "evidence identity mismatch",
            "evidence commit mismatch",
            "required grader",
            "trial indices",
            "suite identity",
            "frozen commit",
        )
    ) or any(result.status == "EVAL_INVALID" for result in case_results)
    decision: Literal["GO", "NO_GO", "EVAL_INVALID"] = (
        "EVAL_INVALID" if invalid else "NO_GO" if failures else "GO"
    )
    return EvalRunReport(
        run_id=run_id,
        policy_id=policy.policy_id,
        suite_id=policy.suite_id,
        suite_version=policy.suite_version,
        git_commit=git_commit,
        generated_at=generated_at or datetime.now(UTC),
        decision=decision,
        case_results=tuple(case_results),
        metrics=metrics,
        gate_failures=tuple(dict.fromkeys(failures)),
    )


def write_evaluation_report(
    output_dir: Path,
    report: EvalRunReport,
    *,
    policy: EvalPolicy,
    cases: Iterable[EvalCase],
    trials: Iterable[EvalTrial],
    evidence: Iterable[EvidenceManifest],
) -> None:
    """Write the mandatory machine and human artifacts for one immutable aggregation."""

    output_dir.mkdir(parents=True, exist_ok=True)
    case_values = tuple(cases)
    trial_values = tuple(trials)
    evidence_values = tuple(evidence)
    (output_dir / "eval-policy.json").write_text(
        policy.model_dump_json(indent=2), encoding="utf-8"
    )
    (output_dir / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (output_dir / "fixture-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "eval-fixtures.v1",
                "fixtures": [
                    fixture.model_dump(mode="json")
                    for case in case_values
                    for fixture in case.fixtures
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "run-metadata.json").write_text(
        json.dumps(
            {
                "schema_version": "eval-run-metadata.v1",
                "run_id": report.run_id,
                "git_commit": report.git_commit,
                "suite_id": report.suite_id,
                "suite_version": report.suite_version,
                "generated_at": report.generated_at.isoformat(),
                "case_count": len(case_values),
                "trial_count": len(trial_values),
                "evidence_manifest_count": len(evidence_values),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    with (output_dir / "case-results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow((
            "eval_case_id", "layer", "status", "passed_trials", "expected_trials",
            "observed_trials", "trial_ids", "summary",
        ))
        for result in report.case_results:
            writer.writerow((
                result.eval_case_id,
                result.layer,
                result.status,
                result.passed_trials,
                result.expected_trials,
                result.observed_trials,
                ";".join(result.trial_ids),
                result.summary,
            ))
    rows = "\n".join(
        f"| {item.eval_case_id} | {item.layer} | {item.status} | "
        f"{item.passed_trials}/{item.expected_trials} |"
        for item in report.case_results
    )
    gates = "无。" if not report.gate_failures else "\n".join(
        f"- {failure}" for failure in report.gate_failures
    )
    markdown = (
        "# PlotAgent Agent Foundation 发布评测\n\n"
        f"- 决策：**{report.decision}**\n"
        f"- 冻结 commit：`{report.git_commit}`\n"
        f"- Suite：`{report.suite_id}` v{report.suite_version}\n\n"
        "## Case / trial\n\n"
        "| Case | Layer | Status | Trials |\n|---|---|---|---:|\n"
        f"{rows}\n\n## 发布门失败\n\n{gates}\n"
    )
    (output_dir / "REPORT.md").write_text(markdown, encoding="utf-8")
