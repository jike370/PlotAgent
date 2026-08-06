"""Injectable outbound network policy and transport boundary.

The module deliberately does not patch sockets, DNS, HTTP clients, or process-wide
state.  Every network-capable adapter receives a :class:`PolicyTransport`, and the
wrapped raw transport is called only after the request is authorized.  Raw
transports must surface redirects instead of following them so each hop is gated.
"""

from __future__ import annotations

import ipaddress
import ssl
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Protocol
from urllib.parse import SplitResult, unquote, urlsplit, urlunsplit

import httpx

from plotagent.security.errors import LocalSecurityError

CONNECT_TIMEOUT_SECONDS: Final = 5.0
READ_TIMEOUT_SECONDS: Final = 60.0
WRITE_TIMEOUT_SECONDS: Final = 30.0
POOL_TIMEOUT_SECONDS: Final = 5.0
DEFAULT_MAX_RESPONSE_BYTES: Final = 4 * 1024 * 1024

# This governs application-controlled headers.  httpx still emits protocol
# necessities such as Host and Content-Length.
_REQUEST_HEADER_ALLOWLIST: Final = frozenset(
    {"accept", "content-type", "idempotency-key", "user-agent"}
)
_RESPONSE_HEADER_ALLOWLIST: Final = frozenset(
    {"content-type", "location", "retry-after", "x-request-id"}
)
_REDIRECT_STATUS_CODES: Final = frozenset({301, 302, 303, 307, 308})


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
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))


class NetworkGate(Protocol):
    def authorize(self, request: NetworkRequest) -> None: ...


class RawTransport(Protocol):
    """A transport that returns redirects without automatically following them."""

    def send(self, request: NetworkRequest) -> NetworkResponse: ...


class BearerTokenProvider(Protocol):
    """Resolve a bearer secret immediately before an HTTP request is emitted."""

    def __call__(self, request: NetworkRequest) -> str | None: ...


class HttpxRawTransport:
    """Synchronous production transport with fixed, payload-free failure semantics."""

    def __init__(
        self,
        *,
        bearer_token_provider: BearerTokenProvider | None = None,
        bearer_required_purposes: frozenset[NetworkPurpose] = frozenset(),
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        self._bearer_token_provider = bearer_token_provider
        self._bearer_required_purposes = bearer_required_purposes
        self._max_response_bytes = max_response_bytes
        timeout = httpx.Timeout(
            connect=CONNECT_TIMEOUT_SECONDS,
            read=READ_TIMEOUT_SECONDS,
            write=WRITE_TIMEOUT_SECONDS,
            pool=POOL_TIMEOUT_SECONDS,
        )
        # HTTPTransport retries default to zero; make that production boundary explicit.
        raw_http = httpx.HTTPTransport(verify=True, retries=0)
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            transport=raw_http,
            trust_env=False,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpxRawTransport:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def send(self, request: NetworkRequest) -> NetworkResponse:
        headers = self._request_headers(request)
        try:
            with self._client.stream(
                request.method.value,
                request.url,
                headers=headers,
                content=request.body,
            ) as response:
                body = bytearray()
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > self._max_response_bytes:
                        raise LocalSecurityError(
                            "NETWORK_RESPONSE_TOO_LARGE", category="network_transport"
                        )
                    body.extend(chunk)
                response_headers = {
                    name.lower(): value
                    for name, value in response.headers.items()
                    if name.lower() in _RESPONSE_HEADER_ALLOWLIST
                }
                redirect_url = (
                    response.headers.get("location")
                    if response.status_code in _REDIRECT_STATUS_CODES
                    else None
                )
                return NetworkResponse(
                    status_code=response.status_code,
                    body=bytes(body),
                    redirect_url=redirect_url,
                    headers=response_headers,
                )
        except LocalSecurityError:
            raise
        except httpx.TimeoutException:
            raise LocalSecurityError("REQUEST_TIMEOUT", category="network_transport") from None
        except httpx.ConnectError as error:
            if _caused_by_tls(error):
                raise LocalSecurityError(
                    "TLS_VALIDATION_FAILED", category="network_transport"
                ) from None
            raise LocalSecurityError(
                "PROVIDER_CONNECTION_FAILED", category="network_transport"
            ) from None
        except httpx.HTTPError:
            raise LocalSecurityError(
                "PROVIDER_CONNECTION_FAILED", category="network_transport"
            ) from None

    def _request_headers(self, request: NetworkRequest) -> dict[str, str]:
        headers: dict[str, str] = {}
        for name, value in request.headers.items():
            normalized = name.lower()
            if (
                normalized not in _REQUEST_HEADER_ALLOWLIST
                or "\r" in name
                or "\n" in name
                or "\r" in value
                or "\n" in value
            ):
                raise LocalSecurityError("NETWORK_HEADER_BLOCKED", category="network_transport")
            headers[name] = value

        token = (
            self._bearer_token_provider(request)
            if self._bearer_token_provider is not None
            else None
        )
        if token is not None:
            if not token or "\r" in token or "\n" in token:
                raise LocalSecurityError("CREDENTIAL_INVALID", category="credential_store")
            headers["Authorization"] = f"Bearer {token}"
        elif request.purpose in self._bearer_required_purposes:
            raise LocalSecurityError("CREDENTIAL_NOT_FOUND", category="credential_store")
        return headers


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
            _Endpoint.parse(endpoint, allow_loopback_http=True) for endpoint in builtin_endpoints
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
            raise LocalSecurityError("NETWORK_BLOCKED_LOCAL_ONLY", category="network_policy")
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
            try:
                redirect_url = _resolve_redirect(current.url, response.redirect_url)
            except ValueError:
                raise LocalSecurityError("REDIRECT_BLOCKED", category="endpoint_policy") from None
            current = replace(current, url=redirect_url)
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
    del source_url
    redirect = _parse_http_url(redirect_url)
    # Redirects must be absolute.  This keeps every next hop explicit and auditable.
    return urlunsplit(redirect)


def _caused_by_tls(error: BaseException) -> bool:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLError):
            return True
        current = current.__cause__ or current.__context__
    return False
