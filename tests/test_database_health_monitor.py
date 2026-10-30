import os
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from application.database_health_monitor import (
    DATABASE_HEALTH_INTERVAL_MS,
    DatabaseHealthMonitor,
    DatabaseHealthSnapshot,
    DatabaseHealthState,
)
from config.database_config import DatabaseSettings
from infrastructure.database.connection import DatabaseErrorCategory
from infrastructure.database.connection import DatabaseConnectionError
from ui.database_status import DatabaseStatusIndicator


@dataclass(frozen=True)
class _Result:
    ready: bool
    category: object = None
    operator_message: str = "ready"
    current_schema_version: int | None = 6
    expected_schema_version: int = 6
    elapsed_ms: int = 25


class _Tasks:
    def __init__(self):
        self.pending = []

    def __call__(self, task):
        self.pending.append(task)

    def run_next(self):
        self.pending.pop(0)()


class _Logger:
    def __init__(self):
        self.records = []

    def record(self, *args, **kwargs):
        self.records.append((args, kwargs))

    @property
    def events(self):
        return [args[1] for args, _kwargs in self.records]


class DatabaseHealthMonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def _monitor(self, results, *, enabled=True, logger=None):
        tasks = _Tasks()

        def probe():
            value = results.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        monitor = DatabaseHealthMonitor(
            enabled=enabled,
            probe=probe if enabled else None,
            support_logger=logger,
            task_runner=tasks,
            now=lambda: datetime(2026, 10, 30, 21, 0, tzinfo=timezone.utc),
        )
        self.addCleanup(monitor.stop)
        return monitor, tasks

    def test_disabled_monitor_schedules_no_probe(self):
        monitor, tasks = self._monitor([], enabled=False)
        monitor.start()

        self.assertEqual(monitor.snapshot.state, DatabaseHealthState.DISABLED)
        self.assertFalse(monitor.timer_active)
        self.assertFalse(tasks.pending)

    def test_startup_success_is_nonblocking_and_transitions_to_ready(self):
        monitor, tasks = self._monitor([_Result(True)])
        states = []
        monitor.state_changed.connect(lambda snapshot: states.append(snapshot.state))

        monitor.start()

        self.assertEqual(monitor.snapshot.state, DatabaseHealthState.CHECKING)
        self.assertTrue(monitor.check_in_progress)
        self.assertEqual(len(tasks.pending), 1)
        self.assertEqual(monitor.interval_ms, DATABASE_HEALTH_INTERVAL_MS)
        self.assertTrue(monitor.timer_active)

        tasks.run_next()

        self.assertEqual(monitor.snapshot.state, DatabaseHealthState.READY)
        self.assertEqual(monitor.snapshot.current_schema_version, 6)
        self.assertEqual(monitor.snapshot.elapsed_ms, 25)
        self.assertEqual(
            states,
            [DatabaseHealthState.CHECKING, DatabaseHealthState.READY],
        )

    def test_failure_then_later_success_recovers(self):
        monitor, tasks = self._monitor(
            [
                _Result(
                    False,
                    DatabaseErrorCategory.SERVER_UNAVAILABLE,
                    "The database server could not be reached.",
                    None,
                    6,
                    5000,
                ),
                _Result(True, elapsed_ms=12),
            ]
        )
        monitor.start()
        tasks.run_next()
        self.assertEqual(monitor.snapshot.state, DatabaseHealthState.UNAVAILABLE)
        self.assertEqual(monitor.snapshot.error_category, "server_unavailable")

        monitor.request_check("manual")
        tasks.run_next()

        self.assertEqual(monitor.snapshot.state, DatabaseHealthState.READY)
        self.assertIsNotNone(monitor.snapshot.last_success_at_utc)

    def test_probe_exception_is_classified_without_exposing_raw_detail(self):
        monitor, tasks = self._monitor(
            [
                DatabaseConnectionError(
                    DatabaseErrorCategory.AUTHENTICATION,
                    "The configured database authentication was rejected by SQL Server.",
                    "PWD=synthetic-secret",
                )
            ]
        )
        monitor.start()
        tasks.run_next()

        self.assertEqual(monitor.snapshot.state, DatabaseHealthState.UNAVAILABLE)
        self.assertEqual(monitor.snapshot.error_category, "authentication")
        self.assertNotIn("synthetic-secret", monitor.snapshot.message)

    def test_overlapping_manual_request_is_coalesced_and_runs_after_current(self):
        logger = _Logger()
        monitor, tasks = self._monitor(
            [_Result(True), _Result(True, elapsed_ms=8)],
            logger=logger,
        )
        monitor.start()

        self.assertFalse(monitor.request_check("manual"))
        self.assertEqual(len(tasks.pending), 1)
        self.assertTrue(
            any(
                kwargs.get("request_coalesced") is True
                for _args, kwargs in logger.records
            )
        )

        tasks.run_next()
        QApplication.processEvents()

        self.assertEqual(len(tasks.pending), 1)
        tasks.run_next()
        self.assertEqual(monitor.snapshot.state, DatabaseHealthState.READY)

    def test_unchanged_periodic_success_does_not_spam_log(self):
        logger = _Logger()
        monitor, tasks = self._monitor(
            [_Result(True), _Result(True, elapsed_ms=4)],
            logger=logger,
        )
        monitor.start()
        tasks.run_next()
        logger.records.clear()

        monitor.request_check("periodic")
        tasks.run_next()

        self.assertEqual(logger.records, [])

    def test_startup_manual_and_state_changes_are_logged(self):
        logger = _Logger()
        monitor, tasks = self._monitor(
            [_Result(True), _Result(False, DatabaseErrorCategory.TIMEOUT, "Timed out")],
            logger=logger,
        )
        monitor.start()
        tasks.run_next()
        monitor.request_check("manual")
        tasks.run_next()

        self.assertIn("database.health_check_requested", logger.events)
        self.assertIn("database.health_check_completed", logger.events)
        self.assertIn("database.health_state_changed", logger.events)
        failure = next(
            kwargs
            for args, kwargs in logger.records
            if args[1] == "database.health_check_completed"
            and kwargs.get("status") == "unavailable"
        )
        self.assertEqual(failure["database_error_category"], "timeout")

    def test_operation_results_update_health_without_starting_probe(self):
        monitor, tasks = self._monitor([_Result(True)])
        monitor.report_operation_result(
            _Result(False, DatabaseErrorCategory.PERMISSION_DENIED, "Access denied")
        )
        self.assertEqual(monitor.snapshot.state, DatabaseHealthState.UNAVAILABLE)
        self.assertFalse(tasks.pending)

        monitor.report_operation_ready()
        self.assertEqual(monitor.snapshot.state, DatabaseHealthState.READY)
        self.assertFalse(tasks.pending)

    def test_stop_ignores_late_probe_result_and_stops_timer(self):
        monitor, tasks = self._monitor([_Result(True)])
        monitor.start()
        self.assertEqual(monitor.snapshot.state, DatabaseHealthState.CHECKING)

        monitor.stop()
        tasks.run_next()

        self.assertFalse(monitor.timer_active)
        self.assertEqual(monitor.snapshot.state, DatabaseHealthState.CHECKING)


class DatabaseStatusIndicatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_indicator_displays_text_tooltip_and_theme_for_each_state(self):
        indicator = DatabaseStatusIndicator("tcp:SERVER,49172", "LWBTestDB")
        self.addCleanup(indicator.close)
        for state, text in (
            (DatabaseHealthState.DISABLED, "Database: Disabled"),
            (DatabaseHealthState.CHECKING, "Database: Checking"),
            (DatabaseHealthState.READY, "Database: Ready"),
            (DatabaseHealthState.UNAVAILABLE, "Database: Unavailable"),
        ):
            with self.subTest(state=state):
                indicator.set_snapshot(
                    DatabaseHealthSnapshot(
                        state,
                        checked_at_utc=datetime(
                            2026, 10, 30, 21, 0, tzinfo=timezone.utc
                        ),
                        elapsed_ms=42,
                        current_schema_version=6,
                        expected_schema_version=6,
                        error_category=(
                            "timeout"
                            if state == DatabaseHealthState.UNAVAILABLE
                            else ""
                        ),
                        message="Synthetic status",
                    )
                )
                self.assertIn(text, indicator.text())
                self.assertIn("tcp:SERVER,49172", indicator.toolTip())
                self.assertIn("LWBTestDB", indicator.toolTip())
                self.assertIn("No permanent connection", indicator.toolTip())
                indicator.apply_theme(False)
                light_style = indicator.styleSheet()
                indicator.apply_theme(True)
                self.assertNotEqual(light_style, indicator.styleSheet())

    def test_indicator_click_emits_clicked_signal(self):
        indicator = DatabaseStatusIndicator()
        self.addCleanup(indicator.close)
        clicks = []
        indicator.clicked.connect(lambda: clicks.append(True))

        indicator.click()

        self.assertEqual(clicks, [True])


if __name__ == "__main__":
    unittest.main()
