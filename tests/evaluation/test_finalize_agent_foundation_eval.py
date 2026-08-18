from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]


def test_finalizer_writes_complete_go_report_for_frozen_trial_counts(tmp_path: Path) -> None:
    commit = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=REPOSITORY, text=True
    ).strip()
    results = [
        {"task_id": f"W{task:02d}", "repeat": repeat, "passed": True}
        for task in range(1, 19)
        for repeat in range(1, 4)
    ]
    results.extend(
        {"task_id": f"R{task:02d}", "repeat": 1, "passed": True}
        for task in range(1, 7)
    )
    raw = tmp_path / "raw-results.json"
    raw.write_text(
        json.dumps(
            {
                "metadata": {
                    "git_commit": commit,
                    "generated_at": "2026-08-18T00:00:00Z",
                },
                "metrics": {"task_exact_rate": 1.0},
                "thresholds": {},
                "results": results,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "final"
    environment = {**os.environ, "PYTHONPATH": str(REPOSITORY / "src")}

    completed = subprocess.run(
        (
            sys.executable,
            str(REPOSITORY / "scripts" / "finalize_agent_foundation_eval.py"),
            "--raw",
            str(raw),
            "--output",
            str(output),
            "--repository",
            str(REPOSITORY),
        ),
        cwd=REPOSITORY,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    metadata = json.loads((output / "run-metadata.json").read_text(encoding="utf-8"))
    manifests = json.loads(
        (output / "evidence-manifests.json").read_text(encoding="utf-8")
    )
    assert report["decision"] == "GO"
    assert report["policy_id"] == "agent-foundation-release-v2"
    assert metadata["case_count"] == 24
    assert metadata["trial_count"] == 60
    assert metadata["evidence_manifest_count"] == 60
    assert len(manifests) == 60
    assert len(tuple((output / "evidence").glob("*.json"))) == 60
