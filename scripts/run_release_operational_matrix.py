from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from plotagent.storage.import_service import ProjectImportService
from plotagent.storage.models import ImportResource
from plotagent.storage.project import ProjectStore

REPOSITORY = Path(__file__).resolve().parents[1]
IMPORT_FIXTURES = REPOSITORY / "tests" / "fixtures" / "import" / "files"

BATCH_NODEIDS = (
    "tests/desktop_core/test_application.py::test_agent_v2_executes_confirmed_batch_and_verifies_every_item",
    "tests/desktop_core/test_application.py::test_agent_v2_step_execution_yields_between_atomic_items_for_cancellation",
    "tests/desktop_core/test_application.py::test_agent_v2_preserves_successful_items_when_one_batch_item_fails",
    "tests/desktop_core/test_application.py::test_agent_v2_explicit_skip_closes_partial_without_model_or_rerun",
    "tests/desktop_core/test_application.py::test_agent_v2_restart_finishes_verified_delivery_without_rerunning_items",
    "tests/desktop_core/test_application.py::test_agent_v2_partial_and_completed_with_skips_survive_restart",
)


@dataclass(frozen=True, slots=True)
class OperationalResult:
    case_id: str
    domain: str
    status: str
    duration_ms: float
    peak_working_set_mb: float | None
    observation: str
    evidence: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_large_csv(path: Path, *, rows: int = 100_000) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("Time_s", "Signal_mV", "Group"))
        for index in range(rows):
            writer.writerow((index / 1000, (index % 997) / 10, f"组{index % 4 + 1}"))


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("page_fault_count", ctypes.c_ulong),
        ("peak_working_set_size", ctypes.c_size_t),
        ("working_set_size", ctypes.c_size_t),
        ("quota_peak_paged_pool_usage", ctypes.c_size_t),
        ("quota_paged_pool_usage", ctypes.c_size_t),
        ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
        ("quota_non_paged_pool_usage", ctypes.c_size_t),
        ("pagefile_usage", ctypes.c_size_t),
        ("peak_pagefile_usage", ctypes.c_size_t),
    ]


if os.name == "nt":
    _kernel32: Any = ctypes.WinDLL("kernel32", use_last_error=True)
    _psapi: Any = ctypes.WinDLL("psapi", use_last_error=True)
    _kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    _get_process_memory_info: Any = _psapi.GetProcessMemoryInfo
    _get_process_memory_info.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_ProcessMemoryCounters),
        ctypes.c_ulong,
    ]
    _get_process_memory_info.restype = ctypes.c_int
    _current_process: int | None = _kernel32.GetCurrentProcess()
else:
    _get_process_memory_info = None
    _current_process = None


def _windows_working_set_bytes() -> int | None:
    if _get_process_memory_info is None or _current_process is None:
        return None
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not _get_process_memory_info(_current_process, ctypes.byref(counters), counters.cb):
        return None
    return int(counters.working_set_size)


def _start_memory_sampler() -> tuple[threading.Event, threading.Thread, list[int]]:
    stop = threading.Event()
    samples: list[int] = []

    def sample() -> None:
        while not stop.wait(0.02):
            value = _windows_working_set_bytes()
            if value is not None:
                samples.append(value)

    first = _windows_working_set_bytes()
    if first is not None:
        samples.append(first)
    thread = threading.Thread(target=sample, name="release-memory-sampler", daemon=True)
    thread.start()
    return stop, thread, samples


def _import_case(
    output: Path,
    *,
    case_id: str,
    source: Path,
    expected_datasets: int,
    expected_rows: int | None = None,
    expected_metadata: bool = False,
) -> OperationalResult:
    workspace = output / "workspaces" / case_id
    started = time.perf_counter()
    stop_sampling, sampler, memory_samples = _start_memory_sampler()
    try:
        with ProjectStore.create(workspace, project_id=f"project:{case_id}") as project:
            outcome = ProjectImportService(project).import_resource(
                ImportResource(resource_id=f"resource:{case_id}", path=source)
            )
            if outcome.kind != "committed":
                raise RuntimeError(f"unexpected import outcome: {outcome.kind}")
            if len(outcome.datasets) != expected_datasets:
                raise RuntimeError(
                    f"expected {expected_datasets} datasets, got {len(outcome.datasets)}"
                )
            row_counts = tuple(
                record.source_dataset.data_ref.row_count for record in outcome.datasets
            )
            if expected_rows is not None and row_counts != (expected_rows,):
                raise RuntimeError(f"expected {expected_rows} rows, got {row_counts}")
            if expected_metadata and not any(
                record.instrument_metadata for record in outcome.datasets
            ):
                raise RuntimeError("instrument metadata was not preserved")
            if not project.verify_registered_objects():
                raise RuntimeError("registered CAS objects failed verification")
            observation = (
                f"datasets={len(outcome.datasets)}; rows={list(row_counts)}; "
                f"source_bytes={source.stat().st_size}; source_sha256={_sha256(source)}"
            )
        status = "PASS"
    except Exception as exc:  # noqa: BLE001 - release evidence must record stable failures
        status = "FAIL"
        observation = f"{type(exc).__name__}: {exc}"
    finally:
        stop_sampling.set()
        sampler.join(timeout=1)
    duration_ms = (time.perf_counter() - started) * 1000
    shutil.rmtree(workspace, ignore_errors=True)
    return OperationalResult(
        case_id=case_id,
        domain="import",
        status=status,
        duration_ms=round(duration_ms, 3),
        peak_working_set_mb=(
            round(max(memory_samples) / 1024 / 1024, 3) if memory_samples else None
        ),
        observation=observation,
        evidence=str(source.relative_to(REPOSITORY))
        if source.is_relative_to(REPOSITORY)
        else source.name,
    )


def _pytest_case(output: Path, nodeid: str) -> OperationalResult:
    case_id = "BATCH-" + hashlib.sha256(nodeid.encode("utf-8")).hexdigest()[:8]
    started = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", nodeid, "-q"],
        cwd=REPOSITORY,
        env={**os.environ, "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    duration_ms = (time.perf_counter() - started) * 1000
    log = output / "pytest" / f"{case_id}.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        f"nodeid={nodeid}\nexit_code={completed.returncode}\n\n"
        f"STDOUT\n{completed.stdout}\nSTDERR\n{completed.stderr}",
        encoding="utf-8",
    )
    summary = next(
        (line.strip() for line in reversed(completed.stdout.splitlines()) if line.strip()),
        "pytest produced no stdout",
    )
    return OperationalResult(
        case_id=case_id,
        domain="batch_state",
        status="PASS" if completed.returncode == 0 else "FAIL",
        duration_ms=round(duration_ms, 3),
        peak_working_set_mb=None,
        observation=f"{nodeid}; {summary}",
        evidence=str(log.relative_to(output)),
    )


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=REPOSITORY, text=True, encoding="utf-8"
    ).strip()


def execute(output: Path) -> tuple[OperationalResult, ...]:
    output.mkdir(parents=True, exist_ok=False)
    large = output / "inputs" / "numeric-cjk-100k.csv"
    large.parent.mkdir(parents=True)
    _write_large_csv(large)
    results = [
        _import_case(
            output,
            case_id="IMPORT-CSV-100K",
            source=large,
            expected_datasets=1,
            expected_rows=100_000,
        ),
        _import_case(
            output,
            case_id="IMPORT-XLSX-MULTISHEET",
            source=IMPORT_FIXTURES / "excel_two_sheets.xlsx",
            expected_datasets=2,
        ),
        _import_case(
            output,
            case_id="IMPORT-TXT-INSTRUMENT",
            source=IMPORT_FIXTURES / "txt_metadata.txt",
            expected_datasets=1,
            expected_metadata=True,
        ),
        _import_case(
            output,
            case_id="IMPORT-TXT-MULTIBLOCK",
            source=IMPORT_FIXTURES / "txt_multi_block.txt",
            expected_datasets=2,
        ),
    ]
    results.extend(_pytest_case(output, nodeid) for nodeid in BATCH_NODEIDS)
    metadata = {
        "schema_version": "release-operational-matrix.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "commit": _git("rev-parse", "HEAD"),
        "worktree_status": _git("status", "--short"),
        "python": sys.version,
        "platform": platform.platform(),
        "case_count": len(results),
        "pass_count": sum(item.status == "PASS" for item in results),
        "fail_count": sum(item.status == "FAIL" for item in results),
        "real_model_calls": 0,
    }
    (output / "run-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output / "matrix-results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(asdict(results[0])))
        writer.writeheader()
        writer.writerows(asdict(item) for item in results)
    lines = [
        "# Release operational matrix",
        "",
        f"- Commit: `{metadata['commit']}`",
        f"- Cases: {metadata['case_count']}",
        f"- PASS: {metadata['pass_count']}",
        f"- FAIL: {metadata['fail_count']}",
        "- Real model calls: 0",
        "",
        "| Case | Domain | Status | Duration ms | Peak working set MB | Observation |",
        "|---|---|---:|---:|---:|---|",
    ]
    for item in results:
        observation = item.observation.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {item.case_id} | {item.domain} | {item.status} | "
            f"{item.duration_ms:.3f} | {item.peak_working_set_mb or ''} | {observation} |"
        )
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tuple(results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    commit = _git("rev-parse", "--short", "HEAD")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default_output = REPOSITORY / "build" / "release-matrix" / f"operational-{commit}-{timestamp}"
    output = args.output or default_output
    results = execute(output.resolve())
    print(output.resolve())
    pass_count = sum(item.status == "PASS" for item in results)
    fail_count = sum(item.status == "FAIL" for item in results)
    print(f"PASS={pass_count} FAIL={fail_count}")
    return 0 if all(item.status == "PASS" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
