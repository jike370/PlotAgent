"""Synchronous gated desktop client for the Beta control-plane protocol."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from plotagent.control_plane.errors import ERRORS
from plotagent.control_plane.models import (
    CredentialRevocationResponse,
    CredentialVerificationResponse,
    ErrorResponse,
    ModelInvokeRequest,
    ModelRunResponse,
    QuotaSnapshot,
    RedeemInviteResponse,
)
from plotagent.security.credentials import CredentialStore
from plotagent.security.network import (
    HttpMethod,
    NetworkPurpose,
    NetworkRequest,
    NetworkResponse,
    PolicyTransport,
)

_ResponseModel = TypeVar("_ResponseModel", bound=BaseModel)
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ControlPlaneClientError(RuntimeError):
    """Stable client error that never includes response bodies or credentials."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.retry_after = retry_after

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class InviteRedemptionResult:
    """Redeem metadata safe to return after the secret is stored in the vault."""

    invite_id: str
    device_id: str
    allowed_model_profile_ids: tuple[str, ...]
    quota_snapshot: QuotaSnapshot
    protocol_version: str


class BuiltinControlPlaneClient:
    """Control-plane client and async ``BuiltinCloudClient`` adapter."""

    def __init__(
        self,
        transport: PolicyTransport,
        credential_store: CredentialStore,
        *,
        base_url: str,
        app_build: str,
        protocol_version: str = "1",
    ) -> None:
        if not app_build or len(app_build) > 64:
            raise ValueError("app_build must be a non-empty bounded value")
        if not protocol_version or len(protocol_version) > 16:
            raise ValueError("protocol_version must be a non-empty bounded value")
        self._transport = transport
        self._credential_store = credential_store
        self._base_url = base_url.rstrip("/")
        self._app_build = app_build
        self._protocol_version = protocol_version

    def redeem_invite(
        self,
        invite_secret: str,
        *,
        installation_id: str | None = None,
    ) -> InviteRedemptionResult:
        request_body = {
            "invite_secret": invite_secret,
            "installation_id": installation_id or str(uuid.uuid4()),
            "app_build": self._app_build,
            "protocol_version": self._protocol_version,
        }
        response = self._send_json(
            method=HttpMethod.POST,
            path="/v1/invites/redeem",
            purpose=NetworkPurpose.INVITATION_REDEEM,
            body=request_body,
            response_type=RedeemInviteResponse,
        )
        self._credential_store.set_device_credential(response.device_credential)
        return InviteRedemptionResult(
            invite_id=response.invite_id,
            device_id=response.device_id,
            allowed_model_profile_ids=tuple(response.allowed_model_profile_ids),
            quota_snapshot=response.quota_snapshot,
            protocol_version=response.protocol_version,
        )

    def verify_credential(self) -> CredentialVerificationResponse:
        return self._send_json(
            method=HttpMethod.POST,
            path="/v1/credentials/verify",
            purpose=NetworkPurpose.DEVICE_CREDENTIAL,
            response_type=CredentialVerificationResponse,
        )

    def revoke_credential(self) -> CredentialRevocationResponse:
        response = self._send_json(
            method=HttpMethod.DELETE,
            path="/v1/credentials/current",
            purpose=NetworkPurpose.DEVICE_CREDENTIAL,
            response_type=CredentialRevocationResponse,
        )
        self._credential_store.delete_device_credential()
        return response

    def quota(self) -> QuotaSnapshot:
        return self._send_json(
            method=HttpMethod.GET,
            path="/v1/quota",
            purpose=NetworkPurpose.QUOTA,
            response_type=QuotaSnapshot,
        )

    def invoke_model_sync(self, request: ModelInvokeRequest) -> ModelRunResponse:
        response = self._send_json(
            method=HttpMethod.POST,
            path="/v1/model-runs",
            purpose=NetworkPurpose.BUILTIN_MODEL,
            body=request.model_dump(mode="json"),
            response_type=ModelRunResponse,
            idempotency_key=request.client_run_id,
        )
        if (
            response.client_run_id != request.client_run_id
            or response.model_profile_id != request.model_profile_id
        ):
            raise ControlPlaneClientError(
                "CONTROL_PLANE_RESPONSE_INVALID", status_code=200
            )
        return response

    def model_run_status(self, client_run_id: str) -> ModelRunResponse:
        if not _RUN_ID_PATTERN.fullmatch(client_run_id):
            raise ControlPlaneClientError("REQUEST_INVALID")
        response = self._send_json(
            method=HttpMethod.GET,
            path=f"/v1/model-runs/{client_run_id}",
            purpose=NetworkPurpose.BUILTIN_MODEL,
            response_type=ModelRunResponse,
            idempotency_key=client_run_id,
        )
        if response.client_run_id != client_run_id:
            raise ControlPlaneClientError(
                "CONTROL_PLANE_RESPONSE_INVALID", status_code=200
            )
        return response

    async def invoke_model(self, request: ModelInvokeRequest) -> object:
        return await asyncio.to_thread(self.invoke_model_sync, request)

    async def cancel_model(self, client_run_id: str) -> None:
        # The current Beta API exposes status but no remote cancellation route.
        # Cancelling the awaiting task therefore never creates a replay or a new run id.
        del client_run_id

    def _send_json(
        self,
        *,
        method: HttpMethod,
        path: str,
        purpose: NetworkPurpose,
        response_type: type[_ResponseModel],
        body: Mapping[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> _ResponseModel:
        headers = {"Accept": "application/json"}
        encoded: bytes | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            try:
                encoded = json.dumps(
                    body,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            except (TypeError, ValueError):
                raise ControlPlaneClientError("REQUEST_INVALID") from None
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        response = self._transport.send(
            NetworkRequest(
                method=method,
                url=f"{self._base_url}{path}",
                purpose=purpose,
                headers=headers,
                body=encoded,
            )
        )
        if not 200 <= response.status_code < 300:
            self._raise_response_error(response)
        try:
            return response_type.model_validate_json(response.body)
        except ValidationError:
            raise ControlPlaneClientError(
                "CONTROL_PLANE_RESPONSE_INVALID", status_code=response.status_code
            ) from None

    def _raise_response_error(self, response: NetworkResponse) -> None:
        code = "CONTROL_PLANE_RESPONSE_INVALID"
        try:
            parsed = ErrorResponse.model_validate_json(response.body)
            if parsed.error.code in ERRORS:
                code = parsed.error.code
        except ValidationError:
            pass
        retry_after: int | None = None
        raw_retry_after = response.headers.get("retry-after")
        if raw_retry_after is not None and raw_retry_after.isdecimal():
            retry_after = int(raw_retry_after)
        raise ControlPlaneClientError(
            code,
            status_code=response.status_code,
            retry_after=retry_after,
        )
