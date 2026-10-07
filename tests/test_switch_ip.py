import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from ui.switch_ip import SwitchIpAddressDialog


class SwitchIpDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_copy_button_copies_only_the_address(self):
        dialog = SwitchIpAddressDialog(
            "192.0.2.15",
            model="OSX-150",
            serial_number="SW-150",
        )

        dialog.copy_button.click()

        self.assertEqual(QApplication.clipboard().text(), "192.0.2.15")
        self.assertEqual(dialog.address_edit.text(), "192.0.2.15")
        dialog.close()


if __name__ == "__main__":
    unittest.main()
