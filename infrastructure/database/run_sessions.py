"""Repository mixins for durable test sessions; all SQL stays in infrastructure."""

from datetime import datetime, timezone
from uuid import UUID

from domain.database_records import require_utc
from domain.run_sessions import (
    RunSessionCheckpoint, RunSessionRecord, SESSION_STALE_SECONDS,
    apply_checkpoint, interrupt_session,
)


class MemoryRunSessions:
    def end_test_session(self, checkpoint: RunSessionCheckpoint, end_reason: str) -> None:
        self._close_test_sessions(checkpoint.run_id, checkpoint, end_reason)

    def test_sessions_for_runs(self, run_ids: tuple[int, ...]) -> tuple[RunSessionRecord, ...]:
        with self._lock:
            return tuple(sorted(
                (s for s in self._test_sessions.values() if s.run_id in run_ids),
                key=lambda s: (s.started_at_utc, s.session_id),
            ))

    def begin_test_session(
        self, run_id: int, client_session_uuid: UUID, started_at_utc: datetime,
        *, partial: bool = False,
    ) -> RunSessionRecord:
        started = require_utc(started_at_utc, "Test session start")
        if not isinstance(client_session_uuid, UUID):
            raise ValueError("A timing session UUID is required")
        with self._lock:
            for item in self._test_sessions.values():
                if item.client_session_uuid == client_session_uuid:
                    if item.run_id != run_id:
                        raise ValueError("Timing session UUID belongs to another run")
                    return item
            run = self.runs[run_id]
            if run.completion_status != "in_progress" or started < run.run_started_at_utc:
                raise ValueError("Timing requires an in-progress run and valid start time")
            sessions = self.test_sessions_for_runs((run_id,))
            for item in sessions:
                if item.ended_at_utc is None:
                    if (started - item.last_checkpoint_at_utc).total_seconds() < SESSION_STALE_SECONDS:
                        raise ValueError("This run has a recent active timing session. Stop it or wait 90 seconds after an interruption before continuing.")
                    self._test_sessions[item.session_id] = interrupt_session(item)
            partial = partial or (not sessions and any(
                m.run_id == run_id for m in self.measurements.values()
            ))
            record = RunSessionRecord(
                self._next("test_session"), run_id, client_session_uuid, started,
                None, 0, started, None, "partial" if partial else "confirmed",
            )
            self._test_sessions[record.session_id] = record
            return record

    def checkpoint_test_session(self, checkpoint: RunSessionCheckpoint) -> RunSessionRecord:
        checkpoint.validate()
        with self._lock:
            current = next((s for s in self._test_sessions.values()
                            if s.client_session_uuid == checkpoint.client_session_uuid), None)
            if current is None:
                raise ValueError("Timing session was not found")
            result = apply_checkpoint(current, checkpoint)
            self._test_sessions[result.session_id] = result
            return result

    def _close_test_sessions(self, run_id, checkpoint=None, end_reason="interrupted"):
        with self._lock:
            sessions = self.test_sessions_for_runs((run_id,))
            if checkpoint is not None:
                current = next((s for s in sessions if s.client_session_uuid == checkpoint.client_session_uuid), None)
                if current is None:
                    raise ValueError("Timing session was not found for this run")
                if any(s.ended_at_utc is None and s.session_id != current.session_id for s in sessions):
                    raise ValueError("A newer active timing session cannot be closed by an old retry")
                result = apply_checkpoint(current, checkpoint, end_reason)
                self._test_sessions[result.session_id] = result
            else:
                for current in sessions:
                    self._test_sessions[current.session_id] = interrupt_session(current)


class SqlRunSessions:
    def end_test_session(self, checkpoint: RunSessionCheckpoint, end_reason: str) -> None:
        with self._factory.transaction() as cursor:
            self._close_test_sessions(cursor, checkpoint.run_id, checkpoint, end_reason)

    _SESSION_SELECT = (
        "SELECT session_id, run_id, client_session_uuid, started_at_utc, "
        "ended_at_utc, active_duration_ms, last_checkpoint_at_utc, end_reason, "
        "timing_quality FROM dbo.IL_RUN_SESSIONS"
    )

    @staticmethod
    def _test_session(row) -> RunSessionRecord:
        def utc(value):
            if value is None:
                return None
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return RunSessionRecord(
            int(row[0]), int(row[1]), UUID(str(row[2])), utc(row[3]), utc(row[4]),
            int(row[5]), utc(row[6]), row[7], str(row[8]),
        )

    def test_sessions_for_runs(self, run_ids: tuple[int, ...]) -> tuple[RunSessionRecord, ...]:
        ids = tuple(dict.fromkeys(int(value) for value in run_ids))
        if not ids:
            return ()
        # Stay below SQL Server's parameter limit for large report searches.
        result = []
        with self._factory.transaction() as cursor:
            for offset in range(0, len(ids), 1000):
                batch = ids[offset:offset + 1000]
                rows = cursor.execute(
                    self._SESSION_SELECT + " WHERE run_id IN (" + ",".join("?" for _ in batch) + ") ORDER BY started_at_utc, session_id",
                    *batch,
                ).fetchall()
                result.extend(self._test_session(row) for row in rows)
        return tuple(result)

    def _save_test_session(self, cursor, session):
        cursor.execute(
            "UPDATE dbo.IL_RUN_SESSIONS SET ended_at_utc = ?, active_duration_ms = ?, "
            "last_checkpoint_at_utc = ?, end_reason = ?, timing_quality = ? WHERE session_id = ?",
            session.ended_at_utc, session.active_duration_ms,
            session.last_checkpoint_at_utc, session.end_reason,
            session.timing_quality, session.session_id,
        )

    def begin_test_session(
        self, run_id: int, client_session_uuid: UUID, started_at_utc: datetime,
        *, partial: bool = False,
    ) -> RunSessionRecord:
        started = require_utc(started_at_utc, "Test session start")
        if not isinstance(client_session_uuid, UUID):
            raise ValueError("A timing session UUID is required")
        with self._factory.transaction() as cursor:
            run = cursor.execute(
                "SELECT completion_status, run_started_at_utc FROM dbo.IL_RUNS WITH (UPDLOCK, HOLDLOCK) WHERE run_id = ?", run_id,
            ).fetchone()
            if run is None:
                raise ValueError("Run was not found")
            existing = cursor.execute(self._SESSION_SELECT + " WHERE client_session_uuid = ?", str(client_session_uuid)).fetchone()
            if existing is not None:
                record = self._test_session(existing)
                if record.run_id != run_id:
                    raise ValueError("Timing session UUID belongs to another run")
                return record
            run_started = run[1].replace(tzinfo=timezone.utc) if run[1].tzinfo is None else run[1]
            if run[0] != "in_progress" or started < run_started:
                raise ValueError("Timing requires an in-progress run and valid start time")
            sessions = tuple(self._test_session(row) for row in cursor.execute(
                self._SESSION_SELECT + " WITH (UPDLOCK, HOLDLOCK) WHERE run_id = ?", run_id
            ).fetchall())
            for current in sessions:
                if current.ended_at_utc is None:
                    if (started - current.last_checkpoint_at_utc).total_seconds() < SESSION_STALE_SECONDS:
                        raise ValueError("This run has a recent active timing session. Stop it or wait 90 seconds after an interruption before continuing.")
                    self._save_test_session(cursor, interrupt_session(current))
            has_measurements = cursor.execute(
                "SELECT TOP (1) measurement_id FROM dbo.IL_MEASUREMENTS WHERE run_id = ?", run_id
            ).fetchone()
            quality = "partial" if partial or (not sessions and has_measurements is not None) else "confirmed"
            row = cursor.execute(
                "INSERT INTO dbo.IL_RUN_SESSIONS (run_id, client_session_uuid, started_at_utc, "
                "active_duration_ms, last_checkpoint_at_utc, timing_quality) "
                "OUTPUT inserted.session_id VALUES (?, ?, ?, 0, ?, ?)",
                run_id, str(client_session_uuid), started, started, quality,
            ).fetchone()
            return RunSessionRecord(int(row[0]), run_id, client_session_uuid, started, None, 0, started, None, quality)

    def checkpoint_test_session(self, checkpoint: RunSessionCheckpoint) -> RunSessionRecord:
        checkpoint.validate()
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                self._SESSION_SELECT + " WITH (UPDLOCK, HOLDLOCK) WHERE client_session_uuid = ?",
                str(checkpoint.client_session_uuid),
            ).fetchone()
            if row is None:
                raise ValueError("Timing session was not found")
            result = apply_checkpoint(self._test_session(row), checkpoint)
            self._save_test_session(cursor, result)
            return result

    def _close_test_sessions(self, cursor, run_id, checkpoint=None, end_reason="interrupted"):
        sessions = tuple(self._test_session(row) for row in cursor.execute(
            self._SESSION_SELECT + " WITH (UPDLOCK, HOLDLOCK) WHERE run_id = ?", run_id,
        ).fetchall())
        if checkpoint is not None:
            current = next((s for s in sessions if s.client_session_uuid == checkpoint.client_session_uuid), None)
            if current is None:
                raise ValueError("Timing session was not found for this run")
            if any(s.ended_at_utc is None and s.session_id != current.session_id for s in sessions):
                raise ValueError("A newer active timing session cannot be closed by an old retry")
            self._save_test_session(cursor, apply_checkpoint(current, checkpoint, end_reason))
        else:
            for current in sessions:
                if current.ended_at_utc is None:
                    self._save_test_session(cursor, interrupt_session(current))
