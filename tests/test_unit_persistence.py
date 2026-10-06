import tempfile
import unittest
from pathlib import Path

from unit_persistence import (
    available_run_numbers,
    build_unit_directory_name,
    find_run_csv_for_number,
    load_unit_record,
    run_csv_for_number,
    run_directory_for_number,
    save_unit_record,
    unit_directory_for_metadata,
)
from infrastructure.unit_persistence import (
    build_unit_directory_name as infrastructure_build_unit_directory_name,
)


class UnitPersistenceTests(unittest.TestCase):
    def test_legacy_module_reexports_infrastructure_directory_rules(self):
        self.assertIs(
            build_unit_directory_name,
            infrastructure_build_unit_directory_name,
        )

    def test_unit_directory_uses_main_board_serial_first(self):
        self.assertEqual(
            build_unit_directory_name(
                {
                    "Main board serial": "17688",
                    "Switch serial": "12345",
                    "Part number": "OSX-150",
                }
            ),
            "Unit-17688",
        )
        self.assertEqual(
            build_unit_directory_name({"Switch serial": "SW/123"}),
            "Unit-Unknown",
        )

    def test_unit_record_stores_shared_configuration_and_run_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unit_directory = unit_directory_for_metadata(
                root,
                {"Main board serial": "17688"},
            )
            run_directory = run_directory_for_number(
                unit_directory,
                2,
                "SW/123",
            )
            save_unit_record(
                unit_directory,
                {
                    "Main board serial": "17688",
                    "Part number": "OSX-150",
                    "Operating band": "O band",
                },
                [{"current_port": 4, "replacement_port": 43}],
                [41, 46, 41],
                2,
                run_directory,
                switch_serial="SW/123",
            )

            record = load_unit_record(unit_directory)
            self.assertEqual(record["unit_metadata"]["Main board serial"], "17688")
            self.assertNotIn("Switch serial", record["unit_metadata"])
            self.assertEqual(
                record["completed_replacements"],
                [{"current_port": 4, "replacement_port": 43}],
            )
            self.assertEqual(len(record["replacement_history"]), 1)
            self.assertEqual(
                record["replacement_history"][0]["current_port"],
                4,
            )
            self.assertEqual(record["designated_spares"], [41, 46])
            self.assertEqual(record["runs"][0]["run_number"], 2)
            self.assertEqual(record["runs"][0]["switch_serial"], "SW/123")
            self.assertEqual(
                run_csv_for_number(unit_directory, 2, "SW/123"),
                run_directory / "Run-2-SW-123.csv",
            )

    def test_unit_record_round_trips_append_only_replacement_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unit_directory = unit_directory_for_metadata(
                root, {"Main board serial": "17688"}
            )
            run_directory = run_directory_for_number(unit_directory, 1, "SW1")
            first = {
                "event_id": "first",
                "event_type": "replacement_recorded",
                "root_port": 14,
                "current_port": 14,
                "replacement_port": 41,
                "reason": "High loss",
                "operator": "DA",
                "recorded_at_utc": "2026-10-06T21:32:18Z",
            }
            second = {
                "event_id": "second",
                "event_type": "replacement_recorded",
                "root_port": 14,
                "current_port": 41,
                "replacement_port": 43,
                "previous_record_id": "first",
                "reason": "Replacement port failed",
                "operator": "JS",
                "recorded_at_utc": "2026-10-09T16:15:00Z",
            }
            save_unit_record(
                unit_directory,
                {"Main board serial": "17688"},
                [{"current_port": 14, "replacement_port": 43}],
                [46],
                1,
                run_directory,
                switch_serial="SW1",
                replacement_history=[first, second],
            )

            record = load_unit_record(unit_directory)
            self.assertEqual(len(record["replacement_history"]), 2)
            self.assertEqual(record["completed_replacements"][0]["replacement_port"], 43)

    def test_available_runs_only_returns_existing_numbered_csvs(self):
        with tempfile.TemporaryDirectory() as directory:
            unit_directory = Path(directory) / "Unit-17688"
            run_one = run_directory_for_number(unit_directory, 1)
            run_one.mkdir(parents=True)
            (run_one / "Run-1.csv").write_text("data", encoding="utf-8")
            run_three = run_directory_for_number(unit_directory, 3)
            run_three.mkdir(parents=True)

            self.assertEqual(available_run_numbers(unit_directory), [1])

    def test_run_lookup_does_not_confuse_run_one_with_run_ten(self):
        with tempfile.TemporaryDirectory() as directory:
            unit_directory = Path(directory) / "Unit-17688"
            run_one = run_directory_for_number(unit_directory, 1, "SW1")
            run_one.mkdir(parents=True)
            run_one_csv = run_one / (run_one.name + ".csv")
            run_one_csv.write_text("run one", encoding="utf-8")
            run_ten = run_directory_for_number(unit_directory, 10, "SW10")
            run_ten.mkdir(parents=True)
            (run_ten / (run_ten.name + ".csv")).write_text(
                "run ten",
                encoding="utf-8",
            )

            self.assertEqual(
                find_run_csv_for_number(unit_directory, 1),
                run_one_csv,
            )


if __name__ == "__main__":
    unittest.main()
