from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[2]
FIXTURES = REPOSITORY / "tests" / "fixtures" / "visual_regression" / "seq20"
SOURCE_SCOPE_VERSION = "seq20-rendering-v1"
SOURCE_SCOPE = (
    Path("pyproject.toml"),
    Path("src/plotagent/charts"),
    Path("src/plotagent/contracts/rendering.py"),
    Path("src/plotagent/contracts/styles.py"),
    Path("src/plotagent/origin"),
    Path("src/plotagent/rendering"),
)
CURRENT_P0_BLOCKERS: tuple[tuple[str, str], ...] = ()
_SHA256 = re.compile(r"[0-9a-f]{64}")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class GateResult:
    decision: str
    failures: tuple[str, ...]


def _source_files(repository: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    for relative in SOURCE_SCOPE:
        path = repository / relative
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(
                candidate
                for candidate in path.rglob("*")
                if candidate.is_file()
                and "__pycache__" not in candidate.parts
                and candidate.suffix not in {".pyc", ".pyo"}
            )
        else:
            raise AssertionError(f"missing SEQ-20 source identity path: {relative.as_posix()}")
    return tuple(sorted(files, key=lambda path: path.relative_to(repository).as_posix()))


def _source_build_sha256(repository: Path) -> str:
    digest = hashlib.sha256()
    for path in _source_files(repository):
        relative = path.relative_to(repository).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _load_manifests() -> tuple[dict[str, Any], ...]:
    return tuple(
        json.loads((FIXTURES / f"batch-{batch}.manifest.json").read_text(encoding="utf-8"))
        for batch in (1, 2, 3)
    )


def _evaluate_gate(
    manifests: tuple[dict[str, Any], ...],
    *,
    current_source_sha256: str,
    known_blockers: tuple[tuple[str, str], ...] = (),
) -> GateResult:
    failures: list[str] = []
    for manifest in manifests:
        batch = manifest["batch"]
        qualification = manifest.get("qualification")
        if not isinstance(qualification, dict):
            failures.extend(
                (
                    f"batch-{batch}:QUALIFICATION_METADATA_MISSING",
                    f"batch-{batch}:SOURCE_BUILD_IDENTITY_MISSING",
                    f"batch-{batch}:BLOCKING_OBSERVATIONS_MISSING",
                    f"batch-{batch}:HUMAN_VISUAL_SIGNATURE_MISSING",
                )
            )
            continue

        identity = qualification.get("source_build_identity")
        if not isinstance(identity, dict):
            failures.append(f"batch-{batch}:SOURCE_BUILD_IDENTITY_MISSING")
        else:
            if identity.get("scope_version") != SOURCE_SCOPE_VERSION:
                failures.append(f"batch-{batch}:SOURCE_SCOPE_VERSION_MISMATCH")
            git_commit = identity.get("git_commit")
            if not isinstance(git_commit, str) or _GIT_COMMIT.fullmatch(git_commit) is None:
                failures.append(f"batch-{batch}:GIT_COMMIT_INVALID")
            source_sha256 = identity.get("source_sha256")
            if not isinstance(source_sha256, str) or _SHA256.fullmatch(source_sha256) is None:
                failures.append(f"batch-{batch}:SOURCE_SHA256_INVALID")
            elif source_sha256 != current_source_sha256:
                failures.append(f"batch-{batch}:SOURCE_BUILD_STALE")

        blocking_observations = qualification.get("blocking_observations")
        if not isinstance(blocking_observations, list):
            failures.append(f"batch-{batch}:BLOCKING_OBSERVATIONS_MISSING")
        else:
            for observation in blocking_observations:
                chart_id = observation.get("chart_type_id", "unknown")
                code = observation.get("code", "UNKNOWN_BLOCKER")
                failures.append(f"{chart_id}:{code}")

        signature = qualification.get("human_visual_signature")
        if not isinstance(signature, dict) or signature.get("status") != "approved":
            failures.append(f"batch-{batch}:HUMAN_VISUAL_SIGNATURE_MISSING")

    failures.extend(f"{chart_id}:{code}" for chart_id, code in known_blockers)
    unique_failures = tuple(dict.fromkeys(failures))
    return GateResult(decision="GO" if not unique_failures else "NO-GO", failures=unique_failures)


def _qualified_manifest(source_sha256: str) -> dict[str, Any]:
    return {
        "batch": 1,
        "qualification": {
            "source_build_identity": {
                "scope_version": SOURCE_SCOPE_VERSION,
                "git_commit": "1" * 40,
                "source_sha256": source_sha256,
            },
            "blocking_observations": [],
            "human_visual_signature": {
                "status": "approved",
                "reviewer": "visual-owner",
                "signed_at": "2026-08-08T00:00:00+00:00",
            },
        },
    }


def test_seq20_current_evidence_is_explicit_visual_no_go() -> None:
    result = _evaluate_gate(
        _load_manifests(),
        current_source_sha256=_source_build_sha256(REPOSITORY),
        known_blockers=CURRENT_P0_BLOCKERS,
    )

    assert result.decision == "NO-GO"
    assert result.failures == tuple(
        f"batch-{batch}:HUMAN_VISUAL_SIGNATURE_MISSING" for batch in (1, 2, 3)
    )


def test_gate_rejects_nonempty_blocking_observations() -> None:
    source_sha256 = _source_build_sha256(REPOSITORY)
    manifest = _qualified_manifest(source_sha256)
    manifest["qualification"]["blocking_observations"] = [
        {
            "chart_type_id": "K09",
            "code": "GROUPED_BAR_OVERLAP",
            "status": "open",
        }
    ]

    result = _evaluate_gate((manifest,), current_source_sha256=source_sha256)

    assert result.decision == "NO-GO"
    assert result.failures == ("K09:GROUPED_BAR_OVERLAP",)


def test_shared_rendering_change_makes_old_qualification_stale() -> None:
    source_sha256 = _source_build_sha256(REPOSITORY)
    manifest = _qualified_manifest("0" * 64)

    result = _evaluate_gate((manifest,), current_source_sha256=source_sha256)

    assert result.decision == "NO-GO"
    assert result.failures == ("batch-1:SOURCE_BUILD_STALE",)


def test_manual_visual_observations_require_signature_not_automatic_blocker() -> None:
    source_sha256 = _source_build_sha256(REPOSITORY)
    manifest = _qualified_manifest(source_sha256)
    manifest["cases"] = [
        {
            "chart_type_id": "X01",
            "visual_observations": ["标题位置需要人工视觉判断。"],
        }
    ]

    result = _evaluate_gate((manifest,), current_source_sha256=source_sha256)

    assert result.decision == "GO"
    assert result.failures == ()
