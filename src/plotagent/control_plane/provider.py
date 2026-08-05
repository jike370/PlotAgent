"""Injectable upstream provider boundary for one structured built-in decision."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    client_run_id: str
    model_profile_id: str
    deployment_id: str
    request_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProviderResult:
    response_payload: dict[str, Any]


class ProviderUnavailableError(Exception):
    """The adapter can prove that it did not produce a usable response."""


class ProviderTimeoutError(Exception):
    """The adapter timed out and cannot prove the upstream outcome."""


class ProviderAdapter(Protocol):
    async def invoke(self, request: ProviderRequest) -> ProviderResult:
        """Forward exactly one structured request to a fixed deployment."""


class UnavailableProviderAdapter:
    """Safe runtime default: starting the service never implies real network access."""

    async def invoke(self, request: ProviderRequest) -> ProviderResult:
        del request
        raise ProviderUnavailableError
