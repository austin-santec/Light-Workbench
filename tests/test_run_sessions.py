"""Timing contracts use deterministic clocks and disposable in-memory runs."""

import os
import unittest
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from application.run_lifecycle_workflow import RunLifecycleWorkflow
from application.run_session_timing import RunSessionClock, TimingCheckpointWriter
from application.database_reporting import DatabaseReportingService
from domain.database_records import AssignmentSpec, RunSpec, SwitchSpec, UnitSpec
from domain.database_reporting import ReportFilters
from domain.run_sessions import RunSessionCheckpoint, summarize_run_timing, session_interval_union_ms
from infrastructure.database.memory_repositories import InMemoryRepositories
from application.database_primary_workflow import DatabasePrimaryRunWorkflow
from domain.database_records import utc_now
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtCore import QEventLoop, QTimer
from ilm_app import MainWindow


NOW = datetime(2026, 11, 10, 9, tzinfo=timezone.utc)


def make_run(repository, serial="TEST", number=1, start=NOW):
    unit = repository.get_or_create(UnitSpec(serial, "OSX-150-1A-001-TEST", 1, "OSX-150"))
    switch = repository.get_or_create(SwitchSpec("SW-" + serial, "OSX-150", 1))
    assignment = repository.get_active(unit.unit_id) or repository.install(
        AssignmentSpec(unit.unit_id, switch.switch_id, start, "AT", {1: 1})
    )
    return repository.create(RunSpec(
        assignment.assignment_id, number, uuid4(), start, "AT", "SM", "O band", "test",
        station_number=99, front_panel_channel_count=1,
    ))


class RunSessionTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryRepositories()
        self.run = make_run(self.repository)
        self.lifecycle = RunLifecycleWorkflow(self.repository, lambda: None)

    def begin(self, minute=0, **kwargs):
        return self.repository.begin_test_session(
            self.run.run_id, uuid4(), NOW + timedelta(minutes=minute), **kwargs
        )

    def checkpoint(self, session, minute, elapsed_ms):
        return RunSessionCheckpoint(
            session.run_id, session.client_session_uuid,
            NOW + timedelta(minutes=minute), elapsed_ms,
        )

    def test_stop_continue_counts_twenty_active_not_sixty_eight_elapsed_minutes(self):
        first = self.begin()
        self.lifecycle.finish_run(self.run.run_id, "stopped", timing_checkpoint=self.checkpoint(first, 12, 720000))
        self.lifecycle.resume_run(self.run.run_id)
        second = self.begin(60)
        finished = self.lifecycle.finish_run(self.run.run_id, "complete", timing_checkpoint=self.checkpoint(second, 68, 480000))
        sessions = self.repository.test_sessions_for_runs((self.run.run_id,))
        summary = summarize_run_timing(finished, sessions)
        self.assertEqual(summary.active_duration_ms, 1200000)
        self.assertEqual(summary.elapsed_ms, 4080000)
        self.assertEqual(summary.stopped_ms, 2880000)
        self.assertEqual(summary.timing_quality, "confirmed")
        self.assertEqual([s.end_reason for s in sessions], ["stopped", "completed"])

    def test_duplicate_start_checkpoint_and_finish_are_idempotent(self):
        session = self.begin()
        self.assertEqual(self.repository.begin_test_session(self.run.run_id, session.client_session_uuid, NOW), session)
        checkpoint = self.checkpoint(session, 1, 60000)
        for _ in range(2):
            self.repository.checkpoint_test_session(checkpoint)
        for _ in range(2):
            self.lifecycle.finish_run(self.run.run_id, "stopped", timing_checkpoint=checkpoint)
        history = self.repository.test_sessions_for_runs((self.run.run_id,))
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].active_duration_ms, 60000)

    def test_older_and_post_close_heartbeats_cannot_regress_or_reopen_session(self):
        session = self.begin()
        latest = self.checkpoint(session, 2, 120000)
        self.repository.checkpoint_test_session(latest)
        self.repository.checkpoint_test_session(self.checkpoint(session, 1, 60000))
        self.lifecycle.finish_run(self.run.run_id, "complete", timing_checkpoint=latest)
        self.repository.checkpoint_test_session(self.checkpoint(session, 3, 180000))
        saved = self.repository.test_sessions_for_runs((self.run.run_id,))[0]
        self.assertEqual(saved.active_duration_ms, 120000)
        self.assertEqual(saved.ended_at_utc, latest.checkpoint_at_utc)

    def test_crash_recovery_closes_at_checkpoint_not_restart(self):
        session = self.begin()
        self.repository.checkpoint_test_session(self.checkpoint(session, 5, 300000))
        second = self.begin(60)
        recovered = self.repository.test_sessions_for_runs((self.run.run_id,))[0]
        self.assertEqual(recovered.ended_at_utc, NOW + timedelta(minutes=5))
        self.assertEqual(recovered.timing_quality, "checkpoint_estimate")
        self.lifecycle.finish_run(self.run.run_id, "complete", timing_checkpoint=self.checkpoint(second, 68, 480000))
        summary = summarize_run_timing(self.repository.get(self.run.run_id), self.repository.test_sessions_for_runs((self.run.run_id,)))
        self.assertEqual(summary.active_duration_ms, 780000)
        self.assertIsNone(summary.stopped_ms)
        self.assertEqual(summary.timing_quality, "checkpoint_estimate")

    def test_recent_live_session_cannot_be_silently_replaced(self):
        self.begin()
        with self.assertRaisesRegex(ValueError, "recent active"):
            self.begin(1)
        self.assertEqual(len(self.repository.test_sessions_for_runs((self.run.run_id,))), 1)

    def test_old_finish_retry_cannot_close_new_active_session(self):
        first = self.begin()
        checkpoint = self.checkpoint(first, 1, 60000)
        self.lifecycle.finish_run(self.run.run_id, "stopped", timing_checkpoint=checkpoint)
        self.lifecycle.resume_run(self.run.run_id)
        self.begin(2)
        with self.assertRaisesRegex(ValueError, "newer active"):
            self.lifecycle.finish_run(self.run.run_id, "stopped", timing_checkpoint=checkpoint)
        self.assertEqual(self.repository.get(self.run.run_id).completion_status, "in_progress")

    def test_invalid_checkpoint_cannot_change_run_or_session(self):
        session = self.begin()
        for checkpoint in (
            replace(self.checkpoint(session, 1, 1000), active_duration_ms=-1),
            replace(self.checkpoint(session, 1, 1000), run_id=999),
            replace(self.checkpoint(session, 1, 1000), client_session_uuid=uuid4()),
        ):
            with self.assertRaises(ValueError):
                self.lifecycle.finish_run(self.run.run_id, "complete", timing_checkpoint=checkpoint)
            self.assertEqual(self.repository.get(self.run.run_id).completion_status, "in_progress")
            self.assertEqual(self.repository.test_sessions_for_runs((self.run.run_id,))[0], session)

    def test_legacy_run_without_sessions_has_no_invented_active_time(self):
        summary = summarize_run_timing(self.run, (), NOW + timedelta(hours=1))
        self.assertIsNone(summary.active_duration_ms)
        self.assertIsNone(summary.stopped_ms)
        self.assertEqual(summary.timing_quality, "unavailable")

    def test_first_new_session_on_old_run_is_labeled_partial(self):
        first = self.begin(partial=True)
        self.lifecycle.finish_run(self.run.run_id, "stopped", timing_checkpoint=self.checkpoint(first, 1, 60000))
        summary = summarize_run_timing(self.repository.get(self.run.run_id), self.repository.test_sessions_for_runs((self.run.run_id,)))
        self.assertEqual(summary.timing_quality, "partial")
        self.assertIsNone(summary.stopped_ms)

    def test_timing_only_close_preserves_incomplete_coverage_lifecycle(self):
        session = self.begin()
        self.repository.end_test_session(self.checkpoint(session, 1, 60000), "stopped")
        self.assertEqual(self.repository.get(self.run.run_id).completion_status, "in_progress")
        self.assertIsNotNone(self.repository.test_sessions_for_runs((self.run.run_id,))[0].ended_at_utc)

    def test_lifecycle_without_final_checkpoint_labels_interruption(self):
        self.begin()
        self.lifecycle.finish_run(self.run.run_id, "failed", NOW + timedelta(hours=5))
        saved = self.repository.test_sessions_for_runs((self.run.run_id,))[0]
        self.assertEqual(saved.ended_at_utc, NOW)
        self.assertEqual(saved.timing_quality, "checkpoint_estimate")

    def test_clock_uses_monotonic_time_and_freezes_retry_payload(self):
        monotonic = [100.0]
        wall = [NOW]
        clock = RunSessionClock(1, now=lambda: wall[0], monotonic=lambda: monotonic[0])
        monotonic[0] += 12.5
        wall[0] -= timedelta(hours=1)
        checkpoint = clock.stop()
        self.assertEqual(checkpoint.active_duration_ms, 12500)
        self.assertGreaterEqual(checkpoint.checkpoint_at_utc, NOW)
        monotonic[0] += 3600
        self.assertIs(clock.stop(), checkpoint)

    def test_report_exposes_numeric_timing_and_unavailable_old_runs(self):
        session = self.begin()
        self.lifecycle.finish_run(self.run.run_id, "complete", timing_checkpoint=self.checkpoint(session, 12, 720000))
        make_run(self.repository, number=2, start=NOW + timedelta(hours=1))
        report = DatabaseReportingService(self.repository).search(ReportFilters(include_all_records=True))
        rows = {r.run_number: r for r in report.runs}
        self.assertEqual(rows[1].active_test_ms, 720000)
        self.assertIsNone(rows[2].active_test_ms)
        self.assertEqual(report.assignments[0].timing_quality, "partial")

    def test_assignment_union_does_not_double_count_overlapping_runs(self):
        first = self.begin()
        self.repository.end_test_session(self.checkpoint(first, 12, 720000), "stopped")
        second = replace(first, session_id=2, run_id=2, started_at_utc=NOW + timedelta(minutes=7), ended_at_utc=NOW + timedelta(minutes=15), active_duration_ms=480000)
        first = self.repository.test_sessions_for_runs((self.run.run_id,))[0]
        self.assertEqual(session_interval_union_ms((first, second)), 900000)


class RunSessionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.repository = InMemoryRepositories()
        run = make_run(self.repository, start=utc_now())
        workflow = DatabasePrimaryRunWorkflow(self.repository, lambda: type("Ready", (), {"ready": True})())
        self.window = MainWindow(database_workflow=workflow)
        self.window._apply_database_run_context(workflow.refresh(run.run_id))
        self.addCleanup(self.window.close)

    def test_start_stop_and_reload_use_persisted_sessions(self):
        window = self.window
        self.assertTrue(window.begin_switch_test_session())
        self.assertTrue(window.timing_checkpoint_timer.isActive())
        self.assertTrue(window._finish_database_run("stopped"))
        window.finish_switch_test_session()
        self.assertFalse(window.timing_checkpoint_timer.isActive())
        self.assertIsNone(window._database_session_clock)
        self.assertIsNotNone(window.database_run_context.timing_sessions[0].ended_at_utc)
        context = window.database_workflow.refresh(window.database_run_context.run.run_id)
        window._apply_database_run_context(context)
        window._refresh_database_timing()
        self.assertIn("Sessions: 1", window.run_timing_label.text())
        self.assertIn("confirmed", window.run_timing_label.text())

    def test_final_failure_retains_frozen_retry_and_blocks_clear(self):
        window = self.window
        window.begin_switch_test_session()
        with patch.object(self.repository, "finish", side_effect=RuntimeError("offline")), patch(
            "ilm_app.QMessageBox.critical"
        ), patch("ilm_app.QMessageBox.warning"):
            self.assertFalse(window._finish_database_run("stopped"))
            checkpoint = window._pending_timing_finish[0]
            self.assertFalse(window.clear_workspace(confirm=False))
            self.assertTrue(window.retry_timing_button.isEnabled())
            self.assertIn("offline", window.run_timing_label.text())
        self.assertTrue(window.retry_timing_save())
        saved = window.database_run_context.timing_sessions[0]
        self.assertEqual(saved.active_duration_ms, checkpoint.active_duration_ms)
        self.assertEqual(saved.ended_at_utc, checkpoint.checkpoint_at_utc)
        self.assertIsNone(window._pending_timing_finish)

    def test_checkpoint_failure_visible_and_success_clears_error(self):
        window = self.window
        window.begin_switch_test_session()
        checkpoint = window._database_session_clock.checkpoint()
        window._timing_checkpoint_failed(checkpoint, "Synthetic timing outage")
        self.assertIn("Synthetic timing outage", window.run_timing_label.text())
        saved = self.repository.checkpoint_test_session(checkpoint)
        window._timing_checkpoint_saved(saved)
        self.assertEqual(window._timing_error, "")

    def test_close_during_run_saves_stop_without_hardware_calls(self):
        window = self.window
        window.begin_switch_test_session()
        event = QCloseEvent()
        window.closeEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertEqual(window.database_run_context.run.completion_status, "stopped")
        self.assertIsNotNone(window.database_run_context.timing_sessions[0].ended_at_utc)

    def test_final_save_failure_prevents_silent_application_close(self):
        window = self.window
        window.begin_switch_test_session()
        event = QCloseEvent()
        with patch.object(self.repository, "finish", side_effect=RuntimeError("offline")), patch(
            "ilm_app.QMessageBox.critical"
        ):
            window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertIsNotNone(window._pending_timing_finish)

    def test_uncertain_start_commit_retries_original_uuid_without_duplicate(self):
        window = self.window
        original = self.repository.begin_test_session
        def committed_then_failed(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("Connection lost after commit")
        with patch.object(self.repository, "begin_test_session", side_effect=committed_then_failed), patch(
            "ilm_app.QMessageBox.critical"
        ):
            self.assertFalse(window.begin_switch_test_session())
        token = window._pending_timing_finish[0].client_session_uuid
        self.assertTrue(window.retry_timing_save())
        sessions = window.database_run_context.timing_sessions
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].client_session_uuid, token)
        self.assertEqual(sessions[0].active_duration_ms, 0)
        self.assertEqual(sessions[0].end_reason, "failed")

    def test_known_start_rejection_does_not_create_false_pending_save(self):
        window = self.window
        with patch.object(self.repository, "begin_test_session", side_effect=ValueError("recent active session")), patch(
            "ilm_app.QMessageBox.critical"
        ):
            self.assertFalse(window.begin_switch_test_session())
        self.assertIsNone(window._database_session_clock)
        self.assertIsNone(window._pending_timing_finish)

    def test_background_checkpoints_coalesce_and_do_not_block_gui(self):
        window = self.window
        window.begin_switch_test_session()
        checkpoint = window._database_session_clock.checkpoint()
        gate = threading.Event()
        entered = threading.Event()
        original = self.repository.checkpoint_test_session
        thread_ids = []
        def delayed_write(value):
            thread_ids.append(threading.get_ident())
            entered.set()
            gate.wait(3)
            return original(value)
        writer = TimingCheckpointWriter(self.repository)
        loop = QEventLoop()
        writer.succeeded.connect(lambda _saved: loop.quit())
        with patch.object(self.repository, "checkpoint_test_session", side_effect=delayed_write):
            self.assertTrue(writer.submit(checkpoint))
            self.assertTrue(entered.wait(1))
            self.assertFalse(writer.submit(checkpoint))
            gate.set()
            QTimer.singleShot(3000, loop.quit)
            loop.exec_()
        writer.close()
        self.assertNotEqual(thread_ids[0], threading.get_ident())

    def test_late_heartbeat_cannot_hide_final_save_failure(self):
        window = self.window
        window.begin_switch_test_session()
        checkpoint = window._database_session_clock.checkpoint()
        saved = self.repository.checkpoint_test_session(checkpoint)
        with patch.object(self.repository, "finish", side_effect=RuntimeError("final save failed")), patch(
            "ilm_app.QMessageBox.critical"
        ):
            self.assertFalse(window._finish_database_run("stopped"))
        window._timing_checkpoint_saved(saved)
        self.assertIn("final save failed", window.run_timing_label.text())


if __name__ == "__main__":
    unittest.main()
