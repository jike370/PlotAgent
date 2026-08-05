import os
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from plotagent.control_plane.config import (
    ControlPlaneSettings,
    ModelProfileSettings,
    load_settings,
)
from plotagent.control_plane.security import SecretHasher
from plotagent.control_plane.store import ControlPlaneStore


def test_environment_validation_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prefix = "PLOTAGENT_CONTROL_PLANE_"
    for key in list(os.environ):
        if key.startswith(prefix):
            monkeypatch.delenv(key)
    monkeypatch.setenv(f"{prefix}DATABASE_PATH", str(tmp_path / "settings.sqlite3"))
    unsafe_secret = "secret-DO-NOT-ECHO"
    monkeypatch.setenv(f"{prefix}SECRET_PEPPER", unsafe_secret)
    monkeypatch.setenv(f"{prefix}DEPLOYED_MODEL_PROFILES", "{}")

    with pytest.raises(RuntimeError) as caught:
        load_settings()

    assert unsafe_secret not in str(caught.value)
    assert "secret_pepper" in str(caught.value)
    assert "deployed_model_profiles" in str(caught.value)


def test_response_retention_must_outlive_provider_timeout(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ControlPlaneSettings(
            database_path=tmp_path / "bad.sqlite3",
            secret_pepper="settings-test-pepper-with-at-least-32-bytes",
            deployed_model_profiles={
                "builtin-beta": ModelProfileSettings(deployment_id="fake", quota_unit=1)
            },
            provider_timeout_seconds=60,
            idempotency_response_ttl_seconds=60,
        )


def test_restart_marks_incomplete_run_unknown_without_second_debit(tmp_path: Path) -> None:
    hasher = SecretHasher.from_text("recovery-test-pepper-with-at-least-32-bytes")
    store = ControlPlaneStore(tmp_path / "recovery.sqlite3", hasher)
    secret = "inv_v1_recovery-0123456789abcdefghijklmnopq"
    invite_id = store.create_invite_grant(
        invite_secret=secret,
        quota_granted=3,
        allowed_model_profile_ids=["builtin-beta"],
    )
    credential = store.redeem_invite(
        invite_secret=secret,
        app_build="test",
        protocol_version="1",
    ).device_credential
    accepted = store.accept_model_run(
        credential=credential,
        client_run_id="crashed-before-provider-proof",
        model_profile_id="builtin-beta",
        context_hash="c" * 64,
        request_fingerprint="same-fingerprint",
        protocol_version="1",
        quota_unit=1,
    )
    assert accepted.created is True

    assert store.recover_incomplete_runs() == 1
    replay = store.accept_model_run(
        credential=credential,
        client_run_id="crashed-before-provider-proof",
        model_profile_id="builtin-beta",
        context_hash="c" * 64,
        request_fingerprint="same-fingerprint",
        protocol_version="1",
        quota_unit=1,
    )

    assert replay.created is False
    assert replay.record.stable_error == "RUN_OUTCOME_UNKNOWN"
    assert store.quota_snapshot_for_invite(invite_id).consumed == 1
    assert store.run_count(invite_id) == 1


def test_expired_idempotent_response_is_pruned_without_replay(tmp_path: Path) -> None:
    database_path = tmp_path / "retention.sqlite3"
    hasher = SecretHasher.from_text("retention-test-pepper-with-at-least-32-bytes")
    store = ControlPlaneStore(database_path, hasher)
    secret = "inv_v1_retention-0123456789abcdefghijklmnop"
    invite_id = store.create_invite_grant(
        invite_secret=secret,
        quota_granted=2,
        allowed_model_profile_ids=["builtin-beta"],
    )
    credential = store.redeem_invite(
        invite_secret=secret,
        app_build="test",
        protocol_version="1",
    ).device_credential
    store.accept_model_run(
        credential=credential,
        client_run_id="retained-run",
        model_profile_id="builtin-beta",
        context_hash="d" * 64,
        request_fingerprint="retained-fingerprint",
        protocol_version="1",
        quota_unit=1,
    )
    assert store.mark_invoking(invite_id, "retained-run") is True
    store.complete_model_run(
        invite_id=invite_id,
        client_run_id="retained-run",
        response_payload={"decision": "NoChange"},
        response_ttl_seconds=3_600,
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE model_runs SET response_expires_at = 0 WHERE client_run_id = 'retained-run'"
        )

    assert store.prune_expired_responses() == 1
    replay = store.accept_model_run(
        credential=credential,
        client_run_id="retained-run",
        model_profile_id="builtin-beta",
        context_hash="d" * 64,
        request_fingerprint="retained-fingerprint",
        protocol_version="1",
        quota_unit=1,
    )
    assert replay.created is False
    assert replay.record.state == "completed"
    assert replay.record.response_payload is None
    assert store.quota_snapshot_for_invite(invite_id).consumed == 1
