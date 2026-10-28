import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox, QSplitter

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
                    "", True, 1.08, 1.12, 1.12,
                    current_loss_1310_db=2.4000,
                    current_loss_1550_db=2.3500,
                    current_worst_loss_db=2.4000,
                ),
            ),
        )

    def test_opening_shows_real_history_and_does_not_queue_recommendation(self):
        dialog = DatabaseReplacementDialog(self.model())

        self.assertEqual(dialog.pending_table.rowCount(), 0)
        self.assertEqual(dialog.recommendation_table.rowCount(), 1)
        self.assertEqual(dialog.recommendation_table.columnCount(), 7)
        self.assertEqual(
            [
                dialog.recommendation_table.horizontalHeaderItem(column).text()
                for column in range(dialog.recommendation_table.columnCount())
            ],
            [
                "Logical",
                "Current Port",
                "Proposed Port",
                "Category",
                "Improvement",
                "Current IL",
                "Candidate IL",
            ],
        )
        self.assertEqual(
            dialog.recommendation_table.item(0, 5).text(),
            "2.4000 / 2.3500 dB",
        )
        self.assertEqual(
            dialog.recommendation_table.item(0, 6).text(),
            "1.0800 / 1.1200 dB",
        )
        self.assertIn(
            "Current physical port: 4",
            dialog.recommendation_table.item(0, 5).toolTip(),
        )
        self.assertIn(
            "Worst case: 2.4000 dB",
            dialog.recommendation_table.item(0, 5).toolTip(),
        )
        self.assertEqual(dialog.history_table.rowCount(), 2)
        self.assertEqual(dialog.history_table.item(1, 0).text(), "9")
        self.assertEqual(dialog.history_table.item(1, 1).text(), "1")
        self.assertEqual(dialog.history_table.item(1, 2).text(), "3")
        self.assertEqual(dialog.history_table.item(1, 3).text(), "4")
        self.assertEqual(dialog.history_table.item(1, 8).text(), "second note")
        self.assertEqual(dialog.result(), 0)
        dialog.close()

    def test_tabs_and_content_follow_light_and_dark_theme(self):
        dialog = DatabaseReplacementDialog(self.model())

        self.assertEqual(dialog.objectName(), "database_replacement_dialog")
        self.assertEqual(dialog.tabs.objectName(), "database_replacement_tabs")
        self.assertEqual(
            dialog.tabs.tabBar().objectName(),
            "database_replacement_tab_bar",
        )
        self.assertEqual(dialog.tabs.count(), 3)
        self.assertIn("#ffffff", dialog.styleSheet())
        for table in (
            dialog.recommendation_table,
            dialog.pending_table,
            dialog.active_mapping_table,
            dialog.spare_table,
            dialog.history_table,
        ):
            self.assertEqual(table.objectName(), "database_replacement_table")

        dialog.apply_theme(True)

        self.assertIn("#25272b", dialog.styleSheet())
        self.assertIn("#3a3e45", dialog.styleSheet())
        self.assertIn("QWidget#database_replacement_tab_page", dialog.styleSheet())
        dialog.close()

    def test_record_tab_uses_resizable_panels_and_compact_controls(self):
        dialog = DatabaseReplacementDialog(self.model())

        self.assertIsInstance(dialog.record_splitter, QSplitter)
        self.assertIs(dialog.record_splitter.widget(0), dialog.record_upper_splitter)
        self.assertIs(dialog.record_splitter.widget(1), dialog.record_lower_splitter)
        self.assertEqual(dialog.record_upper_splitter.count(), 2)
        self.assertEqual(dialog.record_lower_splitter.count(), 2)
        self.assertEqual(dialog.logical_channel_combo.maximumWidth(), 90)
        self.assertEqual(dialog.current_port_edit.maximumWidth(), 90)
        self.assertEqual(dialog.proposed_port_spin.maximumWidth(), 90)
        self.assertTrue(dialog.pending_empty_label.text())
        self.assertFalse(dialog.pending_table.isVisibleTo(dialog))
        dialog.close()

    def test_record_tab_persists_geometry_and_splitter_state(self):
        dialog = DatabaseReplacementDialog(self.model())
        dialog._settings = MagicMock()

        dialog._save_ui_state()

        self.assertTrue(
            any(
                call.args[0] == "database_replacement_dialog_geometry"
                for call in dialog._settings.setValue.call_args_list
            )
        )
        self.assertTrue(
            any(
                call.args[0] == "database_replacement_dialog_size"
                for call in dialog._settings.setValue.call_args_list
            )
        )
        self.assertTrue(
            any(
                call.args[0] == "database_replacement_record_splitter_state"
                for call in dialog._settings.setValue.call_args_list
            )
        )
        dialog._settings.sync.assert_called_once_with()
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
        self.assertEqual(dialog.reason_combo.currentData(), None)
        self.assertEqual(dialog.candidate_il_label.text(), "1.0800 / 1.1200 dB")
        self.assertIn("Candidate physical port: 6", dialog.candidate_il_label.toolTip())
        self.assertEqual(dialog.operator_edit.text(), "AT")
        dialog.operator_edit.setText("JS")
        self.assertEqual(dialog.operator_edit.text(), "JS")
        dialog.close()

    def test_queued_panel_switches_between_empty_state_and_table(self):
        dialog = DatabaseReplacementDialog(self.model())
        dialog.proposed_port_spin.setValue(6)
        dialog.reason_combo.setCurrentIndex(
            dialog.reason_combo.findText("Unknown cause of high loss")
        )
        dialog.queue_replacement()

        self.assertTrue(dialog.pending_empty_label.isHidden())
        self.assertFalse(dialog.pending_table.isHidden())
        dialog.pending_table.selectRow(0)
        dialog.remove_queued_replacement()
        self.assertFalse(dialog.pending_empty_label.isHidden())
        self.assertTrue(dialog.pending_table.isHidden())
        dialog.close()

    def test_reason_choices_and_append_only_correction_mode(self):
        dialog = DatabaseReplacementDialog(self.model())
        self.assertFalse(hasattr(dialog, "physical_completion_check"))
        self.assertEqual(
            [dialog.reason_combo.itemText(index) for index in range(dialog.reason_combo.count())],
            [
                "Select reason...",
                "Dirty/scratched fiber",
                "Issue with terminated boot",
                "Splicing issue",
                "Break in fiber",
                "Unknown cause of high loss",
            ],
        )
        dialog.active_mapping_table.selectRow(0)
        dialog.begin_correction()
        self.assertEqual(dialog.mode_label.text(), "Mode: Mapping correction")
        self.assertEqual(
            [dialog.reason_combo.itemText(index) for index in range(dialog.reason_combo.count())],
            [
                "Select reason...",
                "Correction of previous mapping record",
                "Reversal to previous physical port",
                "Replacement changed again",
                "Other correction",
            ],
        )
        dialog.reason_combo.setCurrentIndex(
            dialog.reason_combo.findText("Reversal to previous physical port")
        )
        with patch("ui.database_replacements.QMessageBox.warning"):
            dialog.queue_replacement()
        self.assertEqual(
            dialog._pending[1].reason,
            "Reversal to previous physical port",
        )
        dialog.close()

    def test_queue_uses_one_authoritative_record_per_logical_channel(self):
        dialog = DatabaseReplacementDialog(self.model())
        dialog.proposed_port_spin.setValue(6)
        dialog.reason_combo.setCurrentIndex(
            dialog.reason_combo.findText("Splicing issue")
        )
        dialog.queue_replacement()

        dialog.proposed_port_spin.setValue(5)
        dialog.reason_combo.setCurrentIndex(
            dialog.reason_combo.findText("Break in fiber")
        )
        with patch(
            "ui.database_replacements.QMessageBox.question",
            return_value=QMessageBox.Yes,
        ):
            dialog.queue_replacement()

        self.assertEqual(dialog.pending_table.rowCount(), 1)
        self.assertEqual(tuple(dialog._pending), (1,))
        self.assertEqual(dialog._pending[1].replacement_physical_port, 5)
        dialog.accept_changes()
        self.assertEqual(len(dialog.replacement_requests), 1)
        self.assertEqual(dialog.replacement_requests[0].replacement_physical_port, 5)
        dialog.close()

    def test_manual_replacement_derives_latest_effective_port_and_saves_details(self):
        dialog = DatabaseReplacementDialog(self.model())
        dialog.logical_channel_combo.setCurrentIndex(
            dialog.logical_channel_combo.findData(1)
        )
        dialog.proposed_port_spin.setValue(6)
        dialog.reason_combo.setCurrentIndex(
            dialog.reason_combo.findText("Splicing issue")
        )
        dialog.operator_edit.setText("JS")
        dialog.details_edit.setText("Operator-supplied details")
        dialog.queue_replacement()
        dialog.accept_changes()

        self.assertEqual(dialog.result(), QDialog.Accepted)
        request = dialog.replacement_requests[0]
        self.assertEqual(request.logical_channel, 1)
        self.assertEqual(request.replacement_physical_port, 6)
        self.assertEqual(request.notes, "Operator-supplied details")
        self.assertEqual(request.replaced_by, "JS")
        dialog.close()

    def test_save_does_not_require_physical_completion_confirmation(self):
        dialog = DatabaseReplacementDialog(self.model())
        dialog.proposed_port_spin.setValue(6)
        dialog.reason_combo.setCurrentIndex(
            dialog.reason_combo.findText("Dirty/scratched fiber")
        )
        dialog.queue_replacement()
        dialog.accept_changes()
        self.assertEqual(dialog.result(), QDialog.Accepted)

        self.assertEqual(dialog.spare_table.item(0, 0).checkState(), Qt.Checked)
        self.assertEqual(dialog.spare_table.item(1, 0).checkState(), Qt.Checked)
        self.assertEqual(dialog.spares_to_designate, (6,))
        self.assertEqual(dialog.spares_to_undesignate, ())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
