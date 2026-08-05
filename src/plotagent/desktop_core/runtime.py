"""Synchronous desktop Core control loop and built-in control services."""

from __future__ import annotations

import json
import re
import sys
import threading
from collections.abc import Callable
from typing import BinaryIO, Final, TextIO

from plotagent import __version__
from plotagent.desktop_core.protocol import (
    CORE_PROTOCOL_VERSION,
    DESKTOP_API_VERSION,
    JsonValue,
    ProtocolFault,
    ProtocolWriter,
    RequestCache,
    RpcRequest,
    parse_request,
    read_frame,
)
from plotagent.desktop_core.services import RpcContext, RpcServiceError, ServiceRegistry
from plotagent.desktop_core.tasks import BoundedWorkerExecutor, TaskControlError, TaskRegistry

_SAFE_CODE: Final = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

type ConfigureServices = Callable[[ServiceRegistry, TaskRegistry, BoundedWorkerExecutor], None]


class SafeStderrLogger:
    """Write allowlisted metadata only; never accept exception text or request data."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._lock = threading.Lock()

    def event(self, event_code: str, *, error_code: str | None = None) -> None:
        if _SAFE_CODE.fullmatch(event_code) is None:
            event_code = "DESKTOP_CORE_LOG_SCHEMA_VIOLATION"
        record = {
            "event_code": event_code,
            "protocol_version": CORE_PROTOCOL_VERSION,
            **(
                {"error_code": error_code}
                if error_code is not None and _SAFE_CODE.fullmatch(error_code) is not None
                else {}
            ),
        }
        encoded = json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        with self._lock:
            self._stream.write(encoded + "\n")
            self._stream.flush()


class CoreRuntime:
    """Own the stdio transport, request cache, task registry, and worker capacity."""

    def __init__(
        self,
        *,
        stdin: BinaryIO | None = None,
        stdout: BinaryIO | None = None,
        stderr: TextIO | None = None,
        heartbeat_interval_seconds: float = 2.5,
        configure_services: ConfigureServices | None = None,
    ) -> None:
        if heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat interval must be positive")
        self._stdin = stdin or sys.stdin.buffer
        self._writer = ProtocolWriter(stdout or sys.stdout.buffer)
        self.logger = SafeStderrLogger(stderr or sys.stderr)
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_sequence = 0
        self._initialized = False
        self._shutdown_after_response = False
        self._closed = False
        self._request_cache = RequestCache()
        self.workers = BoundedWorkerExecutor(max_workers=2, maximum_pending=4)
        self.tasks = TaskRegistry(self._task_notification)
        self.services = ServiceRegistry()
        self._register_builtin_services()
        if configure_services is not None:
            configure_services(self.services, self.tasks, self.workers)

    def run(self) -> int:
        self.logger.event("DESKTOP_CORE_STARTED")
        try:
            while not self._shutdown_after_response:
                frame = read_frame(self._stdin)
                if frame.fault is not None:
                    self._write_fault(frame.fault)
                    if frame.eof:
                        break
                    continue
                if frame.eof:
                    break
                if frame.payload is None:
                    continue
                self._process_payload(frame.payload)
        except (BrokenPipeError, OSError):
            self.logger.event("DESKTOP_CORE_TRANSPORT_CLOSED")
        finally:
            self.close()
        return 0

    def request_shutdown(self) -> None:
        self._shutdown_after_response = True
        self._heartbeat_stop.set()
        self.tasks.cancel_all()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._heartbeat_stop.set()
        heartbeat = self._heartbeat_thread
        if heartbeat is not None and heartbeat is not threading.current_thread():
            heartbeat.join(timeout=max(1.0, self._heartbeat_interval_seconds + 0.25))
        self.tasks.cancel_all()
        self.workers.shutdown()
        self.logger.event("DESKTOP_CORE_STOPPED")

    def _process_payload(self, payload: bytes) -> None:
        try:
            request = parse_request(payload)
        except ProtocolFault as fault:
            self._write_fault(fault)
            return

        try:
            replay = self._request_cache.lookup(request)
        except ProtocolFault as fault:
            self._write_fault(fault)
            return
        if replay is not None:
            self._writer.replay(replay)
            return

        encoded, succeeded = self._dispatch(request)
        self._request_cache.store(request, encoded)
        if (
            succeeded
            and request.method in {"system.initialize", "system.hello"}
            and self._initialized
        ):
            self._writer.notification("system.ready", self._ready_result())
            self._start_heartbeat()

    def _dispatch(self, request: RpcRequest) -> tuple[bytes, bool]:
        context = RpcContext(request_id=request.request_id, tasks=self.tasks, workers=self.workers)
        try:
            if not self._initialized and not request.method.startswith("system."):
                raise RpcServiceError(
                    "CORE_NOT_INITIALIZED",
                    "The Core handshake was not completed.",
                )
            result = self.services.dispatch(request.method, context, request.params)
            return self._writer.success(request.request_id, result), True
        except (RpcServiceError, TaskControlError) as error:
            return self._writer.error(request.request_id, error.code, error.message), False
        except ProtocolFault as fault:
            return self._writer.error(request.request_id, fault.code, fault.message), False
        except Exception:
            self.logger.event("DESKTOP_CORE_REQUEST_FAILED", error_code="INTERNAL_ERROR")
            return (
                self._writer.error(
                    request.request_id,
                    "INTERNAL_ERROR",
                    "The Core request failed.",
                ),
                False,
            )

    def _write_fault(self, fault: ProtocolFault) -> None:
        self.logger.event("DESKTOP_CORE_PROTOCOL_REJECTED", error_code=fault.code)
        if fault.request_id is not None:
            self._writer.error(fault.request_id, fault.code, fault.message)
            return
        self._writer.notification(
            "system.protocol_error",
            {"code": fault.code, "message": fault.message},
        )

    def _register_builtin_services(self) -> None:
        self.services.register("system.initialize", self._initialize)
        self.services.register("system.hello", self._initialize)
        self.services.register("system.ping", self._ping)
        self.services.register("system.shutdown", self._shutdown)
        self.services.register("health.get", self._health)
        self.services.register("system.health", self._health)
        self.services.register("task.get_snapshot", self._task_snapshot)
        self.services.register("tasks.snapshot", self._task_snapshot)
        self.services.register("task.cancel", self._task_cancel)
        self.services.register("tasks.cancel", self._task_cancel)
        self.services.register("task.cancel_all", self._task_cancel_all)
        self.services.register("tasks.cancel_all", self._task_cancel_all)

    def _initialize(self, _context: RpcContext, params: JsonValue | None) -> JsonValue:
        values = _require_object(
            params,
            required={"protocol_version", "desktop_api_version"},
        )
        if values["protocol_version"] != CORE_PROTOCOL_VERSION:
            raise RpcServiceError(
                "PROTOCOL_VERSION_UNSUPPORTED",
                "The Core protocol version was unsupported.",
            )
        if values["desktop_api_version"] != DESKTOP_API_VERSION:
            raise RpcServiceError(
                "DESKTOP_API_VERSION_UNSUPPORTED",
                "The desktop API version was unsupported.",
            )
        self._initialized = True
        return self._ready_result()

    def _ping(self, _context: RpcContext, params: JsonValue | None) -> JsonValue:
        self._require_initialized()
        _require_empty(params)
        return {
            "status": "ok",
            "protocol_version": CORE_PROTOCOL_VERSION,
        }

    def _shutdown(self, _context: RpcContext, params: JsonValue | None) -> JsonValue:
        _require_empty(params)
        self.request_shutdown()
        return {"status": "stopping"}

    def _health(self, _context: RpcContext, params: JsonValue | None) -> JsonValue:
        self._require_initialized()
        _require_empty(params)
        snapshot = self.tasks.snapshot()
        return {
            "status": "ready",
            "protocol_version": CORE_PROTOCOL_VERSION,
            "desktop_api_version": DESKTOP_API_VERSION,
            "core_version": __version__,
            "active_task_count": snapshot["active_task_count"],
            "worker_capacity": self.workers.max_workers,
        }

    def _task_snapshot(self, _context: RpcContext, params: JsonValue | None) -> JsonValue:
        self._require_initialized()
        _require_empty(params)
        return self.tasks.snapshot()

    def _task_cancel(self, _context: RpcContext, params: JsonValue | None) -> JsonValue:
        self._require_initialized()
        values = _require_object(params, required={"task_id"})
        task_id = values["task_id"]
        if not isinstance(task_id, str):
            raise RpcServiceError("INVALID_PARAMS", "The request parameters were invalid.")
        return self.tasks.cancel(task_id)

    def _task_cancel_all(self, _context: RpcContext, params: JsonValue | None) -> JsonValue:
        self._require_initialized()
        _require_empty(params)
        return {"task_ids": list(self.tasks.cancel_all())}

    def _ready_result(self) -> dict[str, JsonValue]:
        return {
            "status": "ready",
            "protocol_version": CORE_PROTOCOL_VERSION,
            "desktop_api_version": DESKTOP_API_VERSION,
            "core_version": __version__,
        }

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise RpcServiceError("CORE_NOT_INITIALIZED", "The Core handshake was not completed.")

    def _task_notification(self, event: dict[str, JsonValue]) -> None:
        self._writer.notification("task.event", event)

    def _start_heartbeat(self) -> None:
        if self._heartbeat_thread is not None:
            return
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="plotagent-core-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.is_set():
            self._heartbeat_sequence += 1
            try:
                self._writer.notification(
                    "health.heartbeat",
                    {
                        "status": "ready",
                        "sequence": self._heartbeat_sequence,
                        "protocol_version": CORE_PROTOCOL_VERSION,
                    },
                )
            except (BrokenPipeError, OSError, ProtocolFault):
                self._heartbeat_stop.set()
                return
            if self._heartbeat_stop.wait(self._heartbeat_interval_seconds):
                return


def _require_empty(params: JsonValue | None) -> None:
    if params is not None and params != {}:
        raise RpcServiceError("INVALID_PARAMS", "The request parameters were invalid.")


def _require_object(
    params: JsonValue | None,
    *,
    required: set[str],
) -> dict[str, JsonValue]:
    if not isinstance(params, dict) or set(params) != required:
        raise RpcServiceError("INVALID_PARAMS", "The request parameters were invalid.")
    return params
