import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from application.coc_workflow import CocRunOption
from domain.coc_preparation import CocSourceRun, prepare_coc
from domain.models import MeasurementRecord
from ui.coc_export_dialog import CocExportDialog


CRITERIA = {
    "model": "OSX-150",
    "warning_enabled": True,
    "warning_above_db": 2.25,
    "fail_above_db": 2.5,
}


def run(run_number, count, front_panel_channel_count=36):
    return CocSourceRun(
        run_number,
        Path("Run-%d.csv" % run_number),
        tuple(
            MeasurementRecord(channel, 1.0, 1.1, channel)
            for channel in range(1, count + 1)
        ),
        {
            "Main board serial": "123",
            "Part number": "OSX-150-1A-%03d-09-FA-00B-2H"
            % front_panel_channel_count,
            "Switch serial": "456",
            "Operating band": "O band",
        },
        CRITERIA,
    )


class CocExportDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_fuller_run_is_default_base_and_current_partial_is_supplemental(self):
        full = run(1, 36)
        partial = run(2, 2)

        def prepare(base, count, supplemental):
            return prepare_coc(base, count, supplemental_run=supplemental)

        dialog = CocExportDialog(
            [CocRunOption(full), CocRunOption(partial)],
            prepare,
            current_run_path=partial.source_path,
        )
        self.assertEqual(dialog.base_run.run_number, 1)
        self.assertEqual(dialog.base_run_combo.currentText(), "Run 1 — 36 written readings")
        self.assertTrue(dialog.use_supplemental_checkbox.isChecked())
        self.assertEqual(dialog.supplemental_run.run_number, 2)
        self.assertFalse(hasattr(dialog, "channel_count_spin"))
        self.assertEqual(dialog.front_panel_count_label.text(), "36")
        self.assertIn("Required front-panel channels: 36", dialog.summary.toPlainText())
        dialog.close()

    def test_base_selection_updates_derived_front_panel_count(self):
        dialog = CocExportDialog(
            [
                CocRunOption(run(1, 2, front_panel_channel_count=2)),
                CocRunOption(run(2, 3, front_panel_channel_count=3)),
            ],
            lambda base, count, supplemental: prepare_coc(
                base, count, supplemental_run=supplemental
            ),
        )

        self.assertIn("Missing channels: None", dialog.summary.toPlainText())
        dialog.base_run_combo.setCurrentIndex(0)
        self.assertEqual(dialog.front_panel_count_label.text(), "2")
        dialog.base_run_combo.setCurrentIndex(1)
        self.assertEqual(dialog.front_panel_count_label.text(), "3")
        dialog.close()

    def test_default_base_prefers_compatible_run_before_greater_coverage(self):
        compatible = run(1, 1)
        incompatible_source = run(2, 2)
        incompatible = CocSourceRun(
            incompatible_source.run_number,
            incompatible_source.source_path,
            incompatible_source.measurements,
            incompatible_source.metadata,
            {**CRITERIA, "model": "OSX-100"},
        )
        dialog = CocExportDialog(
            [CocRunOption(compatible), CocRunOption(incompatible)],
            lambda base, count, supplemental: prepare_coc(
                base, count, supplemental_run=supplemental
            ),
        )

        self.assertEqual(dialog.base_run.run_number, 1)
        dialog.close()

    def test_successful_validation_accepts_dialog(self):
        dialog = CocExportDialog(
            [CocRunOption(run(1, 1, front_panel_channel_count=1))],
            lambda base, count, supplemental: prepare_coc(
                base, count, supplemental_run=supplemental
            ),
        )

        dialog._validate_and_accept()

        self.assertEqual(dialog.result(), dialog.Accepted)

    def test_supplemental_controls_can_be_hidden_from_preparation(self):
        dialog = CocExportDialog(
            [CocRunOption(run(1, 1)), CocRunOption(run(2, 1))],
            lambda base, count, supplemental: prepare_coc(
                base, count, supplemental_run=supplemental
            ),
        )
        dialog.use_supplemental_checkbox.setChecked(False)
        self.assertFalse(dialog.supplemental_run_combo.isEnabled())
        self.assertIsNone(dialog.supplemental_run)
        dialog.close()

    def test_blocked_validation_notifies_support_callback(self):
        blocked_results = []
        dialog = CocExportDialog(
            [CocRunOption(run(1, 1))],
            lambda base, count, supplemental: prepare_coc(
                base, count, supplemental_run=supplemental
            ),
            validation_blocked_callback=blocked_results.append,
        )

        with patch("ui.coc_export_dialog.QMessageBox.warning") as warning:
            dialog._validate_and_accept()

        self.assertEqual(blocked_results, [dialog.preparation_result])
        warning.assert_called_once()
        self.assertNotEqual(dialog.result(), dialog.Accepted)
        dialog.close()

    def test_unexpected_preparation_error_is_retained_for_workflow_boundary(self):
        dialog = CocExportDialog(
            [CocRunOption(run(1, 1))],
            lambda base, count, supplemental: prepare_coc(
                base, count, supplemental_run=supplemental
            ),
        )

        dialog.prepare_callback = lambda *_args: (_ for _ in ()).throw(
            RuntimeError("repository unavailable")
        )
        dialog.refresh_summary()
        self.assertIsInstance(dialog.preparation_error, RuntimeError)
        self.assertIn("repository unavailable", dialog.summary.toPlainText())
        self.assertFalse(dialog.write_button.isEnabled())
        dialog.close()

    def test_invalid_base_part_number_blocks_without_guessing(self):
        source = run(1, 2)
        source = CocSourceRun(
            source.run_number,
            source.source_path,
            source.measurements,
            {**source.metadata, "Part number": "not-a-part-number"},
            source.criteria,
        )
        dialog = CocExportDialog(
            [CocRunOption(source)],
            lambda base, count, supplemental: prepare_coc(
                base, count, supplemental_run=supplemental
            ),
        )

        self.assertEqual(dialog.front_panel_count_label.text(), "Unavailable")
        self.assertFalse(dialog.write_button.isEnabled())
        self.assertIn("part number", dialog.summary.toPlainText().lower())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
