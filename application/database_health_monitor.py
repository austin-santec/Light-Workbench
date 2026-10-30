"""Non-blocking database availability monitoring for the desktop UI."""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from domain.support_events import SupportEventCategory, SupportLogLevel
from infrastructure.database.connection import (
    DatabaseConnectionError,
    DatabaseErrorCategory,
    classify_database_exception,
)


DATABASE_HEALTH_INTERVAL_MS = 60_000
DATABASE_HEALTH_MESSAGE_LIMIT = 300
DATABASE_HEALTH_SOURCES = frozenset({"startup", "periodic", "manual", "operation"})


class DatabaseHealthState(str, Enum):
    """Operator-visible state of the most recently verified database health."""

    DISABLED = "disabled"
    CHECKING = "checking"
    READY = "ready"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class DatabaseHealthSnapshot:
    """Immutable state published from the monitor to presentation code."""

    state: DatabaseHealthState
    checked_at_utc: datetime | None = None
    last_success_at_utc: datetime | None = None
    elapsed_ms: int | None = None
    current_schema_version: int | None = None
    expected_schema_version: int | None = None
    error_category: str = ""
    message: str = ""


def _run_daemon(task: Callable[[], None]):
    """Run one bounded probe without making application shutdown wait for it."""

    thread = threading.Thread(
        target=task,
        name="light-workbench-database-health",
        daemon=True,
    )
    thread.start()
    return thread


class DatabaseHealthMonitor(QObject):
    """Schedule independent read-only probes and publish UI-safe state changes."""

    state_changed = pyqtSignal(object)
    _probe_finished = pyqtSignal(int, int, str, object)

    def __init__(
        self,
        *,
        enabled: bool,
        probe: Callable[[], object] | None,
        support_logger=None,
        interval_ms: int = DATABASE_HEALTH_INTERVAL_MS,
        task_runner: Callable[[Callable[[], None]], object] | None = None,
        now: Callable[[], datetime] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.enabled = bool(enabled and probe is not None)
        self._probe = probe
        self._support_logger = support_logger
        self._task_runner = task_runner or _run_daemon
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._snapshot = DatabaseHealthSnapshot(
            DatabaseHealthState.DISABLED,
            message=(
                "Database monitoring is disabled."
                if not self.enabled
                else "Database availability has not been checked yet."
            ),
        )
        self._stable_state = DatabaseHealthState.DISABLED
        self._started = False
        self._stopped = False
        self._in_flight = False
        self._pending_source = ""
        self._generation = 0
        self._operation_revision = 0
        self._timer = QTimer(self)
        self._timer.setInterval(max(1, int(interval_ms)))
        self._timer.timeout.connect(self._request_periodic_check)
        self._probe_finished.connect(self._handle_probe_finished)

    @property
    def snapshot(self) -> DatabaseHealthSnapshot:
        return self._snapshot

    @property
    def interval_ms(self) -> int:
        return self._timer.interval()

    @property
    def check_in_progress(self) -> bool:
        return self._in_flight

    @property
    def timer_active(self) -> bool:
        return self._timer.isActive()

    def start(self) -> None:
        """Start periodic monitoring and request the non-blocking warm-up probe."""

        if self._started or self._stopped:
            return
        self._started = True
        if not self.enabled:
            self._publish(
                replace(
                    self._snapshot,
                    state=DatabaseHealthState.DISABLED,
                    message="Database monitoring is disabled.",
                )
            )
            return
        self._timer.start()
        self.request_check("startup")

    def request_check(self, source: str = "manual") -> bool:
        """Request one probe; coalesce overlapping work without blocking Qt."""

        source = str(source or "manual").strip().lower()
        if source not in DATABASE_HEALTH_SOURCES - {"operation"}:
            raise ValueError("Unsupported database health-check source")
        if self._stopped or not self.enabled:
            return False
        if self._in_flight:
            if source == "manual":
                self._pending_source = "manual"
            self._record_request(source, coalesced=True)
            return False

        self._in_flight = True
        self._generation += 1
        generation = self._generation
        operation_revision = self._operation_revision
        self._record_request(source, coalesced=False)
        self._publish(
            replace(
                self._snapshot,
                state=DatabaseHealthState.CHECKING,
                message="Checking database availability.",
                error_category="",
            )
        )
        try:
            self._task_runner(
                lambda: self._execute_probe(generation, operation_revision, source)
            )
        except Exception as error:
            self._complete_runner_failure(generation, operation_revision, source, error)
        return True

    def report_operation_result(self, result) -> None:
        """Publish an authoritative readiness result from a real operation."""

        if self._stopped or not self.enabled or result is None:
            return
        self._operation_revision += 1
        self._apply_result(result, "operation")

    def report_operation_ready(self) -> None:
        """Record that a real database workflow completed successfully."""

        if self._stopped or not self.enabled:
            return
        self._operation_revision += 1
        checked_at = self._utc_now()
        previous = self._stable_state
        snapshot = replace(
            self._snapshot,
            state=DatabaseHealthState.READY,
            checked_at_utc=checked_at,
            last_success_at_utc=checked_at,
            elapsed_ms=None,
            error_category="",
            message="A database operation completed successfully.",
        )
        self._stable_state = DatabaseHealthState.READY
        self._publish(snapshot)
        self._record_state_change(previous, DatabaseHealthState.READY, "operation")

    def stop(self) -> None:
        """Stop scheduling work and ignore any late daemon-probe result."""

        if self._stopped:
            return
        self._stopped = True
        self._timer.stop()
        self._pending_source = ""
        self._operation_revision += 1
        self._record(
            "database.health_monitor_stopped",
            status="stopped",
            database_health_state=self._stable_state.value,
        )

    def _request_periodic_check(self) -> None:
        self.request_check("periodic")

    def _execute_probe(
        self,
        generation: int,
        operation_revision: int,
        source: str,
    ) -> None:
        try:
            result = self._probe()
        except Exception as error:
            result = self._exception_result(error)
        try:
            self._probe_finished.emit(
                generation,
                operation_revision,
                source,
                result,
            )
        except RuntimeError:
            # The owning Qt object may already be gone during process shutdown.
            return

    def _complete_runner_failure(
        self,
        generation: int,
        operation_revision: int,
        source: str,
        error: Exception,
    ) -> None:
        self._handle_probe_finished(
            generation,
            operation_revision,
            source,
            self._exception_result(error),
        )

    def _handle_probe_finished(
        self,
        generation: int,
        operation_revision: int,
        source: str,
        result,
    ) -> None:
        if generation != self._generation:
            return
        self._in_flight = False
        if not self._stopped and operation_revision == self._operation_revision:
            self._apply_result(result, source)
        if self._stopped:
            return
        pending_source = self._pending_source
        self._pending_source = ""
        if pending_source:
            QTimer.singleShot(0, lambda: self.request_check(pending_source))

    def _apply_result(self, result, source: str) -> None:
        ready = bool(getattr(result, "ready", False))
        checked_at = self._utc_now()
        elapsed_ms = self._bounded_int(getattr(result, "elapsed_ms", None))
        current_schema = self._bounded_int(
            getattr(result, "current_schema_version", None)
        )
        expected_schema = self._bounded_int(
            getattr(result, "expected_schema_version", None)
        )
        category = getattr(result, "category", None)
        category_value = getattr(category, "value", category) or ""
        message = self._bounded_message(
            getattr(result, "operator_message", "")
            or (
                "The database connection and schema are ready."
                if ready
                else "The database is unavailable."
            )
        )
        previous = self._stable_state
        state = (
            DatabaseHealthState.READY
            if ready
            else DatabaseHealthState.UNAVAILABLE
        )
        snapshot = DatabaseHealthSnapshot(
            state=state,
            checked_at_utc=checked_at,
            last_success_at_utc=(
                checked_at if ready else self._snapshot.last_success_at_utc
            ),
            elapsed_ms=elapsed_ms,
            current_schema_version=current_schema,
            expected_schema_version=expected_schema,
            error_category="" if ready else str(category_value)[:80],
            message=message,
        )
        self._stable_state = state
        self._publish(snapshot)
        changed = previous != state
        if source in {"startup", "manual"} or changed:
            self._record(
                "database.health_check_completed",
                level=(SupportLogLevel.INFO if ready else SupportLogLevel.WARNING),
                status="ready" if ready else "unavailable",
                health_check_source=source,
                database_health_state=state.value,
                database_error_category=snapshot.error_category,
                database_schema_version=current_schema,
                database_expected_schema_version=expected_schema,
                elapsed_ms=elapsed_ms,
                details=message,
            )
        self._record_state_change(previous, state, source)

    def _record_request(self, source: str, *, coalesced: bool) -> None:
        if source not in {"startup", "manual"} and not coalesced:
            return
        self._record(
            "database.health_check_requested",
            status="coalesced" if coalesced else "requested",
            health_check_source=source,
            request_coalesced=coalesced,
            database_health_state=self._stable_state.value,
        )

    def _record_state_change(
        self,
        previous: DatabaseHealthState,
        current: DatabaseHealthState,
        source: str,
    ) -> None:
        if previous == current:
            return
        self._record(
            "database.health_state_changed",
            level=(
                SupportLogLevel.WARNING
                if current == DatabaseHealthState.UNAVAILABLE
                else SupportLogLevel.INFO
            ),
            status=current.value,
            health_check_source=source,
            previous_health_state=previous.value,
            database_health_state=current.value,
        )

    def _record(self, event: str, *, level=SupportLogLevel.INFO, **fields) -> None:
        if self._support_logger is None:
            return
        self._support_logger.record(
            SupportEventCategory.CONNECTION,
            event,
            level=level,
            **fields,
        )

    def _publish(self, snapshot: DatabaseHealthSnapshot) -> None:
        self._snapshot = snapshot
        self.state_changed.emit(snapshot)

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _bounded_int(value) -> int | None:
        if value is None:
            return None
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _bounded_message(value) -> str:
        return str(value or "").strip()[:DATABASE_HEALTH_MESSAGE_LIMIT]

    @staticmethod
    def _exception_result(error: Exception):
        if isinstance(error, DatabaseConnectionError):
            classified = error
        else:
            classified = classify_database_exception(error)

        @dataclass(frozen=True)
        class FailedResult:
            ready: bool = False
            category: DatabaseErrorCategory = classified.category
            operator_message: str = classified.operator_message
            current_schema_version: int | None = None
            expected_schema_version: int | None = None
            elapsed_ms: int = 0

        return FailedResult()


__all__ = [
    "DATABASE_HEALTH_INTERVAL_MS",
    "DatabaseHealthMonitor",
    "DatabaseHealthSnapshot",
    "DatabaseHealthState",
]
