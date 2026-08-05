from __future__ import annotations

import json

import pytest

from plotagent.desktop_core.protocol import ProtocolFault, RequestCache, parse_request


def _request(request_id: str, method: str = "system.ping") -> bytes:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "protocol_version": "1.0",
            "id": request_id,
            "method": method,
        }
    ).encode()


def test_strict_request_parser_rejects_duplicate_keys_and_invalid_ids() -> None:
    with pytest.raises(ProtocolFault, match="PARSE_ERROR"):
        parse_request(
            b'{"jsonrpc":"2.0","protocol_version":"1.0","id":"req:one",'
            b'"id":"req:two","method":"system.ping"}'
        )
    with pytest.raises(ProtocolFault, match="INVALID_REQUEST"):
        parse_request(_request("1"))


def test_request_cache_replays_exact_requests_and_detects_conflicts() -> None:
    cache = RequestCache(capacity=2)
    request = parse_request(_request("req:one"))
    cache.store(request, b"response\n")
    assert cache.lookup(request) == b"response\n"

    conflict = parse_request(_request("req:one", "health.get"))
    with pytest.raises(ProtocolFault, match="IDEMPOTENCY_CONFLICT"):
        cache.lookup(conflict)
