from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast


@dataclass(frozen=True, slots=True)
class CapturedRequest:
    method: str
    path: str
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class FakeResponse:
    status_code: int = 200
    headers: Mapping[str, str] | None = None
    body: bytes = b""


RequestCallback = Callable[[CapturedRequest], FakeResponse]


class _LoopbackHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, callback: RequestCallback) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.callback = callback
        self.requests: list[CapturedRequest] = []


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle()

    def _handle(self) -> None:
        server = cast(_LoopbackHttpServer, self.server)
        length = int(self.headers.get("content-length", "0"))
        request = CapturedRequest(
            method=self.command,
            path=self.path,
            headers=dict(self.headers.items()),
            body=self.rfile.read(length),
        )
        server.requests.append(request)
        response = server.callback(request)
        headers = dict(response.headers or {})
        headers["Content-Length"] = str(len(response.body))
        self.send_response(response.status_code)
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(response.body)

    def log_message(self, *_: object) -> None:
        return


@contextlib.contextmanager
def loopback_server(callback: RequestCallback) -> Iterator[_LoopbackHttpServer]:
    server = _LoopbackHttpServer(callback)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def server_url(server: _LoopbackHttpServer) -> str:
    host, port = server.server_address
    return f"http://{host}:{port}"
