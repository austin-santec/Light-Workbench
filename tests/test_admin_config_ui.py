import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from domain.extra_ports import ExtraChannelRoutingMethod
from domain.limit_profiles import default_limit_profiles
from infrastructure.limit_profile_repository import LimitProfileRepository
from ui.admin_config import AdminConfigDialog


class AdminConfigRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_extra_routing_control_is_only_shown_for_osx150(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = LimitProfileRepository(Path(directory) / "limits.ini")
            dialog = AdminConfigDialog(default_limit_profiles(), repository)
            try:
                self.assertEqual(dialog.model_combo.currentText(), "OSX-100")
                self.assertTrue(dialog.extra_routing_combo.isHidden())

                dialog.model_combo.setCurrentText("OSX-150")
                self.application.processEvents()

                self.assertFalse(dialog.extra_routing_combo.isHidden())
                self.assertEqual(
                    dialog.extra_routing_combo.currentData(),
                    ExtraChannelRoutingMethod.SCPI_MAPPED.value,
                )
            finally:
                dialog.close()

    def test_admin_dialog_saves_cli_direct_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = LimitProfileRepository(Path(directory) / "limits.ini")
            dialog = AdminConfigDialog(default_limit_profiles(), repository)
            dialog.model_combo.setCurrentText("OSX-150")
            index = dialog.extra_routing_combo.findData(
                ExtraChannelRoutingMethod.CLI_DIRECT.value
            )
            dialog.extra_routing_combo.setCurrentIndex(index)

            dialog._save_selected()

            self.assertEqual(
                repository.load_extra_channel_routing_method(),
                ExtraChannelRoutingMethod.CLI_DIRECT,
            )


if __name__ == "__main__":
    unittest.main()
