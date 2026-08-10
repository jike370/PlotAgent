"""Run one dedicated Origin worker with a bounded lifetime."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
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


def _communicate_plan_worker(
    process: subprocess.Popen[str],
    mode: str,
    request: str,
    timeout_seconds: float,
    cancel_requested: Callable[[], bool] | None,
    *,
    cleanup_grace_seconds: float = 5.0,
) -> tuple[str, str, bool] | WorkerInvocation:
    if process.stdin is None or process.stdout is None or process.stderr is None:
        _terminate_worker_tree(process)
        return WorkerInvocation(ok=False, payload=None, stderr="worker pipes unavailable")

    stdin_pipe = process.stdin
    stdout_pipe = process.stdout
    stderr_pipe = process.stderr
    stdin_pipe.write(request)
    stdin_pipe.close()
    messages: queue.Queue[str | None] = queue.Queue()

    def pump_stdout() -> None:
        try:
            for line in stdout_pipe:
                messages.put(line)
        finally:
            messages.put(None)

    reader = threading.Thread(target=pump_stdout, daemon=True)
    reader.start()
    started = time.monotonic()
    lines: list[str] = []
    accepted_response = False
    accepted_success = False
    reached_eof = False
    while not accepted_response and not reached_eof:
        if cancel_requested is not None and cancel_requested():
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
        try:
            message = messages.get(timeout=0.05)
        except queue.Empty:
            if process.poll() is not None and not reader.is_alive():
                reached_eof = True
            continue
        if message is None:
            reached_eof = True
            continue
        lines.append(message)
        try:
            candidate = json.loads(message)
        except json.JSONDecodeError:
            continue
        accepted_response = isinstance(candidate, dict) and "status" in candidate
        accepted_success = accepted_response and candidate.get("status") == "ok"

    if accepted_success and mode == "build-plan":
        try:
            request_payload = json.loads(request)
            temporary_path = Path(str(request_payload["temporary_opju_path"]))
        except (json.JSONDecodeError, KeyError, TypeError):
            _terminate_worker_tree(process)
            return WorkerInvocation(
                ok=False,
                payload=None,
                stderr="worker build response omitted its temporary OPJU path",
            )
        last_signature: tuple[int, int] | None = None
        stable_samples = 0
        while stable_samples < 10:
            if cancel_requested is not None and cancel_requested():
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
                    stderr="worker timed out before the OPJU became stable",
                    timed_out=True,
                )
            if temporary_path.is_file() and temporary_path.stat().st_size > 0:
                stat = temporary_path.stat()
                signature = (stat.st_size, stat.st_mtime_ns)
                stable_samples = stable_samples + 1 if signature == last_signature else 0
                last_signature = signature
            else:
                stable_samples = 0
                last_signature = None
            time.sleep(0.05)
        if process.poll() is None:
            _terminate_worker_tree(process)
    elif accepted_response and process.poll() is None:
        try:
            process.wait(timeout=cleanup_grace_seconds)
        except subprocess.TimeoutExpired:
            _terminate_worker_tree(process)
    elif process.poll() is None:
        try:
            process.wait(timeout=max(0.1, timeout_seconds - (time.monotonic() - started)))
        except subprocess.TimeoutExpired:
            _terminate_worker_tree(process)
            return WorkerInvocation(
                ok=False,
                payload=None,
                stderr="worker timed out",
                timed_out=True,
            )

    reader.join(timeout=1.0)
    stderr = stderr_pipe.read()
    return "".join(lines), stderr, accepted_response


def run_worker(
    mode: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    *,
    cancel_requested: Callable[[], bool] | None = None,
) -> WorkerInvocation:
    if mode not in {"probe", "build-plan", "reopen-plan"}:
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
    accepted_response = False
    if mode in {"build-plan", "reopen-plan"}:
        plan_result = _communicate_plan_worker(
            process,
            mode,
            json.dumps(payload, ensure_ascii=False),
            timeout_seconds,
            cancel_requested,
        )
        if isinstance(plan_result, WorkerInvocation):
            return plan_result
        stdout, stderr, accepted_response = plan_result
    elif cancel_requested is None:
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
        ok=(accepted_response or process.returncode == 0) and response.get("status") == "ok",
        payload=response,
        stderr=stderr.strip(),
    )
