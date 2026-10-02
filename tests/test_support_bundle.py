import hashlib
import json
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

from infrastructure.support_bundle import export_support_bundle, select_support_logs


class SupportBundleTests(unittest.TestCase):
    def test_date_selection_and_bundle_manifest_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logs = root / "logs"
            logs.mkdir()
            included = logs / "light-workbench-2026-10-02.jsonl"
            included.write_text('{"event":"included"}\n', encoding="utf-8")
            excluded = logs / "light-workbench-2026-09-30.jsonl"
            excluded.write_text('{"event":"excluded"}\n', encoding="utf-8")
            (logs / "run.json").write_text("production data", encoding="utf-8")
            (logs / "COC.xlsx").write_bytes(b"workbook")

            selected = select_support_logs(
                logs,
                date(2026, 10, 1),
                date(2026, 10, 2),
            )
            self.assertEqual(selected, [included])

            result = export_support_bundle(
                root / "bundle.zip",
                log_root=logs,
                start_date=date(2026, 10, 1),
                end_date=date(2026, 10, 2),
                application_name="Light Workbench",
                application_version="1.13.0",
                dependency_report="dependency report",
                configuration_summary={
                    "dark_mode": True,
                    "run_root": str(Path.home() / "Documents" / "ILM-Reads"),
                },
            )
            with zipfile.ZipFile(result.path) as archive:
                names = set(archive.namelist())
                self.assertIn("logs/" + included.name, names)
                self.assertNotIn("logs/" + excluded.name, names)
                self.assertNotIn("run.json", names)
                self.assertNotIn("COC.xlsx", names)
                self.assertIn("dependency-report.txt", names)
                self.assertIn("sanitized-configuration.json", names)
                self.assertIn("README.txt", names)
                configuration = json.loads(
                    archive.read("sanitized-configuration.json")
                )
                self.assertTrue(
                    configuration["run_root"].startswith("%USERPROFILE%")
                )
                manifest = json.loads(archive.read("manifest.json"))
                for entry in manifest["files"]:
                    self.assertEqual(
                        entry["sha256"],
                        hashlib.sha256(archive.read(entry["path"])).hexdigest(),
                    )

    def test_existing_destination_gets_collision_safe_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logs = root / "logs"
            logs.mkdir()
            destination = root / "support.zip"
            destination.write_bytes(b"existing")
            result = export_support_bundle(
                destination,
                log_root=logs,
                start_date=date(2026, 10, 2),
                end_date=date(2026, 10, 2),
                application_name="Light Workbench",
                application_version="1.13.0",
                dependency_report="ok",
                configuration_summary={},
            )
            self.assertEqual(result.path.name, "support-2.zip")
            self.assertEqual(destination.read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
