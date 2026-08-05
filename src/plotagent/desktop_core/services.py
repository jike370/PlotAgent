"""Narrow registration boundary for desktop Core control services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from plotagent.desktop_core.protocol import JsonValue
from plotagent.desktop_core.tasks import BoundedWorkerExecutor, TaskRegistry


class RpcServiceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class RpcContext:
    request_id: str
    tasks: TaskRegistry
    workers: BoundedWorkerExecutor


type RpcHandler = Callable[[RpcContext, JsonValue | None], JsonValue]


class ServiceRegistry:
    """Explicit method allowlist; vertical slices register one typed handler at a time."""

    def __init__(self) -> None:
        self._handlers: dict[str, RpcHandler] = {}

    def register(self, method: str, handler: RpcHandler) -> None:
        if method in self._handlers:
            raise ValueError("service method is already registered")
        self._handlers[method] = handler

    def dispatch(self, method: str, context: RpcContext, params: JsonValue | None) -> JsonValue:
        handler = self._handlers.get(method)
        if handler is None:
            raise RpcServiceError("METHOD_NOT_FOUND", "The requested Core method was not found.")
        return handler(context, params)
