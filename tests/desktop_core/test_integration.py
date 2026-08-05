from __future__ import annotations

import json

from .conftest import SidecarProcess


def _initialize(sidecar: SidecarProcess) -> dict[str, object]:
    return sidecar.send_request(
        "req:init",
        "system.initialize",
        {"protocol_version": "1.0", "desktop_api_version": "1.0"},
    )


def test_real_process_handshake_heartbeat_health_and_snapshot(sidecar: SidecarProcess) -> None:
    initialized = _initialize(sidecar)
    assert initialized["result"] == {
        "status": "ready",
        "protocol_version": "1.0",
        "desktop_api_version": "1.0",
        "core_version": "0.1.0",
    }

    ready = sidecar.read_until(lambda value: value.get("method") == "system.ready")
    assert ready["params"] == initialized["result"]
    heartbeat = sidecar.read_until(lambda value: value.get("method") == "health.heartbeat")
    assert heartbeat["params"] == {
        "status": "ready",
        "sequence": 1,
        "protocol_version": "1.0",
    }

    health = sidecar.send_request("req:health", "health.get")
    assert health["result"] == {
        "status": "ready",
        "protocol_version": "1.0",
        "desktop_api_version": "1.0",
        "core_version": "0.1.0",
        "active_task_count": 0,
        "worker_capacity": 2,
    }
    snapshot = sidecar.send_request("req:snapshot", "task.get_snapshot")
    assert snapshot["result"] == {
        "tasks": [],
        "active_task_count": 0,
        "has_committing_task": False,
    }

    stopped = sidecar.send_request("req:stop", "system.shutdown")
    assert stopped["result"] == {"status": "stopping"}
    assert sidecar.wait() == 0
    assert all(
        json.loads(line)["protocol_version"] == "1.0" for line in sidecar.stdout_lines
    )


def test_invalid_frames_are_sanitized_and_the_process_survives(sidecar: SidecarProcess) -> None:
    _initialize(sidecar)
    sidecar.read_until(lambda value: value.get("method") == "system.ready")
    sidecar.read_until(lambda value: value.get("method") == "health.heartbeat")

    sidecar.send_raw(b"{not-json}\n")
    parse_error = sidecar.read_until(
        lambda value: value.get("method") == "system.protocol_error"
    )
    assert parse_error["params"] == {
        "code": "PARSE_ERROR",
        "message": "The protocol frame was not valid JSON.",
    }

    secret = "sk-should-never-be-reflected"
    invalid_params = sidecar.send_request(
        "req:invalid",
        "task.cancel",
        {"task_id": "task:missing", "credential": secret},
    )
    assert invalid_params["error"] == {
        "code": "INVALID_PARAMS",
        "message": "The request parameters were invalid.",
    }

    sidecar.send_raw(b"x" * (1024 * 1024 + 1) + b"\n")
    too_large = sidecar.read_until(
        lambda value: value.get("method") == "system.protocol_error"
        and isinstance(value.get("params"), dict)
        and value["params"].get("code") == "FRAME_TOO_LARGE"
    )
    assert too_large["params"] == {
        "code": "FRAME_TOO_LARGE",
        "message": "The protocol frame exceeded the size limit.",
    }

    nested: object = None
    for _ in range(34):
        nested = [nested]
    too_deep = sidecar.send_request("req:deep", "system.ping", nested)
    assert too_deep["error"] == {
        "code": "INVALID_REQUEST",
        "message": "The request exceeded the JSON depth limit.",
    }

    ping = sidecar.send_request("req:after-invalid", "system.ping")
    assert ping["result"] == {"status": "ok", "protocol_version": "1.0"}
    sidecar.send_request("req:stop", "system.shutdown")
    assert sidecar.wait() == 0

    combined_output = b"".join(sidecar.stdout_lines + sidecar.stderr_lines)
    assert secret.encode("ascii") not in combined_output
    assert b"Traceback" not in combined_output
    assert str(__file__).encode() not in combined_output


def test_request_ids_are_replayed_or_rejected_on_conflict(sidecar: SidecarProcess) -> None:
    _initialize(sidecar)
    first = sidecar.send_request("req:same", "system.ping")
    replay = sidecar.send_request("req:same", "system.ping")
    assert replay == first

    conflict = sidecar.send_request("req:same", "health.get")
    assert conflict["error"] == {
        "code": "IDEMPOTENCY_CONFLICT",
        "message": "The request id was already used for a different request.",
    }
    unknown = sidecar.send_request("req:unknown", "project.import")
    assert unknown["error"] == {
        "code": "METHOD_NOT_FOUND",
        "message": "The requested Core method was not found.",
    }

    sidecar.send_request("req:stop", "system.shutdown")
    assert sidecar.wait() == 0


def test_task_cancel_control_and_eof_are_graceful(sidecar: SidecarProcess) -> None:
    _initialize(sidecar)
    missing = sidecar.send_request(
        "req:cancel",
        "tasks.cancel",
        {"task_id": "task:missing"},
    )
    assert missing["error"] == {
        "code": "TASK_NOT_FOUND",
        "message": "The requested task was not found.",
    }
    sidecar.close_stdin()
    assert sidecar.wait() == 0
