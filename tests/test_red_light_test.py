import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest

from hardware.session import OpticalTestSession
from ui.red_light_test import RedLightTestDialog


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
        self.selected.append(channel)
        return channel + 100

    def close(self):
        self.closed = True


class RedLightTestDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        FakeSwitch.instances.clear()

    def test_menu_dialog_does_not_connect_until_start(self):
        dialog = RedLightTestDialog(switch_factory=FakeSwitch)

        self.assertEqual(FakeSwitch.instances, [])
        self.assertTrue(dialog.start_button.isEnabled())
        self.assertFalse(dialog.channel_spin.isEnabled())
        dialog.close()

    def test_start_selects_first_channel_and_navigation_works(self):
        dialog = RedLightTestDialog(switch_factory=FakeSwitch)
        QTest.mouseClick(dialog.start_button, 1)
        QTest.qWait(100)
        self.application.processEvents()

        switch = FakeSwitch.instances[0]
        self.assertIsInstance(
            dialog.red_controller.worker.hardware_session,
            OpticalTestSession,
        )
        self.assertTrue(switch.connected)
        self.assertEqual(switch.selected, [1])
        self.assertEqual(dialog.channel_spin.maximum(), 4)
        self.assertIn("Physical port 101", dialog.status_label.text())

        QTest.mouseClick(dialog.next_button, 1)
        QTest.qWait(100)
        self.application.processEvents()
        self.assertEqual(switch.selected, [1, 2])

        dialog.channel_spin.setValue(4)
        QTest.qWait(100)
        self.application.processEvents()
        self.assertEqual(switch.selected, [1, 2, 4])
        QTest.mouseClick(dialog.close_button, 1)
        self.application.processEvents()
        self.assertTrue(switch.closed)
        self.assertIsNone(dialog.red_controller.thread)

    def test_stop_disconnects_and_allows_restart(self):
        dialog = RedLightTestDialog(switch_factory=FakeSwitch)
        QTest.mouseClick(dialog.start_button, 1)
        QTest.qWait(100)
        first_switch = FakeSwitch.instances[0]
        QTest.mouseClick(dialog.stop_button, 1)
        self.assertTrue(first_switch.closed)
        self.assertTrue(dialog.start_button.isEnabled())
        self.assertFalse(dialog.channel_spin.isEnabled())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
