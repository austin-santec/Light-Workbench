import tempfile
import unittest
from pathlib import Path

from infrastructure.run_reports import FileRunReportService
from unit_persistence import run_directory_for_number, save_unit_record


class RunReportServiceTests(unittest.TestCase):
    def test_report_service_aggregates_runs_across_units(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unit_directory = root / "Unit-1"
            run_directory = run_directory_for_number(unit_directory, 1, "SW1")
            run_directory.mkdir(parents=True)
            csv_path = run_directory / (run_directory.name + ".csv")
            csv_path.write_text(
                "channel,1310 IL,1550 IL,,Metadata,Value\n"
                "1,1.0000,1.1000,,Run number,1\n"
                "2,2.1000,1.2000,,Switch serial,SW1\n"
                ",,,,Tested by,AJ\n"
                ",,,,Switch test total duration,00:02:00\n",
                encoding="utf-8",
            )
            save_unit_record(
                unit_directory,
                {"Main board serial": "1"},
                [],
                [],
                1,
                run_directory,
                switch_serial="SW1",
            )

            report = FileRunReportService().summarize_root(root, 2.0)

        self.assertEqual(report.run_count, 1)
        self.assertEqual(report.timed_run_count, 1)
        self.assertEqual(report.average_duration_seconds, 120.0)
        self.assertEqual(report.operator_summaries[0].tested_by, "AJ")


if __name__ == "__main__":
    unittest.main()
