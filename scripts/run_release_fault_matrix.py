from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
VITEST = REPOSITORY / "node_modules" / "vitest" / "vitest.mjs"


@dataclass(frozen=True, slots=True)
class FaultCase:
    case_id: str
    domain: str
    runner: str
    target: str
    expected: str


@dataclass(frozen=True, slots=True)
class FaultResult:
    case_id: str
    domain: str
    status: str
    duration_ms: float
    expected: str
    observation: str
    evidence: str


FAULT_CASES = (
    FaultCase(
        "FAULT-TIMEOUT",
        "provider",
        "vitest",
        "src/main/agent/pi-runtime-v2.test.ts::"
        "maps activation timeouts to a stable wall-time budget yield",
        "wall-time budget yield; no accepted terminal result or project side effect",
    ),
    FaultCase(
        "FAULT-RATE-LIMIT",
        "provider",
        "vitest",
        "src/main/agent/agent-foundation-runtime.test.ts::"
        "provider-rate-limit reports an actionable failure before confirmation",
        "actionable rate-limit error; no plan and no project mutation",
    ),
    FaultCase(
        "FAULT-OFFLINE",
        "provider",
        "vitest",
        "src/main/agent/agent-foundation-runtime.test.ts::"
        "provider-offline reports an actionable failure before confirmation",
        "actionable unavailable error; no plan and no project mutation",
    ),
    FaultCase(
        "FAULT-PROXY",
        "provider",
        "vitest",
        "src/main/agent/agent-foundation-runtime.test.ts::"
        "provider-proxy reports an actionable failure before confirmation",
        "proxy transport failure maps to unavailable; no plan and no project mutation",
    ),
    FaultCase(
        "FAULT-BAD-PROVIDER-JSON",
        "protocol",
        "vitest",
        "src/main/agent/pi-runtime-v2.test.ts::"
        "maps malformed provider JSON to a stable known-none failure",
        "typed provider failure with known-none side effects",
    ),
    FaultCase(
        "FAULT-BAD-CORE-JSON",
        "protocol",
        "pytest",
        "tests/desktop_core/test_integration.py::test_invalid_frames_are_sanitized_and_the_process_survives",
        "sanitized protocol error; Core process remains healthy and secrets do not leak",
    ),
    FaultCase(
        "FAULT-CANCEL",
        "task_state",
        "pytest",
        "tests/desktop_core/test_application.py::test_agent_v2_cancel_waits_for_the_running_item_and_preserves_its_receipt",
        "cancel waits for the atomic boundary and preserves the completed receipt",
    ),
    FaultCase(
        "FAULT-PARTIAL",
        "task_state",
        "pytest",
        "tests/desktop_core/test_application.py::test_agent_v2_preserves_successful_items_when_one_batch_item_fails",
        "successful items remain committed while the failed item becomes repairable",
    ),
    FaultCase(
        "FAULT-TRANSIENT-RETRY",
        "task_state",
        "pytest",
        "tests/desktop_core/test_application.py::test_agent_v2_retries_one_transient_failure_without_model_activation",
        "one deterministic transient retry completes without a second model activation",
    ),
    FaultCase(
        "FAULT-EXPLICIT-SAFE-RETRY",
        "task_state",
        "pytest",
        "tests/desktop_core/test_application.py::test_agent_v2_user_safe_retry_replays_failed_item_without_agent_activation",
        "explicit safe retry replays only eligible failed work without model use",
    ),
    FaultCase(
        "FAULT-UNRECOVERABLE",
        "task_state",
        "pytest",
        "tests/desktop_core/test_application.py::test_agent_v2_stops_after_a_scoped_retry_makes_no_progress",
        "no-progress repair stops in partial state and does not loop",
    ),
    FaultCase(
        "FAULT-UNSAFE-RETRY-REJECTED",
        "task_state",
        "pytest",
        "tests/desktop_core/test_application.py::test_agent_v2_scoped_repair_can_request_missing_semantic_input",
        "semantic conflicts cannot use deterministic retry and must request input",
    ),
    FaultCase(
        "FAULT-ATOMIC-DISK-WRITE",
        "storage",
        "pytest",
        "tests/storage/test_project_package.py::test_pack_atomic_overwrite_preserves_existing_target_on_failure",
        "failed replacement preserves the previously published package",
    ),
)


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=REPOSITORY, text=True, encoding="utf-8"
    ).strip()


def _node_executable() -> Path:
    discovered = shutil.which("node")
    if discovered:
        return Path(discovered)
    bundled = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "bin"
        / "node.exe"
    )
    if bundled.is_file():
        return bundled
    raise RuntimeError("Node.js was not available for the frozen fault matrix.")


def _command(case: FaultCase) -> list[str]:
    path, separator, name = case.target.partition("::")
    if not separator or not name:
        raise ValueError(f"invalid frozen target: {case.target}")
    if case.runner == "pytest":
        return [sys.executable, "-m", "pytest", case.target, "-q"]
    if case.runner == "vitest":
        if not VITEST.is_file():
            raise RuntimeError(f"Vitest entrypoint is missing: {VITEST}")
        return [str(_node_executable()), str(VITEST), "run", path, "-t", name]
    raise ValueError(f"unknown runner: {case.runner}")


def _execute_case(output: Path, case: FaultCase) -> FaultResult:
    command = _command(case)
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=REPOSITORY,
        env={**os.environ, "NO_COLOR": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    duration_ms = (time.perf_counter() - started) * 1000
    log = output / "logs" / f"{case.case_id}.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        f"case_id={case.case_id}\ntarget={case.target}\n"
        f"command={json.dumps(command, ensure_ascii=False)}\n"
        f"exit_code={completed.returncode}\n\n"
        f"STDOUT\n{completed.stdout}\nSTDERR\n{completed.stderr}",
        encoding="utf-8",
    )
    nonempty = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    summary = nonempty[-1] if nonempty else "runner produced no stdout"
    return FaultResult(
        case_id=case.case_id,
        domain=case.domain,
        status="PASS" if completed.returncode == 0 else "FAIL",
        duration_ms=round(duration_ms, 3),
        expected=case.expected,
        observation=f"{case.target}; {summary}",
        evidence=str(log.relative_to(output)),
    )


def execute(output: Path) -> tuple[FaultResult, ...]:
    output.mkdir(parents=True, exist_ok=False)
    results = tuple(_execute_case(output, case) for case in FAULT_CASES)
    metadata = {
        "schema_version": "release-fault-matrix.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "commit": _git("rev-parse", "HEAD"),
        "worktree_status": _git("status", "--short"),
        "python": sys.version,
        "platform": platform.platform(),
        "case_count": len(results),
        "pass_count": sum(item.status == "PASS" for item in results),
        "fail_count": sum(item.status == "FAIL" for item in results),
        "real_model_calls": 0,
        "matrix_sha256": hashlib.sha256(
            json.dumps([asdict(case) for case in FAULT_CASES], sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }
    (output / "run-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output / "matrix-results.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(asdict(results[0])))
        writer.writeheader()
        writer.writerows(asdict(item) for item in results)
    lines = [
        "# Release fault matrix",
        "",
        f"- Commit: `{metadata['commit']}`",
        f"- Cases: {metadata['case_count']}",
        f"- PASS: {metadata['pass_count']}",
        f"- FAIL: {metadata['fail_count']}",
        "- Real model calls: 0",
        "",
        "| Case | Domain | Status | Duration ms | Expected | Observation |",
        "|---|---|---:|---:|---|---|",
    ]
    for item in results:
        expected = item.expected.replace("|", "\\|")
        observation = item.observation.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {item.case_id} | {item.domain} | {item.status} | "
            f"{item.duration_ms:.3f} | {expected} | {observation} |"
        )
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    commit = _git("rev-parse", "--short", "HEAD")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default = REPOSITORY / "build" / "release-matrix" / f"fault-{commit}-{timestamp}"
    output = (args.output or default).resolve()
    results = execute(output)
    print(output)
    print(
        f"PASS={sum(item.status == 'PASS' for item in results)} "
        f"FAIL={sum(item.status == 'FAIL' for item in results)}"
    )
    return 0 if all(item.status == "PASS" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
