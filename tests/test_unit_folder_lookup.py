"""Unit-folder UI tests use fake searches and never launch File Explorer."""

import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QObject, QEventLoop, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication, QDialog

from application.part_number_lookup import UnitFolderLookupController
from ui.unit_folder_lookup import UnitFolderLookupDialog


class FakeLookup(QObject):
    succeeded = pyqtSignal(int, str, object)
    failed = pyqtSignal(int, str, str, str)

    def __init__(self):
        super().__init__()
        self.requests = []
        self.closed = False

    def start(self, serial, root, *, switch_model=None):
        self.requests.append((serial, root, switch_model))
        return len(self.requests)

    def close(self):
        self.closed = True


class UnitFolderLookupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def dialog(self, **kwargs):
        controller = FakeLookup()
        dialog = UnitFolderLookupDialog(
            lambda *_args: (), controller=controller, lookup_parent=Path("test-parent"),
            **kwargs,
        )
        self.addCleanup(dialog.close)
        return dialog, controller

    def test_prefill_and_model_hint_only_apply_to_connected_serial(self):
        dialog, controller = self.dialog(connected_serial="18761", connected_model="OSX-150")
        self.assertEqual(dialog.serial_edit.text(), "18761")
        dialog.open_folder()
        self.assertEqual(controller.requests[-1], ("18761", Path("test-parent"), "OSX-150"))
        dialog.serial_edit.setText("SN19243")
        dialog.open_folder()
        self.assertEqual(controller.requests[-1], ("19243", Path("test-parent"), None))

    def test_blank_serial_does_not_start_lookup(self):
        dialog, controller = self.dialog()
        self.assertEqual(dialog.serial_edit.text(), "")
        dialog.open_folder()
        self.assertEqual(controller.requests, [])
        self.assertIn("serial number", dialog.status_label.text())

    def test_single_result_opens_exact_directory(self):
        dialog, controller = self.dialog(connected_serial="18761")
        path = Path("test-parent/OSX-150/SN18761_OSX-150-1A-048-09-FA-00B-3H")
        dialog.open_folder()
        with patch("ui.unit_folder_lookup.QDesktopServices.openUrl", return_value=True) as launch:
            controller.succeeded.emit(1, "18761", (path,))
        self.assertEqual(launch.call_args.args[0].toLocalFile(), str(path).replace("\\", "/"))
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertTrue(controller.closed)

    def test_duplicates_require_explicit_selection(self):
        dialog, controller = self.dialog(connected_serial="18761")
        paths = (Path("OSX-100/SN18761_OSX-100-PART"), Path("OSX-150/SN18761_OSX-150-PART"))
        dialog.open_folder()
        with patch("ui.unit_folder_lookup.QDesktopServices.openUrl", return_value=True) as launch:
            controller.succeeded.emit(1, "18761", paths)
            self.assertFalse(dialog.open_button.isEnabled())
            dialog.open_folder()
            launch.assert_not_called()
            dialog.matches_list.setCurrentRow(1)
            dialog.open_folder()
        self.assertEqual(launch.call_args.args[0].toLocalFile(), str(paths[1]).replace("\\", "/"))

    def test_edit_and_cancel_ignore_late_results(self):
        dialog, controller = self.dialog(connected_serial="18761")
        dialog.open_folder()
        dialog.serial_edit.setText("19243")
        with patch("ui.unit_folder_lookup.QDesktopServices.openUrl") as launch:
            controller.succeeded.emit(1, "18761", (Path("stale"),))
            dialog.open_folder()
            dialog.reject()
            controller.succeeded.emit(2, "19243", (Path("closed"),))
        launch.assert_not_called()
        self.assertTrue(controller.closed)

    def test_search_and_explorer_errors_keep_dialog_available(self):
        dialog, controller = self.dialog(connected_serial="18761")
        dialog.open_folder()
        controller.failed.emit(1, "18761", "lookup_folder_unavailable", "Drive unavailable")
        self.assertIn("Drive unavailable", dialog.status_label.text())
        self.assertTrue(dialog.open_button.isEnabled())
        dialog.open_folder()
        with patch("ui.unit_folder_lookup.QDesktopServices.openUrl", return_value=False):
            controller.succeeded.emit(2, "18761", (Path("some-unit"),))
        self.assertIn("Could not open", dialog.status_label.text())
        self.assertTrue(dialog.open_button.isEnabled())
        self.assertFalse(controller.closed)

    def test_folder_controller_runs_search_off_ui_thread_and_preserves_paths(self):
        ui_thread = threading.get_ident()
        threads = []
        folders = (Path("OSX-100/unit"), Path("OSX-150/unit"))

        def lookup(serial, parent):
            threads.append(threading.get_ident())
            return folders

        controller = UnitFolderLookupController(lookup)
        self.addCleanup(controller.close)
        loop = QEventLoop()
        results = []
        controller.succeeded.connect(lambda *args: (results.append(args), loop.quit()))
        QTimer.singleShot(3000, loop.quit)
        request = controller.start("18761", "test-parent")
        loop.exec_()
        self.assertEqual(results, [(request, "18761", folders)])
        self.assertNotEqual(threads[0], ui_thread)


if __name__ == "__main__":
    unittest.main()
