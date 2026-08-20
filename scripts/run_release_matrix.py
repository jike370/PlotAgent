"""Execute the frozen 34-profile offline release matrix.

This phase intentionally does not start Origin.  It produces real PNG and SVG
artifacts for the minimal and representative cases, verifies stable renderer
errors for edge cases, and exercises the workflow compiler contract used to
block invalid OPJU requests before Origin starts.  Representative OPJU rows are
left UNVERIFIED for the separate live/fresh-Origin phase.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.contracts.workflows import (  # noqa: E402
    DraftFieldBinding,
    TaskDraft,
    TaskDraftItem,
    WorkflowBudget,
    WorkflowContext,
    WorkflowField,
    WorkflowSource,
)
from plotagent.engine import EngineCatalog  # noqa: E402
from plotagent.engine.backends.matplotlib import (  # noqa: E402
    default_matplotlib_backend,
)
from plotagent.engine.ports import EngineRenderSource  # noqa: E402
from plotagent.engine.profiles import ENGINE_PROFILES  # noqa: E402
from plotagent.workflows import DraftCompiler  # noqa: E402
from scripts.release_matrix_cases import RELEASE_CASES, ReleaseCase  # noqa: E402

Status = Literal["PASS", "FAIL", "UNVERIFIED"]
Format = Literal["png", "svg", "opju"]
RASTER_FORMATS: tuple[Format, ...] = ("png", "svg")
ALL_FORMATS: tuple[Format, ...] = (*RASTER_FORMATS, "opju")


@dataclass(frozen=True, slots=True)
class MatrixResult:
    matrix_key: str
    profile_id: str
    variant: str
    format: Format
    status: Status
    evidence_kind: str
    artifact: str | None
    artifact_sha256: str | None
    artifact_size: int | None
    error_type: str | None
    error_message: str | None


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _git(repository: Path, *args: str) -> str:
    return subprocess.check_output(
        ("git", *args), cwd=repository, text=True, encoding="utf-8"
    ).strip()


def _workflow_validation(case: ReleaseCase) -> tuple[bool, str | None, str | None]:
    source_alias = "source_1"
    context = WorkflowContext(
        workflow_run_id=f"workflow:release.{case.profile_id.lower()}.{case.variant}",
        project_id="project:release-matrix",
        project_revision=0,
        instruction="Frozen release-matrix contract validation.",
        sources=(
            WorkflowSource(
                source_alias=source_alias,
                source_dataset_id=case.view.data.dataset_id,
                source_version=case.view.data.version,
                content_hash=case.view.data.content_hash,
                display_name=f"release-matrix.xlsx > {case.profile_id}-{case.variant}",
                row_count=len(case.view.row_ids),
            ),
        ),
        fields=tuple(
            WorkflowField(
                field_alias=f"column_{index}",
                source_alias=source_alias,
                field_id=column.field.field_id,
                name=column.field.name,
                logical_type=column.field.logical_type,
                unit_label=column.field.unit_label,
            )
            for index, column in enumerate(case.view.columns, start=1)
        ),
        selected_source_aliases=(source_alias,),
        selected_profile_ids=(case.profile_id,),
        allowed_profile_ids=tuple(str(profile.profile_id) for profile in ENGINE_PROFILES),
        budget=WorkflowBudget(),
    )
    draft = TaskDraft(
        draft_id=f"draft:release.{case.profile_id.lower()}.{case.variant}",
        workflow_run_id=context.workflow_run_id,
        route="direct",
        summary=f"Release matrix {case.profile_id} {case.variant}",
        confidence=1,
        items=(
            TaskDraftItem(
                task_kind="create",
                item_id=f"item:release.{case.profile_id.lower()}.{case.variant}",
                plot_alias="plot_1",
                profile_id=case.profile_id,
                source_aliases=(source_alias,),
                bindings=tuple(
                    DraftFieldBinding(
                        role=binding.role,
                        source_alias=source_alias,
                        field_alias=f"column_{index}",
                    )
                    for index, binding in enumerate(case.create.bindings, start=1)
                ),
            ),
        ),
    )
    validation = DraftCompiler(EngineCatalog(ENGINE_PROFILES)).validate(draft, context)
    return validation.valid, validation.error_code, validation.message


def _result(
    case: ReleaseCase,
    format: Format,
    *,
    status: Status,
    evidence_kind: str,
    artifact: Path | None = None,
    root: Path,
    error: BaseException | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> MatrixResult:
    return MatrixResult(
        matrix_key=f"{case.profile_id}:{case.variant}:{format}",
        profile_id=case.profile_id,
        variant=case.variant,
        format=format,
        status=status,
        evidence_kind=evidence_kind,
        artifact=(artifact.relative_to(root).as_posix() if artifact is not None else None),
        artifact_sha256=(_sha256(artifact) if artifact is not None else None),
        artifact_size=(artifact.stat().st_size if artifact is not None else None),
        error_type=(type(error).__name__ if error is not None else error_type),
        error_message=(str(error) if error is not None else error_message),
    )


def execute_offline_matrix(output: Path, *, repository: Path) -> tuple[MatrixResult, ...]:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    artifact_root = output / "artifacts"
    backend = default_matplotlib_backend(output / "matplotlib-cache")
    rows: list[MatrixResult] = []

    for case in RELEASE_CASES:
        valid, error_code, error_message = _workflow_validation(case)
        if case.variant == "edge_error":
            if valid or error_code != "FIELD_TYPE_INCOMPATIBLE":
                for format in ALL_FORMATS:
                    rows.append(
                        _result(
                            case,
                            format,
                            status="FAIL",
                            evidence_kind="workflow_contract_error",
                            root=output,
                            error_type=error_code or "EXPECTED_CONTRACT_REJECTION",
                            error_message=error_message or "edge case unexpectedly passed",
                        )
                    )
                continue
            with TemporaryDirectory(prefix="plotagent-release-edge-") as temporary:
                edge_backend = default_matplotlib_backend(Path(temporary))
                try:
                    edge_backend.stage(case.document, (), EngineRenderSource(data=case.view))
                except ValueError as error:
                    for format in RASTER_FORMATS:
                        rows.append(
                            _result(
                                case,
                                format,
                                status="PASS",
                                evidence_kind="stable_renderer_error",
                                root=output,
                                error=error,
                            )
                        )
                except Exception as error:  # pragma: no cover - release diagnostics
                    for format in RASTER_FORMATS:
                        rows.append(
                            _result(
                                case,
                                format,
                                status="FAIL",
                                evidence_kind="unexpected_renderer_error",
                                root=output,
                                error=error,
                            )
                        )
                else:
                    for format in RASTER_FORMATS:
                        rows.append(
                            _result(
                                case,
                                format,
                                status="FAIL",
                                evidence_kind="expected_renderer_rejection",
                                root=output,
                                error_type="EXPECTED_RENDERER_REJECTION",
                                error_message="edge case unexpectedly rendered",
                            )
                        )
            rows.append(
                _result(
                    case,
                    "opju",
                    status="PASS",
                    evidence_kind="stable_workflow_contract_error",
                    root=output,
                    error_type=error_code,
                    error_message=error_message,
                )
            )
            continue

        if not valid:
            for format in ALL_FORMATS:
                rows.append(
                    _result(
                        case,
                        format,
                        status="FAIL",
                        evidence_kind="workflow_contract_validation",
                        root=output,
                        error_type=error_code,
                        error_message=error_message,
                    )
                )
            continue

        change = backend.stage(case.document, (), EngineRenderSource(data=case.view))
        try:
            change.publish()
            change.finalize()
        except Exception:
            change.revert()
            raise
        case_dir = artifact_root / case.profile_id / case.variant
        case_dir.mkdir(parents=True, exist_ok=True)
        for format in RASTER_FORMATS:
            destination = case_dir / f"plot.{format}"
            backend.export(case.document, destination, format)
            rows.append(
                _result(
                    case,
                    format,
                    status="PASS",
                    evidence_kind="matplotlib_artifact",
                    artifact=destination,
                    root=output,
                )
            )
        readback = case_dir / "readback.json"
        readback.write_text(change.readback.model_dump_json(indent=2), encoding="utf-8")
        if case.variant == "minimal":
            rows.append(
                _result(
                    case,
                    "opju",
                    status="PASS",
                    evidence_kind="workflow_contract_qualified",
                    root=output,
                )
            )
        else:
            rows.append(
                _result(
                    case,
                    "opju",
                    status="UNVERIFIED",
                    evidence_kind="origin_live_fresh_required",
                    root=output,
                )
            )

    if len(rows) != 306 or len({row.matrix_key for row in rows}) != 306:
        raise RuntimeError("release matrix must contain exactly 306 unique MatrixKeys")

    rows.sort(key=lambda item: item.matrix_key)
    metadata = {
        "schema_version": "plotagent.release-matrix.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "repository": str(repository.resolve()),
        "git_head": _git(repository, "rev-parse", "HEAD"),
        "git_status_short": _git(repository, "status", "--short"),
        "phase": "offline",
        "profile_count": 34,
        "variant_count": 3,
        "format_count": 3,
        "matrix_key_count": 306,
    }
    (output / "run-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "matrix-results.json").write_text(
        json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (output / "matrix-results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(asdict(rows[0])))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    counts = {
        status: sum(row.status == status for row in rows)
        for status in ("PASS", "FAIL", "UNVERIFIED")
    }
    report = (
        "# PlotAgent 34图离线发布矩阵\n\n"
        f"- Git HEAD: `{metadata['git_head']}`\n"
        f"- MatrixKey: {len(rows)} / 306\n"
        f"- PASS: {counts['PASS']}\n"
        f"- FAIL: {counts['FAIL']}\n"
        f"- UNVERIFIED: {counts['UNVERIFIED']}\n"
        "- 本阶段未启动 Origin；34 个 representative OPJU 必须由后续 "
        "live + fresh-reopen 阶段关闭。\n"
        "- minimal OPJU 只计合同资格；edge/error OPJU 计稳定前置拒绝，符合发布门禁定义。\n"
        f"- 资格结论: {'GO' if counts['FAIL'] == counts['UNVERIFIED'] == 0 else 'NO-GO'}\n"
    )
    (output / "REPORT.md").write_text(report, encoding="utf-8")
    return tuple(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repository = REPOSITORY
    if args.output is None:
        head = _git(repository, "rev-parse", "--short", "HEAD")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = repository / "build" / "release-matrix" / f"offline-{head}-{stamp}"
    else:
        output = args.output
    rows = execute_offline_matrix(output, repository=repository)
    counts = {
        status: sum(row.status == status for row in rows)
        for status in ("PASS", "FAIL", "UNVERIFIED")
    }
    print(f"OUTPUT={output.resolve()}")
    print(f"PASS={counts['PASS']} FAIL={counts['FAIL']} UNVERIFIED={counts['UNVERIFIED']}")
    return 0 if counts["FAIL"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
