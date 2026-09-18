import csv
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from run_data import MeasurementRecord
from run_persistence import (
    RunRecorder,
    build_run_directory_name,
    load_run_json,
)


class RunPersistenceTests(unittest.TestCase):
    def test_run_directory_name_uses_optional_serials_in_requested_order(self):
        now = datetime(2026, 9, 16, 11, 26)
        self.assertEqual(
            build_run_directory_name(
                {
                    "Main board serial": "17688",
                    "Switch serial": "12345678901",
                },
                now,
            ),
            "ILM-Run_260916_1126_17688-12345678901",
        )
        self.assertEqual(
            build_run_directory_name({"Main board serial": "17688"}, now),
            "ILM-Run_260916_1126_17688",
        )
        self.assertEqual(
            build_run_directory_name({"Switch serial": "SW/123"}, now),
            "ILM-Run_260916_1126_SW-123",
        )
        self.assertEqual(
            build_run_directory_name({}, now),
            "ILM-Run_260916_1126",
        )

    def test_save_writes_csv_json_and_attempt_history(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = RunRecorder(
                root=directory,
                metadata={"Mode": "Simulation", "Operating band": "O band"},
                limit=2.0,
            )
            rows = [MeasurementRecord(1, 1.5, 1.6, 1)]
            recorder.record_attempt(1, 1.5, 1.6, 1)
            recorder.save(rows)
            recorder.record_attempt(1, 1.7, 1.8, 1, retest=True)
            recorder.replacement_analysis = {"applicable": False}
            recorder.save([MeasurementRecord(1, 1.7, 1.8, 1)])

            self.assertTrue(recorder.csv_path.is_file())
            self.assertTrue(recorder.json_path.is_file())
            payload = load_run_json(recorder.json_path)
            self.assertEqual(payload["warning_limit_db"], 2.0)
            self.assertEqual(payload["measurements"][0]["physical_port"], 1)
            self.assertEqual(payload["replacement_analysis"]["applicable"], False)
            self.assertEqual(len(payload["attempts"]), 2)
            self.assertTrue(payload["attempts"][1]["retest"])
            with recorder.csv_path.open(newline="", encoding="utf-8") as csv_file:
                csv_rows = list(csv.reader(csv_file))
            self.assertEqual(csv_rows[1][:3], ["1", "1.7000", "1.8000"])

    def test_new_run_does_not_create_output_until_measurement_is_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = RunRecorder(
                root=Path(directory) / "ILM-Reads",
                metadata={"Mode": "Real hardware"},
            )

            self.assertFalse(recorder.directory.exists())
            recorder.record_attempt(1, 1.5, 1.6, 1)
            recorder.save([])
            self.assertFalse(recorder.directory.exists())
            self.assertFalse(recorder.csv_path.exists())
            self.assertFalse(recorder.json_path.exists())

            recorder.save([MeasurementRecord(1, 1.5, 1.6, 1)])
            self.assertTrue(recorder.directory.is_dir())
            self.assertTrue(recorder.csv_path.is_file())
            self.assertTrue(recorder.json_path.is_file())


if __name__ == "__main__":
    unittest.main()
