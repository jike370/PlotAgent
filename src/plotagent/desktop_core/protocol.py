"""Strict JSON-RPC-compatible framing shared with the Electron supervisor."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import BinaryIO, Final

CORE_PROTOCOL_VERSION: Final = "1.0"
DESKTOP_API_VERSION: Final = "1.0"
MAXIMUM_FRAME_BYTES: Final = 1024 * 1024
MAXIMUM_JSON_DEPTH: Final = 32

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9:._-]{0,127}$")
_METHOD = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")

type JsonPrimitive = bool | int | float | str | None
type JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class RpcRequest:
    request_id: str
    method: str
    params: JsonValue | None

    def fingerprint(self) -> str:
        return json.dumps(
            {"method": self.method, "params": self.params},
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )


class ProtocolFault(Exception):
    """A public, sanitized protocol failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        request_id: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.request_id = request_id


@dataclass(frozen=True, slots=True)
class FrameReadResult:
    payload: bytes | None = None
    fault: ProtocolFault | None = None
    eof: bool = False


def read_frame(stream: BinaryIO, maximum_frame_bytes: int = MAXIMUM_FRAME_BYTES) -> FrameReadResult:
    """Read one bounded newline frame without retaining an oversized line."""

    line = stream.readline(maximum_frame_bytes + 2)
    if line == b"":
        return FrameReadResult(eof=True)

    if not line.endswith(b"\n"):
        if len(line) > maximum_frame_bytes:
            _discard_to_newline(stream, maximum_frame_bytes)
            return FrameReadResult(
                fault=ProtocolFault(
                    "FRAME_TOO_LARGE",
                    "The protocol frame exceeded the size limit.",
                )
            )
        return FrameReadResult(
            fault=ProtocolFault("TRUNCATED_FRAME", "The protocol frame was truncated."),
            eof=True,
        )

    payload = line[:-1]
    if payload.endswith(b"\r"):
        payload = payload[:-1]
    if len(payload) > maximum_frame_bytes:
        return FrameReadResult(
            fault=ProtocolFault(
                "FRAME_TOO_LARGE",
                "The protocol frame exceeded the size limit.",
            )
        )
    if not payload:
        return FrameReadResult(
            fault=ProtocolFault("INVALID_FRAME", "The protocol frame was empty.")
        )
    return FrameReadResult(payload=payload)


def parse_request(payload: bytes) -> RpcRequest:
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ProtocolFault("INVALID_FRAME", "The protocol frame was not valid UTF-8.") from error

    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_non_finite_number,
        )
    except (ValueError, RecursionError, json.JSONDecodeError) as error:
        raise ProtocolFault("PARSE_ERROR", "The protocol frame was not valid JSON.") from error

    if not isinstance(value, dict):
        raise ProtocolFault("INVALID_REQUEST", "The request must be a JSON object.")

    raw_id = value.get("id")
    request_id = raw_id if isinstance(raw_id, str) and _IDENTIFIER.fullmatch(raw_id) else None
    if not _is_json_value(value):
        raise ProtocolFault(
            "INVALID_REQUEST",
            "The request exceeded the JSON depth limit.",
            request_id=request_id,
        )
    allowed_keys = {"jsonrpc", "protocol_version", "id", "method", "params"}
    required_keys = {"jsonrpc", "protocol_version", "id", "method"}
    if not required_keys.issubset(value) or not set(value).issubset(allowed_keys):
        raise ProtocolFault(
            "INVALID_REQUEST",
            "The request envelope was invalid.",
            request_id=request_id,
        )
    if value["jsonrpc"] != "2.0":
        raise ProtocolFault(
            "INVALID_REQUEST",
            "The JSON-RPC version was invalid.",
            request_id=request_id,
        )
    if value["protocol_version"] != CORE_PROTOCOL_VERSION:
        raise ProtocolFault(
            "PROTOCOL_VERSION_UNSUPPORTED",
            "The Core protocol version was unsupported.",
            request_id=request_id,
        )
    if request_id is None:
        raise ProtocolFault("INVALID_REQUEST", "The request id was invalid.")
    method = value["method"]
    if not isinstance(method, str) or _METHOD.fullmatch(method) is None:
        raise ProtocolFault(
            "INVALID_REQUEST",
            "The request method was invalid.",
            request_id=request_id,
        )
    params = value.get("params")
    return RpcRequest(request_id=request_id, method=method, params=params)


class ProtocolWriter:
    """Serialize every stdout write so notifications cannot interleave responses."""

    def __init__(self, stream: BinaryIO, maximum_frame_bytes: int = MAXIMUM_FRAME_BYTES) -> None:
        import threading

        self._stream = stream
        self._maximum_frame_bytes = maximum_frame_bytes
        self._lock = threading.Lock()

    def success(self, request_id: str, result: JsonValue) -> bytes:
        return self._write_message(
            {
                "jsonrpc": "2.0",
                "protocol_version": CORE_PROTOCOL_VERSION,
                "id": request_id,
                "result": result,
            }
        )

    def error(self, request_id: str, code: str, message: str) -> bytes:
        return self._write_message(
            {
                "jsonrpc": "2.0",
                "protocol_version": CORE_PROTOCOL_VERSION,
                "id": request_id,
                "error": {"code": code, "message": message},
            }
        )

    def notification(self, method: str, params: JsonValue | None = None) -> bytes:
        message: dict[str, JsonValue] = {
            "jsonrpc": "2.0",
            "protocol_version": CORE_PROTOCOL_VERSION,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        return self._write_message(message)

    def replay(self, encoded: bytes) -> None:
        with self._lock:
            self._stream.write(encoded)
            self._stream.flush()

    def _write_message(self, message: dict[str, JsonValue]) -> bytes:
        try:
            encoded = (
                json.dumps(
                    message,
                    allow_nan=False,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("ascii")
                + b"\n"
            )
        except (TypeError, ValueError) as error:
            raise ProtocolFault(
                "INTERNAL_ERROR",
                "The Core response could not be encoded.",
            ) from error
        if len(encoded) - 1 > self._maximum_frame_bytes:
            raise ProtocolFault("INTERNAL_ERROR", "The Core response exceeded the size limit.")
        with self._lock:
            self._stream.write(encoded)
            self._stream.flush()
        return encoded


@dataclass(frozen=True, slots=True)
class _CachedResponse:
    fingerprint: str
    encoded: bytes


class RequestCache:
    """Bounded per-process replay cache for JSON-RPC request ids."""

    def __init__(self, capacity: int = 1024) -> None:
        if capacity < 1:
            raise ValueError("request cache capacity must be positive")
        self._capacity = capacity
        self._responses: OrderedDict[str, _CachedResponse] = OrderedDict()

    def lookup(self, request: RpcRequest) -> bytes | None:
        cached = self._responses.get(request.request_id)
        if cached is None:
            return None
        self._responses.move_to_end(request.request_id)
        if cached.fingerprint != request.fingerprint():
            raise ProtocolFault(
                "IDEMPOTENCY_CONFLICT",
                "The request id was already used for a different request.",
                request_id=request.request_id,
            )
        return cached.encoded

    def store(self, request: RpcRequest, encoded: bytes) -> None:
        self._responses[request.request_id] = _CachedResponse(request.fingerprint(), encoded)
        self._responses.move_to_end(request.request_id)
        while len(self._responses) > self._capacity:
            self._responses.popitem(last=False)


def is_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _discard_to_newline(stream: BinaryIO, chunk_size: int) -> None:
    while True:
        chunk = stream.readline(chunk_size)
        if chunk == b"" or chunk.endswith(b"\n"):
            return


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_non_finite_number(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _is_json_value(value: object) -> bool:
    stack: list[tuple[object, int]] = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        if depth > MAXIMUM_JSON_DEPTH:
            return False
        if current is None or isinstance(current, (str, bool)):
            continue
        if isinstance(current, int):
            continue
        if isinstance(current, float):
            if current != current or current in {float("inf"), float("-inf")}:
                return False
            continue
        if isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
            continue
        if isinstance(current, dict):
            for key, item in current.items():
                if not isinstance(key, str) or len(key) > 128:
                    return False
                stack.append((item, depth + 1))
            continue
        return False
    return True
