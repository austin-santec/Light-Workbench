import tempfile
import unittest
from pathlib import Path

from dependency_check import (
    FAIL,
    PASS,
    WARN,
    DependencyReport,
    check_op815,
    check_run_folder,
    check_visa,
)


class FakeResourceManager:
    def __init__(self, resources=()):
        self.resources = resources
        self.closed = False

    def list_resources(self):
        return self.resources

    def close(self):
        self.closed = True


class FakeMeter:
    def __init__(self, devices=()):
        self.devices = devices
        self.closed = False

    def find_devices(self):
        return self.devices

    def close(self):
        self.closed = True


class DependencyCheckTests(unittest.TestCase):
    def test_visa_check_loads_backend_and_closes_manager(self):
        manager = FakeResourceManager(("USB0::0x2428::0xD00D::INSTR",))

        result = check_visa(lambda: manager)

        self.assertEqual(result.status, PASS)
        self.assertIn("1 VISA resource", result.details)
        self.assertTrue(manager.closed)

    def test_visa_check_reports_backend_failure(self):
        result = check_visa(
            lambda: (_ for _ in ()).throw(RuntimeError("backend missing"))
        )

        self.assertEqual(result.status, FAIL)
        self.assertIn("backend missing", result.details)

    def test_op815_check_distinguishes_missing_device(self):
        meter = FakeMeter()

        result = check_op815(lambda: meter)

        self.assertEqual(result.status, WARN)
        self.assertIn("no OP815 device", result.details)
        self.assertTrue(meter.closed)

    def test_run_folder_check_writes_and_cleans_up_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            result = check_run_folder(Path(directory) / "ILM-Reads")

            self.assertEqual(result.status, PASS)
            self.assertTrue((Path(directory) / "ILM-Reads").is_dir())
            self.assertEqual(
                list((Path(directory) / "ILM-Reads").iterdir()), []
            )

    def test_report_contains_diagnostic_identity_only(self):
        report = DependencyReport(
            "2026-09-16T13:55:00-07:00",
            "TEST-COMPUTER",
            (),
        )

        text = report.as_text()

        self.assertIn("Checked: 2026-09-16T13:55:00-07:00", text)
        self.assertIn("Computer: TEST-COMPUTER", text)
        self.assertNotIn("COC", text)


if __name__ == "__main__":
    unittest.main()
