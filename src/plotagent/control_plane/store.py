"""SQLite persistence and atomic shared-quota operations."""

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from plotagent.control_plane.errors import ControlPlaneError
from plotagent.control_plane.models import QuotaSnapshot, RunState
from plotagent.control_plane.security import SecretHasher, generate_device_credential

SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class VerifiedCredential:
    invite_id: str
    device_id: str
    allowed_model_profile_ids: tuple[str, ...]
    quota_snapshot: QuotaSnapshot


@dataclass(frozen=True, slots=True)
class RedeemedCredential(VerifiedCredential):
    device_credential: str


@dataclass(frozen=True, slots=True)
class ModelRunRecord:
    invite_id: str
    client_run_id: str
    device_id: str
    model_profile_id: str
    state: RunState
    quota_unit: int
    response_payload: dict[str, Any] | None
    stable_error: str | None
    created_at: datetime
    finished_at: datetime | None
    response_expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class AcceptedModelRun:
    record: ModelRunRecord
    quota_snapshot: QuotaSnapshot
    created: bool


class ControlPlaneStore:
    """Connection-per-operation SQLite store suitable for a small multi-threaded Beta."""

    def __init__(self, path: Path, hasher: SecretHasher, *, busy_timeout_ms: int = 10_000) -> None:
        self._path = path
        self._hasher = hasher
        self._busy_timeout_ms = busy_timeout_ms
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self._path,
            timeout=self._busy_timeout_ms / 1000,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        try:
            yield connection
        except ControlPlaneError:
            raise
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            code = (
                "CONTROL_PLANE_BUSY"
                if "locked" in message or "busy" in message
                else "INTERNAL_ERROR"
            )
            raise ControlPlaneError(code) from None
        except sqlite3.Error:
            raise ControlPlaneError("INTERNAL_ERROR") from None
        finally:
            connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def _initialize(self) -> None:
        with self._connection() as connection:
            version = cast(int, connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in (0, SCHEMA_VERSION):
                raise RuntimeError("Unsupported control-plane SQLite schema version")
            connection.execute("PRAGMA journal_mode = WAL")
            if version == SCHEMA_VERSION:
                return
            connection.execute("PRAGMA synchronous = FULL")
            connection.executescript(
                """
                BEGIN IMMEDIATE;

                CREATE TABLE invite_grants (
                    invite_id TEXT PRIMARY KEY,
                    invite_secret_hash TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK (status IN ('active', 'expired', 'revoked')),
                    expires_at REAL,
                    quota_policy_id TEXT NOT NULL,
                    quota_granted INTEGER NOT NULL CHECK (quota_granted >= 0),
                    quota_consumed INTEGER NOT NULL DEFAULT 0
                        CHECK (quota_consumed >= 0 AND quota_consumed <= quota_granted),
                    period_start REAL,
                    reset_at REAL,
                    allowed_model_profiles_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    revoked_at REAL
                );

                CREATE TABLE device_credentials (
                    device_id TEXT PRIMARY KEY,
                    invite_id TEXT NOT NULL REFERENCES invite_grants(invite_id),
                    credential_hash TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK (status IN ('active', 'blocked', 'revoked')),
                    app_build TEXT NOT NULL,
                    protocol_version TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    revoked_at REAL
                );
                CREATE INDEX device_credentials_invite_idx
                    ON device_credentials(invite_id);

                CREATE TABLE model_runs (
                    invite_id TEXT NOT NULL REFERENCES invite_grants(invite_id),
                    client_run_id TEXT NOT NULL,
                    device_id TEXT NOT NULL REFERENCES device_credentials(device_id),
                    model_profile_id TEXT NOT NULL,
                    context_hash TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    protocol_version TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (
                        state IN ('accepted', 'invoking', 'completed', 'failed', 'cancelled')
                    ),
                    quota_unit INTEGER NOT NULL CHECK (quota_unit > 0),
                    provider_attempted INTEGER NOT NULL DEFAULT 0
                        CHECK (provider_attempted IN (0, 1)),
                    response_json TEXT,
                    stable_error TEXT,
                    created_at REAL NOT NULL,
                    finished_at REAL,
                    response_expires_at REAL,
                    PRIMARY KEY (invite_id, client_run_id)
                );
                CREATE INDEX model_runs_device_idx ON model_runs(device_id, created_at);
                CREATE INDEX model_runs_response_expiry_idx ON model_runs(response_expires_at);

                PRAGMA user_version = 1;
                COMMIT;
                """
            )

    def create_invite_grant(
        self,
        *,
        invite_secret: str,
        quota_granted: int,
        allowed_model_profile_ids: Sequence[str],
        quota_policy_id: str = "per-invocation-v1",
        expires_at: datetime | None = None,
        period_start: datetime | None = None,
        reset_at: datetime | None = None,
    ) -> str:
        """Operator hook used to seed a grant; the plaintext secret is never stored."""

        if len(invite_secret) < 16 or quota_granted < 0 or not allowed_model_profile_ids:
            raise ValueError("Invalid invite grant definition")
        invite_id = f"ig_{uuid4().hex}"
        now = _now_timestamp()
        allowed = sorted(set(allowed_model_profile_ids))
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO invite_grants (
                    invite_id, invite_secret_hash, status, expires_at, quota_policy_id,
                    quota_granted, quota_consumed, period_start, reset_at,
                    allowed_model_profiles_json, created_at
                ) VALUES (?, ?, 'active', ?, ?, ?, 0, ?, ?, ?, ?)
                """,
                (
                    invite_id,
                    self._hasher.digest("invite", invite_secret),
                    _timestamp(expires_at),
                    quota_policy_id,
                    quota_granted,
                    _timestamp(period_start),
                    _timestamp(reset_at),
                    json.dumps(allowed, separators=(",", ":")),
                    now,
                ),
            )
        return invite_id

    def redeem_invite(
        self,
        *,
        invite_secret: str,
        app_build: str,
        protocol_version: str,
    ) -> RedeemedCredential:
        credential = generate_device_credential()
        credential_hash = self._hasher.digest("device", credential)
        now = _now_timestamp()
        with self._transaction() as connection:
            grant = connection.execute(
                "SELECT * FROM invite_grants WHERE invite_secret_hash = ?",
                (self._hasher.digest("invite", invite_secret),),
            ).fetchone()
            if grant is None:
                raise ControlPlaneError("INVITE_INVALID")
            self._assert_grant_active(grant, now)
            device_id = f"dev_{uuid4().hex}"
            connection.execute(
                """
                INSERT INTO device_credentials (
                    device_id, invite_id, credential_hash, status, app_build,
                    protocol_version, created_at
                ) VALUES (?, ?, ?, 'active', ?, ?, ?)
                """,
                (device_id, grant["invite_id"], credential_hash, app_build, protocol_version, now),
            )
            quota = self._quota_snapshot(grant, now)
            allowed = self._allowed_profiles(grant)
        return RedeemedCredential(
            invite_id=cast(str, grant["invite_id"]),
            device_id=device_id,
            allowed_model_profile_ids=allowed,
            quota_snapshot=quota,
            device_credential=credential,
        )

    def verify_credential(self, credential: str) -> VerifiedCredential:
        now = _now_timestamp()
        with self._connection() as connection:
            row = self._credential_row(connection, credential)
            self._assert_credential_active(row, now)
            return self._verified_from_row(row, now)

    def revoke_credential(self, credential: str) -> tuple[str, str]:
        now = _now_timestamp()
        with self._transaction() as connection:
            row = self._credential_row(connection, credential)
            self._assert_credential_active(row, now)
            connection.execute(
                """
                UPDATE device_credentials
                SET status = 'revoked', revoked_at = ?
                WHERE device_id = ?
                """,
                (now, row["device_id"]),
            )
            return cast(str, row["invite_id"]), cast(str, row["device_id"])

    def revoke_grant(self, invite_id: str) -> None:
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE invite_grants
                SET status = 'revoked', revoked_at = ?
                WHERE invite_id = ? AND status != 'revoked'
                """,
                (_now_timestamp(), invite_id),
            )

    def block_device(self, device_id: str) -> None:
        with self._transaction() as connection:
            connection.execute(
                "UPDATE device_credentials SET status = 'blocked' WHERE device_id = ?",
                (device_id,),
            )

    def accept_model_run(
        self,
        *,
        credential: str,
        client_run_id: str,
        model_profile_id: str,
        context_hash: str,
        request_fingerprint: str,
        protocol_version: str,
        quota_unit: int | None,
    ) -> AcceptedModelRun:
        now = _now_timestamp()
        with self._transaction() as connection:
            auth = self._credential_row(connection, credential)
            self._assert_credential_active(auth, now)
            existing = connection.execute(
                """
                SELECT * FROM model_runs
                WHERE invite_id = ? AND client_run_id = ?
                """,
                (auth["invite_id"], client_run_id),
            ).fetchone()
            if existing is not None:
                if (
                    existing["request_fingerprint"] != request_fingerprint
                    or existing["model_profile_id"] != model_profile_id
                    or existing["context_hash"] != context_hash
                    or existing["protocol_version"] != protocol_version
                ):
                    raise ControlPlaneError("IDEMPOTENCY_CONFLICT")
                return AcceptedModelRun(
                    record=self._run_record(existing),
                    quota_snapshot=self._quota_snapshot(auth, now),
                    created=False,
                )

            if quota_unit is None:
                raise ControlPlaneError("MODEL_PROFILE_UNAVAILABLE")
            if model_profile_id not in self._allowed_profiles(auth):
                raise ControlPlaneError("MODEL_PROFILE_UNAVAILABLE")
            updated = connection.execute(
                """
                UPDATE invite_grants
                SET quota_consumed = quota_consumed + ?
                WHERE invite_id = ? AND quota_consumed + ? <= quota_granted
                """,
                (quota_unit, auth["invite_id"], quota_unit),
            )
            if updated.rowcount != 1:
                raise ControlPlaneError("QUOTA_EXHAUSTED")
            connection.execute(
                """
                INSERT INTO model_runs (
                    invite_id, client_run_id, device_id, model_profile_id, context_hash,
                    request_fingerprint, protocol_version, state, quota_unit, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'accepted', ?, ?)
                """,
                (
                    auth["invite_id"],
                    client_run_id,
                    auth["device_id"],
                    model_profile_id,
                    context_hash,
                    request_fingerprint,
                    protocol_version,
                    quota_unit,
                    now,
                ),
            )
            run_row = connection.execute(
                "SELECT * FROM model_runs WHERE invite_id = ? AND client_run_id = ?",
                (auth["invite_id"], client_run_id),
            ).fetchone()
            grant_row = connection.execute(
                "SELECT * FROM invite_grants WHERE invite_id = ?",
                (auth["invite_id"],),
            ).fetchone()
            if run_row is None or grant_row is None:
                raise ControlPlaneError("INTERNAL_ERROR")
            return AcceptedModelRun(
                record=self._run_record(run_row),
                quota_snapshot=self._quota_snapshot(grant_row, now),
                created=True,
            )

    def mark_invoking(self, invite_id: str, client_run_id: str) -> bool:
        with self._transaction() as connection:
            updated = connection.execute(
                """
                UPDATE model_runs
                SET state = 'invoking', provider_attempted = 1
                WHERE invite_id = ? AND client_run_id = ?
                    AND state = 'accepted' AND provider_attempted = 0
                """,
                (invite_id, client_run_id),
            )
            return updated.rowcount == 1

    def complete_model_run(
        self,
        *,
        invite_id: str,
        client_run_id: str,
        response_payload: dict[str, Any],
        response_ttl_seconds: int,
    ) -> ModelRunRecord:
        now = _now_timestamp()
        response_json = json.dumps(
            response_payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with self._transaction() as connection:
            updated = connection.execute(
                """
                UPDATE model_runs
                SET state = 'completed', response_json = ?, stable_error = NULL,
                    finished_at = ?, response_expires_at = ?
                WHERE invite_id = ? AND client_run_id = ? AND state = 'invoking'
                """,
                (response_json, now, now + response_ttl_seconds, invite_id, client_run_id),
            )
            if updated.rowcount != 1:
                raise ControlPlaneError("RUN_OUTCOME_UNKNOWN")
            return self._required_run(connection, invite_id, client_run_id)

    def fail_model_run(
        self,
        *,
        invite_id: str,
        client_run_id: str,
        stable_error: str,
    ) -> ModelRunRecord:
        now = _now_timestamp()
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE model_runs
                SET state = 'failed', stable_error = ?, response_json = NULL,
                    finished_at = ?, response_expires_at = NULL
                WHERE invite_id = ? AND client_run_id = ? AND state IN ('accepted', 'invoking')
                """,
                (stable_error, now, invite_id, client_run_id),
            )
            return self._required_run(connection, invite_id, client_run_id)

    def get_model_run(self, *, credential: str, client_run_id: str) -> AcceptedModelRun:
        now = _now_timestamp()
        with self._connection() as connection:
            auth = self._credential_row(connection, credential)
            self._assert_credential_active(auth, now)
            row = connection.execute(
                "SELECT * FROM model_runs WHERE invite_id = ? AND client_run_id = ?",
                (auth["invite_id"], client_run_id),
            ).fetchone()
            if row is None:
                raise ControlPlaneError("RUN_OUTCOME_UNKNOWN")
            return AcceptedModelRun(
                record=self._run_record(row),
                quota_snapshot=self._quota_snapshot(auth, now),
                created=False,
            )

    def recover_incomplete_runs(self) -> int:
        """Make a restart conservative: accepted/invoking outcomes are never replayed."""

        now = _now_timestamp()
        with self._transaction() as connection:
            updated = connection.execute(
                """
                UPDATE model_runs
                SET state = 'failed', stable_error = 'RUN_OUTCOME_UNKNOWN', finished_at = ?
                WHERE state IN ('accepted', 'invoking')
                """,
                (now,),
            )
            return updated.rowcount

    def prune_expired_responses(self) -> int:
        now = _now_timestamp()
        with self._transaction() as connection:
            updated = connection.execute(
                """
                UPDATE model_runs
                SET response_json = NULL
                WHERE response_json IS NOT NULL AND response_expires_at <= ?
                """,
                (now,),
            )
            return updated.rowcount

    def run_count(self, invite_id: str) -> int:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM model_runs WHERE invite_id = ?", (invite_id,)
            ).fetchone()
            return cast(int, row[0])

    def quota_snapshot_for_invite(self, invite_id: str) -> QuotaSnapshot:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM invite_grants WHERE invite_id = ?", (invite_id,)
            ).fetchone()
            if row is None:
                raise ControlPlaneError("INVITE_INVALID")
            return self._quota_snapshot(row, _now_timestamp())

    def _credential_row(self, connection: sqlite3.Connection, credential: str) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT
                d.device_id, d.credential_hash, d.status AS device_status,
                d.app_build, d.protocol_version AS device_protocol_version,
                g.*
            FROM device_credentials AS d
            JOIN invite_grants AS g ON g.invite_id = d.invite_id
            WHERE d.credential_hash = ?
            """,
            (self._hasher.digest("device", credential),),
        ).fetchone()
        if row is None:
            raise ControlPlaneError("DEVICE_CREDENTIAL_INVALID")
        return cast(sqlite3.Row, row)

    def _assert_credential_active(self, row: sqlite3.Row, now: float) -> None:
        device_status = row["device_status"]
        if device_status == "blocked":
            raise ControlPlaneError("DEVICE_BLOCKED")
        if device_status != "active":
            raise ControlPlaneError("DEVICE_CREDENTIAL_INVALID")
        self._assert_grant_active(row, now)

    @staticmethod
    def _assert_grant_active(row: sqlite3.Row, now: float) -> None:
        status = row["status"]
        if status == "revoked":
            raise ControlPlaneError("INVITE_REVOKED")
        expires_at = row["expires_at"]
        if status == "expired" or (expires_at is not None and cast(float, expires_at) <= now):
            raise ControlPlaneError("INVITE_EXPIRED")
        if status != "active":
            raise ControlPlaneError("INVITE_INVALID")

    def _verified_from_row(self, row: sqlite3.Row, now: float) -> VerifiedCredential:
        return VerifiedCredential(
            invite_id=cast(str, row["invite_id"]),
            device_id=cast(str, row["device_id"]),
            allowed_model_profile_ids=self._allowed_profiles(row),
            quota_snapshot=self._quota_snapshot(row, now),
        )

    @staticmethod
    def _allowed_profiles(row: sqlite3.Row) -> tuple[str, ...]:
        value = json.loads(cast(str, row["allowed_model_profiles_json"]))
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ControlPlaneError("INTERNAL_ERROR")
        return tuple(value)

    @staticmethod
    def _quota_snapshot(row: sqlite3.Row, now: float) -> QuotaSnapshot:
        granted = cast(int, row["quota_granted"])
        consumed = cast(int, row["quota_consumed"])
        return QuotaSnapshot(
            invite_id=cast(str, row["invite_id"]),
            granted=granted,
            consumed=consumed,
            remaining=granted - consumed,
            period_start=_datetime(row["period_start"]),
            reset_at=_datetime(row["reset_at"]),
            server_time=_datetime(now) or datetime.now(UTC),
        )

    def _required_run(
        self, connection: sqlite3.Connection, invite_id: str, client_run_id: str
    ) -> ModelRunRecord:
        row = connection.execute(
            "SELECT * FROM model_runs WHERE invite_id = ? AND client_run_id = ?",
            (invite_id, client_run_id),
        ).fetchone()
        if row is None:
            raise ControlPlaneError("RUN_OUTCOME_UNKNOWN")
        return self._run_record(row)

    @staticmethod
    def _run_record(row: sqlite3.Row) -> ModelRunRecord:
        response: dict[str, Any] | None = None
        if row["response_json"] is not None:
            loaded = json.loads(cast(str, row["response_json"]))
            if not isinstance(loaded, dict):
                raise ControlPlaneError("INTERNAL_ERROR")
            response = loaded
        return ModelRunRecord(
            invite_id=cast(str, row["invite_id"]),
            client_run_id=cast(str, row["client_run_id"]),
            device_id=cast(str, row["device_id"]),
            model_profile_id=cast(str, row["model_profile_id"]),
            state=cast(RunState, row["state"]),
            quota_unit=cast(int, row["quota_unit"]),
            response_payload=response,
            stable_error=cast(str | None, row["stable_error"]),
            created_at=_datetime(row["created_at"]) or datetime.now(UTC),
            finished_at=_datetime(row["finished_at"]),
            response_expires_at=_datetime(row["response_expires_at"]),
        )


def _now_timestamp() -> float:
    return datetime.now(UTC).timestamp()


def _timestamp(value: datetime | None) -> float | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("Control-plane timestamps must be timezone-aware")
    return value.timestamp()


def _datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(cast(float, value), UTC)
