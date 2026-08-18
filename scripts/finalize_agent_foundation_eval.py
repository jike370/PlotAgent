"""Convert one real Agent Foundation run into the versioned P10 evidence contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from plotagent.evaluation.contracts import (
    EvalPolicy,
    EvalTrial,
    EvidenceArtifact,
    EvidenceManifest,
    GraderResult,
    MetricThreshold,
)
from plotagent.evaluation.runner import (
    aggregate_evaluation,
    verify_evidence_files,
    write_evaluation_report,
)
from plotagent.evaluation.suite import load_migrated_seq70_suite


def _artifact(path: Path, root: Path, *, artifact_id: str) -> EvidenceArtifact:
    payload = path.read_bytes()
    return EvidenceArtifact(
        artifact_id=artifact_id,
        kind="trace",
        path=path.relative_to(root).as_posix(),
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_length=len(payload),
    )


def _thresholds(values: dict[str, object]) -> tuple[MetricThreshold, ...]:
    thresholds: list[MetricThreshold] = []
    for name, raw_value in values.items():
        if not isinstance(raw_value, int | float) or isinstance(raw_value, bool):
            raise ValueError(f"threshold {name} is not numeric")
        maximum = name.endswith("_max")
        thresholds.append(MetricThreshold(
            metric=name[:-4] if maximum else name,
            direction="maximum" if maximum else "minimum",
            value=float(raw_value),
        ))
    return tuple(thresholds)


def finalize(raw_path: Path, output_dir: Path, repository: Path) -> None:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    metadata = cast(dict[str, object], raw["metadata"])
    git_commit = str(metadata["git_commit"])
    generated_at = datetime.fromisoformat(str(metadata["generated_at"]).replace("Z", "+00:00"))
    cases = load_migrated_seq70_suite(
        repository,
        repository / "tests/fixtures/evaluation/agent-foundation-v2-suite.json",
    )
    case_by_task = {case.eval_case_id.rsplit(":", 1)[-1]: case for case in cases}
    raw_metrics = {
        key: float(value)
        for key, value in cast(dict[str, object], raw["metrics"]).items()
        if isinstance(value, int | float) and not isinstance(value, bool)
    }
    policy = EvalPolicy(
        policy_id="agent-foundation-release-v1",
        suite_id="agent-foundation-regression",
        suite_version=1,
        frozen_at=datetime(2026, 8, 18, tzinfo=UTC),
        required_layers=("E2", "E3"),
        trials_by_layer={"E2": 1, "E3": 3},
        thresholds=_thresholds(cast(dict[str, object], raw["thresholds"])),
        critical_trial_count=3,
    )
    evidence_dir = output_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    trials: list[EvalTrial] = []
    manifests: list[EvidenceManifest] = []
    for result_value in cast(list[object], raw["results"]):
        result = cast(dict[str, object], result_value)
        task_id = str(result["task_id"])
        case = case_by_task.get(task_id)
        if case is None:
            raise ValueError(f"raw result references unknown task {task_id}")
        repeat = int(cast(int, result["repeat"]))
        trial_id = f"trial:{task_id}.r{repeat}"
        evidence_path = evidence_dir / f"{task_id}.r{repeat}.json"
        evidence_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        manifest = EvidenceManifest(
            manifest_id=f"manifest:{task_id}.r{repeat}",
            eval_case_id=case.eval_case_id,
            trial_id=trial_id,
            git_commit=git_commit,
            generated_at=generated_at,
            artifacts=(
                _artifact(
                    evidence_path,
                    output_dir,
                    artifact_id=f"artifact:{task_id}.r{repeat}.trace",
                ),
            ),
            environment={"entry": "agent-foundation-v2", "runner": "real-provider"},
        )
        file_failures = verify_evidence_files(output_dir, manifest)
        if file_failures:
            raise ValueError("; ".join(file_failures))
        passed = result.get("passed") is True
        status: Literal["PASS", "FAIL"] = "PASS" if passed else "FAIL"
        failure_message = str(result.get("failure") or "evaluation expectation was not met")
        graders = tuple(
            GraderResult(
                grader_id=grader.grader_id,
                kind=grader.kind,
                status=status,
                summary=(
                    "Real Agent/Core trace satisfied the frozen claim."
                    if passed
                    else failure_message
                ),
                observed={"task_id": task_id, "repeat": repeat},
            )
            for grader in case.graders
        )
        trial = EvalTrial(
            trial_id=trial_id,
            eval_case_id=case.eval_case_id,
            trial_index=repeat,
            status=status,
            started_at=generated_at,
            completed_at=generated_at,
            git_commit=git_commit,
            evidence_manifest_id=manifest.manifest_id,
            grader_results=graders,
            metrics=raw_metrics,
            failure_code=None if passed else f"CASE_{task_id}_FAILED",
            failure_message=None if passed else failure_message,
        )
        trials.append(trial)
        manifests.append(manifest)

    report = aggregate_evaluation(
        run_id=f"agent-foundation-{generated_at.strftime('%Y%m%d%H%M%S')}",
        git_commit=git_commit,
        cases=cases,
        policy=policy,
        trials=trials,
        evidence=manifests,
        generated_at=generated_at,
    )
    write_evaluation_report(
        output_dir,
        report,
        policy=policy,
        cases=cases,
        trials=trials,
        evidence=manifests,
    )
    (output_dir / "evidence-manifests.json").write_text(
        json.dumps(
            [manifest.model_dump(mode="json") for manifest in manifests],
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"AGENT_FOUNDATION_{report.decision} {output_dir}")
    if report.decision != "GO":
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    args = parser.parse_args()
    finalize(args.raw.resolve(), args.output.resolve(), args.repository.resolve())


if __name__ == "__main__":
    main()
