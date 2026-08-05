"""Canonical JSON and content hashing for immutable contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import cast

from pydantic import BaseModel

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]


def _json_value(value: BaseModel | JsonValue) -> JsonValue:
    if isinstance(value, BaseModel):
        return cast(JsonValue, value.model_dump(mode="json", by_alias=True, exclude_none=False))
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    return value


def canonical_json(value: BaseModel | JsonValue) -> str:
    """Return compact, sorted, UTF-8-safe JSON and reject non-finite numbers."""

    return json.dumps(
        _json_value(value),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_hash(value: BaseModel | JsonValue) -> str:
    """Return the lowercase SHA-256 of the canonical UTF-8 representation."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
