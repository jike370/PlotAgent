"""Run one dedicated Origin worker with a bounded lifetime."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkerInvocation:
    ok: bool
    payload: dict[str, Any] | None
    stderr: str
    timed_out: bool = False
    cancelled: bool = False


def _worker_environment() -> dict[str, str]:
    environment = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[2])
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = source_root if not existing else source_root + os.pathsep + existing
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def _terminate_worker_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def run_worker(
    mode: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    *,
    cancel_requested: Callable[[], bool] | None = None,
) -> WorkerInvocation:
    if mode not in {"probe", "build", "reopen", "build-plan", "reopen-plan"}:
        raise ValueError(f"unsupported Origin worker mode: {mode}")
    command = [sys.executable, "-m", "plotagent.origin._worker", mode]
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=_worker_environment(),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if cancel_requested is None:
        try:
            stdout, stderr = process.communicate(
                json.dumps(payload, ensure_ascii=False), timeout=timeout_seconds
            )
        except subprocess.TimeoutExpired:
            _terminate_worker_tree(process)
            return WorkerInvocation(
                ok=False, payload=None, stderr="worker timed out", timed_out=True
            )
    else:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            _terminate_worker_tree(process)
            return WorkerInvocation(ok=False, payload=None, stderr="worker pipes unavailable")
        process.stdin.write(json.dumps(payload, ensure_ascii=False))
        process.stdin.close()
        started = time.monotonic()
        while process.poll() is None:
            if cancel_requested():
                _terminate_worker_tree(process)
                return WorkerInvocation(
                    ok=False,
                    payload=None,
                    stderr="worker cancelled",
                    cancelled=True,
                )
            if time.monotonic() - started >= timeout_seconds:
                _terminate_worker_tree(process)
                return WorkerInvocation(
                    ok=False,
                    payload=None,
                    stderr="worker timed out",
                    timed_out=True,
                )
            time.sleep(0.05)
        stdout = process.stdout.read()
        stderr = process.stderr.read()

    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return WorkerInvocation(ok=False, payload=None, stderr=stderr or "worker returned no JSON")
    try:
        response = json.loads(lines[-1])
    except json.JSONDecodeError:
        return WorkerInvocation(
            ok=False,
            payload=None,
            stderr=(stderr + "\ninvalid worker output: " + stdout).strip(),
        )
    if not isinstance(response, dict):
        return WorkerInvocation(ok=False, payload=None, stderr="worker JSON was not an object")
    return WorkerInvocation(
        ok=process.returncode == 0 and response.get("status") == "ok",
        payload=response,
        stderr=stderr.strip(),
    )
