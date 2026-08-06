from __future__ import annotations

import logging
import socket

import pytest

from plotagent.security import (
    HttpMethod,
    HttpxRawTransport,
    LocalSecurityError,
    NetworkMode,
    NetworkPolicyGate,
    NetworkPurpose,
    NetworkRequest,
    PolicyTransport,
)
from tests.http_server import FakeResponse, loopback_server, server_url


def test_real_loopback_custom_endpoint_uses_bounded_header_surface() -> None:
    def respond(_: object) -> FakeResponse:
        return FakeResponse(
            headers={
                "Content-Type": "application/json",
                "X-Request-Id": "safe-request-id",
                "X-Not-Allowlisted": "discard-me",
            },
            body=b'{"ok":true}',
        )

    with loopback_server(respond) as server, HttpxRawTransport() as raw:
        base_url = f"{server_url(server)}/v1"
        transport = PolicyTransport(
            NetworkPolicyGate(NetworkMode.CUSTOM_PROVIDER, custom_endpoint=base_url),
            raw,
        )
        response = transport.send(
            NetworkRequest(
                HttpMethod.POST,
                f"{base_url}/responses",
                NetworkPurpose.CUSTOM_MODEL,
                headers={"Content-Type": "application/json"},
                body=b"{}",
            )
        )

    assert response.status_code == 200
    assert response.body == b'{"ok":true}'
    assert response.headers == {
        "content-type": "application/json",
        "x-request-id": "safe-request-id",
    }
    assert len(server.requests) == 1


def test_real_redirect_is_regated_before_out_of_scope_server_call() -> None:
    with loopback_server(lambda _: FakeResponse(body=b"must-not-be-called")) as outside:
        redirect = f"{server_url(outside)}/v1/responses"
        with (
            loopback_server(lambda _: FakeResponse(307, {"Location": redirect})) as origin,
            HttpxRawTransport() as raw,
        ):
            base_url = f"{server_url(origin)}/v1"
            transport = PolicyTransport(
                NetworkPolicyGate(NetworkMode.CUSTOM_PROVIDER, custom_endpoint=base_url),
                raw,
            )

            with pytest.raises(LocalSecurityError) as captured:
                transport.send(
                    NetworkRequest(
                        HttpMethod.POST,
                        f"{base_url}/responses",
                        NetworkPurpose.CUSTOM_MODEL,
                    )
                )

    assert captured.value.code == "NETWORK_ENDPOINT_BLOCKED"
    assert len(origin.requests) == 1
    assert outside.requests == []


def test_real_loopback_local_only_blocks_before_any_server_call() -> None:
    with (
        loopback_server(lambda _: FakeResponse(body=b"must-not-be-called")) as server,
        HttpxRawTransport() as raw,
    ):
        transport = PolicyTransport(NetworkPolicyGate(NetworkMode.LOCAL_ONLY), raw)
        with pytest.raises(LocalSecurityError) as captured:
            transport.send(
                NetworkRequest(
                    HttpMethod.GET,
                    f"{server_url(server)}/v1/quota",
                    NetworkPurpose.QUOTA,
                )
            )

    assert captured.value.code == "NETWORK_BLOCKED_LOCAL_ONLY"
    assert server.requests == []


def test_non_https_non_loopback_is_rejected_without_network_access() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        NetworkPolicyGate(
            NetworkMode.CUSTOM_PROVIDER,
            custom_endpoint="http://models.example.test/v1",
        )


def test_raw_transport_rejects_unknown_headers_and_oversized_body() -> None:
    payload = b"x" * 33
    with loopback_server(lambda _: FakeResponse(body=payload)) as server:
        base_url = f"{server_url(server)}/v1"
        with HttpxRawTransport(max_response_bytes=32) as raw:
            transport = PolicyTransport(
                NetworkPolicyGate(NetworkMode.CUSTOM_PROVIDER, custom_endpoint=base_url),
                raw,
            )
            with pytest.raises(LocalSecurityError) as header_error:
                transport.send(
                    NetworkRequest(
                        HttpMethod.GET,
                        f"{base_url}/responses",
                        NetworkPurpose.CUSTOM_MODEL,
                        headers={"X-Untrusted": "blocked"},
                    )
                )
            assert server.requests == []

            with pytest.raises(LocalSecurityError) as size_error:
                transport.send(
                    NetworkRequest(
                        HttpMethod.GET,
                        f"{base_url}/responses",
                        NetworkPurpose.CUSTOM_MODEL,
                    )
                )

    assert header_error.value.code == "NETWORK_HEADER_BLOCKED"
    assert size_error.value.code == "NETWORK_RESPONSE_TOO_LARGE"
    assert len(server.requests) == 1


def test_connection_failure_is_stable_and_does_not_log_request_path(
    caplog: pytest.LogCaptureFixture,
) -> None:
    canary_path = "path-DO-NOT-LEAK"
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}/{canary_path}"
    caplog.set_level(logging.DEBUG)

    with HttpxRawTransport() as raw:
        transport = PolicyTransport(
            NetworkPolicyGate(NetworkMode.CUSTOM_PROVIDER, custom_endpoint=base_url),
            raw,
        )
        with pytest.raises(LocalSecurityError) as captured:
            transport.send(
                NetworkRequest(
                    HttpMethod.GET,
                    f"{base_url}/responses",
                    NetworkPurpose.CUSTOM_MODEL,
                )
            )

    assert captured.value.code == "PROVIDER_CONNECTION_FAILED"
    assert canary_path not in str(captured.value)
    assert canary_path not in repr(captured.value)
    assert canary_path not in caplog.text
