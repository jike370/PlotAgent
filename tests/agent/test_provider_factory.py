from __future__ import annotations

import pytest

import plotagent.agent.providers.factory as provider_factory
from plotagent.agent.providers import CustomProviderConfig, LocalOnlyProvider, create_provider
from plotagent.security import InMemoryCredentialStore, NetworkMode


def test_local_only_factory_never_constructs_network_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_transport(**_: object) -> None:
        raise AssertionError("RawTransport must not be created in local_only")

    monkeypatch.setattr(provider_factory, "HttpxRawTransport", forbidden_transport)

    provider = create_provider(
        NetworkMode.LOCAL_ONLY,
        credential_store=InMemoryCredentialStore(),
        app_build="test",
    )

    assert isinstance(provider, LocalOnlyProvider)


def test_custom_provider_requires_exactly_one_custom_configuration() -> None:
    store = InMemoryCredentialStore()
    with pytest.raises(ValueError, match="custom_provider"):
        create_provider(
            NetworkMode.CUSTOM_PROVIDER,
            credential_store=store,
            app_build="test",
        )

    provider = create_provider(
        NetworkMode.CUSTOM_PROVIDER,
        credential_store=store,
        app_build="test",
        custom_config=CustomProviderConfig(
            provider_config_id="custom-test",
            base_url="https://models.example.test/v1",
            model_id="synthetic-model",
        ),
    )
    assert provider.identity.provider_config_id == "custom-test"
