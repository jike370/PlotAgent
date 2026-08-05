"""Injectable outbound network policy and transport boundary.

The module deliberately does not patch sockets, DNS, HTTP clients, or process-wide
state.  Every network-capable adapter receives a :class:`PolicyTransport`, and the
wrapped raw transport is called only after the request is authorized.  Raw
transports must surface redirects instead of following them so each hop is gated.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol
from urllib.parse import SplitResult, unquote, urlsplit, urlunsplit

from plotagent.security.errors import LocalSecurityError


class NetworkMode(StrEnum):
    BUILTIN_PROXY = "builtin_proxy"
    CUSTOM_PROVIDER = "custom_provider"
    LOCAL_ONLY = "local_only"


class NetworkPurpose(StrEnum):
    BUILTIN_MODEL = "builtin_model"
    INVITATION_REDEEM = "invitation_redeem"
    DEVICE_CREDENTIAL = "device_credential"
    QUOTA = "quota"
    CUSTOM_MODEL = "custom_model"
    UPDATE = "update"
    REMOTE_CONFIG = "remote_config"
    ANALYTICS = "analytics"
    DIAGNOSTIC = "diagnostic"
    EXTERNAL_URL = "external_url"


class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


@dataclass(frozen=True, slots=True)
class NetworkRequest:
    method: HttpMethod
    url: str
    purpose: NetworkPurpose
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))


@dataclass(frozen=True, slots=True)
class NetworkResponse:
    status_code: int
    body: bytes = b""
    redirect_url: str | None = None


class NetworkGate(Protocol):
    def authorize(self, request: NetworkRequest) -> None: ...


class RawTransport(Protocol):
    """A transport that returns redirects without automatically following them."""

    def send(self, request: NetworkRequest) -> NetworkResponse: ...


@dataclass(frozen=True, slots=True)
class _Endpoint:
    scheme: str
    host: str
    port: int
    base_path: str

    @classmethod
    def parse(cls, value: str, *, allow_loopback_http: bool) -> _Endpoint:
        parsed = _parse_http_url(value)
        if parsed.query or parsed.fragment:
            raise ValueError("endpoint cannot contain query or fragment")
        host = parsed.hostname
        if host is None:
            raise ValueError("endpoint host is required")
        loopback = _is_loopback_literal(host)
        if parsed.scheme == "http" and not (allow_loopback_http and loopback):
            raise ValueError("non-loopback endpoints require HTTPS")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        base_path = _canonical_path(parsed.path)
        return cls(parsed.scheme, host.lower(), port, base_path)

    def contains(self, parsed: SplitResult) -> bool:
        host = parsed.hostname
        if host is None:
            return False
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            path = _canonical_path(parsed.path)
        except ValueError:
            return False
        if (parsed.scheme, host.lower(), port) != (self.scheme, self.host, self.port):
            return False
        if self.base_path == "/":
            return True
        return path == self.base_path or path.startswith(f"{self.base_path}/")


class NetworkPolicyGate:
    """Authorize only the endpoint and operation selected by ``NetworkMode``."""

    _BUILTIN_PURPOSES = frozenset(
        {
            NetworkPurpose.BUILTIN_MODEL,
            NetworkPurpose.INVITATION_REDEEM,
            NetworkPurpose.DEVICE_CREDENTIAL,
            NetworkPurpose.QUOTA,
        }
    )
    _NEVER_NETWORKED = frozenset(
        {
            NetworkPurpose.UPDATE,
            NetworkPurpose.REMOTE_CONFIG,
            NetworkPurpose.ANALYTICS,
            NetworkPurpose.DIAGNOSTIC,
            NetworkPurpose.EXTERNAL_URL,
        }
    )

    def __init__(
        self,
        mode: NetworkMode,
        *,
        builtin_endpoints: tuple[str, ...] = (),
        custom_endpoint: str | None = None,
    ) -> None:
        self.mode = mode
        self._builtin_endpoints = tuple(
            _Endpoint.parse(endpoint, allow_loopback_http=False)
            for endpoint in builtin_endpoints
        )
        self._custom_endpoint = (
            _Endpoint.parse(custom_endpoint, allow_loopback_http=True)
            if custom_endpoint is not None
            else None
        )
        if mode is NetworkMode.CUSTOM_PROVIDER and self._custom_endpoint is None:
            raise ValueError("custom_provider requires an explicit endpoint")

    def authorize(self, request: NetworkRequest) -> None:
        if self.mode is NetworkMode.LOCAL_ONLY:
            raise LocalSecurityError(
                "NETWORK_BLOCKED_LOCAL_ONLY", category="network_policy"
            )
        if request.purpose in self._NEVER_NETWORKED:
            raise LocalSecurityError("NETWORK_PURPOSE_BLOCKED", category="network_policy")

        try:
            parsed = _parse_http_url(request.url)
        except ValueError as error:
            raise LocalSecurityError(
                "NETWORK_ENDPOINT_BLOCKED", category="endpoint_policy"
            ) from error

        if self.mode is NetworkMode.BUILTIN_PROXY:
            allowed = request.purpose in self._BUILTIN_PURPOSES and any(
                endpoint.contains(parsed) for endpoint in self._builtin_endpoints
            )
        else:
            allowed = (
                request.purpose is NetworkPurpose.CUSTOM_MODEL
                and self._custom_endpoint is not None
                and self._custom_endpoint.contains(parsed)
            )
        if not allowed:
            raise LocalSecurityError("NETWORK_ENDPOINT_BLOCKED", category="endpoint_policy")


class PolicyTransport:
    """Gate every request and redirect before delegating to an injected transport."""

    def __init__(
        self,
        gate: NetworkGate,
        transport: RawTransport,
        *,
        max_redirects: int = 5,
    ) -> None:
        if max_redirects < 0:
            raise ValueError("max_redirects cannot be negative")
        self._gate = gate
        self._transport = transport
        self._max_redirects = max_redirects

    def send(self, request: NetworkRequest) -> NetworkResponse:
        current = request
        for redirect_count in range(self._max_redirects + 1):
            self._gate.authorize(current)
            response = self._transport.send(current)
            if response.redirect_url is None:
                return response
            if redirect_count == self._max_redirects:
                raise LocalSecurityError("NETWORK_REDIRECT_LIMIT", category="endpoint_policy")
            current = replace(current, url=_resolve_redirect(current.url, response.redirect_url))
        raise AssertionError("redirect loop must return or raise")


def _parse_http_url(value: str) -> SplitResult:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("only absolute HTTP(S) URLs are supported")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL credentials are forbidden")
    try:
        _ = parsed.port
    except ValueError as error:
        raise ValueError("invalid endpoint port") from error
    return parsed


def _is_loopback_literal(host: str) -> bool:
    normalized = host.rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _canonical_path(path: str) -> str:
    if "\\" in path:
        raise ValueError("endpoint path cannot contain backslashes")
    decoded = unquote(path)
    if decoded != unquote(decoded):
        raise ValueError("endpoint path cannot contain nested encoding")
    segments = decoded.split("/")
    if any(segment in {".", ".."} for segment in segments):
        raise ValueError("endpoint path cannot contain dot segments")
    return decoded.rstrip("/") or "/"


def _resolve_redirect(source_url: str, redirect_url: str) -> str:
    redirect = _parse_http_url(redirect_url)
    # Redirects must be absolute.  This keeps every next hop explicit and auditable.
    return urlunsplit(redirect)
