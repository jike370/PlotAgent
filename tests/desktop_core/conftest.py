from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import BinaryIO

import pytest


class SidecarProcess:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        source = str(root / "src")
        env["PYTHONPATH"] = (
            source
            if existing_pythonpath is None
            else os.pathsep.join((source, existing_pythonpath))
        )
        self.process = subprocess.Popen(
            [sys.executable, "-m", "plotagent.desktop_core"],
            cwd=root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        assert self.process.stderr is not None
        self.stdin = self.process.stdin
        self._stdout_queue: queue.Queue[bytes] = queue.Queue()
        self._stderr_queue: queue.Queue[bytes] = queue.Queue()
        self.stdout_lines: list[bytes] = []
        self.stderr_lines: list[bytes] = []
        self._stdout_thread = self._reader(
            self.process.stdout,
            self._stdout_queue,
            self.stdout_lines,
        )
        self._stderr_thread = self._reader(
            self.process.stderr,
            self._stderr_queue,
            self.stderr_lines,
        )

    @staticmethod
    def _reader(
        stream: BinaryIO,
        target: queue.Queue[bytes],
        captured: list[bytes],
    ) -> threading.Thread:
        def read_lines() -> None:
            for line in iter(stream.readline, b""):
                captured.append(line)
                target.put(line)

        thread = threading.Thread(target=read_lines, daemon=True)
        thread.start()
        return thread

    def send_request(
        self,
        request_id: str,
        method: str,
        params: object = ...,
    ) -> dict[str, object]:
        message: dict[str, object] = {
            "jsonrpc": "2.0",
            "protocol_version": "1.0",
            "id": request_id,
            "method": method,
        }
        if params is not ...:
            message["params"] = params
        self.send_raw(json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n")
        return self.read_until(lambda value: value.get("id") == request_id)

    def send_raw(self, value: bytes) -> None:
        self.stdin.write(value)
        self.stdin.flush()

    def read_until(
        self,
        predicate: object,
        *,
        timeout: float = 5.0,
    ) -> dict[str, object]:
        assert callable(predicate)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError("timed out waiting for sidecar protocol message")
            try:
                line = self._stdout_queue.get(timeout=remaining)
            except queue.Empty as error:
                raise AssertionError("timed out waiting for sidecar protocol message") from error
            value = json.loads(line)
            assert isinstance(value, dict)
            if predicate(value):
                return value

    def wait(self, timeout: float = 5.0) -> int:
        return self.process.wait(timeout=timeout)

    def close_stdin(self) -> None:
        if not self.stdin.closed:
            self.stdin.close()

    def cleanup(self) -> None:
        self.close_stdin()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self._stdout_thread.join(timeout=1)
        self._stderr_thread.join(timeout=1)


@pytest.fixture
def sidecar() -> SidecarProcess:
    process = SidecarProcess()
    try:
        yield process
    finally:
        process.cleanup()
