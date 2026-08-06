from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from plotagent.security import (
    HttpMethod,
    LocalSecurityError,
    NetworkMode,
    NetworkPolicyGate,
    NetworkPurpose,
    NetworkRequest,
    NetworkResponse,
    PolicyTransport,
)


@dataclass
class RecordingTransport:
    responses: list[NetworkResponse] = field(default_factory=list)
    requests: list[NetworkRequest] = field(default_factory=list)

    def send(self, request: NetworkRequest) -> NetworkResponse:
        self.requests.append(request)
        return self.responses.pop(0) if self.responses else NetworkResponse(200, b"ok")


@pytest.mark.parametrize("purpose", list(NetworkPurpose))
@pytest.mark.parametrize(
    "url",
    [
        "https://proxy.plotagent.example/v1/model",
        "http://localhost:11434/v1/chat",
        "http://127.0.0.1:11434/v1/chat",
        "http://[::1]:11434/v1/chat",
    ],
)
def test_local_only_blocks_every_request_before_transport(
    purpose: NetworkPurpose, url: str
) -> None:
    raw = RecordingTransport()
    transport = PolicyTransport(NetworkPolicyGate(NetworkMode.LOCAL_ONLY), raw)

    with pytest.raises(LocalSecurityError) as captured:
        transport.send(NetworkRequest(HttpMethod.POST, url, purpose))

    assert captured.value.code == "NETWORK_BLOCKED_LOCAL_ONLY"
    assert raw.requests == []


def test_custom_provider_allows_only_explicit_loopback_endpoint_and_base_path() -> None:
    raw = RecordingTransport()
    gate = NetworkPolicyGate(
        NetworkMode.CUSTOM_PROVIDER,
        custom_endpoint="http://127.0.0.1:11434/v1",
    )
    transport = PolicyTransport(gate, raw)

    response = transport.send(
        NetworkRequest(
            HttpMethod.POST,
            "http://127.0.0.1:11434/v1/chat/completions",
            NetworkPurpose.CUSTOM_MODEL,
        )
    )

    assert response.status_code == 200
    assert len(raw.requests) == 1
    for blocked in (
        "http://localhost:11434/v1/chat/completions",
        "http://127.0.0.1:11435/v1/chat/completions",
        "http://127.0.0.1:11434/admin",
        "http://127.0.0.1:11434/v1/%2e%2e/admin",
    ):
        with pytest.raises(LocalSecurityError) as captured:
            transport.send(NetworkRequest(HttpMethod.POST, blocked, NetworkPurpose.CUSTOM_MODEL))
        assert captured.value.code == "NETWORK_ENDPOINT_BLOCKED"
    assert len(raw.requests) == 1


def test_custom_non_loopback_endpoint_requires_https() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        NetworkPolicyGate(
            NetworkMode.CUSTOM_PROVIDER,
            custom_endpoint="http://models.example.test/v1",
        )


def test_builtin_mode_cannot_call_custom_or_background_purposes() -> None:
    raw = RecordingTransport()
    transport = PolicyTransport(
        NetworkPolicyGate(
            NetworkMode.BUILTIN_PROXY,
            builtin_endpoints=("https://proxy.plotagent.example/v1",),
        ),
        raw,
    )
    assert (
        transport.send(
            NetworkRequest(
                HttpMethod.POST,
                "https://proxy.plotagent.example/v1/model",
                NetworkPurpose.BUILTIN_MODEL,
            )
        ).status_code
        == 200
    )

    for purpose in (
        NetworkPurpose.CUSTOM_MODEL,
        NetworkPurpose.UPDATE,
        NetworkPurpose.REMOTE_CONFIG,
        NetworkPurpose.ANALYTICS,
        NetworkPurpose.DIAGNOSTIC,
        NetworkPurpose.EXTERNAL_URL,
    ):
        with pytest.raises(LocalSecurityError):
            transport.send(
                NetworkRequest(
                    HttpMethod.POST,
                    "https://proxy.plotagent.example/v1/model",
                    purpose,
                )
            )
    assert len(raw.requests) == 1


def test_redirect_is_regated_before_second_transport_call() -> None:
    raw = RecordingTransport(
        responses=[NetworkResponse(307, redirect_url="https://other.example/v1/model")]
    )
    transport = PolicyTransport(
        NetworkPolicyGate(
            NetworkMode.BUILTIN_PROXY,
            builtin_endpoints=("https://proxy.plotagent.example/v1",),
        ),
        raw,
    )

    with pytest.raises(LocalSecurityError) as captured:
        transport.send(
            NetworkRequest(
                HttpMethod.POST,
                "https://proxy.plotagent.example/v1/model",
                NetworkPurpose.BUILTIN_MODEL,
            )
        )

    assert captured.value.code == "NETWORK_ENDPOINT_BLOCKED"
    assert len(raw.requests) == 1
