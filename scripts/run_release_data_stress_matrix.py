"""Run the deterministic large/missing/extreme/dynamic-series release matrix."""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.engine.backends.matplotlib import default_matplotlib_backend  # noqa: E402
from plotagent.engine.ports import EngineRenderSource  # noqa: E402
from scripts.release_matrix_cases import (  # noqa: E402
    ColumnCase,
    ReleaseCase,
    _release_case,
)
from scripts.run_release_operational_matrix import _start_memory_sampler  # noqa: E402

STRESS_CASE_IDS = (
    "LARGE-K01-100K-RENDER",
    "MISSING-K01-GAPS",
    "MISSING-K20-HEATMAP",
    "EXTREME-K01-LINE",
    "EXTREME-K08-COLUMN",
    "DYNAMIC-X03-2-4-2",
    "DYNAMIC-X38-1-4-2",
    "DYNAMIC-X39-2-5-2",
)


@dataclass(frozen=True, slots=True)
class StressResult:
    case_id: str
    domain: str
    status: str
    duration_ms: float
    peak_working_set_mb: float | None
    observation: str
    artifacts: str
    error: str | None = None


def _git(*args: str) -> str:
    return subprocess.check_output(
        ("git", *args), cwd=REPOSITORY, text=True, encoding="utf-8"
    ).strip()


def _column(
    role: str,
    name: str,
    logical_type: str,
    values: tuple[float | int | str | None, ...],
) -> ColumnCase:
    return ColumnCase(role, name, logical_type, values)  # type: ignore[arg-type]


def _case(profile_id: str, columns: tuple[ColumnCase, ...]) -> ReleaseCase:
    return _release_case(profile_id, "representative", columns)


def _large_k01(rows: int) -> ReleaseCase:
    x = tuple(index / 1000 for index in range(rows))
    y = tuple(math.sin(index / 211) + (index % 37) / 1000 for index in range(rows))
    return _case(
        "K01",
        (
            _column("x", "Time", "numeric", x),
            _column("y", "Signal", "numeric", y),
        ),
    )


def _static_cases(large_rows: int) -> tuple[tuple[str, str, ReleaseCase], ...]:
    return (
        ("LARGE-K01-100K-RENDER", "large_render", _large_k01(large_rows)),
        (
            "MISSING-K01-GAPS",
            "missing_values",
            _case(
                "K01",
                (
                    _column("x", "Time", "numeric", tuple(range(8))),
                    _column("y", "Signal", "numeric", (1, 2, None, 4, 3, None, 5, 6)),
                ),
            ),
        ),
        (
            "MISSING-K20-HEATMAP",
            "missing_values",
            _case(
                "K20",
                (
                    _column(
                        "row",
                        "Row",
                        "categorical",
                        ("A", "A", "A", "B", "B", "B", "C", "C", "C"),
                    ),
                    _column(
                        "column",
                        "Column",
                        "categorical",
                        ("X", "Y", "Z", "X", "Y", "Z", "X", "Y", "Z"),
                    ),
                    _column("value", "Value", "numeric", (1, 2, 3, 4, None, 6, 7, 8, 9)),
                ),
            ),
        ),
        (
            "EXTREME-K01-LINE",
            "finite_extremes",
            _case(
                "K01",
                (
                    _column("x", "X", "numeric", (0, 1, 2, 3, 4)),
                    _column("y", "Y", "numeric", (-1e12, -1e-12, 0, 1e-12, 1e12)),
                ),
            ),
        ),
        (
            "EXTREME-K08-COLUMN",
            "finite_extremes",
            _case(
                "K08",
                (
                    _column(
                        "category",
                        "Category",
                        "categorical",
                        ("negative", "zero", "positive"),
                    ),
                    _column("value", "Value", "numeric", (-1e12, 0, 1e12)),
                ),
            ),
        ),
    )


def _dynamic_case(profile_id: str, count: int) -> ReleaseCase:
    rows = 8
    prefix: tuple[ColumnCase, ...]
    if profile_id == "X03":
        prefix = (
            _column(
                "category",
                "Category",
                "categorical",
                tuple(f"C{index + 1}" for index in range(rows)),
            ),
        )
    elif profile_id == "X38":
        prefix = (_column("x", "X", "numeric", tuple(range(rows))),)
    elif profile_id == "X39":
        prefix = ()
    else:  # pragma: no cover - frozen caller set
        raise ValueError(profile_id)
    series = tuple(
        _column(
            f"series_{index}",
            f"Series {index}",
            "numeric",
            tuple(index * 10 + row for row in range(rows)),
        )
        for index in range(1, count + 1)
    )
    return _case(profile_id, (*prefix, *series))


def _render_case(
    *, case_id: str, domain: str, case: ReleaseCase, output: Path
) -> StressResult:
    started = time.perf_counter()
    stop, sampler, samples = _start_memory_sampler()
    case_dir = output / "artifacts" / case_id
    try:
        backend = default_matplotlib_backend(output / "_cache" / case_id)
        change = backend.stage(case.document, (), EngineRenderSource(data=case.view))
        change.publish()
        change.finalize()
        case_dir.mkdir(parents=True, exist_ok=True)
        png = case_dir / "plot.png"
        backend.export(case.document, png, "png")
        if not png.is_file() or png.stat().st_size <= 0:
            raise RuntimeError("renderer did not publish a non-empty PNG")
        series_count = sum(
            str(item.semantic_id).startswith("series:") for item in change.readback.objects
        )
        observation = (
            f"rows={len(case.view.row_ids)}; columns={len(case.view.columns)}; "
            f"series_objects={series_count}; png_bytes={png.stat().st_size}"
        )
        status = "PASS"
        error = None
    except Exception as exc:  # noqa: BLE001 - evidence must preserve all failures
        status = "FAIL"
        observation = "render failed"
        error = f"{type(exc).__name__}: {exc}"
    finally:
        stop.set()
        sampler.join(timeout=1)
    return StressResult(
        case_id=case_id,
        domain=domain,
        status=status,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        peak_working_set_mb=(round(max(samples) / 1024 / 1024, 3) if samples else None),
        observation=observation,
        artifacts=str(case_dir.relative_to(output)),
        error=error,
    )


def _dynamic_result(
    *, case_id: str, profile_id: str, counts: tuple[int, int, int], output: Path
) -> StressResult:
    started = time.perf_counter()
    stop, sampler, samples = _start_memory_sampler()
    case_dir = output / "artifacts" / case_id
    observations: list[str] = []
    try:
        for step, count in enumerate(counts, start=1):
            case = _dynamic_case(profile_id, count)
            backend = default_matplotlib_backend(output / "_cache" / case_id / f"step-{step}")
            change = backend.stage(case.document, (), EngineRenderSource(data=case.view))
            change.publish()
            change.finalize()
            png = case_dir / f"step-{step}-{count}-series.png"
            backend.export(case.document, png, "png")
            actual = sum(
                str(item.semantic_id).startswith("series:")
                for item in change.readback.objects
            )
            expected = count + (1 if profile_id == "X39" else 0)
            if actual != expected:
                raise RuntimeError(
                    f"{profile_id} expected {expected} series objects at step {step}, got {actual}"
                )
            observations.append(f"step{step}={count}/{actual}")
        status = "PASS"
        error = None
    except Exception as exc:  # noqa: BLE001 - evidence must preserve all failures
        status = "FAIL"
        error = f"{type(exc).__name__}: {exc}"
    finally:
        stop.set()
        sampler.join(timeout=1)
    return StressResult(
        case_id=case_id,
        domain="dynamic_series",
        status=status,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        peak_working_set_mb=(round(max(samples) / 1024 / 1024, 3) if samples else None),
        observation="; ".join(observations),
        artifacts=str(case_dir.relative_to(output)),
        error=error,
    )


def execute(output: Path, *, large_rows: int = 100_000) -> tuple[StressResult, ...]:
    output.mkdir(parents=True, exist_ok=False)
    results = [
        _render_case(case_id=case_id, domain=domain, case=case, output=output)
        for case_id, domain, case in _static_cases(large_rows)
    ]
    results.extend(
        (
            _dynamic_result(
                case_id="DYNAMIC-X03-2-4-2",
                profile_id="X03",
                counts=(2, 4, 2),
                output=output,
            ),
            _dynamic_result(
                case_id="DYNAMIC-X38-1-4-2",
                profile_id="X38",
                counts=(1, 4, 2),
                output=output,
            ),
            _dynamic_result(
                case_id="DYNAMIC-X39-2-5-2",
                profile_id="X39",
                counts=(2, 5, 2),
                output=output,
            ),
        )
    )
    if tuple(item.case_id for item in results) != STRESS_CASE_IDS:
        raise RuntimeError("data stress result order differs from the frozen matrix")
    metadata = {
        "schema_version": "plotagent.release-data-stress.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "git_head": _git("rev-parse", "HEAD"),
        "git_status_short": _git("status", "--short"),
        "platform": platform.platform(),
        "python": sys.version,
        "large_rows": large_rows,
        "case_count": len(results),
        "pass_count": sum(item.status == "PASS" for item in results),
        "fail_count": sum(item.status == "FAIL" for item in results),
        "real_model_calls": 0,
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
        "# Release data stress matrix",
        "",
        f"- Git HEAD: `{metadata['git_head']}`",
        f"- PASS: {metadata['pass_count']}",
        f"- FAIL: {metadata['fail_count']}",
        f"- Large-render rows: {large_rows}",
        "- Real model calls: 0",
        "",
        "| Case | Domain | Status | Duration ms | Peak MB | Observation | Error |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for item in results:
        values = (
            item.case_id,
            item.domain,
            item.status,
            f"{item.duration_ms:.3f}",
            "" if item.peak_working_set_mb is None else str(item.peak_working_set_mb),
            item.observation,
            item.error or "",
        )
        escaped = tuple(value.replace("|", "\\|").replace("\n", " ") for value in values)
        lines.append("| " + " | ".join(escaped) + " |")
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tuple(results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    head = _git("rev-parse", "--short", "HEAD")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = args.output or (
        REPOSITORY / "build" / "release-matrix" / f"data-stress-{head}-{stamp}"
    )
    results = execute(output.resolve())
    print(f"OUTPUT={output.resolve()}")
    print(
        f"PASS={sum(item.status == 'PASS' for item in results)} "
        f"FAIL={sum(item.status == 'FAIL' for item in results)}"
    )
    return 0 if all(item.status == "PASS" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
