from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from plotagent.control_plane.errors import ControlPlaneError
from plotagent.control_plane.security import SecretHasher
from plotagent.control_plane.store import ControlPlaneStore

PROFILE_ID = "builtin-beta"
INVITE_SECRET = "inv_v1_concurrency-0123456789abcdefghijklmnop"


def make_store(tmp_path: Path, *, quota: int) -> tuple[ControlPlaneStore, str, str, str]:
    store = ControlPlaneStore(
        tmp_path / "concurrency.sqlite3",
        SecretHasher.from_text("concurrency-test-pepper-with-32-bytes"),
        busy_timeout_ms=30_000,
    )
    invite_id = store.create_invite_grant(
        invite_secret=INVITE_SECRET,
        quota_granted=quota,
        allowed_model_profile_ids=[PROFILE_ID],
    )
    first = store.redeem_invite(
        invite_secret=INVITE_SECRET,
        app_build="test",
        protocol_version="1",
    )
    second = store.redeem_invite(
        invite_secret=INVITE_SECRET,
        app_build="test",
        protocol_version="1",
    )
    return store, invite_id, first.device_credential, second.device_credential


def test_concurrent_unique_runs_never_overdraw_shared_quota(tmp_path: Path) -> None:
    quota = 12
    store, invite_id, first, second = make_store(tmp_path, quota=quota)

    def accept(index: int) -> str:
        try:
            accepted = store.accept_model_run(
                credential=first if index % 2 == 0 else second,
                client_run_id=f"unique-{index}",
                model_profile_id=PROFILE_ID,
                context_hash=f"{index:064x}",
                request_fingerprint=f"fingerprint-{index}",
                protocol_version="1",
                quota_unit=1,
            )
            return "created" if accepted.created else "replayed"
        except ControlPlaneError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=20) as executor:
        outcomes = list(executor.map(accept, range(60)))

    snapshot = store.quota_snapshot_for_invite(invite_id)
    assert outcomes.count("created") == quota
    assert outcomes.count("QUOTA_EXHAUSTED") == 60 - quota
    assert snapshot.consumed == snapshot.granted == quota
    assert snapshot.remaining == 0
    assert store.run_count(invite_id) == quota


def test_concurrent_same_run_id_debits_exactly_once(tmp_path: Path) -> None:
    store, invite_id, first, second = make_store(tmp_path, quota=30)

    def accept(index: int) -> bool:
        accepted = store.accept_model_run(
            credential=first if index % 2 == 0 else second,
            client_run_id="one-shared-run-id",
            model_profile_id=PROFILE_ID,
            context_hash="b" * 64,
            request_fingerprint="same-keyed-request-fingerprint",
            protocol_version="1",
            quota_unit=1,
        )
        return accepted.created

    with ThreadPoolExecutor(max_workers=20) as executor:
        created_flags = list(executor.map(accept, range(60)))

    snapshot = store.quota_snapshot_for_invite(invite_id)
    assert created_flags.count(True) == 1
    assert created_flags.count(False) == 59
    assert snapshot.consumed == 1
    assert snapshot.remaining == 29
    assert store.run_count(invite_id) == 1
