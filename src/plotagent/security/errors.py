"""Stable, payload-free errors for local security boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

_SAFE_DETAIL_VALUES: Final = frozenset(
    {
        "network_policy",
        "endpoint_policy",
        "network_transport",
        "credential_store",
        "log_schema",
        "diagnostic_schema",
        "diagnostic_consent",
        "temp_acl",
        "temp_cleanup",
        "schema_version",
        "migration_pair",
        "migration_copy",
        "migration_execute",
        "migration_validate",
        "migration_switch",
        "legacy_component",
    }
)


class LocalSecurityError(RuntimeError):
    """An error whose printable form never contains user data or local paths."""

    def __init__(self, code: str, *, category: str) -> None:
        if category not in _SAFE_DETAIL_VALUES:
            raise ValueError("error category must be a stable allowlisted value")
        super().__init__(code)
        self.code = code
        self.details: Mapping[str, str] = MappingProxyType({"category": category})

    def __str__(self) -> str:
        return self.code
