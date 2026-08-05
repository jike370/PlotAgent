"""HTTP models for the narrow Beta control-plane protocol."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class RedeemInviteRequest(StrictModel):
    invite_secret: SecretStr = Field(min_length=16, max_length=256)
    installation_id: str = Field(
        pattern=(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-"
            r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
        )
    )
    app_build: str = Field(min_length=1, max_length=64)
    protocol_version: str = Field(min_length=1, max_length=16)


class QuotaSnapshot(StrictModel):
    invite_id: str
    granted: int
    consumed: int
    remaining: int
    period_start: datetime | None = None
    reset_at: datetime | None = None
    server_time: datetime


class RedeemInviteResponse(StrictModel):
    invite_id: str
    device_id: str
    device_credential: str
    allowed_model_profile_ids: list[str]
    quota_snapshot: QuotaSnapshot
    protocol_version: str


class CredentialVerificationResponse(StrictModel):
    invite_id: str
    device_id: str
    allowed_model_profile_ids: list[str]
    quota_snapshot: QuotaSnapshot
    protocol_version: str


class CredentialRevocationResponse(StrictModel):
    invite_id: str
    device_id: str
    revoked: Literal[True] = True
    server_time: datetime


class ModelInvokeRequest(StrictModel):
    client_run_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    model_profile_id: str = Field(min_length=1, max_length=128)
    context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_payload: dict[str, Any]
    protocol_version: str = Field(min_length=1, max_length=16)


RunState = Literal["accepted", "invoking", "completed", "failed", "cancelled"]


class ModelRunResponse(StrictModel):
    client_run_id: str
    model_profile_id: str
    state: RunState
    quota_unit: int
    quota_snapshot: QuotaSnapshot
    response_payload: dict[str, Any] | None = None
    idempotency_replayed: bool
    created_at: datetime
    finished_at: datetime | None = None


class ErrorBody(StrictModel):
    code: str
    message: str
    retryable: bool
    retry_after: int | None = None


class ErrorResponse(StrictModel):
    error: ErrorBody
