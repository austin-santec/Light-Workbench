import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from domain.measurement_attempts import new_measurement_attempt
from domain.models import MeasurementRecord
from ui.reading_history import ReadingHistoryDialog, history_rows, history_tsv


class ReadingHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def _attempts(self):
        first = new_measurement_attempt(
            MeasurementRecord(14, 2.6000, 2.4000, 14),
            operator_initials="AB",
            run_id="run-1",
        )
        second = new_measurement_attempt(
            MeasurementRecord(14, 2.1000, 2.0000, 41),
            prior=first,
            operator_initials="CD",
            run_id="run-1",
        )
        return [first, second]

    def test_history_rows_identify_current_and_superseded_attempts(self):
        attempts = self._attempts()

        rows = history_rows(attempts)
        superseded_rows = history_rows([attempts[0]], status_source=attempts)

        self.assertEqual(rows[0][2], "Superseded")
        self.assertEqual(rows[1][2], "Current")
        self.assertEqual(superseded_rows[0][2], "Superseded")

    def test_history_tsv_has_headers_and_both_wavelengths(self):
        text = history_tsv(self._attempts())

        self.assertIn("Channel\tAttempt\tStatus", text)
        self.assertIn("14\t1\tSuperseded\t2.6000\t2.4000", text)
        self.assertIn("14\t2\tCurrent\t2.1000\t2.0000", text)

    def test_dialog_is_read_only_and_can_filter_current_attempts(self):
        dialog = ReadingHistoryDialog(self._attempts())

        self.assertEqual(dialog.history_table.rowCount(), 2)
        dialog.status_filter.setCurrentIndex(1)
        self.assertEqual(dialog.history_table.rowCount(), 1)
        self.assertEqual(dialog.history_table.item(0, 2).text(), "Current")
        self.assertEqual(int(dialog.history_table.editTriggers()), 0)
        dialog.close()


if __name__ == "__main__":
    unittest.main()
