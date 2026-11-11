"""Persisted switch-test intervals and honest timing summaries."""

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID
from collections.abc import Iterable

from domain.database_records import RunRecord, require_positive, require_utc, utc_now


SESSION_END_REASONS = {"completed", "stopped", "failed", "interrupted"}
SESSION_STALE_SECONDS = 90


@dataclass(frozen=True)
class RunSessionCheckpoint:
    run_id: int
    client_session_uuid: UUID
    checkpoint_at_utc: datetime
    active_duration_ms: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "checkpoint_at_utc",
            require_utc(self.checkpoint_at_utc, "Timing checkpoint"),
        )

    def validate(self) -> None:
        require_positive(self.run_id, "Run ID")
        require_utc(self.checkpoint_at_utc, "Timing checkpoint")
        if not isinstance(self.client_session_uuid, UUID):
            raise ValueError("A timing session UUID is required")
        if isinstance(self.active_duration_ms, bool) or not isinstance(self.active_duration_ms, int):
            raise ValueError("Active duration must be whole milliseconds")
        if self.active_duration_ms < 0:
            raise ValueError("Active duration cannot be negative")


@dataclass(frozen=True)
class RunSessionRecord:
    session_id: int
    run_id: int
    client_session_uuid: UUID
    started_at_utc: datetime
    ended_at_utc: datetime | None
    active_duration_ms: int
    last_checkpoint_at_utc: datetime
    end_reason: str | None
    timing_quality: str


def apply_checkpoint(
    session: RunSessionRecord,
    checkpoint: RunSessionCheckpoint,
    end_reason: str | None = None,
) -> RunSessionRecord:
    """Absolute counters make retries/late heartbeats non-additive."""
    checkpoint.validate()
    if (session.run_id, session.client_session_uuid) != (
        checkpoint.run_id, checkpoint.client_session_uuid
    ):
        raise ValueError("Timing checkpoint belongs to another run/session")
    if end_reason is not None and end_reason not in SESSION_END_REASONS:
        raise ValueError("Invalid timing session end reason")
    if checkpoint.checkpoint_at_utc < session.started_at_utc:
        raise ValueError("Timing checkpoint precedes session start")
    if session.ended_at_utc is not None:
        return session
    latest = max(session.last_checkpoint_at_utc, checkpoint.checkpoint_at_utc)
    return replace(
        session,
        active_duration_ms=max(session.active_duration_ms, checkpoint.active_duration_ms),
        last_checkpoint_at_utc=latest,
        ended_at_utc=latest if end_reason else None,
        end_reason=end_reason,
    )


def interrupt_session(session: RunSessionRecord) -> RunSessionRecord:
    """Close only at the last durable checkpoint, never at recovery time."""
    if session.ended_at_utc is not None:
        return session
    return replace(
        session,
        ended_at_utc=session.last_checkpoint_at_utc,
        end_reason="interrupted",
        timing_quality=("partial" if session.timing_quality == "partial" else "checkpoint_estimate"),
    )


@dataclass(frozen=True)
class RunTimingSummary:
    session_count: int
    active_duration_ms: int | None
    elapsed_ms: int
    stopped_ms: int | None
    timing_quality: str


def summarize_run_timing(
    run: RunRecord,
    sessions: Iterable[RunSessionRecord],
    now: datetime | None = None,
) -> RunTimingSummary:
    """No sessions means unavailable, not zero or a reconstructed duration."""
    sessions = tuple(sessions)
    if any(item.run_id != run.run_id for item in sessions):
        raise ValueError("Timing history contains another run")
    end = run.run_ended_at_utc or now or utc_now()
    elapsed = max(0, int((end - run.run_started_at_utc).total_seconds() * 1000))
    if not sessions:
        return RunTimingSummary(0, None, elapsed, None, "unavailable")
    active = sum(item.active_duration_ms for item in sessions)
    if any(item.timing_quality == "partial" for item in sessions):
        quality = "partial"
    elif any(item.timing_quality == "checkpoint_estimate" for item in sessions):
        quality = "checkpoint_estimate"
    elif any(item.ended_at_utc is None for item in sessions):
        quality = "provisional"
    else:
        quality = "confirmed"
    stopped = max(0, elapsed - active) if quality == "confirmed" else None
    return RunTimingSummary(len(sessions), active, elapsed, stopped, quality)


def session_interval_union_ms(sessions: Iterable[RunSessionRecord]) -> int:
    """Chronological covered intervals, not summed station/testing effort."""
    intervals = sorted(
        (item.started_at_utc, item.ended_at_utc or item.last_checkpoint_at_utc)
        for item in sessions
    )
    total = 0
    start = end = None
    for next_start, next_end in intervals:
        if start is None:
            start, end = next_start, next_end
        elif next_start <= end:
            end = max(end, next_end)
        else:
            total += int((end - start).total_seconds() * 1000)
            start, end = next_start, next_end
    if start is not None:
        total += int((end - start).total_seconds() * 1000)
    return max(0, total)
