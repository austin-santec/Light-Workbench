import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from application.database_primary_workflow import DatabasePrimaryRunWorkflow
from domain.database_records import SwitchSpec, UnitSpec
from infrastructure.database.memory_repositories import InMemoryRepositories
from ilm_app import MainWindow


class _Ready:
    ready = True
    operator_message = "ready"


class DatabasePrimaryUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.repositories = InMemoryRepositories()
        self.workflow = DatabasePrimaryRunWorkflow(
            self.repositories,
            readiness_check=lambda: _Ready(),
        )
        self.context = self.workflow.start_new_run(
            unit_spec=UnitSpec(
                "MB-DB-1",
                "OSX-150-1A-002-09-FA-00B-3H",
                2,
                "OSX-150",
            ),
            switch_spec=SwitchSpec("SW-DB-1", "OSX-150", 4),
            installed_by="AT",
            initial_channel_map={1: 1, 2: 2},
            tested_by="AT",
            wavelength_mode="SM",
            operating_band="O band",
            application_version="test",
            measurement_hardware={
                "planned_channels": [1, 2],
                "opm_wavelengths_nm": [1310, 1550],
                "source_wavelengths_nm": [1310, 1550],
                "source_ids": [0, 1],
            },
            limit_snapshot={
                "model": "OSX-150",
                "wavelength_mode": "SM",
                "profile_name": "test",
                "revision": 1,
                "too_good_below_db": 0.5,
                "warning_enabled": True,
                "warning_above_db": 2.25,
                "fail_above_db": 2.5,
            },
            part_number_snapshot="OSX-150-1A-002-09-FA-00B-3H",
            front_panel_channel_count=2,
        )

    def _window(self):
        window = MainWindow(database_workflow=self.workflow)
        window._apply_database_run_context(self.context)
        window.active_run_reference_snapshot = {"snapshot_id": "ref-1"}
        return window

    def test_database_write_updates_ui_without_creating_file_recorder(self):
        window = self._window()
        window.run_repository.new_recorder = MagicMock(
            side_effect=AssertionError("file recorder must not be used")
        )
        window.hardware_pending_reading = (1, 1, 0.65, 0.50)

        self.assertTrue(window.commit_hardware_reading())

        current = self.repositories.current_for_run(self.context.run.run_id)
        self.assertEqual(len(current), 1)
        self.assertEqual(len(window.run_data.measurements), 1)
        self.assertIsNone(window.run_recorder)
        window.run_repository.new_recorder.assert_not_called()
        window.close()

    def test_failed_database_write_retains_pending_sample_and_does_not_advance(self):
        window = self._window()
        worker = MagicMock()
        window.hardware_worker = worker
        window.hardware_pending_reading = (1, 1, 0.65, 0.50)
        original_commit = self.workflow.commit_measurement
        self.workflow.commit_measurement = MagicMock(
            side_effect=RuntimeError("database offline")
        )

        with patch("ilm_app.QMessageBox.critical") as message:
            self.assertFalse(window._commit_and_advance_hardware())

        self.assertIsNotNone(window.database_pending_measurement)
        self.assertEqual(len(self.repositories.current_for_run(self.context.run.run_id)), 0)
        worker.write_current.assert_not_called()
        self.assertIn("still pending", message.call_args.args[2])
        self.workflow.commit_measurement = original_commit
        window.hardware_worker = None
        window.close()

    def test_load_run_uses_database_identity_and_does_not_upload_files(self):
        window = MainWindow(database_workflow=self.workflow)
        window.hardware_main_board_serial.setText("MB-DB-1")
        window.hardware_run_number.setValue(1)
        window.run_repository.load_csv = MagicMock(
            side_effect=AssertionError("numbered database load must not read CSV")
        )

        window.load_selected_unit_run()

        self.assertEqual(window.database_run_context.run.run_id, self.context.run.run_id)
        self.assertEqual(window.metadata_labels["Source file"].text(), "SQL Server")
        window.run_repository.load_csv.assert_not_called()
        window.close()


if __name__ == "__main__":
    unittest.main()
