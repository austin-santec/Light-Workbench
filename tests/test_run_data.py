import tempfile
import unittest
from pathlib import Path

from run_data import load_run_csv


class RunDataTests(unittest.TestCase):
    def test_loads_measurements_and_side_by_side_metadata(self):
        csv_text = (
            "channel,1310 IL,1550 IL,,Metadata,Value\n"
            "1,2.1000,1.9000,,Main board serial,MB123\n"
            "2,1.5000,2.2000,,Operating band,O band\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.csv"
            path.write_text(csv_text, encoding="utf-8")

            run_data = load_run_csv(path)

        self.assertEqual(len(run_data.measurements), 2)
        self.assertEqual(run_data.metadata["Main board serial"], "MB123")
        self.assertEqual(run_data.metadata["Operating band"], "O band")
        self.assertEqual([record.channel for record in run_data.over_limit(2.0)], [1, 2])

    def test_loads_measurement_only_csv(self):
        csv_text = "channel,1310 IL,1550 IL\n1,1.2,1.3\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.csv"
            path.write_text(csv_text, encoding="utf-8")

            run_data = load_run_csv(path)

        self.assertEqual(run_data.metadata, {})
        self.assertEqual(run_data.measurements[0].loss_1310, 1.2)

    def test_analysis_counts_each_wavelength_and_both(self):
        csv_text = (
            "channel,1310 IL,1550 IL\n"
            "1,2.1,1.0\n"
            "2,1.0,2.1\n"
            "3,2.1,2.1\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.csv"
            path.write_text(csv_text, encoding="utf-8")

            summary = load_run_csv(path).analysis(2.0)

        self.assertEqual(summary["over_limit"], 3)
        self.assertEqual(summary["over_1310"], 2)
        self.assertEqual(summary["over_1310_channels"], [1, 3])
        self.assertEqual(summary["over_1550"], 2)
        self.assertEqual(summary["over_1550_channels"], [2, 3])
        self.assertEqual(summary["over_both"], 1)
        self.assertEqual(summary["over_both_channels"], [3])


if __name__ == "__main__":
    unittest.main()
