"""Stable, payload-free errors for the Beta control plane."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ErrorDefinition:
    status_code: int
    message: str
    retryable: bool = False


ERRORS: dict[str, ErrorDefinition] = {
    "REQUEST_INVALID": ErrorDefinition(
        422, "The request does not match the control-plane contract."
    ),
    "PROTOCOL_VERSION_UNSUPPORTED": ErrorDefinition(
        409, "The requested protocol version is unavailable."
    ),
    "INVITE_INVALID": ErrorDefinition(401, "The invitation is invalid."),
    "INVITE_EXPIRED": ErrorDefinition(403, "The invitation has expired."),
    "INVITE_REVOKED": ErrorDefinition(403, "The invitation has been revoked."),
    "DEVICE_CREDENTIAL_INVALID": ErrorDefinition(401, "The device credential is invalid."),
    "DEVICE_BLOCKED": ErrorDefinition(403, "The device credential is blocked."),
    "MODEL_PROFILE_UNAVAILABLE": ErrorDefinition(409, "The model profile is unavailable."),
    "QUOTA_EXHAUSTED": ErrorDefinition(409, "The shared invitation quota is exhausted."),
    "RATE_LIMITED": ErrorDefinition(429, "The device is temporarily rate limited.", True),
    "IDEMPOTENCY_CONFLICT": ErrorDefinition(
        409, "The client run id was already used for a different request."
    ),
    "RUN_OUTCOME_UNKNOWN": ErrorDefinition(
        409, "The upstream outcome cannot be proven; do not replay with a new run id."
    ),
    "PROVIDER_UNAVAILABLE": ErrorDefinition(503, "The built-in model provider is unavailable."),
    "CONTROL_PLANE_BUSY": ErrorDefinition(
        503, "The control plane is temporarily busy; retry with the same run id.", True
    ),
    "INTERNAL_ERROR": ErrorDefinition(500, "The control plane could not complete the request."),
}


class ControlPlaneError(Exception):
    """An expected error whose response is entirely defined by its stable code."""

    def __init__(self, code: str, *, retry_after: int | None = None) -> None:
        if code not in ERRORS:
            raise ValueError("Unknown stable control-plane error code")
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after

    @property
    def definition(self) -> ErrorDefinition:
        return ERRORS[self.code]
