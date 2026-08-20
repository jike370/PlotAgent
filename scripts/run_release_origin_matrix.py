"""Close the 34 representative OPJU rows using real fresh Origin processes."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.engine import PlotDocument, SetTitle  # noqa: E402
from plotagent.engine.backends.origin import (  # noqa: E402
    SubprocessOriginWorker,
    preflight_origin,
)
from plotagent.engine.backends.origin.messages import OriginWorkerRequest  # noqa: E402
from plotagent.engine.ports import EngineRenderSource  # noqa: E402
from scripts.release_matrix_cases import RELEASE_CASES, ReleaseCase  # noqa: E402
from scripts.run_release_matrix import MatrixResult  # noqa: E402


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.check_output(
        ("git", *args), cwd=REPOSITORY, text=True, encoding="utf-8"
    ).strip()


def _load_offline_rows(offline: Path, output: Path) -> tuple[MatrixResult, ...]:
    rows: list[MatrixResult] = []
    for raw in json.loads((offline / "matrix-results.json").read_text(encoding="utf-8")):
        row = MatrixResult(**raw)
        if row.artifact is not None:
            source = offline / Path(row.artifact)
            row = replace(
                row,
                artifact=os.path.relpath(source, output).replace("\\", "/"),
            )
        rows.append(row)
    return tuple(rows)


def _edited_history(case: ReleaseCase) -> tuple[SetTitle, PlotDocument]:
    title = SetTitle(
        action_id=f"action:release-{case.profile_id.lower()}-representative-title",
        target=case.document.plot_id,
        expected_plot_version=1,
        text=f"{case.profile_id} representative release evidence",
    )
    document = case.document.model_copy(
        update={
            "plot_version": 2,
            "parent_version": 1,
            "applied_action_ids": (*case.document.applied_action_ids, title.action_id),
        }
    )
    return title, document


def _request(
    case: ReleaseCase,
    *,
    install_dir: Path,
    output: Path,
    previous: Path | None,
    title: SetTitle | None = None,
    document: PlotDocument | None = None,
) -> OriginWorkerRequest:
    actions = (case.create,) if title is None else (case.create, title)
    return OriginWorkerRequest(
        install_dir=str(install_dir),
        output_opju=str(output),
        previous_opju=None if previous is None else str(previous),
        document=case.document if document is None else document,
        actions=actions,
        source=EngineRenderSource(data=case.view),
    )


def _fresh_verify(request_path: Path, opju: Path, png: Path, result: Path) -> None:
    completed = subprocess.run(
        (
            sys.executable,
            str(REPOSITORY / "scripts" / "verify_release_origin_project.py"),
            str(request_path),
            str(opju),
            str(png),
            str(result),
        ),
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "fresh Origin verifier failed: "
            + (completed.stderr.strip() or completed.stdout.strip() or "unknown error")
        )


def execute_origin_matrix(
    output: Path,
    *,
    offline: Path,
    worker: SubprocessOriginWorker | None = None,
    profile_ids: tuple[str, ...] | None = None,
) -> tuple[MatrixResult, ...]:
    output = output.resolve()
    offline = offline.resolve()
    output.mkdir(parents=True, exist_ok=False)
    offline_metadata = json.loads((offline / "run-metadata.json").read_text(encoding="utf-8"))
    head = _git("rev-parse", "HEAD")
    if offline_metadata["git_head"] != head:
        raise RuntimeError("offline matrix HEAD differs from the current Origin run HEAD")
    offline_rows = _load_offline_rows(offline, output)
    rows = {row.matrix_key: row for row in offline_rows}
    probe_target = output / "origin-preflight.opju"
    probe = preflight_origin(probe_target)
    if probe.status != "ready":
        raise RuntimeError(probe.error.message)
    install_dir = Path(probe.environment.install_dir)
    live_worker = worker or SubprocessOriginWorker(timeout_seconds=900)
    failures: dict[str, str] = {}

    selected = None if profile_ids is None else set(profile_ids)
    cases = tuple(
        case
        for case in RELEASE_CASES
        if case.variant == "representative" and (selected is None or case.profile_id in selected)
    )
    if selected is not None and {case.profile_id for case in cases} != selected:
        unknown = sorted(selected - {case.profile_id for case in cases})
        raise ValueError(f"unknown release profile ids: {unknown}")
    for index, case in enumerate(cases, start=1):
        print(f"[{index:02d}/{len(cases):02d}] {case.profile_id}", flush=True)
        case_dir = output / case.profile_id
        default_dir = case_dir / "default"
        representative_dir = case_dir / "representative"
        default_dir.mkdir(parents=True)
        representative_dir.mkdir(parents=True)
        default_opju = default_dir / "plot.opju"
        edited_opju = representative_dir / "plot.opju"
        try:
            default_request = _request(
                case,
                install_dir=install_dir,
                output=default_opju,
                previous=None,
            )
            default_response = live_worker.run(default_request)
            title, edited_document = _edited_history(case)
            edited_request = _request(
                case,
                install_dir=install_dir,
                output=edited_opju,
                previous=default_opju,
                title=title,
                document=edited_document,
            )
            edited_response = live_worker.run(edited_request)
            if default_response.readback.data_hash != edited_response.readback.data_hash:
                raise RuntimeError("Origin edit changed the immutable representative data hash")
            if not default_response.readback.objects or not edited_response.readback.objects:
                raise RuntimeError("Origin readback did not expose editable native objects")
            fresh_result = representative_dir / "fresh-readback.json"
            fresh_png = representative_dir / "fresh.png"
            _fresh_verify(
                edited_opju.with_suffix(".request.json"),
                edited_opju,
                fresh_png,
                fresh_result,
            )
            fresh = json.loads(fresh_result.read_text(encoding="utf-8"))
            if fresh["plot_version"] != 2 or fresh["profile_id"] != case.profile_id:
                raise RuntimeError("fresh Origin readback identifies the wrong plot version")
            (default_dir / "readback.json").write_text(
                default_response.readback.model_dump_json(indent=2), encoding="utf-8"
            )
            (representative_dir / "readback.json").write_text(
                edited_response.readback.model_dump_json(indent=2), encoding="utf-8"
            )
            key = f"{case.profile_id}:representative:opju"
            rows[key] = replace(
                rows[key],
                status="PASS",
                evidence_kind="origin_live_edit_fresh_readback",
                artifact=edited_opju.relative_to(output).as_posix(),
                artifact_sha256=_sha(edited_opju),
                artifact_size=edited_opju.stat().st_size,
                error_type=None,
                error_message=None,
            )
        except Exception as error:  # continue to expose all profile failures
            failures[case.profile_id] = f"{type(error).__name__}: {error}"
            key = f"{case.profile_id}:representative:opju"
            rows[key] = replace(
                rows[key],
                status="FAIL",
                evidence_kind="origin_live_edit_fresh_readback",
                error_type=type(error).__name__,
                error_message=str(error),
            )

    merged = tuple(sorted(rows.values(), key=lambda row: row.matrix_key))
    if len(merged) != 306 or len({row.matrix_key for row in merged}) != 306:
        raise RuntimeError("merged Origin matrix must contain 306 unique MatrixKeys")
    counts = {
        status: sum(row.status == status for row in merged)
        for status in ("PASS", "FAIL", "UNVERIFIED")
    }
    metadata = {
        "schema_version": "plotagent.release-origin-matrix.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "git_head": head,
        "git_status_short": _git("status", "--short"),
        "offline_matrix": str(offline),
        "origin_display_name": probe.environment.display_name,
        "origin_display_version": probe.environment.display_version,
        "origin_discovery_source": probe.environment.discovery_source,
        "profile_count": len(cases),
        "matrix_key_count": 306,
        "failures": failures,
    }
    (output / "run-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "matrix-results.json").write_text(
        json.dumps(
            [asdict(row) for row in merged],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    with (output / "matrix-results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(asdict(merged[0])))
        writer.writeheader()
        writer.writerows(asdict(row) for row in merged)
    failure_lines = "\n".join(f"  - {key}: {value}" for key, value in failures.items())
    report = (
        "# PlotAgent 34图 Origin representative 矩阵\n\n"
        f"- Git HEAD: `{head}`\n"
        f"- PASS: {counts['PASS']}\n"
        f"- FAIL: {counts['FAIL']}\n"
        f"- UNVERIFIED: {counts['UNVERIFIED']}\n"
        "- 证据链: 官方路线生成 → 新进程编辑 → 再一新进程机械复核与PNG导出。\n"
        f"- 资格结论: {'GO' if counts['FAIL'] == counts['UNVERIFIED'] == 0 else 'NO-GO'}\n"
        + (f"- 失败：\n{failure_lines}\n" if failures else "")
    )
    (output / "REPORT.md").write_text(report, encoding="utf-8")
    return merged


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--profiles",
        help="comma-separated pilot subset; omit for all 34 profiles",
    )
    args = parser.parse_args()
    if args.output is None:
        head = _git("rev-parse", "--short", "HEAD")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = REPOSITORY / "build" / "release-matrix" / f"origin-{head}-{stamp}"
    else:
        output = args.output
    profile_ids = (
        None
        if args.profiles is None
        else tuple(value.strip() for value in args.profiles.split(",") if value.strip())
    )
    rows = execute_origin_matrix(
        output,
        offline=args.offline,
        profile_ids=profile_ids,
    )
    counts = {
        status: sum(row.status == status for row in rows)
        for status in ("PASS", "FAIL", "UNVERIFIED")
    }
    print(f"OUTPUT={output.resolve()}")
    print(f"PASS={counts['PASS']} FAIL={counts['FAIL']} UNVERIFIED={counts['UNVERIFIED']}")
    return 0 if counts["FAIL"] == counts["UNVERIFIED"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
