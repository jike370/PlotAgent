import logging
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from plotagent.control_plane.app import create_app
from plotagent.control_plane.config import ControlPlaneSettings, ModelProfileSettings
from plotagent.control_plane.provider import (
    ProviderRequest,
    ProviderResult,
    ProviderTimeoutError,
)

INVITE_SECRET = "inv_v1_0123456789abcdefghijklmnopqrstuvwxyzABCDEFG"
PROFILE_ID = "builtin-beta"


@dataclass
class RecordingProvider:
    mode: Literal["success", "timeout", "unsafe_exception"] = "success"
    calls: list[ProviderRequest] = field(default_factory=list)

    async def invoke(self, request: ProviderRequest) -> ProviderResult:
        self.calls.append(request)
        if self.mode == "timeout":
            raise ProviderTimeoutError
        if self.mode == "unsafe_exception":
            raise RuntimeError("provider-token-DO-NOT-LEAK prompt-DO-NOT-LEAK")
        return ProviderResult({"decision": "NoChange", "schema_version": "1"})


@pytest.fixture
def provider() -> RecordingProvider:
    return RecordingProvider()


@pytest.fixture
def settings(tmp_path: Path) -> ControlPlaneSettings:
    return ControlPlaneSettings(
        database_path=tmp_path / "control-plane.sqlite3",
        secret_pepper="test-pepper-value-with-at-least-32-bytes",
        deployed_model_profiles={
            PROFILE_ID: ModelProfileSettings(deployment_id="fake-deployment", quota_unit=1)
        },
        provider_timeout_seconds=1.0,
        idempotency_response_ttl_seconds=3_600,
    )


@pytest.fixture
def app(settings: ControlPlaneSettings, provider: RecordingProvider) -> FastAPI:
    application = create_app(settings, provider=provider)
    application.state.control_plane.store.create_invite_grant(
        invite_secret=INVITE_SECRET,
        quota_granted=4,
        allowed_model_profile_ids=[PROFILE_ID],
    )
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def redeem(client: TestClient, *, installation_id: str) -> dict[str, object]:
    response = client.post(
        "/v1/invites/redeem",
        json={
            "invite_secret": INVITE_SECRET,
            "installation_id": installation_id,
            "app_build": "beta-test",
            "protocol_version": "1",
        },
    )
    assert response.status_code == 200
    return response.json()


def auth(credential: object) -> dict[str, str]:
    assert isinstance(credential, str)
    return {"Authorization": f"Bearer {credential}"}


def invoke_body(
    run_id: str,
    *,
    context_hash: str = "a" * 64,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "client_run_id": run_id,
        "model_profile_id": PROFILE_ID,
        "context_hash": context_hash,
        "request_payload": payload or {"instruction": "draw the selected chart"},
        "protocol_version": "1",
    }


def test_two_devices_share_one_grant_and_quota(
    client: TestClient, provider: RecordingProvider
) -> None:
    first = redeem(client, installation_id="40fb57ee-50f6-4aa3-a43d-a49affbc3d5a")
    second = redeem(client, installation_id="ea7bc8a9-415f-48b2-bc93-05caecfbf112")

    assert first["invite_id"] == second["invite_id"]
    assert first["device_id"] != second["device_id"]

    one = client.post(
        "/v1/model-runs",
        headers=auth(first["device_credential"]),
        json=invoke_body("shared-device-one"),
    )
    two = client.post(
        "/v1/model-runs",
        headers=auth(second["device_credential"]),
        json=invoke_body("shared-device-two"),
    )

    assert one.status_code == two.status_code == 200
    assert two.json()["quota_snapshot"]["consumed"] == 2
    assert (
        client.get("/v1/quota", headers=auth(first["device_credential"])).json()["remaining"] == 2
    )
    assert len(provider.calls) == 2


def test_redeeming_same_random_installation_again_does_not_grant_new_quota(
    client: TestClient,
) -> None:
    installation_id = "18b3de66-73b2-417d-b44e-78080438ff87"
    first = redeem(client, installation_id=installation_id)
    reinstalled = redeem(client, installation_id=installation_id)

    assert first["invite_id"] == reinstalled["invite_id"]
    assert first["device_id"] != reinstalled["device_id"]
    assert first["device_credential"] != reinstalled["device_credential"]
    for field_name in ("granted", "consumed", "remaining"):
        assert first["quota_snapshot"][field_name] == reinstalled["quota_snapshot"][field_name]


def test_duplicate_is_replayed_without_double_charge_or_provider_call(
    client: TestClient, provider: RecordingProvider
) -> None:
    redeemed = redeem(client, installation_id="271b8112-116d-4229-9a7d-14cf22330bf0")
    headers = auth(redeemed["device_credential"])
    body = invoke_body("duplicate-run")

    first = client.post("/v1/model-runs", headers=headers, json=body)
    duplicate = client.post("/v1/model-runs", headers=headers, json=body)

    assert first.status_code == duplicate.status_code == 200
    assert first.json()["response_payload"] == duplicate.json()["response_payload"]
    assert first.json()["idempotency_replayed"] is False
    assert duplicate.json()["idempotency_replayed"] is True
    assert duplicate.json()["quota_snapshot"]["consumed"] == 1
    assert len(provider.calls) == 1


def test_quota_exhaustion_only_blocks_new_builtin_runs(
    settings: ControlPlaneSettings, provider: RecordingProvider
) -> None:
    application = create_app(settings, provider=provider)
    application.state.control_plane.store.create_invite_grant(
        invite_secret=INVITE_SECRET,
        quota_granted=1,
        allowed_model_profile_ids=[PROFILE_ID],
    )
    with TestClient(application) as client:
        redeemed = redeem(client, installation_id="5d22f92a-b4ce-43e6-8298-bf315228091f")
        headers = auth(redeemed["device_credential"])
        assert (
            client.post(
                "/v1/model-runs", headers=headers, json=invoke_body("last-unit")
            ).status_code
            == 200
        )

        exhausted = client.post("/v1/model-runs", headers=headers, json=invoke_body("over-quota"))
        assert exhausted.status_code == 409
        assert exhausted.json()["error"]["code"] == "QUOTA_EXHAUSTED"
        assert len(provider.calls) == 1

        # There is intentionally no custom-provider cloud endpoint or ledger mutation.
        custom = client.post("/v1/custom-provider/model-runs", json={"anything": "local"})
        assert custom.status_code == 422
        assert client.get("/v1/quota", headers=headers).json()["consumed"] == 1


def test_idempotency_conflict_and_custom_provider_shape_do_not_charge(
    client: TestClient, provider: RecordingProvider
) -> None:
    redeemed = redeem(client, installation_id="b1c96b91-fea7-470c-a4bb-c0678874971f")
    headers = auth(redeemed["device_credential"])
    original = invoke_body("conflict-run", payload={"instruction": "first"})
    assert client.post("/v1/model-runs", headers=headers, json=original).status_code == 200

    changed = invoke_body("conflict-run", payload={"instruction": "second"})
    conflict = client.post("/v1/model-runs", headers=headers, json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    changed_profile = dict(original)
    changed_profile["model_profile_id"] = "unknown-profile"
    conflict = client.post("/v1/model-runs", headers=headers, json=changed_profile)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    unavailable = invoke_body("unavailable-profile-run")
    unavailable["model_profile_id"] = "unknown-profile"
    rejected_profile = client.post("/v1/model-runs", headers=headers, json=unavailable)
    assert rejected_profile.status_code == 409
    assert rejected_profile.json()["error"]["code"] == "MODEL_PROFILE_UNAVAILABLE"

    custom = invoke_body("custom-provider-run")
    custom["provider_type"] = "custom"
    rejected = client.post("/v1/model-runs", headers=headers, json=custom)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "REQUEST_INVALID"
    assert client.get("/v1/quota", headers=headers).json()["consumed"] == 1
    assert len(provider.calls) == 1


@pytest.mark.parametrize(
    ("mode", "expected_code", "expected_status"),
    [
        ("timeout", "RUN_OUTCOME_UNKNOWN", 409),
        ("unsafe_exception", "PROVIDER_UNAVAILABLE", 503),
    ],
)
def test_provider_failure_is_stable_and_never_replayed(
    settings: ControlPlaneSettings,
    mode: Literal["timeout", "unsafe_exception"],
    expected_code: str,
    expected_status: int,
) -> None:
    provider = RecordingProvider(mode=mode)
    application = create_app(settings, provider=provider)
    application.state.control_plane.store.create_invite_grant(
        invite_secret=INVITE_SECRET,
        quota_granted=2,
        allowed_model_profile_ids=[PROFILE_ID],
    )
    with TestClient(application) as client:
        redeemed = redeem(client, installation_id="68ef1221-1060-4030-a7e1-87446d826bdd")
        headers = auth(redeemed["device_credential"])
        body = invoke_body("provider-failure")
        first = client.post("/v1/model-runs", headers=headers, json=body)
        duplicate = client.post("/v1/model-runs", headers=headers, json=body)

        assert first.status_code == duplicate.status_code == expected_status
        assert first.json()["error"]["code"] == expected_code
        assert duplicate.json()["error"]["code"] == expected_code
        assert client.get("/v1/quota", headers=headers).json()["consumed"] == 1
        assert len(provider.calls) == 1


def test_revoke_block_expire_and_grant_revoke_are_distinct(
    settings: ControlPlaneSettings, provider: RecordingProvider
) -> None:
    application = create_app(settings, provider=provider)
    store = application.state.control_plane.store
    invite_id = store.create_invite_grant(
        invite_secret=INVITE_SECRET,
        quota_granted=4,
        allowed_model_profile_ids=[PROFILE_ID],
    )
    expired_secret = "inv_v1_expired-0123456789abcdefghijklmnopqrst"
    store.create_invite_grant(
        invite_secret=expired_secret,
        quota_granted=1,
        allowed_model_profile_ids=[PROFILE_ID],
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    with TestClient(application) as client:
        first = redeem(client, installation_id="16655169-88be-4e8c-8451-66bc354e30d5")
        second = redeem(client, installation_id="1d650320-da21-440b-a465-b31d1d0d95fb")

        revoked = client.delete("/v1/credentials/current", headers=auth(first["device_credential"]))
        assert revoked.status_code == 200
        assert (
            client.post("/v1/credentials/verify", headers=auth(first["device_credential"])).json()[
                "error"
            ]["code"]
            == "DEVICE_CREDENTIAL_INVALID"
        )

        assert isinstance(second["device_id"], str)
        store.block_device(second["device_id"])
        assert (
            client.post("/v1/credentials/verify", headers=auth(second["device_credential"])).json()[
                "error"
            ]["code"]
            == "DEVICE_BLOCKED"
        )

        third = redeem(client, installation_id="1516c181-cb16-45d2-b035-3073c9d7f214")
        store.revoke_grant(invite_id)
        assert (
            client.post("/v1/credentials/verify", headers=auth(third["device_credential"])).json()[
                "error"
            ]["code"]
            == "INVITE_REVOKED"
        )

        expired = client.post(
            "/v1/invites/redeem",
            json={
                "invite_secret": expired_secret,
                "installation_id": "56e762b1-8c85-43d2-9899-61aee31c873d",
                "app_build": "beta-test",
                "protocol_version": "1",
            },
        )
        assert expired.json()["error"]["code"] == "INVITE_EXPIRED"


def test_logs_errors_and_database_do_not_contain_request_or_secrets(
    settings: ControlPlaneSettings, caplog: pytest.LogCaptureFixture
) -> None:
    provider = RecordingProvider(mode="unsafe_exception")
    application = create_app(settings, provider=provider)
    application.state.control_plane.store.create_invite_grant(
        invite_secret=INVITE_SECRET,
        quota_granted=1,
        allowed_model_profile_ids=[PROFILE_ID],
    )
    prompt = "prompt-DO-NOT-LEAK"
    sample = "sample-DO-NOT-LEAK"
    caplog.set_level(logging.INFO, logger="plotagent.control_plane")

    with TestClient(application) as client:
        redeemed = redeem(client, installation_id="912dff6e-e920-4413-9531-7e95cbfdb4a0")
        credential = redeemed["device_credential"]
        response = client.post(
            "/v1/model-runs",
            headers=auth(credential),
            json=invoke_body("safe-error", payload={"prompt": prompt, "sample": sample}),
        )
        assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
        serialized_response = response.text
        assert prompt not in serialized_response
        assert sample not in serialized_response
        assert "provider-token-DO-NOT-LEAK" not in serialized_response

    log_output = caplog.text
    assert INVITE_SECRET not in log_output
    assert str(credential) not in log_output
    assert prompt not in log_output
    assert sample not in log_output
    assert "provider-token-DO-NOT-LEAK" not in log_output

    with sqlite3.connect(settings.database_path) as connection:
        schema_columns = set()
        for table in ("invite_grants", "device_credentials", "model_runs"):
            schema_columns.update(
                row[1] for row in connection.execute(f"PRAGMA table_info({table})")
            )
        stored = " ".join(
            str(value)
            for row in connection.execute(
                """
                SELECT context_hash, request_fingerprint, response_json, stable_error
                FROM model_runs
                """
            )
            for value in row
            if value is not None
        )
        invite_hash = connection.execute("SELECT invite_secret_hash FROM invite_grants").fetchone()[
            0
        ]
        credential_hash = connection.execute(
            "SELECT credential_hash FROM device_credentials"
        ).fetchone()[0]

    assert not schema_columns.intersection(
        {"installation_id", "email", "profile", "account_id", "hardware_fingerprint"}
    )
    assert prompt not in stored and sample not in stored
    assert invite_hash != INVITE_SECRET
    assert credential_hash != credential


def test_validation_error_does_not_echo_invalid_secret(client: TestClient) -> None:
    invalid_secret = "secret-DO-NOT-ECHO"
    response = client.post(
        "/v1/invites/redeem",
        json={
            "invite_secret": invalid_secret,
            "installation_id": "not-a-random-uuid",
            "app_build": "beta-test",
            "protocol_version": "1",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_INVALID"
    assert invalid_secret not in response.text
