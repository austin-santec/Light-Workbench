"""Operation-scoped metrics for database-backed run loading.

This module intentionally contains measurement only. It does not change query
selection, transaction boundaries, or connection lifetime.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Mapping


_current_metrics: ContextVar["DatabaseLoadMetrics | None"] = ContextVar(
    "light_workbench_database_load_metrics",
    default=None,
)

_COUNT_KEYS = (
    "database_connection_count",
    "database_transaction_count",
    "related_run_count",
    "measurement_history_count",
    "projection_measurement_row_count",
    "projection_measurement_query_count",
    "current_measurement_count",
    "replacement_history_count",
    "designated_spare_event_count",
    "active_spare_count",
    "persisted_analysis_count",
    "persisted_recommendation_count",
)


@dataclass
class DatabaseLoadMetrics:
    """Mutable collector scoped to one logical database load operation."""

    source: str
    operation_id: str = field(
        default_factory=lambda: "db-load-" + uuid.uuid4().hex
    )
    started_at: float = field(default_factory=time.perf_counter)
    stage_timings_ms: dict[str, int] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    current_stage: str = ""
    failure_stage: str = ""
    completed_at: float | None = None

    def __post_init__(self):
        for key in _COUNT_KEYS:
            self.counts.setdefault(key, 0)

    def begin_stage(self, name: str) -> float:
        """Mark a stage start and return its monotonic timestamp."""
        self.current_stage = str(name)
        return time.perf_counter()

    def end_stage(self, name: str, started_at: float) -> None:
        """Accumulate one stage duration in milliseconds."""
        self.add_stage_elapsed(name, time.perf_counter() - started_at)
        self.current_stage = ""

    def add_stage_elapsed(self, name: str, elapsed_seconds: float) -> None:
        """Accumulate an already measured stage duration."""
        elapsed = max(0.0, float(elapsed_seconds))
        key = str(name)
        self.stage_timings_ms[key] = self.stage_timings_ms.get(key, 0) + int(
            elapsed * 1000
        )

    def set_count(self, name: str, value: int) -> None:
        self.counts[str(name)] = max(0, int(value))

    def increment(self, name: str, amount: int = 1) -> None:
        key = str(name)
        self.counts[key] = self.counts.get(key, 0) + int(amount)

    def finish(self) -> None:
        if self.completed_at is None:
            self.completed_at = time.perf_counter()

    @property
    def elapsed_ms(self) -> int:
        end = self.completed_at or time.perf_counter()
        return max(0, int((end - self.started_at) * 1000))

    def summary(self) -> "DatabaseLoadSummary":
        """Return an immutable snapshot suitable for a loaded context."""
        return DatabaseLoadSummary(
            operation_id=self.operation_id,
            source=self.source,
            elapsed_ms=self.elapsed_ms,
            stage_timings_ms=dict(self.stage_timings_ms),
            counts=dict(self.counts),
            failure_stage=self.failure_stage,
        )


@dataclass(frozen=True)
class DatabaseLoadSummary:
    """Immutable load metrics attached to a loaded database context."""

    operation_id: str
    source: str
    elapsed_ms: int
    stage_timings_ms: Mapping[str, int]
    counts: Mapping[str, int]
    failure_stage: str = ""

    def support_fields(self) -> dict[str, object]:
        """Return fields used by the support-event allowlist."""
        fields: dict[str, object] = {
            "load_source": self.source,
            "stage_timings_ms": dict(self.stage_timings_ms),
            "elapsed_ms": self.elapsed_ms,
        }
        fields.update(self.counts)
        if self.failure_stage:
            fields["failure_stage"] = self.failure_stage
        return fields


def current_metrics() -> DatabaseLoadMetrics | None:
    """Return the collector active in the current execution context."""
    return _current_metrics.get()


class activate_metrics:
    """Context manager used by the workflow while loading one database run."""

    def __init__(self, metrics: DatabaseLoadMetrics):
        self.metrics = metrics
        self._token = None

    def __enter__(self):
        self._token = _current_metrics.set(self.metrics)
        return self.metrics

    def __exit__(self, _exception_type, _exception, _traceback):
        if self._token is not None:
            _current_metrics.reset(self._token)
        return False


def record_connection() -> None:
    """Increment the active load's physical connection count, if any."""
    metrics = current_metrics()
    if metrics is not None:
        metrics.increment("database_connection_count")


def record_transaction() -> None:
    """Increment the active load's transaction count, if any."""
    metrics = current_metrics()
    if metrics is not None:
        metrics.increment("database_transaction_count")


@contextmanager
def measure_active_stage(name: str):
    """Measure infrastructure work against the active logical load."""
    metrics = current_metrics()
    if metrics is None:
        yield
        return
    started = time.perf_counter()
    try:
        yield
    except BaseException:
        metrics.failure_stage = str(name)
        raise
    finally:
        metrics.add_stage_elapsed(name, time.perf_counter() - started)


__all__ = [
    "DatabaseLoadMetrics",
    "DatabaseLoadSummary",
    "activate_metrics",
    "current_metrics",
    "measure_active_stage",
    "record_connection",
    "record_transaction",
]
