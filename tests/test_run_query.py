import tempfile
import unittest
from pathlib import Path

from infrastructure.run_query import FileRunQueryService
from unit_persistence import run_directory_for_number, save_unit_record


class RunQueryTests(unittest.TestCase):
    def test_query_service_summarizes_indexed_unit_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            unit_directory = Path(directory) / "Unit-17688"
            run_directory = run_directory_for_number(unit_directory, 1, "SW1")
            run_directory.mkdir(parents=True)
            csv_path = run_directory / (run_directory.name + ".csv")
            csv_path.write_text(
                "channel,1310 IL,1550 IL,,Metadata,Value\n"
                "1,1.0000,1.1000,,Run number,1\n"
                "2,2.1000,1.2000,,Switch serial,SW1\n",
                encoding="utf-8",
            )
            save_unit_record(
                unit_directory,
                {"Main board serial": "17688"},
                [],
                [],
                1,
                run_directory,
                switch_serial="SW1",
            )

            summaries = FileRunQueryService().summarize_unit_runs(
                unit_directory,
                2.0,
            )

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].switch_serial, "SW1")
        self.assertEqual(summaries[0].over_limit_channel_count, 1)


if __name__ == "__main__":
    unittest.main()
