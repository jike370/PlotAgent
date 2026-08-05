"""Mode-aware provider factory with secret and network construction boundaries."""

from __future__ import annotations

from plotagent.agent.providers.base import (
    ModelProvider,
    OutputCapability,
    ProviderCapabilities,
    ProviderDecisionRequest,
    ProviderIdentity,
    ProviderProtocol,
    ProviderWireResponse,
)
from plotagent.agent.providers.builtin import BuiltinProviderConfig, BuiltinProxyProvider
from plotagent.agent.providers.custom import CustomProviderConfig, OpenAICompatibleProvider
from plotagent.control_plane.client import BuiltinControlPlaneClient
from plotagent.security.credentials import CredentialStore
from plotagent.security.errors import LocalSecurityError
from plotagent.security.network import (
    HttpxRawTransport,
    NetworkMode,
    NetworkPolicyGate,
    NetworkPurpose,
    NetworkRequest,
    PolicyTransport,
)


class LocalOnlyProvider:
    """Non-networking provider used to preserve a single orchestrator interface."""

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            provider_type="local_only",
            provider_config_id="local-only",
            endpoint_origin="local-only",
            model_id="none",
            model_profile="none",
        )

    async def resolve_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(OutputCapability.P0, ProviderProtocol.NONE)

    async def decide(self, request: ProviderDecisionRequest) -> ProviderWireResponse:
        del request
        raise LocalSecurityError("NETWORK_BLOCKED_LOCAL_ONLY", category="network_policy")

    async def repair(
        self,
        request: ProviderDecisionRequest,
        *,
        invalid_candidate: str,
        schema_error_categories: tuple[str, ...],
    ) -> ProviderWireResponse:
        del request, invalid_candidate, schema_error_categories
        raise LocalSecurityError("NETWORK_BLOCKED_LOCAL_ONLY", category="network_policy")

    async def cancel(self, client_model_run_id: str) -> None:
        del client_model_run_id


def create_provider(
    mode: NetworkMode,
    *,
    credential_store: CredentialStore,
    app_build: str,
    builtin_config: BuiltinProviderConfig | None = None,
    custom_config: CustomProviderConfig | None = None,
) -> ModelProvider:
    """Create exactly the adapter allowed by ``mode``.

    ``local_only`` exits before constructing ``HttpxRawTransport``.
    """

    if mode is NetworkMode.LOCAL_ONLY:
        return LocalOnlyProvider()

    if mode is NetworkMode.BUILTIN_PROXY:
        if builtin_config is None or custom_config is not None:
            raise ValueError("builtin_proxy requires only builtin_config")

        def builtin_bearer(request: NetworkRequest) -> str | None:
            if request.purpose is NetworkPurpose.INVITATION_REDEEM:
                return None
            return credential_store.get_device_credential()

        raw = HttpxRawTransport(
            bearer_token_provider=builtin_bearer,
            bearer_required_purposes=frozenset(
                {
                    NetworkPurpose.BUILTIN_MODEL,
                    NetworkPurpose.DEVICE_CREDENTIAL,
                    NetworkPurpose.QUOTA,
                }
            ),
        )
        transport = PolicyTransport(
            NetworkPolicyGate(
                NetworkMode.BUILTIN_PROXY,
                builtin_endpoints=(builtin_config.endpoint_origin,),
            ),
            raw,
        )
        client = BuiltinControlPlaneClient(
            transport,
            credential_store,
            base_url=builtin_config.endpoint_origin,
            app_build=app_build,
            protocol_version=builtin_config.protocol_version,
        )
        return BuiltinProxyProvider(client, builtin_config)

    if custom_config is None or builtin_config is not None:
        raise ValueError("custom_provider requires only custom_config")

    def custom_bearer(request: NetworkRequest) -> str | None:
        del request
        return credential_store.get_custom_api_key(custom_config.provider_config_id)

    raw = HttpxRawTransport(bearer_token_provider=custom_bearer)
    transport = PolicyTransport(
        NetworkPolicyGate(
            NetworkMode.CUSTOM_PROVIDER,
            custom_endpoint=custom_config.base_url,
        ),
        raw,
    )
    return OpenAICompatibleProvider(transport, custom_config)
