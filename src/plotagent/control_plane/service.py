"""Application service enforcing proxy, idempotency, and quota semantics."""

import asyncio
import json
from datetime import UTC, datetime
from typing import NoReturn

from plotagent.control_plane.config import ControlPlaneSettings
from plotagent.control_plane.errors import ControlPlaneError
from plotagent.control_plane.logging import SafeControlPlaneLogger
from plotagent.control_plane.models import (
    CredentialRevocationResponse,
    CredentialVerificationResponse,
    ModelInvokeRequest,
    ModelRunResponse,
    RedeemInviteRequest,
    RedeemInviteResponse,
)
from plotagent.control_plane.provider import (
    ProviderAdapter,
    ProviderRequest,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from plotagent.control_plane.security import SecretHasher
from plotagent.control_plane.store import AcceptedModelRun, ControlPlaneStore, ModelRunRecord


class ControlPlaneService:
    def __init__(
        self,
        *,
        settings: ControlPlaneSettings,
        store: ControlPlaneStore,
        provider: ProviderAdapter,
        hasher: SecretHasher,
        logger: SafeControlPlaneLogger,
    ) -> None:
        self.settings = settings
        self.store = store
        self._provider = provider
        self._hasher = hasher
        self._logger = logger

    def startup_recover(self) -> None:
        self.store.recover_incomplete_runs()
        self.store.prune_expired_responses()

    def redeem(self, request: RedeemInviteRequest) -> RedeemInviteResponse:
        self._validate_protocol(request.protocol_version)
        # installation_id proves no hardware identity: it is deliberately neither
        # persisted nor logged.
        redeemed = self.store.redeem_invite(
            invite_secret=request.invite_secret.get_secret_value(),
            app_build=request.app_build,
            protocol_version=request.protocol_version,
        )
        self._logger.redeem(invite_id=redeemed.invite_id, device_id=redeemed.device_id)
        return RedeemInviteResponse(
            invite_id=redeemed.invite_id,
            device_id=redeemed.device_id,
            device_credential=redeemed.device_credential,
            allowed_model_profile_ids=list(redeemed.allowed_model_profile_ids),
            quota_snapshot=redeemed.quota_snapshot,
            protocol_version=self.settings.protocol_version,
        )

    def verify(self, credential: str) -> CredentialVerificationResponse:
        verified = self.store.verify_credential(credential)
        return CredentialVerificationResponse(
            invite_id=verified.invite_id,
            device_id=verified.device_id,
            allowed_model_profile_ids=list(verified.allowed_model_profile_ids),
            quota_snapshot=verified.quota_snapshot,
            protocol_version=self.settings.protocol_version,
        )

    def revoke_current(self, credential: str) -> CredentialRevocationResponse:
        invite_id, device_id = self.store.revoke_credential(credential)
        self._logger.credential_revoked(invite_id=invite_id, device_id=device_id)
        return CredentialRevocationResponse(
            invite_id=invite_id,
            device_id=device_id,
            server_time=datetime.now(UTC),
        )

    async def invoke(
        self, *, credential: str, request: ModelInvokeRequest
    ) -> tuple[ModelRunResponse, int]:
        self._validate_protocol(request.protocol_version)
        profile = self.settings.deployed_model_profiles.get(request.model_profile_id)
        self.store.prune_expired_responses()
        fingerprint = self._request_fingerprint(request)
        accepted = self.store.accept_model_run(
            credential=credential,
            client_run_id=request.client_run_id,
            model_profile_id=request.model_profile_id,
            context_hash=request.context_hash,
            request_fingerprint=fingerprint,
            protocol_version=request.protocol_version,
            quota_unit=profile.quota_unit if profile is not None else None,
        )
        if not accepted.created:
            return self._present(accepted, idempotency_replayed=True)
        if profile is None:
            raise ControlPlaneError("INTERNAL_ERROR")

        self._logger.run(
            client_run_id=accepted.record.client_run_id,
            invite_id=accepted.record.invite_id,
            device_id=accepted.record.device_id,
            model_profile_id=accepted.record.model_profile_id,
            quota_unit=accepted.record.quota_unit,
            state="accepted",
            idempotency_replayed=False,
        )
        if not self.store.mark_invoking(accepted.record.invite_id, accepted.record.client_run_id):
            failed = self.store.fail_model_run(
                invite_id=accepted.record.invite_id,
                client_run_id=accepted.record.client_run_id,
                stable_error="RUN_OUTCOME_UNKNOWN",
            )
            self._raise_run_error(failed, idempotency_replayed=False)

        provider_request = ProviderRequest(
            client_run_id=request.client_run_id,
            model_profile_id=request.model_profile_id,
            deployment_id=profile.deployment_id,
            request_payload=request.request_payload,
        )
        try:
            async with asyncio.timeout(self.settings.provider_timeout_seconds):
                provider_result = await self._provider.invoke(provider_request)
            completed = self.store.complete_model_run(
                invite_id=accepted.record.invite_id,
                client_run_id=accepted.record.client_run_id,
                response_payload=provider_result.response_payload,
                response_ttl_seconds=self.settings.idempotency_response_ttl_seconds,
            )
        except asyncio.CancelledError:
            self.store.fail_model_run(
                invite_id=accepted.record.invite_id,
                client_run_id=accepted.record.client_run_id,
                stable_error="RUN_OUTCOME_UNKNOWN",
            )
            raise
        except (TimeoutError, ProviderTimeoutError):
            failed = self.store.fail_model_run(
                invite_id=accepted.record.invite_id,
                client_run_id=accepted.record.client_run_id,
                stable_error="RUN_OUTCOME_UNKNOWN",
            )
            self._raise_run_error(failed, idempotency_replayed=False)
        except (ProviderUnavailableError, ValueError, TypeError):
            failed = self.store.fail_model_run(
                invite_id=accepted.record.invite_id,
                client_run_id=accepted.record.client_run_id,
                stable_error="PROVIDER_UNAVAILABLE",
            )
            self._raise_run_error(failed, idempotency_replayed=False)
        except ControlPlaneError:
            raise
        except Exception:
            # Adapter exceptions can contain request bodies or provider tokens.
            # Never stringify them.
            failed = self.store.fail_model_run(
                invite_id=accepted.record.invite_id,
                client_run_id=accepted.record.client_run_id,
                stable_error="PROVIDER_UNAVAILABLE",
            )
            self._raise_run_error(failed, idempotency_replayed=False)

        current = AcceptedModelRun(
            record=completed,
            quota_snapshot=self.store.quota_snapshot_for_invite(completed.invite_id),
            created=True,
        )
        self._logger.run(
            client_run_id=completed.client_run_id,
            invite_id=completed.invite_id,
            device_id=completed.device_id,
            model_profile_id=completed.model_profile_id,
            quota_unit=completed.quota_unit,
            state="completed",
            idempotency_replayed=False,
        )
        return self._present(current, idempotency_replayed=False)

    def get_run(self, *, credential: str, client_run_id: str) -> tuple[ModelRunResponse, int]:
        self.store.prune_expired_responses()
        accepted = self.store.get_model_run(
            credential=credential,
            client_run_id=client_run_id,
        )
        return self._present(accepted, idempotency_replayed=True)

    def _present(
        self, accepted: AcceptedModelRun, *, idempotency_replayed: bool
    ) -> tuple[ModelRunResponse, int]:
        record = accepted.record
        if record.state == "failed":
            self._raise_run_error(record, idempotency_replayed=idempotency_replayed)
        if record.state == "completed" and record.response_payload is None:
            raise ControlPlaneError("RUN_OUTCOME_UNKNOWN")
        status_code = 202 if record.state in ("accepted", "invoking") else 200
        return (
            ModelRunResponse(
                client_run_id=record.client_run_id,
                model_profile_id=record.model_profile_id,
                state=record.state,
                quota_unit=record.quota_unit,
                quota_snapshot=accepted.quota_snapshot,
                response_payload=record.response_payload,
                idempotency_replayed=idempotency_replayed,
                created_at=record.created_at,
                finished_at=record.finished_at,
            ),
            status_code,
        )

    def _raise_run_error(self, record: ModelRunRecord, *, idempotency_replayed: bool) -> NoReturn:
        stable_error = record.stable_error or "RUN_OUTCOME_UNKNOWN"
        self._logger.run(
            client_run_id=record.client_run_id,
            invite_id=record.invite_id,
            device_id=record.device_id,
            model_profile_id=record.model_profile_id,
            quota_unit=record.quota_unit,
            state="failed",
            idempotency_replayed=idempotency_replayed,
            stable_error=stable_error,
        )
        raise ControlPlaneError(stable_error)

    def _validate_protocol(self, protocol_version: str) -> None:
        if protocol_version != self.settings.protocol_version:
            raise ControlPlaneError("PROTOCOL_VERSION_UNSUPPORTED")

    def _request_fingerprint(self, request: ModelInvokeRequest) -> str:
        try:
            canonical = json.dumps(
                {
                    "client_run_id": request.client_run_id,
                    "context_hash": request.context_hash,
                    "model_profile_id": request.model_profile_id,
                    "protocol_version": request.protocol_version,
                    "request_payload": request.request_payload,
                },
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise ControlPlaneError("REQUEST_INVALID") from None
        return self._hasher.request_fingerprint(canonical)
