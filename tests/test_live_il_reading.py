import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from hardware.session import OpticalTestSession
from ui.live_il_reading import LIVE_UPDATE_PAUSE_MS, LiveILReadingDialog


class FakeMeter:
    instances = []
    reference_measurements = 0

    def __init__(self):
        self.description = "Fake OP815"
        self.connected = False
        self.closed = False
        self.__class__.instances.append(self)

    def connect(self):
        self.connected = True

    def measure_both_wavelengths(self):
        if not self.connected:
            raise RuntimeError("Fake meter is not connected.")
        return {1310: 1.0, 1550: 1.1}

    def measure_reference_wavelengths(self):
        self.__class__.reference_measurements += 1
        return self.measure_both_wavelengths()

    def close(self):
        self.connected = False
        self.closed = True


class DisconnectedFakeMeter(FakeMeter):
    def connect(self):
        raise RuntimeError("No OP815/ILM was detected over USB.")


class LiveILReadingDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        FakeMeter.instances.clear()
        FakeMeter.reference_measurements = 0

    def test_live_updates_use_quarter_second_software_pause(self):
        self.assertEqual(LIVE_UPDATE_PAUSE_MS, 250)

    def test_meter_connects_only_after_start_and_reads_without_switch_or_files(self):
        dialog = LiveILReadingDialog(
            reference_1310=0.72,
            reference_1550=0.28,
            meter_factory=FakeMeter,
        )

        self.assertEqual(FakeMeter.instances, [])
        self.assertFalse(dialog.read_button.isEnabled())

        QTest.mouseClick(dialog.start_button, Qt.LeftButton)
        QTest.qWait(100)
        meter = FakeMeter.instances[0]
        self.assertIsInstance(dialog.worker.hardware_session, OpticalTestSession)
        self.assertTrue(meter.connected)
        self.assertTrue(dialog.read_button.isEnabled())
        self.assertTrue(dialog.calculate_reference_button.isEnabled())

        QTest.mouseClick(dialog.read_button, Qt.LeftButton)
        QTest.qWait(100)
        self.assertEqual(dialog.reading_1310_label.text(), "1310 nm IL: -0.2800 dB")
        self.assertEqual(dialog.reading_1550_label.text(), "1550 nm IL: -0.8200 dB")
        self.assertIn("No data was saved", dialog.status_label.text())

        QTest.mouseClick(dialog.calculate_reference_button, Qt.LeftButton)
        QTest.qWait(100)
        self.assertAlmostEqual(dialog.reference_1310_spin.value(), 1.00)
        self.assertAlmostEqual(dialog.reference_1550_spin.value(), 1.10)
        self.assertEqual(FakeMeter.reference_measurements, 1)
        self.assertIsNone(dialog.reference_progress)
        self.assertIn("Reference calculated", dialog.status_label.text())

        QTest.mouseClick(dialog.read_button, Qt.LeftButton)
        QTest.qWait(100)
        self.assertEqual(dialog.reading_1310_label.text(), "1310 nm IL: 0.0000 dB")

        dialog.close()
        QTest.qWait(100)
        self.assertTrue(meter.closed)

    def test_connection_failure_is_reported_and_worker_is_cleaned_up(self):
        dialog = LiveILReadingDialog(meter_factory=DisconnectedFakeMeter)

        QTest.mouseClick(dialog.start_button, Qt.LeftButton)
        QTest.qWait(150)

        self.assertIn("Connection failed", dialog.status_label.text())
        self.assertIsNone(dialog.worker)
        self.assertIsNone(dialog.thread)
        self.assertTrue(DisconnectedFakeMeter.instances[-1].closed)
        dialog.close()

    def test_reference_changes_can_be_shared_with_main_setup(self):
        dialog = LiveILReadingDialog(
            reference_1310=0.72,
            reference_1550=0.28,
            meter_factory=FakeMeter,
        )
        values = []
        dialog.references_changed.connect(lambda first, second: values.append((first, second)))

        dialog.reference_1310_spin.setValue(0.73)
        dialog.reference_1550_spin.setValue(0.29)

        self.assertEqual(values[-1], (0.73, 0.29))
        dialog.set_reference_values(0.81, 0.39)
        self.assertAlmostEqual(dialog.reference_1310_spin.value(), 0.81)
        self.assertAlmostEqual(dialog.reference_1550_spin.value(), 0.39)
        dialog.close()

    def test_repeatability_records_readings_and_updates_statistics_without_files(self):
        dialog = LiveILReadingDialog(
            reference_1310=0.72,
            reference_1550=0.28,
            meter_factory=FakeMeter,
        )
        QTest.mouseClick(dialog.start_button, Qt.LeftButton)
        QTest.qWait(100)

        QTest.mouseClick(dialog.repeatability_button, Qt.LeftButton)
        self.assertFalse(dialog.repeatability_box.isHidden())
        self.assertGreaterEqual(dialog.width(), 1000)
        self.assertGreaterEqual(dialog.height(), 650)
        self.assertTrue(dialog.repeatability_read_button.isEnabled())
        self.assertFalse(dialog.read_button.isEnabled())

        QTest.mouseClick(dialog.repeatability_read_button, Qt.LeftButton)
        QTest.qWait(100)
        self.assertEqual(dialog.repeatability_table.rowCount(), 1)
        self.assertEqual(
            dialog.repeatability_table.item(0, 1).text(), "-0.2800"
        )
        self.assertIn("Range: 0.0000 dB", dialog.repeatability_stats_1310_label.text())

        QTest.mouseClick(dialog.repeatability_read_button, Qt.LeftButton)
        QTest.qWait(100)
        self.assertEqual(dialog.repeatability_table.rowCount(), 2)

        QTest.mouseClick(dialog.repeatability_finish_button, Qt.LeftButton)
        self.assertFalse(dialog.repeatability_active)
        self.assertTrue(dialog.read_button.isEnabled())
        self.assertFalse(dialog.repeatability_read_button.isEnabled())
        dialog.close()
        QTest.qWait(100)

    def test_live_updates_toggle_indicator_and_stop_cleanly(self):
        dialog = LiveILReadingDialog(meter_factory=FakeMeter)
        QTest.mouseClick(dialog.start_button, Qt.LeftButton)
        QTest.qWait(100)

        self.assertTrue(dialog.live_update_indicator.isHidden())
        QTest.mouseClick(dialog.live_update_button, Qt.LeftButton)
        QTest.qWait(100)

        self.assertTrue(dialog.live_updates_active)
        self.assertFalse(dialog.live_update_indicator.isHidden())
        self.assertEqual(dialog.live_update_button.text(), "Stop Live Updates")

        QTest.mouseClick(dialog.live_update_button, Qt.LeftButton)
        self.assertFalse(dialog.live_updates_active)
        self.assertTrue(dialog.live_update_indicator.isHidden())
        self.assertEqual(dialog.live_update_button.text(), "Start Live Updates")
        dialog.close()
        QTest.qWait(100)

    def test_reference_controls_match_two_decimal_behavior(self):
        dialog = LiveILReadingDialog(reference_1310=0.72, reference_1550=0.28)

        for spin, value in (
            (dialog.reference_1310_spin, 0.72),
            (dialog.reference_1550_spin, 0.28),
        ):
            self.assertEqual(spin.decimals(), 2)
            self.assertAlmostEqual(spin.singleStep(), 0.01)
            spin.setValue(value)
            spin.stepUp()
            self.assertAlmostEqual(spin.value(), value + 0.01)
            spin.stepDown()
            self.assertAlmostEqual(spin.value(), value)
        dialog.close()

    def test_closing_active_dialog_disconnects_meter_without_stop_button(self):
        dialog = LiveILReadingDialog(meter_factory=FakeMeter)
        QTest.mouseClick(dialog.start_button, Qt.LeftButton)
        QTest.qWait(100)
        meter = FakeMeter.instances[0]

        dialog.close()
        QTest.qWait(100)

        self.assertTrue(meter.closed)
        self.assertIsNone(dialog.worker)
        self.assertIsNone(dialog.thread)

    def test_close_button_disconnects_after_opening_repeatability(self):
        dialog = LiveILReadingDialog(meter_factory=FakeMeter)
        QTest.mouseClick(dialog.start_button, Qt.LeftButton)
        QTest.qWait(100)
        QTest.mouseClick(dialog.repeatability_button, Qt.LeftButton)

        QTest.mouseClick(dialog.close_button, Qt.LeftButton)
        QTest.qWait(200)

        self.assertTrue(FakeMeter.instances[0].closed)
        self.assertIsNone(dialog.worker)
        self.assertIsNone(dialog.thread)
        self.assertEqual(dialog.live_controller._command_connections, [])

    def test_close_is_rejected_when_meter_shutdown_times_out(self):
        dialog = LiveILReadingDialog(meter_factory=FakeMeter)
        QTest.mouseClick(dialog.start_button, Qt.LeftButton)
        QTest.qWait(100)
        meter = FakeMeter.instances[0]

        original_stop_and_wait = dialog.live_controller.stop_and_wait
        dialog.live_controller.stop_and_wait = lambda: False
        close_event = QCloseEvent()
        with patch("ui.live_il_reading.QMessageBox.warning"):
            dialog.closeEvent(close_event)

        self.assertFalse(close_event.isAccepted())
        self.assertFalse(meter.closed)
        self.assertIsNotNone(dialog.live_controller.worker)
        self.assertIsNotNone(dialog.live_controller.thread)

        dialog.live_controller.stop_and_wait = original_stop_and_wait
        self.assertTrue(dialog._shutdown_worker())
        QTest.qWait(100)
        self.assertTrue(meter.closed)
        self.assertIsNone(dialog.live_controller.worker)
        self.assertIsNone(dialog.live_controller.thread)


if __name__ == "__main__":
    unittest.main()
