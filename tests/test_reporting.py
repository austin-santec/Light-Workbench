import unittest

from domain.reporting import summarize_run
from domain.models import MeasurementRecord


class ReportingTests(unittest.TestCase):
    def test_summary_counts_only_supplied_written_measurements(self):
        summary = summarize_run(
            [
                MeasurementRecord(1, 1.0, 1.1),
                MeasurementRecord(2, 2.1, 1.2),
            ],
            {
                "Run number": "3",
                "Switch serial": "SW-3",
                "Tested by": "AJ",
                "Switch test total duration": "00:04:05",
            },
            2.0,
        )

        self.assertEqual(summary.run_number, 3)
        self.assertEqual(summary.accepted_channel_count, 2)
        self.assertEqual(summary.over_limit_channel_count, 1)
        self.assertEqual(summary.total_duration_seconds, 245.0)


if __name__ == "__main__":
    unittest.main()
