"""Export one graph from an OPJU in a standalone Origin process.

OriginPro 2024 SR1 has a confirmed OLE/COM rendering defect that can draw
spurious lines above text while an embedded or externally automated Origin
session renders a graph.  The OPJU itself is not modified by that defect and
renders correctly when opened by an independent Origin executable.  Release
visual evidence therefore has to use the latter process boundary.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def _origin_executable(install_dir: Path) -> Path:
    candidates = (
        install_dir / "Origin64.exe",
        install_dir / "Origin.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"no supported Origin executable found under {install_dir}"
    )


def _labtalk_string(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\").replace('"', '\\"')


def _standalone_ogs(opju_path: Path, png_path: Path) -> str:
    return "\n".join(
        (
            "[Main]",
            f'string figAgentProject$ = "{_labtalk_string(opju_path)}";',
            "doc -o %(figAgentProject$);",
            "doc -e P",
            "{",
            (
                "    expGraph type:=png "
                f'path:="{_labtalk_string(png_path.parent)}" '
                f'filename:="{png_path.stem}" '
                "tr1.unit:=2 tr1.width:=1600 overwrite:=replace;"
            ),
            "}",
            "doc -s;",
            "exit;",
            "",
        )
    )


def export_origin_png_standalone(
    *,
    install_dir: Path,
    opju_path: Path,
    png_path: Path,
    timeout_seconds: float = 180,
) -> None:
    """Open ``opju_path`` outside COM and export its sole graph to PNG."""

    install_dir = install_dir.resolve()
    opju_path = opju_path.resolve()
    png_path = png_path.resolve()
    if not opju_path.is_file():
        raise FileNotFoundError(f"Origin project does not exist: {opju_path}")
    if png_path.suffix.lower() != ".png":
        raise ValueError("standalone Origin visual evidence must use a .png target")
    png_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.unlink(missing_ok=True)
    executable = _origin_executable(install_dir)

    with tempfile.TemporaryDirectory(
        prefix="fig-agent-origin-standalone-",
        dir=png_path.parent,
    ) as temporary:
        temporary_path = Path(temporary)
        ogs_path = temporary_path / "export.ogs"
        log_path = temporary_path / "origin-script.log"
        ogs_path.write_text(
            _standalone_ogs(opju_path, png_path),
            encoding="utf-8",
        )
        command = (
            f'"{executable}" -HS -SLOG "{log_path}" '
            f'-RS run.section("{_labtalk_string(ogs_path)}", Main)'
        )
        completed = subprocess.run(
            command,
            executable=str(executable),
            cwd=install_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            log = (
                log_path.read_text(encoding="utf-8", errors="replace")
                if log_path.exists()
                else ""
            )
            detail = completed.stderr.strip() or completed.stdout.strip() or log.strip()
            raise RuntimeError(
                "standalone Origin export failed"
                + (f": {detail}" if detail else f" with exit code {completed.returncode}")
            )
    if not png_path.is_file() or png_path.stat().st_size <= 0:
        raise RuntimeError("standalone Origin did not export a non-empty PNG")
