"""Non-blocking orchestration for always-on engineering support logging."""

import queue
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from config.app_config import (
    DEFAULT_PATHS,
    SUPPORT_LOG_MAX_FILE_BYTES,
    SUPPORT_LOG_MAX_TOTAL_BYTES,
    SUPPORT_LOG_QUEUE_CAPACITY,
    SUPPORT_LOG_RETENTION_DAYS,
)
from config.app_info import APP_NAME, APP_VERSION
from domain.support_events import (
    ALLOWED_EVENT_FIELDS,
    SUPPORT_LOG_SCHEMA_VERSION,
    SupportEvent,
    SupportEventCategory,
    SupportLogLevel,
    utc_timestamp,
)
from infrastructure.support_log_writer import SupportLogWriter


@dataclass(frozen=True)
class SupportLoggingStatus:
    """Snapshot displayed by the Logging Status dialog."""

    healthy: bool
    active_folder: str
    active_filename: str
    app_instance_id: str
    schema_version: int
    queue_depth: int
    dropped_event_count: int
    last_writer_error: str
    retention_days: int | None
    max_file_bytes: int
    max_total_bytes: int
    fallback_active: bool
    memory_event_count: int
    total_size_bytes: int = 0
    over_size_limit: bool = False


@dataclass(frozen=True)
class WorkflowContext:
    """Correlation information shared by one operator workflow."""

    workflow_type: str
    workflow_id: str


class TraceEventFanout:
    """Deliver one hardware trace to independent, failure-isolated subscribers."""

    def __init__(self):
        self._subscribers = []
        self._lock = threading.RLock()

    def subscribe(self, callback: Callable[[dict], None]) -> None:
        if callback is None:
            return
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[dict], None]) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def __call__(self, payload: dict) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers)
        for callback in subscribers:
            try:
                callback(dict(payload))
            except Exception:
                continue


class SupportLoggingService:
    """Accept structured events without blocking UI or hardware threads."""

    _STOP = object()

    def __init__(
        self,
        writer: SupportLogWriter,
        *,
        application_name: str = APP_NAME,
        application_version: str = APP_VERSION,
        queue_capacity: int = SUPPORT_LOG_QUEUE_CAPACITY,
        local_now: Callable[[], datetime] | None = None,
        app_instance_id: str | None = None,
    ):
        self.writer = writer
        self.application_name = application_name
        self.application_version = application_version
        self.app_instance_id = app_instance_id or uuid.uuid4().hex
        self.local_now = local_now or (lambda: datetime.now().astimezone())
        self._queue = queue.Queue(maxsize=max(1, int(queue_capacity)))
        self._dropped_count = 0
        self._reported_dropped_count = 0
        self._drop_lock = threading.Lock()
        self._closed = False
        self._listener = threading.Thread(
            target=self._listen,
            name="light-workbench-support-logging",
            daemon=True,
        )
        self._listener.start()
        self.trace_fanout = TraceEventFanout()
        self.trace_fanout.subscribe(self.record_hardware_trace)

    @classmethod
    def create_default(cls) -> "SupportLoggingService":
        return cls(
            SupportLogWriter(
                DEFAULT_PATHS.support_log_root,
                DEFAULT_PATHS.support_log_fallback_root,
            )
        )

    def new_workflow(self, workflow_type: str) -> WorkflowContext:
        return WorkflowContext(
            workflow_type=str(workflow_type),
            workflow_id="wf-" + uuid.uuid4().hex,
        )

    @staticmethod
    def new_operation_id(prefix: str = "op") -> str:
        return "%s-%s" % (prefix, uuid.uuid4().hex)

    def record(
        self,
        category: SupportEventCategory | str,
        event: str,
        *,
        level: SupportLogLevel | str = SupportLogLevel.INFO,
        workflow_id: str = "",
        operation_id: str = "",
        **fields,
    ) -> bool:
        """Queue one event and return without propagating logging failures."""
        if self._closed:
            return False
        try:
            category_value = (
                category
                if isinstance(category, SupportEventCategory)
                else SupportEventCategory(str(category))
            )
            level_value = (
                level if isinstance(level, SupportLogLevel) else SupportLogLevel(str(level))
            )
            allowed = {
                key: value for key, value in fields.items() if key in ALLOWED_EVENT_FIELDS
            }
            current = self.local_now()
            support_event = SupportEvent(
                timestamp_utc=utc_timestamp(),
                local_date=current.date().isoformat(),
                level=level_value,
                category=category_value,
                event=str(event),
                application_name=self.application_name,
                application_version=self.application_version,
                app_instance_id=self.app_instance_id,
                workflow_id=str(workflow_id or ""),
                operation_id=str(operation_id or ""),
                fields=allowed,
            )
            return self._enqueue(support_event, level_value)
        except Exception:
            return False

    def _enqueue(self, support_event: SupportEvent, level: SupportLogLevel) -> bool:
        try:
            self._queue.put_nowait(support_event)
            return True
        except queue.Full:
            with self._drop_lock:
                self._dropped_count += 1
            if level not in (SupportLogLevel.WARNING, SupportLogLevel.ERROR, SupportLogLevel.CRITICAL):
                return False
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                self._queue.put_nowait(support_event)
                return True
            except (queue.Empty, queue.Full):
                return False

    def _listen(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is self._STOP:
                    return
                if isinstance(item, tuple) and item[0] == "flush":
                    self.writer.flush()
                    item[1].set()
                    continue
                self._write_dropped_event_if_needed()
                self.writer.write(item.to_dict())
            except Exception:
                # The listener is the final safety boundary. Logging failures
                # cannot be allowed to terminate the queue consumer.
                continue
            finally:
                self._queue.task_done()

    def _write_dropped_event_if_needed(self) -> None:
        with self._drop_lock:
            dropped = self._dropped_count
            if dropped <= self._reported_dropped_count:
                return
            newly_dropped = dropped - self._reported_dropped_count
            self._reported_dropped_count = dropped
        current = self.local_now()
        event = SupportEvent(
            timestamp_utc=utc_timestamp(),
            local_date=current.date().isoformat(),
            level=SupportLogLevel.WARNING,
            category=SupportEventCategory.LOGGING,
            event="logging.events_dropped",
            application_name=self.application_name,
            application_version=self.application_version,
            app_instance_id=self.app_instance_id,
            fields={
                "dropped_event_count": newly_dropped,
                "details": "The bounded support-log queue overflowed.",
            },
        )
        self.writer.write(event.to_dict())

    def record_exception(
        self,
        event: str,
        error_type,
        error,
        traceback_object,
        *,
        category=SupportEventCategory.APPLICATION,
    ) -> None:
        stack = "".join(
            traceback.format_exception(error_type, error, traceback_object)
        )
        self.record(
            category,
            event,
            level=SupportLogLevel.CRITICAL,
            error_type=getattr(error_type, "__name__", str(error_type)),
            error_message=str(error),
            stack_trace=stack,
            status="unhandled",
        )

    def record_hardware_trace(self, payload: dict) -> None:
        """Translate an OP815/switch trace payload into the global schema."""
        mapping = {
            "method": "acquisition_method",
            "channel": "logical_channel",
            "meter_serial": "device_serial",
            "meter_description": "model",
            "error": "error_message",
        }
        fields = {}
        for key, value in dict(payload or {}).items():
            target = mapping.get(key, key)
            if target in ALLOWED_EVENT_FIELDS:
                fields[target] = value
        fields.setdefault("device_category", payload.get("device_category", "power_meter"))
        self.record(
            SupportEventCategory.HARDWARE,
            "hardware.%s" % str(payload.get("event", "trace")),
            level=(
                SupportLogLevel.ERROR
                if str(payload.get("status", "")).lower() in ("error", "exception", "failed")
                else SupportLogLevel.WARNING
                if str(payload.get("status", "")).lower() == "warning"
                else SupportLogLevel.INFO
            ),
            workflow_id=str(payload.get("workflow_id", "") or ""),
            operation_id=str(
                payload.get("operation_id")
                or payload.get("measurement_id")
                or ""
            ),
            **fields,
        )

    def flush(self, timeout: float = 2.0) -> bool:
        if self._closed:
            return True
        marker = threading.Event()
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            try:
                self._queue.put_nowait(("flush", marker))
                return marker.wait(max(0.0, deadline - time.monotonic()))
            except queue.Full:
                time.sleep(0.01)
        return False

    def shutdown(self, timeout: float = 2.0) -> None:
        if self._closed:
            return
        self.record(SupportEventCategory.APPLICATION, "application.shutdown")
        self.flush(timeout=max(0.1, timeout * 0.6))
        self._closed = True
        try:
            self._queue.put_nowait(self._STOP)
        except queue.Full:
            return
        self._listener.join(timeout=max(0.1, timeout * 0.4))
        self.writer.close()

    def status(self) -> SupportLoggingStatus:
        active_root = self.writer.active_root
        active_path = self.writer.active_path
        with self._drop_lock:
            dropped = self._dropped_count
        return SupportLoggingStatus(
            healthy=self.writer.healthy,
            active_folder=str(active_root or self.writer.preferred_root),
            active_filename=active_path.name if active_path else "Not created yet",
            app_instance_id=self.app_instance_id,
            schema_version=SUPPORT_LOG_SCHEMA_VERSION,
            queue_depth=self._queue.qsize(),
            dropped_event_count=dropped,
            last_writer_error=self.writer.last_error,
            retention_days=SUPPORT_LOG_RETENTION_DAYS,
            max_file_bytes=SUPPORT_LOG_MAX_FILE_BYTES,
            max_total_bytes=SUPPORT_LOG_MAX_TOTAL_BYTES,
            fallback_active=self.writer.fallback_active,
            memory_event_count=len(self.writer.memory_events),
            total_size_bytes=getattr(self.writer, "total_size_bytes", 0),
            over_size_limit=getattr(self.writer, "over_size_limit", False),
        )


_global_service: SupportLoggingService | None = None


def set_support_logging_service(service: SupportLoggingService | None) -> None:
    global _global_service
    _global_service = service


def get_support_logging_service() -> SupportLoggingService | None:
    return _global_service


def support_event(category, event, **fields) -> bool:
    service = get_support_logging_service()
    return service.record(category, event, **fields) if service is not None else False


def install_exception_hooks(service: SupportLoggingService):
    """Install preserving main- and worker-thread exception hooks."""
    previous_sys_hook = sys.excepthook
    previous_thread_hook = getattr(threading, "excepthook", None)

    def system_hook(error_type, error, traceback_object):
        service.record_exception(
            "application.unhandled_exception",
            error_type,
            error,
            traceback_object,
        )
        service.flush(0.5)
        previous_sys_hook(error_type, error, traceback_object)

    def thread_hook(arguments):
        service.record_exception(
            "application.worker_unhandled_exception",
            arguments.exc_type,
            arguments.exc_value,
            arguments.exc_traceback,
        )
        if previous_thread_hook is not None:
            previous_thread_hook(arguments)

    sys.excepthook = system_hook
    if previous_thread_hook is not None:
        threading.excepthook = thread_hook
    return previous_sys_hook, previous_thread_hook


__all__ = [
    "SupportLoggingService",
    "SupportLoggingStatus",
    "TraceEventFanout",
    "WorkflowContext",
    "get_support_logging_service",
    "install_exception_hooks",
    "set_support_logging_service",
    "support_event",
]
