"""Stable failures raised by the pure plot-calculation service."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType


class PlotCalculationError(ValueError):
    """A deterministic W3 calculation rejection with a stable registry code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = MappingProxyType(dict(details or {}))
