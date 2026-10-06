import os
import threading
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEventLoop, QTimer
from PyQt5.QtWidgets import QApplication

from application.part_number_lookup import (
    PartNumberLookupController,
    classify_part_lookup_error,
)


class PartNumberLookupControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_lookup_runs_off_ui_thread_and_emits_success(self):
        ui_thread_id = threading.get_ident()
        lookup_thread_ids = []

        def lookup(serial, root):
            lookup_thread_ids.append(threading.get_ident())
            self.assertEqual(serial, "12345")
            self.assertEqual(root, Path("lookup-root"))
            return "OSX-150-PART"

        controller = PartNumberLookupController(lookup)
        result = []
        loop = QEventLoop()
        controller.succeeded.connect(
            lambda *values: (result.append(values), loop.quit())
        )
        QTimer.singleShot(3000, loop.quit)

        request_id = controller.start("12345", Path("lookup-root"))
        loop.exec_()

        self.assertEqual(result, [(request_id, "12345", "OSX-150-PART")])
        self.assertNotEqual(lookup_thread_ids[0], ui_thread_id)
        controller.close()

    def test_lookup_failure_preserves_specific_category_and_message(self):
        def lookup(_serial, _root):
            raise FileNotFoundError("Lookup folder unavailable")

        controller = PartNumberLookupController(lookup)
        result = []
        loop = QEventLoop()
        controller.failed.connect(lambda *values: (result.append(values), loop.quit()))
        QTimer.singleShot(3000, loop.quit)

        request_id = controller.start("12345", Path("missing"))
        loop.exec_()

        self.assertEqual(
            result,
            [
                (
                    request_id,
                    "12345",
                    "lookup_folder_unavailable",
                    "Lookup folder unavailable",
                )
            ],
        )
        controller.close()

    def test_error_categories_distinguish_existing_lookup_failures(self):
        self.assertEqual(
            classify_part_lookup_error(LookupError("No folder was found")),
            "no_matching_serial",
        )
        self.assertEqual(
            classify_part_lookup_error(LookupError("More than one folder was found")),
            "multiple_matches",
        )
        self.assertEqual(
            classify_part_lookup_error(
                LookupError("The matching folder does not contain a part number.")
            ),
            "missing_part_number",
        )
        self.assertEqual(
            classify_part_lookup_error(OSError("Access denied")),
            "filesystem_error",
        )


if __name__ == "__main__":
    unittest.main()
