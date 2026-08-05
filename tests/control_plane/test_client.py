from __future__ import annotations

import asyncio
import json
import logging
import uuid

import pytest

from plotagent.control_plane.client import (
    BuiltinControlPlaneClient,
    ControlPlaneClientError,
)
from plotagent.control_plane.models import ModelInvokeRequest, ModelRunResponse
from plotagent.security import (
    HttpxRawTransport,
    InMemoryCredentialStore,
    NetworkMode,
    NetworkPolicyGate,
    NetworkPurpose,
    NetworkRequest,
    PolicyTransport,
)
from tests.http_server import (
    CapturedRequest,
    FakeResponse,
    loopback_server,
    server_url,
)

DEVICE_SECRET = "device-v1-DO-NOT-LEAK"
INVITE_SECRET = "invite-v1-DO-NOT-LEAK"
SERVER_TIME = "2026-08-05T00:00:00Z"


def quota_payload() -> dict[str, object]:
    return {
        "invite_id": "invite-1",
        "granted": 4,
        "consumed": 1,
        "remaining": 3,
        "period_start": None,
        "reset_at": None,
        "server_time": SERVER_TIME,
    }


def model_run_payload(*, replayed: bool) -> dict[str, object]:
    return {
        "client_run_id": "run-idempotent",
        "model_profile_id": "profile-v1",
        "state": "completed",
        "quota_unit": 1,
        "quota_snapshot": quota_payload(),
        "response_payload": {
            "provider_request_id": "provider-request-1",
            "decision": {"decision_type": "no_change", "reason_code": "already_satisfied"},
        },
        "idempotency_replayed": replayed,
        "created_at": SERVER_TIME,
        "finished_at": SERVER_TIME,
    }


def client_for(
    base_url: str,
    store: InMemoryCredentialStore,
) -> tuple[BuiltinControlPlaneClient, HttpxRawTransport]:
    def bearer(request: NetworkRequest) -> str | None:
        if request.purpose is NetworkPurpose.INVITATION_REDEEM:
            return None
        return store.get_device_credential()

    raw = HttpxRawTransport(
        bearer_token_provider=bearer,
        bearer_required_purposes=frozenset(
            {
                NetworkPurpose.BUILTIN_MODEL,
                NetworkPurpose.DEVICE_CREDENTIAL,
                NetworkPurpose.QUOTA,
            }
        ),
    )
    transport = PolicyTransport(
        NetworkPolicyGate(
            NetworkMode.BUILTIN_PROXY,
            builtin_endpoints=(f"{base_url}/v1",),
        ),
        raw,
    )
    return (
        BuiltinControlPlaneClient(
            transport,
            store,
            base_url=base_url,
            app_build="integration-test",
            protocol_version="1",
        ),
        raw,
    )


def test_builtin_client_redeem_auth_quota_invoke_status_and_revoke() -> None:
    invoke_count = 0

    def respond(request: CapturedRequest) -> FakeResponse:
        nonlocal invoke_count
        authorization = request.headers.get("Authorization")
        if request.path == "/v1/invites/redeem":
            body = json.loads(request.body)
            assert body["invite_secret"] == INVITE_SECRET
            assert uuid.UUID(body["installation_id"]).version == 4
            assert authorization is None
            payload = {
                "invite_id": "invite-1",
                "device_id": "device-1",
                "device_credential": DEVICE_SECRET,
                "allowed_model_profile_ids": ["profile-v1"],
                "quota_snapshot": quota_payload(),
                "protocol_version": "1",
            }
        else:
            assert authorization == f"Bearer {DEVICE_SECRET}"
            if request.path == "/v1/credentials/verify":
                payload = {
                    "invite_id": "invite-1",
                    "device_id": "device-1",
                    "allowed_model_profile_ids": ["profile-v1"],
                    "quota_snapshot": quota_payload(),
                    "protocol_version": "1",
                }
            elif request.path == "/v1/quota":
                payload = quota_payload()
            elif request.path == "/v1/model-runs" and request.method == "POST":
                invoke_count += 1
                body = json.loads(request.body)
                assert body["client_run_id"] == "run-idempotent"
                assert request.headers["Idempotency-Key"] == "run-idempotent"
                payload = model_run_payload(replayed=invoke_count > 1)
            elif request.path == "/v1/model-runs/run-idempotent":
                assert request.headers["Idempotency-Key"] == "run-idempotent"
                payload = model_run_payload(replayed=True)
            elif request.path == "/v1/credentials/current" and request.method == "DELETE":
                payload = {
                    "invite_id": "invite-1",
                    "device_id": "device-1",
                    "revoked": True,
                    "server_time": SERVER_TIME,
                }
            else:
                return FakeResponse(404, body=b"{}")
        return FakeResponse(
            headers={"Content-Type": "application/json"},
            body=json.dumps(payload).encode(),
        )

    store = InMemoryCredentialStore()
    with loopback_server(respond) as server:
        client, raw = client_for(server_url(server), store)
        try:
            redeemed = client.redeem_invite(INVITE_SECRET)
            assert not hasattr(redeemed, "device_credential")
            assert store.get_device_credential() == DEVICE_SECRET
            assert client.verify_credential().device_id == "device-1"
            assert client.quota().remaining == 3

            request = ModelInvokeRequest(
                client_run_id="run-idempotent",
                model_profile_id="profile-v1",
                context_hash="a" * 64,
                request_payload={"instruction": "synthetic"},
                protocol_version="1",
            )
            first = asyncio.run(client.invoke_model(request))
            assert isinstance(first, ModelRunResponse)
            second = client.invoke_model_sync(request)
            assert second.idempotency_replayed is True
            assert client.model_run_status(request.client_run_id).state == "completed"
            assert client.revoke_credential().revoked is True
            assert store.get_device_credential() is None
        finally:
            raw.close()

    assert invoke_count == 2
    assert len(server.requests) == 7


def test_builtin_client_never_retries_or_exposes_bearer_in_error_or_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def unavailable(_: CapturedRequest) -> FakeResponse:
        payload = {
            "error": {
                "code": "PROVIDER_UNAVAILABLE",
                "message": f"malicious echo {DEVICE_SECRET}",
                "retryable": False,
                "retry_after": None,
            }
        }
        return FakeResponse(
            503,
            {"Content-Type": "application/json"},
            json.dumps(payload).encode(),
        )

    caplog.set_level(logging.DEBUG)
    store = InMemoryCredentialStore()
    store.set_device_credential(DEVICE_SECRET)
    with loopback_server(unavailable) as server:
        client, raw = client_for(server_url(server), store)
        try:
            with pytest.raises(ControlPlaneClientError) as captured:
                client.quota()
        finally:
            raw.close()

    assert captured.value.code == "PROVIDER_UNAVAILABLE"
    assert str(captured.value) == "PROVIDER_UNAVAILABLE"
    assert DEVICE_SECRET not in repr(captured.value)
    assert DEVICE_SECRET not in caplog.text
    assert len(server.requests) == 1
