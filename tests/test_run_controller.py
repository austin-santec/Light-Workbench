import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEventLoop, QTimer
from PyQt5.QtWidgets import QApplication

from application.run_controller import HardwareRunController, HardwareRunRequest
from domain.models import RunState


class FakeMeter:
    description = "Fake meter"
    usb_serial = "METER-1"

    def connect(self):
        pass

    def measure_both_wavelengths(self):
        return {1310: -1.0, 1550: -1.1}

    def measure_reference_wavelengths(self):
        return self.measure_both_wavelengths()

    def close(self):
        pass


class FakeSwitch:
    def connect(self):
        pass

    def configured_channel_count(self):
        return 1

    def set_channel(self, channel):
        return channel

    def close(self):
        pass


class RunControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_controller_owns_run_thread_and_returns_to_idle_after_completion(self):
        controller = HardwareRunController()
        self.assertFalse(controller.is_active)
        states = []
        completed = []
        thread_finished = []
        controller.state_changed.connect(states.append)
        controller.completed.connect(lambda: completed.append(True))

        loop = QEventLoop()
        controller.thread_finished.connect(
            lambda: (thread_finished.append(True), loop.quit())
        )
        controller.operator_required.connect(
            lambda _channel, _port: controller.continue_current()
        )
        controller.reading_ready.connect(
            lambda *_values: controller.write_current()
        )

        controller.start(
            HardwareRunRequest(
                power_meter_factory=FakeMeter,
                switch_factory=FakeSwitch,
                channels=[1],
                reference_powers={1310: 0.72, 1550: 0.28},
            )
        )

        self.assertTrue(controller.is_active)

        QTimer.singleShot(3000, loop.quit)
        loop.exec_()

        self.assertEqual(completed, [True])
        self.assertEqual(thread_finished, [True])
        self.assertEqual(controller.state, RunState.IDLE)
        self.assertIn(RunState.STARTING, states)
        self.assertIn(RunState.WAITING_FOR_CABLE, states)
        self.assertIn(RunState.READY_TO_WRITE, states)
        self.assertIn(RunState.COMPLETED, states)


if __name__ == "__main__":
    unittest.main()
