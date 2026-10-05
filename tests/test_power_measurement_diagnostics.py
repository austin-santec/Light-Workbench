import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QWidget

from hardware.session import OpticalTestSession
from ui.power_measurement_diagnostics import PowerMeasurementDiagnosticsDialog


class FakeMeter:
    instances = []

    def __init__(self):
        self.description = "Fake OP815"
        self.usb_serial = "fake-meter"
        self.connected = False
        self.closed = False
        self.diagnostic_verification = False
        self.__class__.instances.append(self)

    def connect(self):
        self.connected = True

    def measure_both_wavelengths(self):
        if not self.connected:
            raise RuntimeError("Fake meter is not connected.")
        return {1310: -0.9400, 1550: -0.5000}

    def measure_reference_wavelengths(self):
        if not self.connected:
            raise RuntimeError("Fake meter is not connected.")
        return {1310: -0.0400, 1550: 0.1400}

    def set_diagnostic_verification(self, enabled):
        self.diagnostic_verification = bool(enabled)

    def close(self):
        self.connected = False
        self.closed = True


class FakeSwitch:
    instances = []

    def __init__(self):
        self.connected = False
        self.closed = False
        self.selected = []
        self.__class__.instances.append(self)

    def connect(self):
        self.connected = True

    def configured_channel_count(self):
        return 4

    def set_channel(self, channel):
        if not self.connected:
            raise RuntimeError("Fake switch is not connected.")
        self.selected.append(channel)
        return channel + 100

    def close(self):
        self.connected = False
        self.closed = True


class IncompleteFakeMeter(FakeMeter):
    def measure_both_wavelengths(self):
        return {1310: -0.9400}


class DarkReferenceMeter(FakeMeter):
    def measure_reference_wavelengths(self):
        return {1310: -45.23, 1550: -41.0}


class BlockedMeasurementMeter(FakeMeter):
    def measure_both_wavelengths(self):
        raise RuntimeError("Requested 1310 nm, but the ILM selected 1550 nm.")


class PowerMeasurementDiagnosticsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        FakeMeter.instances.clear()
        FakeSwitch.instances.clear()

    @staticmethod
    def wait_for(condition, timeout=500):
        elapsed = 0
        while not condition() and elapsed < timeout:
            QTest.qWait(25)
            elapsed += 25
        return condition()

    def create_dialog(self):
        return PowerMeasurementDiagnosticsDialog(
            meter_factory=FakeMeter,
            switch_factory=FakeSwitch,
            reference_1310=-0.04,
            reference_1550=0.14,
        )

    def test_meter_is_optional_until_operator_connects_it(self):
        dialog = self.create_dialog()

        self.assertEqual(FakeMeter.instances, [])
        self.assertFalse(dialog.read_button.isEnabled())
        dialog.close()

    def test_variation_analysis_is_right_side_and_toggleable(self):
        dialog = self.create_dialog()

        self.assertTrue(dialog.variation_analysis_visible)
        self.assertEqual(dialog.analysis_splitter.widget(1), dialog.variation_analysis_panel)
        self.assertIsNotNone(dialog.analysis_scroll_area.widget())
        self.assertEqual(dialog.toggle_analysis_button.text(), "Hide Variation Analysis")

        dialog.analysis_results_label.setText("Analysis remains available")
        QTest.mouseClick(dialog.toggle_analysis_button, Qt.LeftButton)
        self.assertFalse(dialog.variation_analysis_visible)
        self.assertTrue(dialog.variation_analysis_panel.isHidden())
        self.assertEqual(dialog.toggle_analysis_button.text(), "Show Variation Analysis")

        QTest.mouseClick(dialog.toggle_analysis_button, Qt.LeftButton)
        self.assertTrue(dialog.variation_analysis_visible)
        self.assertFalse(dialog.variation_analysis_panel.isHidden())
        self.assertEqual(dialog.analysis_results_label.text(), "Analysis remains available")
        dialog.close()

    def test_variation_analysis_uses_light_and_dark_theme_colors(self):
        light_parent = QWidget()
        light_parent.dark_mode_enabled = False
        light_dialog = PowerMeasurementDiagnosticsDialog(
            parent=light_parent,
            meter_factory=FakeMeter,
            switch_factory=FakeSwitch,
        )
        self.assertIn("#f7f8f9", light_dialog.analysis_scroll_area.styleSheet())
        self.assertIn("#202124", light_dialog.analysis_results_label.styleSheet())
        light_dialog.close()
        light_parent.close()

        dark_parent = QWidget()
        dark_parent.dark_mode_enabled = True
        dark_dialog = PowerMeasurementDiagnosticsDialog(
            parent=dark_parent,
            meter_factory=FakeMeter,
            switch_factory=FakeSwitch,
        )
        self.assertIn("#2b2e33", dark_dialog.analysis_scroll_area.styleSheet())
        self.assertIn("#e8eaed", dark_dialog.analysis_results_label.styleSheet())
        self.assertIn(
            "#2b2e33", dark_dialog.analysis_scroll_area.viewport().styleSheet()
        )
        self.assertIn(
            "background-color: #e60013",
            dark_dialog.analysis_scroll_area.widget().styleSheet(),
        )
        dark_dialog.close()
        dark_parent.close()

    def test_reads_show_raw_power_exact_math_and_history_without_files(self):
        dialog = self.create_dialog()
        with tempfile.TemporaryDirectory() as output_dir:
            before = set(os.listdir(output_dir))
            QTest.mouseClick(dialog.connect_meter_button, Qt.LeftButton)
            self.assertTrue(self.wait_for(lambda: dialog.meter_connected))

            self.assertIsInstance(
                dialog.meter_controller.worker.hardware_session,
                OpticalTestSession,
            )
            QTest.mouseClick(dialog.read_button, Qt.LeftButton)
            self.assertTrue(self.wait_for(lambda: dialog.history_table.rowCount() == 1))

            self.assertEqual(
                dialog.current_labels[1310]["measured"].text(), "-0.9400 dBm"
            )
            self.assertEqual(
                dialog.current_labels[1310]["calculation"].text(),
                "(-0.04) - (-0.9400) = 0.9000 dB",
            )
            self.assertEqual(
                dialog.current_labels[1550]["calculation"].text(),
                "0.14 - (-0.5000) = 0.6400 dB",
            )
            self.assertEqual(dialog.history_table.item(0, 4).text(), "-0.9400")
            self.assertEqual(dialog.history_table.item(0, 9).text(), "0.6400")
            self.assertEqual(dialog.history_table.item(0, 10).text(), "Manual")
            self.assertEqual(set(os.listdir(output_dir)), before)

            dialog.reference_1310_spin.setValue(0.00)
            dialog.reference_1550_spin.setValue(0.00)
            QTest.mouseClick(dialog.read_button, Qt.LeftButton)
            self.assertTrue(self.wait_for(lambda: dialog.history_table.rowCount() == 2))
            self.assertEqual(dialog.history_table.item(0, 5).text(), "-0.04")
            self.assertEqual(dialog.history_table.item(1, 5).text(), "0.00")

        meter = FakeMeter.instances[0]
        dialog.close()
        self.assertTrue(meter.closed)

    def test_analysis_buttons_separate_manual_and_monitoring_readings(self):
        dialog = self.create_dialog()
        QTest.mouseClick(dialog.connect_meter_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: dialog.meter_connected))

        for _ in range(2):
            QTest.mouseClick(dialog.read_button, Qt.LeftButton)
            self.assertTrue(
                self.wait_for(lambda: not dialog.read_pending)
            )
        self.assertTrue(dialog.analyze_repeatability_button.isEnabled())
        self.assertFalse(dialog.analyze_stability_button.isEnabled())
        QTest.mouseClick(dialog.analyze_repeatability_button, Qt.LeftButton)
        self.assertIn("Repeatability Analysis", dialog.analysis_results_label.text())
        self.assertIn("Samples: 2 (manual readings)", dialog.analysis_results_label.text())
        QTest.mouseClick(dialog.copy_analysis_button, Qt.LeftButton)
        self.assertIn(
            "Repeatability Analysis",
            QApplication.clipboard().text(),
        )

        QTest.mouseClick(dialog.start_monitor_button, Qt.LeftButton)
        self.assertTrue(
            self.wait_for(
                lambda: sum(
                    reading.method == "Monitoring" for reading in dialog.history
                )
                >= 2,
                timeout=1200,
            )
        )
        QTest.mouseClick(dialog.stop_monitor_button, Qt.LeftButton)
        QTest.mouseClick(dialog.analyze_stability_button, Qt.LeftButton)
        self.assertIn("Stability Analysis", dialog.analysis_results_label.text())
        self.assertIn("monitoring readings", dialog.analysis_results_label.text())
        dialog.close()

    def test_analysis_with_one_sample_shows_clear_message(self):
        dialog = self.create_dialog()
        QTest.mouseClick(dialog.connect_meter_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: dialog.meter_connected))
        self.assertTrue(FakeMeter.instances[0].diagnostic_verification)
        QTest.mouseClick(dialog.read_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: not dialog.read_pending))

        with patch(
            "ui.power_measurement_diagnostics.QMessageBox.information"
        ) as information:
            QTest.mouseClick(dialog.analyze_repeatability_button, Qt.LeftButton)

        information.assert_called_once()
        self.assertIn("at least two", dialog.status_label.text())
        dialog.close()

    def test_partial_two_wavelength_reading_is_not_added_to_history(self):
        dialog = PowerMeasurementDiagnosticsDialog(
            meter_factory=IncompleteFakeMeter,
            switch_factory=FakeSwitch,
        )
        QTest.mouseClick(dialog.connect_meter_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: dialog.meter_connected))
        QTest.mouseClick(dialog.read_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: not dialog.read_pending))
        self.assertEqual(dialog.history_table.rowCount(), 0)
        self.assertEqual(dialog.current_labels[1310]["measured"].text(), "-")
        dialog.close()

    def test_blocked_measurement_is_not_added_to_history_or_monitoring(self):
        dialog = PowerMeasurementDiagnosticsDialog(
            meter_factory=BlockedMeasurementMeter,
            switch_factory=FakeSwitch,
        )
        QTest.mouseClick(dialog.connect_meter_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: dialog.meter_connected))
        QTest.mouseClick(dialog.read_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: not dialog.read_pending))
        self.assertFalse(dialog.monitoring_active)
        self.assertEqual(dialog.history_table.rowCount(), 0)
        self.assertEqual(dialog.history, [])
        dialog.close()

    def test_reference_calculation_is_local_until_operator_applies_it(self):
        dialog = self.create_dialog()
        applied = []
        dialog.references_changed.connect(lambda first, second: applied.append((first, second)))
        QTest.mouseClick(dialog.connect_meter_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: dialog.meter_connected))

        QTest.mouseClick(dialog.calculate_reference_button, Qt.LeftButton)
        self.assertTrue(
            self.wait_for(lambda: dialog.reference_progress is None)
        )
        self.assertAlmostEqual(dialog.reference_1310_spin.value(), -0.04)
        self.assertAlmostEqual(dialog.reference_1550_spin.value(), 0.14)
        self.assertEqual(applied, [])

        QTest.mouseClick(dialog.apply_reference_button, Qt.LeftButton)
        self.assertEqual(applied, [(-0.04, 0.14)])
        dialog.close()

    def test_dark_reference_is_not_available_for_application(self):
        dialog = PowerMeasurementDiagnosticsDialog(
            meter_factory=DarkReferenceMeter,
            switch_factory=FakeSwitch,
        )
        QTest.mouseClick(dialog.connect_meter_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: dialog.meter_connected))

        QTest.mouseClick(dialog.calculate_reference_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: not dialog.reference_pending))
        self.assertIn("below the expected signal level", dialog.status_label.text())

        dialog.last_reference_measurements = {1310: -45.23, 1550: -41.0}
        with patch("ui.power_measurement_diagnostics.QMessageBox.warning") as warning:
            dialog.apply_references()

        warning.assert_called_once()
        self.assertEqual(dialog.last_reference_measurements[1310], -45.23)
        dialog.close()

    def test_optional_switch_routes_channel_without_being_required_for_meter_reading(self):
        dialog = self.create_dialog()
        QTest.mouseClick(dialog.connect_switch_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: dialog.switch_connected))
        self.assertEqual(dialog.channel_spin.maximum(), 4)

        dialog.channel_spin.setValue(3)
        QTest.mouseClick(dialog.set_channel_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: dialog.last_physical_port == 103))
        self.assertEqual(FakeSwitch.instances[0].selected, [3])
        self.assertEqual(dialog.physical_port_label.text(), "103")

        dialog.close()
        self.assertTrue(FakeSwitch.instances[0].closed)

    def test_previous_and_next_route_the_adjacent_logical_channels(self):
        dialog = self.create_dialog()
        QTest.mouseClick(dialog.connect_switch_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: dialog.switch_connected))

        dialog.channel_spin.setValue(2)
        QTest.mouseClick(dialog.set_channel_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: dialog.last_physical_port == 102))
        QTest.mouseClick(dialog.next_channel_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: dialog.last_physical_port == 103))
        QTest.mouseClick(dialog.previous_channel_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: dialog.last_physical_port == 102))
        self.assertEqual(FakeSwitch.instances[0].selected, [2, 3, 2])
        dialog.close()

    def test_no_readings_leave_history_empty_and_do_not_create_output(self):
        dialog = self.create_dialog()
        with tempfile.TemporaryDirectory() as output_dir:
            before = set(os.listdir(output_dir))
            self.assertEqual(dialog.history_table.rowCount(), 0)
            self.assertFalse(dialog.clear_history_button.isEnabled())
            self.assertEqual(set(os.listdir(output_dir)), before)
        dialog.close()

    def test_history_can_be_exported_as_csv_or_json(self):
        dialog = self.create_dialog()
        QTest.mouseClick(dialog.connect_meter_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: dialog.meter_connected))
        QTest.mouseClick(dialog.read_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: not dialog.read_pending))

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "history.csv"
            with patch(
                "ui.power_measurement_diagnostics.QFileDialog.getSaveFileName",
                return_value=(str(csv_path), "CSV Files (*.csv)"),
            ), patch.object(dialog, "_ask_trace_export", return_value=False):
                QTest.mouseClick(dialog.export_history_button, Qt.LeftButton)
            self.assertIn("Method", csv_path.read_text(encoding="utf-8-sig"))

            json_path = Path(directory) / "history.json"
            with patch(
                "ui.power_measurement_diagnostics.QFileDialog.getSaveFileName",
                return_value=(str(json_path), "JSON Files (*.json)"),
            ), patch.object(dialog, "_ask_trace_export", return_value=False):
                QTest.mouseClick(dialog.export_history_button, Qt.LeftButton)
            self.assertIn("readings", json_path.read_text(encoding="utf-8"))

        dialog.close()

    def test_history_export_can_include_optional_hardware_trace(self):
        dialog = self.create_dialog()
        QTest.mouseClick(dialog.connect_meter_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: dialog.meter_connected))
        QTest.mouseClick(dialog.read_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: not dialog.read_pending))
        dialog.trace_recorder.record(
            {
                "event": "read_power",
                "measurement_id": 1,
                "method": "Manual",
                "raw_power_dbm": -0.94,
            }
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.csv"
            with patch(
                "ui.power_measurement_diagnostics.QFileDialog.getSaveFileName",
                return_value=(str(path), "CSV Files (*.csv)"),
            ), patch.object(dialog, "_ask_trace_export", return_value=True):
                QTest.mouseClick(dialog.export_history_button, Qt.LeftButton)

            trace_path = Path(directory) / "history-hardware-trace.csv"
            self.assertTrue(trace_path.exists())
            self.assertIn("read_power", trace_path.read_text(encoding="utf-8-sig"))

        dialog.close()

    def test_monitoring_can_be_stopped_and_does_not_change_persistence(self):
        dialog = self.create_dialog()
        QTest.mouseClick(dialog.connect_meter_button, Qt.LeftButton)
        self.assertTrue(self.wait_for(lambda: dialog.meter_connected))
        QTest.mouseClick(dialog.start_monitor_button, Qt.LeftButton)
        self.assertTrue(dialog.monitoring_active)
        self.assertFalse(dialog.live_indicator.isHidden())
        QTest.mouseClick(dialog.stop_monitor_button, Qt.LeftButton)
        self.assertFalse(dialog.monitoring_active)
        self.assertTrue(dialog.live_indicator.isHidden())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
