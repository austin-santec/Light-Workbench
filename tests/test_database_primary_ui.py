import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from application.database_primary_workflow import DatabasePrimaryRunWorkflow
from domain.database_records import SwitchSpec, UnitSpec
from domain.models import PendingMeasurementToken, ProvisionalMeasurement
from infrastructure.database.memory_repositories import InMemoryRepositories
from ilm_app import MainWindow
from uuid import uuid4


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

    def _write(self, context, channel, first=0.65, second=0.50):
        pending = self.workflow.measurements.prepare_measurement(
            run_id=context.run.run_id,
            logical_channel=channel,
            physical_port=channel,
            wavelength_1_nm=1310,
            wavelength_1_il_db=first,
            wavelength_2_nm=1550,
            wavelength_2_il_db=second,
            reference_snapshot={"snapshot_id": "ref-1"},
            written_by="AT",
        )
        _record, refreshed = self.workflow.commit_measurement(pending)
        return refreshed

    def _start_second_run(self):
        self.workflow.finish_run(self.context.run.run_id, "complete")
        return self.workflow.start_new_run(
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

    def test_successful_database_write_acknowledges_the_same_pending_sample(self):
        window = self._window()
        worker = MagicMock()
        window.hardware_worker = worker
        window.hardware_pending_reading = (1, 1, 0.65, 0.50)

        self.assertTrue(window._commit_and_advance_hardware())

        worker.write_current.assert_called_once_with()
        worker.acknowledge_persisted_measurement.assert_called_once()
        acknowledgement = (
            worker.acknowledge_persisted_measurement.call_args.args[0]
        )
        self.assertEqual(acknowledgement.run_id, self.context.run.run_id)
        self.assertEqual(acknowledgement.logical_channel, 1)
        self.assertEqual(acknowledgement.physical_port, 1)
        window.hardware_worker = None
        window.close()

    def test_worker_accepted_payload_is_the_sample_committed_to_database(self):
        window = self._window()
        worker = MagicMock()
        window.hardware_worker = worker
        token = PendingMeasurementToken(
            operation_id="measurement-atomic",
            measurement_uuid=uuid4(),
            logical_channel=2,
            physical_port=2,
            run_id=self.context.run.run_id,
        )
        provisional = ProvisionalMeasurement(token, 0.65, 0.50)

        window.hardware_persistence_requested(provisional)

        current = self.repositories.current_for_run(self.context.run.run_id)
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].logical_channel, 2)
        self.assertAlmostEqual(float(current[0].wavelength_1_il_db), 0.65)
        self.assertAlmostEqual(float(current[0].wavelength_2_il_db), 0.50)
        worker.acknowledge_persisted_measurement.assert_called_once()
        window.hardware_worker = None
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
        worker.write_current.assert_called_once_with()
        worker.acknowledge_persisted_measurement.assert_not_called()
        self.assertIn("still pending", message.call_args.args[2])
        self.workflow.commit_measurement = original_commit
        window.hardware_worker = None
        window.close()

    def test_completion_reconciliation_blocks_complete_when_channels_are_missing(self):
        window = self._window()

        with patch("ilm_app.QMessageBox.warning") as message:
            window.hardware_completed()

        self.assertEqual(
            window.database_run_context.run.completion_status,
            "in_progress",
        )
        self.assertIn("Missing planned channels", window._run_completion_reason)
        message.assert_called_once()
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

    def test_loaded_context_publishes_comparison_and_coc_data_without_queries(self):
        self.context = self._write(self.context, 1)
        second = self._start_second_run()
        second = self._write(second, 2, 0.70, 0.60)
        loaded = self.workflow.load_run(second.run.run_id)
        guarded_workflow = MagicMock(wraps=self.workflow)
        window = MainWindow(database_workflow=guarded_workflow)

        timings = window._apply_database_run_context(loaded)

        self.assertEqual(window.comparison_run_combo.count(), 2)
        self.assertEqual(window.comparison_run_combo.itemText(1), "Run 1")
        self.assertEqual(
            window.comparison_run_combo.itemData(1),
            "database:%d" % self.context.run.run_id,
        )
        self.assertEqual(
            tuple(option.source.run_number for option in window._coc_run_options()),
            (1, 2),
        )
        self.assertIn("context_publication", timings)
        self.assertIn("status_composite", timings)
        guarded_workflow.assert_not_called()

        window.refresh_run_status()
        window.refresh_run_status()
        guarded_workflow.assert_not_called()

        window.comparison_run_combo.setCurrentIndex(1)
        guarded_workflow.load_run.assert_called_once_with(
            self.context.run.run_id,
            load_source="comparison",
        )
        window.close()

    def test_database_reports_action_opens_read_only_reporting_dialog(self):
        window = MainWindow(database_workflow=self.workflow)
        before = (
            len(self.repositories.runs),
            len(self.repositories.measurements),
            len(self.repositories.replacements),
        )

        with patch("ilm_app.DatabaseReportsDialog") as dialog_type:
            window.database_reports_action.trigger()

        dialog_type.assert_called_once_with(self.workflow.reporting, window)
        dialog_type.return_value.exec_.assert_called_once_with()
        self.assertEqual(
            before,
            (
                len(self.repositories.runs),
                len(self.repositories.measurements),
                len(self.repositories.replacements),
            ),
        )
        window.close()


if __name__ == "__main__":
    unittest.main()
