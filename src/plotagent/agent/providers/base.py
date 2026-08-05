"""Capability-based provider interface for one structured decision."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol
from urllib.parse import urlsplit

from plotagent.contracts.agent_context import ContextEnvelope
from plotagent.contracts.canonical import canonical_hash


class OutputCapability(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P0 = "P0"


class ProviderProtocol(StrEnum):
    BUILTIN_PROXY = "builtin_proxy"
    RESPONSES = "responses"
    CHAT_COMPLETIONS = "chat_completions"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    output_capability: OutputCapability
    protocol: ProviderProtocol
    streaming: bool = False
    usage_reported: bool = True


@dataclass(frozen=True, slots=True)
class ProviderIdentity:
    provider_type: Literal["builtin", "custom", "local_only"]
    provider_config_id: str
    endpoint_origin: str
    model_id: str
    model_profile: str
    deployment_id: str | None = None


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    version: str
    text: str

    @property
    def prompt_hash(self) -> str:
        return canonical_hash({"version": self.version, "text": self.text})


@dataclass(frozen=True, slots=True)
class ProviderDecisionRequest:
    client_model_run_id: str
    envelope: ContextEnvelope
    decision_schema: dict[str, object]
    decision_schema_hash: str
    prompt_template: PromptTemplate


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    source: str = "unavailable"


@dataclass(frozen=True, slots=True)
class ProviderWireResponse:
    provider_request_id: str | None
    output_text: str
    usage: ProviderUsage = ProviderUsage()

    @property
    def response_hash(self) -> str:
        return hashlib.sha256(self.output_text.encode("utf-8")).hexdigest()


def normalize_endpoint_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("provider endpoint must be an absolute safe HTTP(S) URL")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    host = parsed.hostname.lower()
    rendered_host = f"[{host}]" if ":" in host else host
    return f"{parsed.scheme}://{rendered_host}:{port}"


class ModelProvider(Protocol):
    @property
    def identity(self) -> ProviderIdentity: ...

    async def resolve_capabilities(self) -> ProviderCapabilities: ...

    async def decide(self, request: ProviderDecisionRequest) -> ProviderWireResponse: ...

    async def repair(
        self,
        request: ProviderDecisionRequest,
        *,
        invalid_candidate: str,
        schema_error_categories: tuple[str, ...],
    ) -> ProviderWireResponse: ...

    async def cancel(self, client_model_run_id: str) -> None: ...
