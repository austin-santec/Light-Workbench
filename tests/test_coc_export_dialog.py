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


def run(run_number, count):
    return CocSourceRun(
        run_number,
        Path("Run-%d.csv" % run_number),
        tuple(
            MeasurementRecord(channel, 1.0, 1.1, channel)
            for channel in range(1, count + 1)
        ),
        {
            "Main board serial": "123",
            "Part number": "OSX-150-1A-036-09-FA-00B-2H",
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
            initial_channel_count=36,
            current_run_path=partial.source_path,
        )
        self.assertEqual(dialog.base_run.run_number, 1)
        self.assertEqual(dialog.base_run_combo.currentText(), "Run 1 — 36 written readings")
        self.assertTrue(dialog.use_supplemental_checkbox.isChecked())
        self.assertEqual(dialog.supplemental_run.run_number, 2)
        self.assertIn("Required front-panel channels: 36", dialog.summary.toPlainText())
        dialog.close()

    def test_summary_updates_when_front_panel_count_changes(self):
        dialog = CocExportDialog(
            [CocRunOption(run(1, 2))],
            lambda base, count, supplemental: prepare_coc(
                base, count, supplemental_run=supplemental
            ),
            initial_channel_count=1,
        )

        self.assertIn("Missing channels: None", dialog.summary.toPlainText())
        dialog.channel_count_spin.setValue(3)
        self.assertIn("Missing channels: 3", dialog.summary.toPlainText())
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
            initial_channel_count=2,
        )

        self.assertEqual(dialog.base_run.run_number, 1)
        dialog.close()

    def test_successful_validation_accepts_dialog(self):
        dialog = CocExportDialog(
            [CocRunOption(run(1, 1))],
            lambda base, count, supplemental: prepare_coc(
                base, count, supplemental_run=supplemental
            ),
            initial_channel_count=1,
        )

        dialog._validate_and_accept()

        self.assertEqual(dialog.result(), dialog.Accepted)

    def test_supplemental_controls_can_be_hidden_from_preparation(self):
        dialog = CocExportDialog(
            [CocRunOption(run(1, 1)), CocRunOption(run(2, 1))],
            lambda base, count, supplemental: prepare_coc(
                base, count, supplemental_run=supplemental
            ),
            initial_channel_count=1,
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
            initial_channel_count=2,
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
            initial_channel_count=1,
        )

        dialog.prepare_callback = lambda *_args: (_ for _ in ()).throw(
            RuntimeError("repository unavailable")
        )
        dialog.refresh_summary()
        self.assertIsInstance(dialog.preparation_error, RuntimeError)
        self.assertIn("repository unavailable", dialog.summary.toPlainText())
        self.assertFalse(dialog.write_button.isEnabled())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
