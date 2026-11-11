"""Exercise SQL repository transaction boundaries without contacting SQL Server."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
import unittest
from uuid import UUID, uuid4

from domain.run_sessions import RunSessionCheckpoint, RunSessionRecord
from infrastructure.database.memory_repositories import InMemoryRepositories
from infrastructure.database.sql_repositories import SqlRepositories
from tests.test_run_sessions import make_run, NOW


class Cursor:
    def __init__(self, factory):
        self.factory = factory
        self.rows = []
        self.rowcount = 1

    def execute(self, sql, *args):
        sql = " ".join(sql.split())
        self.factory.calls.append((sql, args))
        if sql.startswith("SELECT") and "FROM dbo.IL_RUN_SESSIONS" in sql:
            if "client_session_uuid = ?" in sql:
                selected = [s for s in self.factory.sessions.values() if s.client_session_uuid == UUID(str(args[0]))]
            else:
                selected = [s for s in self.factory.sessions.values() if s.run_id in args]
            self.rows = [tuple(s.__dict__.values()) for s in selected]
        elif sql.startswith("INSERT INTO dbo.IL_RUN_SESSIONS"):
            run_id, token, started, checkpoint, quality = args
            session = RunSessionRecord(len(self.factory.sessions) + 1, run_id, UUID(token), started, None, 0, checkpoint, None, quality)
            self.factory.sessions[session.session_id] = session
            self.rows = [(session.session_id,)]
        elif sql.startswith("UPDATE dbo.IL_RUN_SESSIONS"):
            ended, duration, checkpoint, reason, quality, session_id = args
            self.factory.sessions[session_id] = replace(self.factory.sessions[session_id], ended_at_utc=ended, active_duration_ms=duration, last_checkpoint_at_utc=checkpoint, end_reason=reason, timing_quality=quality)
            self.rows = []
        elif sql.startswith("UPDATE dbo.IL_RUNS"):
            if self.factory.fail_final:
                raise RuntimeError("Injected final lifecycle failure")
            self.factory.run = replace(self.factory.run, completion_status=args[0], run_ended_at_utc=args[1])
            self.rows = []
        elif "FROM dbo.IL_MEASUREMENTS" in sql:
            self.rows = []
        elif "FROM dbo.IL_RUNS AS run" in sql:
            self.rows = [self.factory.run]
        elif "SELECT completion_status" in sql:
            self.rows = [(self.factory.run.completion_status, self.factory.run.run_started_at_utc)]
        elif "SELECT run_id FROM dbo.IL_RUNS" in sql:
            self.rows = [(self.factory.run.run_id,)]
        else:
            raise AssertionError(sql)
        return self

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Factory:
    def __init__(self):
        self.run = make_run(InMemoryRepositories())
        self.sessions = {}
        self.calls = []
        self.fail_final = False
        self.rollbacks = 0

    @contextmanager
    def transaction(self):
        before = self.run, dict(self.sessions)
        try:
            yield Cursor(self)
        except Exception:
            self.run, self.sessions = before
            self.rollbacks += 1
            raise


class Repository(SqlRepositories):
    @staticmethod
    def _run(row):
        return row

    def _run_by_id(self, cursor, run_id):
        return self._factory.run


class SqlRunSessionTests(unittest.TestCase):
    def setUp(self):
        self.factory = Factory()
        self.repository = Repository(self.factory)
        self.token = uuid4()

    def test_start_checkpoint_finish_and_late_retry_are_parameterized(self):
        session = self.repository.begin_test_session(1, self.token, NOW)
        self.assertEqual(self.repository.begin_test_session(1, self.token, NOW), session)
        checkpoint = RunSessionCheckpoint(1, self.token, NOW + timedelta(minutes=2), 120000)
        self.repository.checkpoint_test_session(checkpoint)
        self.repository.finish(1, "complete", checkpoint.checkpoint_at_utc, timing_checkpoint=checkpoint)
        self.repository.checkpoint_test_session(replace(checkpoint, active_duration_ms=240000))
        saved = self.repository.test_sessions_for_runs((1,))[0]
        self.assertEqual(saved.active_duration_ms, 120000)
        self.assertEqual(saved.end_reason, "completed")
        self.assertTrue(any("UPDLOCK, HOLDLOCK" in sql for sql, _args in self.factory.calls))
        self.assertTrue(all(str(self.token) not in sql for sql, _args in self.factory.calls))

    def test_final_session_and_lifecycle_update_roll_back_together(self):
        original = self.repository.begin_test_session(1, self.token, NOW)
        self.factory.fail_final = True
        checkpoint = RunSessionCheckpoint(1, self.token, NOW + timedelta(minutes=2), 120000)
        with self.assertRaisesRegex(RuntimeError, "Injected"):
            self.repository.finish(1, "complete", checkpoint.checkpoint_at_utc, timing_checkpoint=checkpoint)
        self.assertEqual(self.repository.test_sessions_for_runs((1,)), (original,))
        self.assertEqual(self.factory.run.completion_status, "in_progress")
        self.assertEqual(self.factory.rollbacks, 1)
        self.factory.fail_final = False
        self.repository.finish(1, "complete", checkpoint.checkpoint_at_utc, timing_checkpoint=checkpoint)
        self.assertEqual(self.factory.run.completion_status, "complete")

    def test_recovery_uses_last_saved_time_and_estimated_quality(self):
        self.repository.begin_test_session(1, self.token, NOW)
        self.repository.checkpoint_test_session(RunSessionCheckpoint(1, self.token, NOW + timedelta(minutes=2), 120000))
        self.repository.begin_test_session(1, uuid4(), NOW + timedelta(hours=12))
        old = self.repository.test_sessions_for_runs((1,))[0]
        self.assertEqual(old.ended_at_utc, NOW + timedelta(minutes=2))
        self.assertEqual(old.timing_quality, "checkpoint_estimate")

    def test_bulk_report_history_chunks_below_parameter_limit(self):
        self.repository.test_sessions_for_runs(tuple(range(1, 2002)))
        queries = [(sql, args) for sql, args in self.factory.calls if "IN (" in sql]
        self.assertEqual([len(args) for _sql, args in queries], [1000, 1000, 1])


if __name__ == "__main__":
    unittest.main()
