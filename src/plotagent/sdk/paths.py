"""Filesystem authority used only by untrusted external transports."""

from __future__ import annotations

from pathlib import Path

from plotagent.sdk.errors import PlotAgentSDKError


def authorized_import_path(value: str | Path, roots: tuple[Path, ...]) -> Path:
    candidate = Path(value).resolve()
    if not candidate.is_file() or not any(is_within(candidate, root) for root in roots):
        raise PlotAgentSDKError(
            "IMPORT_PATH_NOT_AUTHORIZED",
            "The import source was outside the authorized roots.",
        )
    return candidate


def authorized_export_path(name: str, root: Path) -> Path:
    candidate = (root.resolve() / name).resolve()
    if candidate.parent != root.resolve() or not name or Path(name).name != name:
        raise PlotAgentSDKError(
            "EXPORT_PATH_NOT_AUTHORIZED",
            "The export destination was outside the authorized root.",
        )
    return candidate


def is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return False
    return True
