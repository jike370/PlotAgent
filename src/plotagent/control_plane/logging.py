"""Allowlisted structured logging that never accepts arbitrary request values."""

import json
import logging
from typing import Literal

RunLogState = Literal["accepted", "invoking", "completed", "failed", "cancelled"]


class SafeControlPlaneLogger:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("plotagent.control_plane")

    def redeem(self, *, invite_id: str, device_id: str) -> None:
        self._emit("invite_redeemed", invite_id=invite_id, device_id=device_id)

    def credential_revoked(self, *, invite_id: str, device_id: str) -> None:
        self._emit("credential_revoked", invite_id=invite_id, device_id=device_id)

    def run(
        self,
        *,
        client_run_id: str,
        invite_id: str,
        device_id: str,
        model_profile_id: str,
        quota_unit: int,
        state: RunLogState,
        idempotency_replayed: bool,
        stable_error: str | None = None,
    ) -> None:
        self._emit(
            "model_run",
            client_run_id=client_run_id,
            invite_id=invite_id,
            device_id=device_id,
            model_profile_id=model_profile_id,
            quota_unit=quota_unit,
            state=state,
            idempotency_replayed=idempotency_replayed,
            stable_error=stable_error,
        )

    def error(self, stable_error: str) -> None:
        self._emit("request_failed", stable_error=stable_error)

    def _emit(self, event: str, **fields: str | int | bool | None) -> None:
        payload = {
            "event": event,
            **{key: value for key, value in fields.items() if value is not None},
        }
        self._logger.info(json.dumps(payload, sort_keys=True, separators=(",", ":")))
