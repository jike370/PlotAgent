from __future__ import annotations

import asyncio
import logging

import pytest

import plotagent.agent.providers.factory as provider_factory
from plotagent.agent.audit import InMemoryAuditSink
from plotagent.agent.context import ContextBuilder
from plotagent.agent.orchestrator import SingleAgentOrchestrator
from plotagent.agent.providers import CustomProviderConfig, LocalOnlyProvider, create_provider
from plotagent.agent.validation import DecisionValidator
from plotagent.contracts.canonical import canonical_json
from plotagent.security import InMemoryCredentialStore, NetworkMode
from tests.agent.helpers import authority, context_request, no_change_payload
from tests.http_server import CapturedRequest, FakeResponse, loopback_server, server_url


def test_local_only_factory_does_not_construct_raw_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_transport(**_: object) -> None:
        raise AssertionError("RawTransport must not be created in local_only")

    monkeypatch.setattr(provider_factory, "HttpxRawTransport", forbidden_transport)

    provider = provider_factory.create_provider(
        NetworkMode.LOCAL_ONLY,
        credential_store=InMemoryCredentialStore(),
        app_build="test",
    )

    assert isinstance(provider, LocalOnlyProvider)


def test_custom_secret_is_injected_only_at_transport_boundary_and_not_audited(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "custom-key-DO-NOT-LEAK"

    def respond(_: CapturedRequest) -> FakeResponse:
        return FakeResponse(
            headers={"Content-Type": "application/json"},
            body=(
                '{"id":"provider-request","output_text":'
                + canonical_json(no_change_payload())
                + "}"
            ).encode(),
        )

    caplog.set_level(logging.DEBUG)
    store = InMemoryCredentialStore()
    store.set_custom_api_key("custom-test", secret)
    with loopback_server(respond) as server:
        config = CustomProviderConfig(
            provider_config_id="custom-test",
            base_url=f"{server_url(server)}/v1",
            model_id="synthetic-model",
        )
        provider = create_provider(
            NetworkMode.CUSTOM_PROVIDER,
            credential_store=store,
            app_build="test",
            custom_config=config,
        )
        sink = InMemoryAuditSink()
        runtime = SingleAgentOrchestrator(
            network_mode=NetworkMode.CUSTOM_PROVIDER,
            context_builder=ContextBuilder(),
            provider=provider,
            validator=DecisionValidator(),
            audit_sink=sink,
        )

        result = asyncio.run(
            runtime.run(
                client_model_run_id="factory-custom-run",
                context_request=context_request(),
                validation_authority=authority(),
            )
        )

    assert result.accepted is True
    assert len(server.requests) == 2
    assert all(
        request.headers.get("Authorization") == f"Bearer {secret}" for request in server.requests
    )
    assert "api_key" not in CustomProviderConfig.__dataclass_fields__
    safe_surfaces = " ".join(
        (
            repr(config),
            repr(provider.identity),
            canonical_json(result.audit),
            caplog.text,
        )
    )
    assert secret not in safe_surfaces
