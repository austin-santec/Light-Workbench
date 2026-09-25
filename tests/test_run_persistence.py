import csv
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from run_data import MeasurementRecord
from run_persistence import (
    RunRecorder,
    build_run_csv_path,
    build_run_directory_name,
    find_run_json_path,
    load_run_json,
)
from infrastructure.run_persistence import RunRecorder as InfrastructureRunRecorder


class RunPersistenceTests(unittest.TestCase):
    def test_legacy_module_reexports_infrastructure_recorder(self):
        self.assertIs(RunRecorder, InfrastructureRunRecorder)

    def test_run_directory_name_uses_optional_serials_in_requested_order(self):
        now = datetime(2026, 9, 16, 11, 26, 53)
        self.assertEqual(
            build_run_directory_name(
                {
                    "Main board serial": "17688",
                    "Switch serial": "12345678901",
                },
                now,
            ),
            "ILM-Run_260916_112653_17688-12345678901",
        )
        self.assertEqual(
            build_run_directory_name({"Main board serial": "17688"}, now),
            "ILM-Run_260916_112653_17688",
        )
        self.assertEqual(
            build_run_directory_name({"Switch serial": "SW/123"}, now),
            "ILM-Run_260916_112653_SW-123",
        )
        self.assertEqual(
            build_run_directory_name({}, now),
            "ILM-Run_260916_112653",
        )

    def test_run_csv_uses_final_directory_name(self):
        directory = Path("ILM-Run_260916_112653_test1-test1")
        self.assertEqual(
            build_run_csv_path(directory),
            directory / "ILM-Run_260916_112653_test1-test1.csv",
        )

    def test_save_writes_measurements_without_derived_analysis_or_attempt_history(self):
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
            recorder.completed_replacements = [
                {
                    "current_port": 1,
                    "replacement_port": 49,
                }
            ]
            recorder.save([MeasurementRecord(1, 1.7, 1.8, 1)])

            self.assertTrue(recorder.csv_path.is_file())
            self.assertTrue(recorder.json_path.is_file())
            payload = load_run_json(recorder.json_path)
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["warning_limit_db"], 2.0)
            self.assertEqual(payload["measurements"][0]["physical_port"], 1)
            self.assertNotIn("replacement_analysis", payload)
            self.assertNotIn("completed_replacements", payload)
            self.assertNotIn("attempts", payload)
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
            self.assertEqual(
                recorder.csv_path.name,
                "%s.csv" % recorder.directory.name,
            )
            self.assertEqual(
                recorder.json_path.name,
                "%s.json" % recorder.directory.name,
            )
            self.assertTrue(recorder.json_path.is_file())

    def test_fixed_directory_recorder_writes_a_numbered_run_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            run_directory = Path(directory) / "Unit-17688" / "Run-2"
            recorder = RunRecorder(
                metadata={"Run number": "2", "Operating band": "C band"},
                directory=run_directory,
            )
            recorder.save([MeasurementRecord(1, 1.0, 1.1, 1)])

            self.assertEqual(recorder.csv_path, run_directory / "Run-2.csv")
            self.assertTrue((run_directory / "Run-2.csv").is_file())
            self.assertTrue((run_directory / "Run-2.json").is_file())

    def test_existing_legacy_run_json_remains_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "output.csv"
            legacy_json_path = Path(directory) / "run.json"
            csv_path.write_text("channel,1310 IL,1550 IL\n1,1.0,1.0\n", encoding="utf-8")
            legacy_json_path.write_text("{}\n", encoding="utf-8")

            self.assertEqual(find_run_json_path(csv_path), legacy_json_path)
            recorder = RunRecorder.from_existing(csv_path)
            self.assertEqual(recorder.json_path, legacy_json_path)

    def test_rename_for_metadata_updates_run_files_and_coc(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = RunRecorder(
                root=directory,
                metadata={
                    "Main board serial": "17688",
                    "Switch serial": "12345",
                    "COC output file": "COC OSX-150 17688.xlsx",
                    "COC output path": "placeholder",
                },
            )
            recorder.save([MeasurementRecord(1, 1.0, 1.1, 1)])
            coc_path = recorder.directory / "COC OSX-150 17688.xlsx"
            coc_path.write_bytes(b"test workbook")

            original_timestamp = recorder.directory.name.split("_")[1:3]
            updated_metadata = recorder.rename_for_metadata(
                {
                    "Main board serial": "17689",
                    "Switch serial": "67890",
                    "COC output file": "COC OSX-150 17688.xlsx",
                    "COC output path": str(coc_path),
                }
            )

            self.assertEqual(
                recorder.directory.name,
                "ILM-Run_%s_%s_17689-67890"
                % (original_timestamp[0], original_timestamp[1]),
            )
            self.assertTrue(recorder.csv_path.is_file())
            self.assertTrue(recorder.json_path.is_file())
            self.assertTrue(
                (recorder.directory / "COC OSX-150 17689.xlsx").is_file()
            )
            self.assertEqual(
                updated_metadata["COC output file"],
                "COC OSX-150 17689.xlsx",
            )
            self.assertEqual(
                updated_metadata["COC output path"],
                str(recorder.directory / "COC OSX-150 17689.xlsx"),
            )


if __name__ == "__main__":
    unittest.main()
