import os
import unittest
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QPlainTextEdit

from application.support_logging import SupportLoggingStatus
from ui.support_logs import LoggingStatusDialog, SupportBundleDialog


class SupportLogsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_bundle_date_range_defaults_to_today_and_previous_two_days(self):
        dialog = SupportBundleDialog(today=date(2026, 10, 2))
        self.assertEqual(dialog.start_date, date(2026, 9, 30))
        self.assertEqual(dialog.end_date, date(2026, 10, 2))
        dialog.close()

    def test_status_dialog_displays_health_and_fallback_details(self):
        status = SupportLoggingStatus(
            healthy=False,
            active_folder="C:/Temp/LightWorkbench/logs",
            active_filename="light-workbench-2026-10-02.jsonl",
            app_instance_id="app-test",
            schema_version=1,
            queue_depth=3,
            dropped_event_count=2,
            last_writer_error="preferred directory unavailable",
            retention_days=30,
            max_file_bytes=25 * 1024 * 1024,
            max_total_bytes=500 * 1024 * 1024,
            fallback_active=True,
            memory_event_count=1,
        )
        dialog = LoggingStatusDialog(status)
        views = dialog.findChildren(QPlainTextEdit)
        self.assertEqual(len(views), 1)
        self.assertIn("Fallback directory active: Yes", views[0].toPlainText())
        self.assertIn("Dropped events: 2", views[0].toPlainText())
        dialog.setStyleSheet("QDialog { background: #202124; color: #e8eaed; }")
        self.assertIn("#202124", dialog.styleSheet())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
