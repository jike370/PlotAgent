"""Stable, payload-free Agent runtime errors."""

from __future__ import annotations

from collections.abc import Iterable


class AgentRuntimeError(RuntimeError):
    def __init__(self, code: str, *, categories: Iterable[str] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.categories = tuple(dict.fromkeys(categories))

    def __str__(self) -> str:
        return self.code
