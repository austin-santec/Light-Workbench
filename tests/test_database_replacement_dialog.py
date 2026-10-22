import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from application.replacement_persistence_workflow import (
    ReplacementEditorModel,
    ReplacementRecommendation,
)
from domain.database_records import ChannelMapRecord, ReplacementRecord
from ui.database_replacements import DatabaseReplacementDialog


NOW = datetime(2026, 10, 21, 18, 0, tzinfo=timezone.utc)


class DatabaseReplacementDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def model(self):
        return ReplacementEditorModel(
            assignment_id=7,
            related_run_id=11,
            unit_label="MB-1",
            switch_label="OSX-150 SW-1",
            default_operator="AT",
            channel_map=(
                ChannelMapRecord(7, 1, 2, 1, 1, 4, True, 9, NOW),
                ChannelMapRecord(7, 1, 2, 2, 2, 2, False),
            ),
            replacement_history=(
                ReplacementRecord(8, 7, 1, 1, 3, "First", "AT", NOW, 10, "first note"),
                ReplacementRecord(9, 7, 1, 3, 4, "Again", "JS", NOW, 11, "second note"),
            ),
            existing_spares=(5,),
            recommended_spares=(6,),
            measured_physical_ports=(6,),
            recommendations=(
                ReplacementRecommendation(
                    1, 4, 6, "required", 1.2,
                    "Formal insertion-loss failure", True,
                ),
            ),
        )

    def test_opening_shows_real_history_and_does_not_queue_recommendation(self):
        dialog = DatabaseReplacementDialog(self.model())

        self.assertEqual(dialog.pending_table.rowCount(), 0)
        self.assertEqual(dialog.recommendation_table.rowCount(), 1)
        self.assertEqual(dialog.history_table.rowCount(), 2)
        self.assertEqual(dialog.history_table.item(1, 0).text(), "9")
        self.assertEqual(dialog.history_table.item(1, 1).text(), "1")
        self.assertEqual(dialog.history_table.item(1, 2).text(), "3")
        self.assertEqual(dialog.history_table.item(1, 3).text(), "4")
        self.assertEqual(dialog.history_table.item(1, 8).text(), "second note")
        self.assertEqual(dialog.result(), 0)
        dialog.close()

    def test_recommendation_populates_known_fields_and_editable_operator(self):
        dialog = DatabaseReplacementDialog(self.model())
        dialog.recommendation_table.selectRow(0)
        dialog.use_selected_recommendation()

        self.assertEqual(dialog.logical_channel_combo.currentData(), 1)
        self.assertEqual(dialog.current_port_edit.text(), "4")
        self.assertEqual(dialog.proposed_port_spin.value(), 6)
        self.assertEqual(dialog.category_edit.text(), "Required")
        self.assertEqual(dialog.improvement_edit.text(), "1.2000 dB")
        self.assertEqual(dialog.reason_edit.text(), "Formal insertion-loss failure")
        self.assertEqual(dialog.operator_edit.text(), "AT")
        dialog.operator_edit.setText("JS")
        self.assertEqual(dialog.operator_edit.text(), "JS")
        dialog.close()

    def test_manual_replacement_derives_latest_effective_port_and_saves_details(self):
        dialog = DatabaseReplacementDialog(self.model())
        dialog.logical_channel_combo.setCurrentIndex(
            dialog.logical_channel_combo.findData(1)
        )
        dialog.proposed_port_spin.setValue(6)
        dialog.reason_edit.setText("Correction")
        dialog.operator_edit.setText("JS")
        dialog.details_edit.setText("Operator-supplied details")
        dialog.queue_replacement()
        dialog.physical_completion_check.setChecked(True)
        dialog.accept_changes()

        self.assertEqual(dialog.result(), QDialog.Accepted)
        request = dialog.replacement_requests[0]
        self.assertEqual(request.logical_channel, 1)
        self.assertEqual(request.replacement_physical_port, 6)
        self.assertEqual(request.notes, "Operator-supplied details")
        self.assertEqual(request.replaced_by, "JS")
        dialog.close()

    def test_confirmation_required_and_spares_are_not_silently_removed(self):
        dialog = DatabaseReplacementDialog(self.model())
        dialog.proposed_port_spin.setValue(6)
        dialog.reason_edit.setText("Manual")
        dialog.queue_replacement()
        with patch.object(QMessageBox, "warning") as warning:
            dialog.accept_changes()
        warning.assert_called_once()
        self.assertNotEqual(dialog.result(), QDialog.Accepted)

        self.assertEqual(dialog.spare_table.item(0, 0).checkState(), Qt.Checked)
        self.assertEqual(dialog.spare_table.item(1, 0).checkState(), Qt.Checked)
        dialog.physical_completion_check.setChecked(True)
        dialog.accept_changes()
        self.assertEqual(dialog.spares_to_designate, (6,))
        self.assertEqual(dialog.spares_to_undesignate, ())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
