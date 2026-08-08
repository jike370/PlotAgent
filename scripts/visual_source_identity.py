"""Stable source identities for visual-qualification evidence.

The identity is computed from Git blobs at a named commit, not from checkout
bytes.  That keeps it stable across Windows CRLF conversion while preserving
binary files byte-for-byte.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Sequence
from pathlib import Path

DIGEST_ALGORITHM = "git-blob-framed-sha256-v1"


class SourceIdentityError(RuntimeError):
    """Raised when a visual source identity cannot be produced safely."""


def _scope_pathspecs(scope: Sequence[Path]) -> tuple[str, ...]:
    pathspecs: list[str] = []
    for path in scope:
        if path.is_absolute() or ".." in path.parts:
            raise SourceIdentityError(f"source identity path must be repository-relative: {path}")
        pathspec = path.as_posix().strip("/")
        if not pathspec:
            raise SourceIdentityError("source identity path must not be empty")
        pathspecs.append(pathspec)
    if not pathspecs:
        raise SourceIdentityError("source identity scope must not be empty")
    return tuple(pathspecs)


def _git(repository: Path, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            ("git", *arguments),
            cwd=repository,
            check=True,
            capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise SourceIdentityError(detail or f"git {' '.join(arguments)} failed") from exc


def resolve_commit(repository: Path, commit: str = "HEAD") -> str:
    resolved = _git(repository, "rev-parse", "--verify", f"{commit}^{{commit}}").decode(
        "ascii"
    ).strip().lower()
    if len(resolved) != 40 or any(character not in "0123456789abcdef" for character in resolved):
        raise SourceIdentityError("git did not return a full SHA-1 commit identity")
    return resolved


def assert_scope_clean(repository: Path, scope: Sequence[Path]) -> None:
    """Reject staged, unstaged, or untracked changes inside ``scope``."""

    pathspecs = _scope_pathspecs(scope)
    status = _git(
        repository,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--",
        *pathspecs,
    )
    if status:
        summary = status.replace(b"\0", b"\n").decode("utf-8", errors="replace").strip()
        raise SourceIdentityError(f"source identity scope is dirty:\n{summary}")


def git_blob_framed_sha256(
    repository: Path,
    scope: Sequence[Path],
    *,
    commit: str = "HEAD",
) -> str:
    """Hash tracked Git blob bytes using the established path/content framing."""

    pathspecs = _scope_pathspecs(scope)
    resolved = resolve_commit(repository, commit)
    for pathspec in pathspecs:
        _git(repository, "cat-file", "-e", f"{resolved}:{pathspec}")

    tree = _git(
        repository,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        resolved,
        "--",
        *pathspecs,
    )
    entries: list[tuple[bytes, str]] = []
    for record in tree.split(b"\0"):
        if not record:
            continue
        metadata, separator, relative = record.partition(b"\t")
        if not separator:
            raise SourceIdentityError("git ls-tree returned an invalid record")
        fields = metadata.split()
        if len(fields) != 3 or fields[1] != b"blob":
            raise SourceIdentityError("source identity scope contains a non-blob Git entry")
        entries.append((relative, fields[2].decode("ascii")))
    if not entries:
        raise SourceIdentityError("source identity scope contains no tracked blobs")

    digest = hashlib.sha256()
    for relative, object_id in sorted(entries, key=lambda item: item[0]):
        content = _git(repository, "cat-file", "blob", object_id)
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def source_build_identity(
    repository: Path,
    scope: Sequence[Path],
    *,
    scope_version: str,
    commit: str = "HEAD",
    require_clean: bool = True,
) -> dict[str, str]:
    """Return a manifest-ready identity bound to one committed source tree."""

    if require_clean:
        assert_scope_clean(repository, scope)
    resolved = resolve_commit(repository, commit)
    return {
        "scope_version": scope_version,
        "digest_algorithm": DIGEST_ALGORITHM,
        "git_commit": resolved,
        "source_sha256": git_blob_framed_sha256(repository, scope, commit=resolved),
    }
