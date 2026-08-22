"""Run the representative common-edit matrix in Matplotlib and Origin."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.engine.backends.matplotlib import (  # noqa: E402
    default_matplotlib_backend,
)
from plotagent.engine.backends.origin import (  # noqa: E402
    SubprocessOriginWorker,
    preflight_origin,
)
from plotagent.engine.backends.origin.messages import OriginWorkerRequest  # noqa: E402
from plotagent.engine.contracts import PlotEngineAction  # noqa: E402
from plotagent.engine.ports import EngineReadback, EngineRenderSource  # noqa: E402
from scripts.release_matrix_actions import (  # noqa: E402
    action_parameter_names,
    document_for_actions,
    isolated_edit_cases,
    representative_edit_actions,
)
from scripts.release_matrix_cases import RELEASE_CASES, ReleaseCase  # noqa: E402
from scripts.run_release_origin_matrix import _fresh_verify  # noqa: E402


@dataclass(frozen=True, slots=True)
class EditResult:
    profile_id: str
    operation: str
    backend: str
    status: str
    plot_version: int
    target: str
    parameters: tuple[str, ...]
    evidence: str | None
    error: str | None


def _git(*args: str) -> str:
    return subprocess.check_output(
        ("git", *args), cwd=REPOSITORY, text=True, encoding="utf-8"
    ).strip()


def _origin_request(
    case: ReleaseCase,
    history: tuple[PlotEngineAction, ...],
    *,
    install_dir: Path,
    output: Path,
    previous: Path,
) -> OriginWorkerRequest:
    actions: tuple[PlotEngineAction, ...] = (case.create, *history)
    return OriginWorkerRequest(
        install_dir=str(install_dir),
        output_opju=str(output),
        previous_opju=str(previous),
        document=document_for_actions(case, actions[1:]),
        actions=actions,
        source=EngineRenderSource(data=case.view),
    )


def _failed_rows(
    case: ReleaseCase,
    actions: tuple[PlotEngineAction, ...],
    *,
    backend: Literal["matplotlib", "origin"],
    error: Exception,
) -> tuple[EditResult, ...]:
    version = document_for_actions(case, actions).plot_version
    return tuple(
        EditResult(
            profile_id=case.profile_id,
            operation=action.operation,
            backend=backend,
            status="FAIL",
            plot_version=version,
            target=str(getattr(action, "target", case.document.plot_id)),
            parameters=tuple(sorted(action_parameter_names(action))),
            evidence=None,
            error=f"{type(error).__name__}: {error}",
        )
        for action in actions
    )


def execute_edit_matrix(
    output: Path,
    *,
    origin_baseline: Path,
    profile_ids: tuple[str, ...] | None = None,
) -> tuple[EditResult, ...]:
    output = output.resolve()
    origin_baseline = origin_baseline.resolve()
    output.mkdir(parents=True, exist_ok=False)
    baseline_metadata = json.loads(
        (origin_baseline / "run-metadata.json").read_text(encoding="utf-8")
    )
    probe = preflight_origin(output / "origin-preflight.opju")
    if probe.status != "ready":
        raise RuntimeError(probe.error.message)
    install_dir = Path(probe.environment.install_dir)
    worker = SubprocessOriginWorker(timeout_seconds=900)
    matplotlib = default_matplotlib_backend(output / "matplotlib-cache")
    selected = None if profile_ids is None else set(profile_ids)
    cases = tuple(
        case
        for case in RELEASE_CASES
        if case.variant == "representative"
        and (selected is None or case.profile_id in selected)
    )
    if selected is not None and {case.profile_id for case in cases} != selected:
        raise ValueError(
            f"unknown release profiles: {sorted(selected - {case.profile_id for case in cases})}"
        )
    results: list[EditResult] = []
    failures: dict[str, str] = {}
    isolated_contracts: list[dict[str, object]] = []
    isolated_focal_parameter_count = 0

    for index, case in enumerate(cases, start=1):
        print(f"[{index:02d}/{len(cases):02d}] {case.profile_id}", flush=True)
        profile_dir = output / case.profile_id
        profile_dir.mkdir(parents=True)
        baseline_readback = EngineReadback.model_validate_json(
            (
                origin_baseline
                / case.profile_id
                / "default"
                / "readback.json"
            ).read_text(encoding="utf-8")
        )
        actions = representative_edit_actions(case, baseline_readback)
        for isolated in isolated_edit_cases(case, baseline_readback):
            isolated_focal_parameter_count += len(isolated.focal_parameters)
            isolated_contracts.append(
                {
                    "case_id": isolated.case_id,
                    "profile_id": isolated.profile_id,
                    "operation": isolated.operation,
                    "focal_parameters": isolated.focal_parameters,
                    "dependency_parameters": isolated.dependency_parameters,
                    "comparison_mode": isolated.comparison_mode,
                    "evidence_reason": isolated.evidence_reason,
                    "action_a": isolated.action.model_dump(mode="json"),
                    "action_b": isolated.comparison_action.model_dump(mode="json"),
                }
            )

        final_document = document_for_actions(case, actions)
        try:
            mpl_change = matplotlib.stage(
                final_document,
                actions,
                EngineRenderSource(data=case.view),
            )
            mpl_change.publish()
            mpl_change.finalize()
            mpl_dir = profile_dir / "matplotlib"
            mpl_dir.mkdir()
            for format in ("png", "svg"):
                matplotlib.export(
                    final_document,
                    mpl_dir / f"edited.{format}",
                    format,
                )
            (mpl_dir / "readback.json").write_text(
                mpl_change.readback.model_dump_json(indent=2), encoding="utf-8"
            )
            for action in actions:
                results.append(
                    EditResult(
                        profile_id=case.profile_id,
                        operation=action.operation,
                        backend="matplotlib",
                        status="PASS",
                        plot_version=final_document.plot_version,
                        target=str(getattr(action, "target", case.document.plot_id)),
                        parameters=tuple(sorted(action_parameter_names(action))),
                        evidence=(mpl_dir / "readback.json").relative_to(output).as_posix(),
                        error=None,
                    )
                )
        except Exception as error:
            failures[f"{case.profile_id}:matplotlib"] = (
                f"{type(error).__name__}: {error}"
            )
            results.extend(
                _failed_rows(case, actions, backend="matplotlib", error=error)
            )

        try:
            previous = origin_baseline / case.profile_id / "default" / "plot.opju"
            if not previous.is_file():
                raise FileNotFoundError(f"missing baseline Origin OPJU: {previous}")
            final_request: OriginWorkerRequest | None = None
            for action_count in range(1, len(actions) + 1):
                history = actions[:action_count]
                version_dir = profile_dir / "origin" / f"v{action_count + 1}"
                version_dir.mkdir(parents=True)
                target = version_dir / "plot.opju"
                request = _origin_request(
                    case,
                    history,
                    install_dir=install_dir,
                    output=target,
                    previous=previous,
                )
                response = worker.run(request)
                (version_dir / "readback.json").write_text(
                    response.readback.model_dump_json(indent=2), encoding="utf-8"
                )
                previous = target
                final_request = request
            if final_request is None:
                raise RuntimeError("release profile produced no edit actions")
            final_dir = previous.parent
            fresh_json = final_dir / "fresh-readback.json"
            fresh_png = final_dir / "fresh.png"
            _fresh_verify(
                previous.with_suffix(".request.json"),
                previous,
                fresh_png,
                fresh_json,
            )
            for action in actions:
                results.append(
                    EditResult(
                        profile_id=case.profile_id,
                        operation=action.operation,
                        backend="origin",
                        status="PASS",
                        plot_version=final_request.document.plot_version,
                        target=str(getattr(action, "target", case.document.plot_id)),
                        parameters=tuple(sorted(action_parameter_names(action))),
                        evidence=fresh_json.relative_to(output).as_posix(),
                        error=None,
                    )
                )
        except Exception as error:
            failures[f"{case.profile_id}:origin"] = f"{type(error).__name__}: {error}"
            results.extend(_failed_rows(case, actions, backend="origin", error=error))

    with (output / "edit-results.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(asdict(results[0])))
        writer.writeheader()
        writer.writerows(asdict(row) for row in results)
    (output / "edit-results.json").write_text(
        json.dumps([asdict(row) for row in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output / "isolated-edit-contracts.json").write_text(
        json.dumps(isolated_contracts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    counts = {
        status: sum(row.status == status for row in results)
        for status in ("PASS", "FAIL")
    }
    metadata = {
        "schema_version": "plotagent.release-edit-matrix.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "git_head": _git("rev-parse", "HEAD"),
        "git_status_short": _git("status", "--short"),
        "origin_baseline": str(origin_baseline),
        "origin_baseline_head": baseline_metadata["git_head"],
        "profile_count": len(cases),
        "result_count": len(results),
        "parameter_result_count": sum(len(row.parameters) for row in results),
        "isolated_contract_case_count": len(isolated_contracts),
        "isolated_focal_parameter_count": isolated_focal_parameter_count,
        "failures": failures,
    }
    (output / "run-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = (
        "# PlotAgent 34图公共编辑矩阵\n\n"
        f"- Profiles: {len(cases)}\n"
        f"- PASS: {counts['PASS']}\n"
        f"- FAIL: {counts['FAIL']}\n"
        "- 每图按能力声明覆盖标题、轴、系列、图例、色图、误差、数据标签和图形参数。\n"
        f"- 单参数合同: {len(isolated_contracts)} 个原子用例。\n"
        "- Origin 每个动作形成独立线性版本，最终由另一进程 fresh 复核。\n"
        f"- 资格结论: {'GO' if counts['FAIL'] == 0 else 'NO-GO'}\n"
    )
    (output / "REPORT.md").write_text(report, encoding="utf-8")
    return tuple(results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin-baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--profiles")
    args = parser.parse_args()
    head = _git("rev-parse", "--short", "HEAD")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = args.output or (
        REPOSITORY / "build" / "release-matrix" / f"edits-{head}-{stamp}"
    )
    profiles = (
        None
        if args.profiles is None
        else tuple(value.strip() for value in args.profiles.split(",") if value.strip())
    )
    rows = execute_edit_matrix(
        output,
        origin_baseline=args.origin_baseline,
        profile_ids=profiles,
    )
    failures = sum(row.status == "FAIL" for row in rows)
    print(f"OUTPUT={output.resolve()}")
    print(f"PASS={len(rows) - failures} FAIL={failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
