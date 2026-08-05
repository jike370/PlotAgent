from __future__ import annotations

import io
import json

from plotagent.desktop_core.runtime import CoreRuntime
from plotagent.desktop_core.services import RpcContext, ServiceRegistry
from plotagent.desktop_core.tasks import BoundedWorkerExecutor, TaskRegistry


def test_unhandled_service_exception_is_sanitized() -> None:
    secret = "credential-value-that-must-not-escape"

    def configure(
        services: ServiceRegistry,
        _tasks: TaskRegistry,
        _workers: BoundedWorkerExecutor,
    ) -> None:
        def explode(_context: RpcContext, _params: object) -> object:
            raise RuntimeError(secret)

        services.register("test.explode", explode)

    requests = [
        {
            "jsonrpc": "2.0",
            "protocol_version": "1.0",
            "id": "req:init",
            "method": "system.initialize",
            "params": {"protocol_version": "1.0", "desktop_api_version": "1.0"},
        },
        {
            "jsonrpc": "2.0",
            "protocol_version": "1.0",
            "id": "req:explode",
            "method": "test.explode",
        },
        {
            "jsonrpc": "2.0",
            "protocol_version": "1.0",
            "id": "req:stop",
            "method": "system.shutdown",
        },
    ]
    stdin = io.BytesIO(
        b"".join(
            json.dumps(request, separators=(",", ":")).encode("ascii") + b"\n"
            for request in requests
        )
    )
    stdout = io.BytesIO()
    stderr = io.StringIO()
    runtime = CoreRuntime(
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        heartbeat_interval_seconds=60,
        configure_services=configure,
    )

    assert runtime.run() == 0
    messages = [json.loads(line) for line in stdout.getvalue().splitlines()]
    failed = next(message for message in messages if message.get("id") == "req:explode")
    assert failed["error"] == {
        "code": "INTERNAL_ERROR",
        "message": "The Core request failed.",
    }
    combined = stdout.getvalue() + stderr.getvalue().encode()
    assert secret.encode() not in combined
    assert b"Traceback" not in combined
