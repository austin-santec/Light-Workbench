"""Thread-safe in-memory collection for optional diagnostic hardware traces."""

from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from domain.diagnostic_trace import DiagnosticTraceEvent


class DiagnosticTraceRecorder:
    """Collect trace events without writing files or affecting hardware calls."""

    def __init__(self, application_version: str):
        self.session_id = uuid4().hex
        self.started_at = self._now()
        self.application_version = application_version
        self._events: list[DiagnosticTraceEvent] = []
        self._lock = Lock()
        self._metadata = {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "application_version": application_version,
        }

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def record(self, values: dict[str, object]) -> None:
        """Store one event; tracing must never interrupt a hardware operation."""
        try:
            metadata_values = {
                key: values[key]
                for key in ("meter_description", "meter_serial")
                if values.get(key) not in (None, "")
            }
            if metadata_values:
                self.update_metadata(**metadata_values)
            event = DiagnosticTraceEvent.from_mapping(values, self.session_id)
            with self._lock:
                self._events.append(event)
        except Exception:
            # Optional diagnostics cannot be allowed to change the measurement
            # path if a malformed callback payload is ever produced.
            return

    def update_metadata(self, **values: object) -> None:
        """Add session-level device metadata after the meter connects."""
        with self._lock:
            self._metadata.update(values)

    def events(self) -> tuple[DiagnosticTraceEvent, ...]:
        """Return a stable snapshot safe for export from the UI thread."""
        with self._lock:
            return tuple(self._events)

    def metadata(self) -> dict[str, object]:
        """Return a copy of session metadata safe for export."""
        with self._lock:
            values = dict(self._metadata)
        values.setdefault("event_count", len(self.events()))
        values.setdefault("exported_at", self._now())
        return values

    def clear(self) -> None:
        """Discard the current session's in-memory events."""
        with self._lock:
            self._events.clear()


__all__ = ["DiagnosticTraceRecorder"]
