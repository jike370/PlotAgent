"""Built-in proxy provider through an injected cloud-control-plane client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel

from plotagent.agent.errors import AgentRuntimeError
from plotagent.agent.providers.base import (
    OutputCapability,
    ProviderCapabilities,
    ProviderDecisionRequest,
    ProviderIdentity,
    ProviderProtocol,
    ProviderUsage,
    ProviderWireResponse,
    normalize_endpoint_origin,
)
from plotagent.contracts.canonical import canonical_json
from plotagent.control_plane.client import ControlPlaneClientError
from plotagent.control_plane.models import ModelInvokeRequest


class BuiltinCloudClient(Protocol):
    async def invoke_model(self, request: ModelInvokeRequest) -> object: ...

    async def cancel_model(self, client_run_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class BuiltinProviderConfig:
    provider_config_id: str
    endpoint_origin: str
    model_profile_id: str
    model_id: str
    deployment_id: str
    protocol_version: str = "1"


class BuiltinProxyProvider:
    def __init__(self, client: BuiltinCloudClient, config: BuiltinProviderConfig) -> None:
        self._client = client
        self._config = config

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            provider_type="builtin",
            provider_config_id=self._config.provider_config_id,
            endpoint_origin=normalize_endpoint_origin(self._config.endpoint_origin),
            model_id=self._config.model_id,
            model_profile=self._config.model_profile_id,
            deployment_id=self._config.deployment_id,
        )

    async def resolve_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(OutputCapability.P1, ProviderProtocol.BUILTIN_PROXY)

    async def decide(self, request: ProviderDecisionRequest) -> ProviderWireResponse:
        invoke = ModelInvokeRequest(
            client_run_id=request.client_model_run_id,
            model_profile_id=self._config.model_profile_id,
            context_hash=request.envelope.context_hash,
            request_payload={
                "prompt_template": {
                    "version": request.prompt_template.version,
                    "hash": request.prompt_template.prompt_hash,
                    "text": request.prompt_template.text,
                },
                "context_envelope": request.envelope.model_dump(mode="json"),
                "agent_decision_schema": request.decision_schema,
                "agent_decision_schema_hash": request.decision_schema_hash,
                "store": False,
                "tools": [],
            },
            protocol_version=self._config.protocol_version,
        )
        try:
            response = await self._client.invoke_model(invoke)
        except ControlPlaneClientError as error:
            raise AgentRuntimeError(error.code) from None
        payload = _response_payload(response)
        output = payload.get("decision", payload.get("output_text"))
        if isinstance(output, dict):
            output_text = canonical_json(output)
        elif isinstance(output, str):
            output_text = output
        else:
            raise AgentRuntimeError("SCHEMA_INVALID")
        usage_value = payload.get("usage")
        usage = _usage(usage_value)
        request_id = payload.get("provider_request_id")
        return ProviderWireResponse(
            provider_request_id=request_id if isinstance(request_id, str) else None,
            output_text=output_text,
            usage=usage,
        )

    async def repair(
        self,
        request: ProviderDecisionRequest,
        *,
        invalid_candidate: str,
        schema_error_categories: tuple[str, ...],
    ) -> ProviderWireResponse:
        del request, invalid_candidate, schema_error_categories
        raise AgentRuntimeError("SCHEMA_INVALID")

    async def cancel(self, client_model_run_id: str) -> None:
        await self._client.cancel_model(client_model_run_id)


def _response_payload(response: object) -> dict[str, Any]:
    if isinstance(response, BaseModel):
        dumped = response.model_dump(mode="python")
    elif isinstance(response, dict):
        dumped = response
    else:
        raise AgentRuntimeError("PROVIDER_CONNECTION_FAILED")
    nested = dumped.get("response_payload")
    if isinstance(nested, dict):
        return nested
    return dumped


def _usage(value: object) -> ProviderUsage:
    if not isinstance(value, dict):
        return ProviderUsage()
    input_tokens = value.get("input_tokens", 0)
    output_tokens = value.get("output_tokens", 0)
    return ProviderUsage(
        input_tokens=input_tokens if isinstance(input_tokens, int) else 0,
        output_tokens=output_tokens if isinstance(output_tokens, int) else 0,
        source="provider",
    )
