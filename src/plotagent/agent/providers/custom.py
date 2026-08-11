"""OpenAI-compatible Responses-first provider over the gated network transport."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from pydantic import TypeAdapter, ValidationError

from plotagent.agent.engine_client import EngineAgentDecision
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
from plotagent.agent.providers.engine_prompt import engine_agent_prompt
from plotagent.contracts.agent_context import ContextEnvelope
from plotagent.contracts.canonical import JsonValue, canonical_hash, canonical_json
from plotagent.engine import EngineActionCodec, EngineCatalog
from plotagent.engine.profiles import ENGINE_PROFILES
from plotagent.security.network import (
    HttpMethod,
    NetworkPurpose,
    NetworkRequest,
    NetworkResponse,
    PolicyTransport,
)


class _ProtocolUnsupported(Exception):
    pass


class _StructuredOutputUnsupported(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CustomProviderConfig:
    provider_config_id: str
    base_url: str
    model_id: str
    model_profile: str = "custom-fixed"


class OpenAICompatibleProvider:
    def __init__(
        self,
        transport: PolicyTransport,
        config: CustomProviderConfig,
        *,
        capabilities: ProviderCapabilities | None = None,
    ) -> None:
        self._transport = transport
        self._config = config
        self._capabilities = capabilities

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            provider_type="custom",
            provider_config_id=self._config.provider_config_id,
            endpoint_origin=normalize_endpoint_origin(self._config.base_url),
            model_id=self._config.model_id,
            model_profile=self._config.model_profile,
        )

    async def resolve_capabilities(self) -> ProviderCapabilities:
        if self._capabilities is not None:
            return self._capabilities
        schema = TypeAdapter(EngineAgentDecision).json_schema(mode="validation")
        synthetic = ProviderDecisionRequest(
            client_model_run_id="synthetic-probe",
            envelope=_synthetic_envelope(),
            decision_schema=schema,
            decision_schema_hash=canonical_hash(schema),
            prompt_template=engine_agent_prompt(
                EngineActionCodec(EngineCatalog(ENGINE_PROFILES))
            ),
        )
        try:
            wire = self._invoke(synthetic, ProviderProtocol.RESPONSES, strict=True)
            if _valid_decision(wire.output_text):
                self._capabilities = ProviderCapabilities(
                    OutputCapability.P1, ProviderProtocol.RESPONSES
                )
                return self._capabilities
            self._capabilities = ProviderCapabilities(OutputCapability.P0, ProviderProtocol.NONE)
            return self._capabilities
        except (_ProtocolUnsupported, _StructuredOutputUnsupported):
            pass
        try:
            wire = self._invoke(synthetic, ProviderProtocol.CHAT_COMPLETIONS, strict=True)
            if _valid_decision(wire.output_text):
                self._capabilities = ProviderCapabilities(
                    OutputCapability.P1, ProviderProtocol.CHAT_COMPLETIONS
                )
                return self._capabilities
            self._capabilities = ProviderCapabilities(OutputCapability.P0, ProviderProtocol.NONE)
            return self._capabilities
        except _StructuredOutputUnsupported:
            pass
        except _ProtocolUnsupported:
            self._capabilities = ProviderCapabilities(OutputCapability.P0, ProviderProtocol.NONE)
            return self._capabilities
        try:
            wire = self._invoke(synthetic, ProviderProtocol.CHAT_COMPLETIONS, strict=False)
        except (_ProtocolUnsupported, _StructuredOutputUnsupported, AgentRuntimeError):
            self._capabilities = ProviderCapabilities(OutputCapability.P0, ProviderProtocol.NONE)
            return self._capabilities
        self._capabilities = ProviderCapabilities(
            OutputCapability.P2 if _valid_decision(wire.output_text) else OutputCapability.P0,
            ProviderProtocol.CHAT_COMPLETIONS
            if _valid_decision(wire.output_text)
            else ProviderProtocol.NONE,
        )
        return self._capabilities

    async def decide(self, request: ProviderDecisionRequest) -> ProviderWireResponse:
        capabilities = await self.resolve_capabilities()
        if capabilities.output_capability is OutputCapability.P0:
            raise AgentRuntimeError("PROVIDER_UNSUPPORTED")
        return self._invoke(
            request,
            capabilities.protocol,
            strict=capabilities.output_capability is OutputCapability.P1,
        )

    async def repair(
        self,
        request: ProviderDecisionRequest,
        *,
        invalid_candidate: str,
        schema_error_categories: tuple[str, ...],
    ) -> ProviderWireResponse:
        capabilities = await self.resolve_capabilities()
        if capabilities.output_capability is not OutputCapability.P2:
            raise AgentRuntimeError("SCHEMA_INVALID")
        return self._invoke(
            request,
            capabilities.protocol,
            strict=False,
            repair_candidate=invalid_candidate,
            schema_errors=schema_error_categories,
        )

    async def cancel(self, client_model_run_id: str) -> None:
        del client_model_run_id

    def _invoke(
        self,
        request: ProviderDecisionRequest,
        protocol: ProviderProtocol,
        *,
        strict: bool,
        repair_candidate: str | None = None,
        schema_errors: tuple[str, ...] = (),
    ) -> ProviderWireResponse:
        body = self._request_body(
            request,
            protocol,
            strict=strict,
            repair_candidate=repair_candidate,
            schema_errors=schema_errors,
        )
        suffix = "responses" if protocol is ProviderProtocol.RESPONSES else "chat/completions"
        response = self._transport.send(
            NetworkRequest(
                method=HttpMethod.POST,
                url=f"{self._config.base_url.rstrip('/')}/{suffix}",
                purpose=NetworkPurpose.CUSTOM_MODEL,
                headers={"Content-Type": "application/json"},
                body=canonical_json(cast(JsonValue, body)).encode("utf-8"),
            )
        )
        self._classify_error(response, strict=strict)
        return self._extract(response, protocol)

    def _request_body(
        self,
        request: ProviderDecisionRequest,
        protocol: ProviderProtocol,
        *,
        strict: bool,
        repair_candidate: str | None,
        schema_errors: tuple[str, ...],
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "context_envelope": request.envelope.model_dump(mode="json"),
            "context_hash": request.envelope.context_hash,
            "agent_decision_schema_hash": request.decision_schema_hash,
        }
        if not strict:
            # JSON-object mode cannot carry a schema in response_format. Include the
            # same public contract in the prompt payload so P2 providers do not have
            # to guess the AgentDecision shape from its hash.
            data["agent_decision_schema"] = request.decision_schema
        if repair_candidate is not None:
            data["repair"] = {
                "candidate": repair_candidate,
                "schema_error_categories": schema_errors,
                "instruction": "Repair only schema shape; add no project data or new intent.",
            }
        user_content = canonical_json(cast(JsonValue, data))
        if protocol is ProviderProtocol.RESPONSES:
            return {
                "model": self._config.model_id,
                "store": False,
                "input": [
                    {"role": "system", "content": request.prompt_template.text},
                    {"role": "user", "content": user_content},
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "agent_decision",
                        "strict": True,
                        "schema": request.decision_schema,
                    }
                },
            }
        response_format: dict[str, object]
        if strict:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "agent_decision",
                    "strict": True,
                    "schema": request.decision_schema,
                },
            }
        else:
            response_format = {"type": "json_object"}
        return {
            "model": self._config.model_id,
            "store": False,
            "messages": [
                {"role": "system", "content": request.prompt_template.text},
                {"role": "user", "content": user_content},
            ],
            "response_format": response_format,
        }

    def _classify_error(self, response: NetworkResponse, *, strict: bool) -> None:
        if response.status_code < 400:
            return
        if response.status_code in {404, 405, 501}:
            raise _ProtocolUnsupported
        error_code = _error_code(response.body)
        if strict and error_code in {
            "unsupported_parameter",
            "unsupported_response_format",
            "json_schema_unsupported",
        }:
            raise _StructuredOutputUnsupported
        if strict and _describes_structured_output_error(response.body):
            raise _StructuredOutputUnsupported
        raise AgentRuntimeError("PROVIDER_CONNECTION_FAILED")

    def _extract(
        self, response: NetworkResponse, protocol: ProviderProtocol
    ) -> ProviderWireResponse:
        try:
            payload = json.loads(response.body)
        except (TypeError, ValueError):
            raise AgentRuntimeError("SCHEMA_INVALID") from None
        if not isinstance(payload, dict):
            raise AgentRuntimeError("SCHEMA_INVALID")
        request_id = payload.get("id")
        if protocol is ProviderProtocol.RESPONSES:
            output_items = payload.get("output")
            if isinstance(output_items, list) and any(
                isinstance(item, dict) and item.get("type") in {"function_call", "tool_call"}
                for item in output_items
            ):
                raise AgentRuntimeError("AGENT_FORBIDDEN_PAYLOAD")
            text = payload.get("output_text")
            if not isinstance(text, str):
                text = _responses_text(payload)
        else:
            text = _chat_text(payload)
        if not isinstance(text, str):
            raise AgentRuntimeError("SCHEMA_INVALID")
        return ProviderWireResponse(
            provider_request_id=request_id if isinstance(request_id, str) else None,
            output_text=text,
            usage=_provider_usage(payload.get("usage")),
        )


def _error_code(body: bytes) -> str | None:
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        error_code = error.get("code")
        if isinstance(error_code, str):
            return error_code
    return None


def _describes_structured_output_error(body: bytes) -> bool:
    """Recognize providers that report schema incompatibility with a generic code."""

    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False
    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    error_type = error.get("type")
    error_code = error.get("code")
    if error_type != "invalid_request_error" and error_code != "invalid_request_error":
        return False
    details = " ".join(
        value.casefold()
        for key in ("message", "param")
        if isinstance((value := error.get(key)), str)
    )
    return any(
        marker in details
        for marker in ("json schema", "json_schema", "response_format", "structured output")
    )


def _responses_text(payload: dict[str, Any]) -> str | None:
    output = payload.get("output")
    if not isinstance(output, list):
        return None
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str):
                    return text
    return None


def _chat_text(payload: dict[str, Any]) -> str | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict) or message.get("tool_calls"):
        raise AgentRuntimeError("AGENT_FORBIDDEN_PAYLOAD")
    content = message.get("content")
    return content if isinstance(content, str) else None


def _provider_usage(value: object) -> ProviderUsage:
    if not isinstance(value, dict):
        return ProviderUsage()
    input_value = value.get("input_tokens", value.get("prompt_tokens", 0))
    output_value = value.get("output_tokens", value.get("completion_tokens", 0))
    return ProviderUsage(
        input_tokens=input_value if isinstance(input_value, int) else 0,
        output_tokens=output_value if isinstance(output_value, int) else 0,
        source="provider",
    )


def _valid_decision(value: str) -> bool:
    try:
        TypeAdapter(EngineAgentDecision).validate_json(value)
    except ValidationError:
        return False
    return True


def _synthetic_envelope() -> ContextEnvelope:
    from plotagent.agent.context.builder import (
        AuthoritativeProjectContext,
        ContextBuilder,
        ContextBuildRequest,
        DisclosureGrant,
    )
    from plotagent.agent.context.state import ConversationState
    from plotagent.contracts.agent_context import ChartCapabilities, ContextObjectRef

    target = ContextObjectRef(
        object_alias="active_target",
        object_id="project:synthetic",
        object_version=1,
        object_type="project",
        content_hash="0" * 64,
    )
    return ContextBuilder().build(
        ContextBuildRequest(
            user_instruction="Return no_change for this synthetic probe.",
            locale="en-US",
            project=AuthoritativeProjectContext(
                target=target,
                dataset_content_hash="0" * 64,
            ),
            conversation_state=ConversationState(current_target=target),
            chart_capabilities=ChartCapabilities(
                capability_version="synthetic-v1",
                allowed_action_types=("create_plot",),
            ),
            disclosure_grant=DisclosureGrant(
                provider_type="custom",
                provider_config_id="synthetic",
                retention_disclosure_version="synthetic-v1",
                retention_acknowledged=True,
                allowed_categories=frozenset({"user_instruction", "chart_capabilities"}),
            ),
        )
    )
