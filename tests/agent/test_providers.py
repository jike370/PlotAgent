from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from pydantic import TypeAdapter

from plotagent.agent.context import ContextBuilder
from plotagent.agent.providers import (
    BuiltinProviderConfig,
    BuiltinProxyProvider,
    CustomProviderConfig,
    OpenAICompatibleProvider,
    OutputCapability,
    ProviderDecisionRequest,
    ProviderProtocol,
)
from plotagent.agent.providers.prompt import AGENT_PROMPT
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.decisions import AgentDecision
from plotagent.control_plane.models import ModelInvokeRequest
from plotagent.security import (
    NetworkMode,
    NetworkPolicyGate,
    NetworkRequest,
    NetworkResponse,
    PolicyTransport,
)
from tests.agent.helpers import context_request, no_change_payload


@dataclass
class RecordingRawTransport:
    responses: list[NetworkResponse]
    requests: list[NetworkRequest] = field(default_factory=list)

    def send(self, request: NetworkRequest) -> NetworkResponse:
        self.requests.append(request)
        return self.responses.pop(0)


def chat_success() -> NetworkResponse:
    return NetworkResponse(
        200,
        json.dumps(
            {
                "id": "chat-synthetic",
                "choices": [{"message": {"content": no_change_payload()}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            }
        ).encode(),
    )


def custom_provider(raw: RecordingRawTransport) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        PolicyTransport(
            NetworkPolicyGate(
                NetworkMode.CUSTOM_PROVIDER,
                custom_endpoint="http://127.0.0.1:11434/v1",
            ),
            raw,
        ),
        CustomProviderConfig(
            provider_config_id="custom-probe",
            base_url="http://127.0.0.1:11434/v1",
            model_id="synthetic-model",
        ),
    )


def test_custom_probe_falls_back_responses_to_chat_strict() -> None:
    raw = RecordingRawTransport(
        [NetworkResponse(404, b'{"error":{"code":"not_found"}}'), chat_success()]
    )
    provider = custom_provider(raw)

    capabilities = asyncio.run(provider.resolve_capabilities())

    assert capabilities.output_capability is OutputCapability.P1
    assert capabilities.protocol is ProviderProtocol.CHAT_COMPLETIONS
    assert [request.url for request in raw.requests] == [
        "http://127.0.0.1:11434/v1/responses",
        "http://127.0.0.1:11434/v1/chat/completions",
    ]
    bodies = [json.loads(request.body or b"{}") for request in raw.requests]
    assert bodies[0]["store"] is False
    assert bodies[0]["text"]["format"]["strict"] is True
    assert bodies[1]["response_format"]["json_schema"]["strict"] is True
    serialized = json.dumps(bodies, ensure_ascii=False)
    assert "synthetic probe" in serialized
    assert "温度" not in serialized
    assert all("tools" not in body for body in bodies)
    assert all("previous_response_id" not in body for body in bodies)


def test_custom_probe_prefers_responses_strict_when_available() -> None:
    raw = RecordingRawTransport(
        [
            NetworkResponse(
                200,
                json.dumps(
                    {
                        "id": "response-synthetic",
                        "output_text": no_change_payload(),
                    }
                ).encode(),
            )
        ]
    )
    capabilities = asyncio.run(custom_provider(raw).resolve_capabilities())

    assert capabilities.output_capability is OutputCapability.P1
    assert capabilities.protocol is ProviderProtocol.RESPONSES
    assert len(raw.requests) == 1


def test_custom_probe_degrades_to_p2_json_only_after_strict_is_unsupported() -> None:
    unsupported = NetworkResponse(
        400,
        b'{"error":{"code":"unsupported_response_format"}}',
    )
    raw = RecordingRawTransport([NetworkResponse(404), unsupported, chat_success()])
    provider = custom_provider(raw)

    capabilities = asyncio.run(provider.resolve_capabilities())

    assert capabilities.output_capability is OutputCapability.P2
    assert capabilities.protocol is ProviderProtocol.CHAT_COMPLETIONS
    json_mode = json.loads(raw.requests[-1].body or b"{}")
    assert json_mode["response_format"] == {"type": "json_object"}
    prompt_payload = json.loads(json_mode["messages"][1]["content"])
    assert prompt_payload["agent_decision_schema"]
    assert prompt_payload["agent_decision_schema_hash"]


def test_custom_probe_degrades_when_provider_uses_generic_schema_error() -> None:
    generic_schema_error = NetworkResponse(
        400,
        json.dumps(
            {
                "error": {
                    "type": "invalid_request_error",
                    "code": "invalid_request_error",
                    "message": "Invalid json schema: one of type, anyOf, or ref is required",
                }
            }
        ).encode(),
    )
    raw = RecordingRawTransport([generic_schema_error, generic_schema_error, chat_success()])

    capabilities = asyncio.run(custom_provider(raw).resolve_capabilities())

    assert capabilities.output_capability is OutputCapability.P2
    assert capabilities.protocol is ProviderProtocol.CHAT_COMPLETIONS
    assert [request.url.rsplit("/", 2)[-2:] for request in raw.requests] == [
        ["v1", "responses"],
        ["chat", "completions"],
        ["chat", "completions"],
    ]
    json_mode = json.loads(raw.requests[-1].body or b"{}")
    assert json_mode["response_format"] == {"type": "json_object"}
    prompt_payload = json.loads(json_mode["messages"][1]["content"])
    assert prompt_payload["agent_decision_schema"]


@dataclass
class FakeCloudClient:
    requests: list[ModelInvokeRequest] = field(default_factory=list)
    cancel_ids: list[str] = field(default_factory=list)

    async def invoke_model(self, request: ModelInvokeRequest) -> object:
        self.requests.append(request)
        return {
            "response_payload": {
                "provider_request_id": "proxy-request",
                "decision": json.loads(no_change_payload()),
                "usage": {"input_tokens": 7, "output_tokens": 4},
            }
        }

    async def cancel_model(self, client_run_id: str) -> None:
        self.cancel_ids.append(client_run_id)


def test_builtin_provider_uses_injected_cloud_client_and_fixed_structured_payload() -> None:
    cloud = FakeCloudClient()
    provider = BuiltinProxyProvider(
        cloud,
        BuiltinProviderConfig(
            provider_config_id="builtin-beta",
            endpoint_origin="https://proxy.plotagent.example:443",
            model_profile_id="profile-v1",
            model_id="fixed-model",
            deployment_id="deployment-v1",
        ),
    )
    envelope = ContextBuilder().build(context_request())
    schema = TypeAdapter(AgentDecision).json_schema(mode="validation")
    request = ProviderDecisionRequest(
        client_model_run_id="run:builtin",
        envelope=envelope,
        decision_schema=schema,
        decision_schema_hash=canonical_hash(schema),
        prompt_template=AGENT_PROMPT,
    )

    response = asyncio.run(provider.decide(request))

    assert json.loads(response.output_text) == json.loads(no_change_payload())
    assert len(cloud.requests) == 1
    payload = cloud.requests[0].request_payload
    assert payload["store"] is False
    assert payload["tools"] == []
    assert payload["context_envelope"]["context_hash"] == envelope.context_hash
    assert payload["prompt_template"]["hash"] == AGENT_PROMPT.prompt_hash
    assert provider.identity.deployment_id == "deployment-v1"


def test_agent_prompt_maps_explicit_edits_and_treats_preservation_as_a_constraint() -> None:
    assert AGENT_PROMPT.version == "agent-decision-v3"
    assert "plot title or 图标题 to set_plot_title" in AGENT_PROMPT.text
    assert "Never emit a style patch merely to preserve" in AGENT_PROMPT.text
    assert "minimum necessary question instead of guessing" in AGENT_PROMPT.text
