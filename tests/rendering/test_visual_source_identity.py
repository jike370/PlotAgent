from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.visual_source_identity import (
    DIGEST_ALGORITHM,
    SourceIdentityError,
    assert_scope_clean,
    git_blob_framed_sha256,
    source_build_identity,
)

REPOSITORY = Path(__file__).resolve().parents[2]
SOURCE_COMMIT = "5982a0853de03f908063b8f24e7f13ef89d81bb9"
SOURCE_SHA256 = "60d6f4bd58ca3cd86dc9e86c3ca2d1752c6c94e1dc981018fa8f429db8f8401d"
SOURCE_SCOPE = (
    Path("pyproject.toml"),
    Path("src/plotagent/charts"),
    Path("src/plotagent/contracts/rendering.py"),
    Path("src/plotagent/contracts/styles.py"),
    Path("src/plotagent/origin"),
    Path("src/plotagent/rendering"),
)


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(("git", *arguments), cwd=repository, check=True, capture_output=True)


def _git_is_ancestor(repository: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ("git", "merge-base", "--is-ancestor", ancestor, descendant),
        cwd=repository,
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.name", "PlotAgent Test")
    _git(repository, "config", "user.email", "plotagent@example.invalid")
    source = repository / "source"
    source.mkdir()
    (source / "module.txt").write_bytes(b"alpha\nbeta\n")
    (source / "payload.bin").write_bytes(b"\x00binary\r\nvalue\xff")
    _git(repository, "add", "source")
    _git(repository, "commit", "--quiet", "-m", "fixture")
    return repository


def test_git_blob_identity_is_stable_across_worktree_crlf(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    source = repository / "source" / "module.txt"
    before = git_blob_framed_sha256(repository, (Path("source"),))

    source.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))

    assert source.read_bytes() == b"alpha\r\nbeta\r\n"
    assert git_blob_framed_sha256(repository, (Path("source"),)) == before
    identity = source_build_identity(
        repository,
        (Path("source"),),
        scope_version="test-v2",
        require_clean=False,
    )
    assert identity["digest_algorithm"] == DIGEST_ALGORITHM
    assert identity["source_sha256"] == before


@pytest.mark.parametrize("dirty_kind", ("unstaged", "staged", "untracked"))
def test_scope_clean_gate_rejects_all_worktree_changes(
    tmp_path: Path, dirty_kind: str
) -> None:
    repository = _repository(tmp_path)
    if dirty_kind == "untracked":
        (repository / "source" / "untracked.txt").write_text("new", encoding="utf-8")
    else:
        (repository / "source" / "module.txt").write_text("changed", encoding="utf-8")
        if dirty_kind == "staged":
            _git(repository, "add", "source/module.txt")

    with pytest.raises(SourceIdentityError, match="scope is dirty"):
        assert_scope_clean(repository, (Path("source"),))
    with pytest.raises(SourceIdentityError, match="scope is dirty"):
        source_build_identity(
            repository,
            (Path("source"),),
            scope_version="test-v2",
        )


def test_binary_git_blob_is_hashed_without_eol_normalization(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    relative = b"source/payload.bin"
    payload = b"\x00binary\r\nvalue\xff"
    expected = hashlib.sha256(
        len(relative).to_bytes(4, "big")
        + relative
        + len(payload).to_bytes(8, "big")
        + payload
    ).hexdigest()

    assert git_blob_framed_sha256(
        repository,
        (Path("source/payload.bin"),),
    ) == expected


def test_frozen_visual_manifests_share_canonical_source_identity() -> None:
    assert git_blob_framed_sha256(REPOSITORY, SOURCE_SCOPE, commit=SOURCE_COMMIT) == SOURCE_SHA256
    assert git_blob_framed_sha256(REPOSITORY, SOURCE_SCOPE) == SOURCE_SHA256
    manifests = {
        **{
            REPOSITORY
            / "tests"
            / "fixtures"
            / "visual_regression"
            / "seq20"
            / f"batch-{batch}.manifest.json": "seq20-rendering-v2"
            for batch in (1, 2, 3, 4)
        },
        **{
            REPOSITORY
            / "tests"
            / "fixtures"
            / "visual_regression"
            / lane
            / "manifest.json": f"{lane}-rendering-v2"
            for lane in ("visual29-fixed", "visual29-matrix", "visual29-structural")
        },
    }
    for path, scope_version in manifests.items():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        qualification = manifest["qualification"]
        identity = qualification["source_build_identity"]
        assert identity["scope_version"] == scope_version
        assert identity["digest_algorithm"] == DIGEST_ALGORITHM
        assert identity["source_sha256"] == SOURCE_SHA256
        assert _git_is_ancestor(REPOSITORY, SOURCE_COMMIT, identity["git_commit"])
        assert (
            git_blob_framed_sha256(
                REPOSITORY,
                SOURCE_SCOPE,
                commit=identity["git_commit"],
            )
            == SOURCE_SHA256
        )

    structural = json.loads(
        (
            REPOSITORY
            / "tests"
            / "fixtures"
            / "visual_regression"
            / "visual29-structural"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert all(
        state["source_sha256"] == SOURCE_SHA256
        for case in structural["cases"]
        for state in case["states"].values()
    )
