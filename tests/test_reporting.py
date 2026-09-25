import unittest

from domain.reporting import RunSummary, aggregate_run_summaries, summarize_run
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

    def test_aggregate_reports_overall_and_per_operator_timing(self):
        summaries = [
            RunSummary(
                run_number=1,
                switch_serial="SW-1",
                tested_by="AJ",
                accepted_channel_count=48,
                over_limit_channel_count=2,
                warning_limit_db=2.0,
                total_duration_seconds=120.0,
                start_time="",
                stop_time="",
            ),
            RunSummary(
                run_number=2,
                switch_serial="SW-2",
                tested_by="AJ",
                accepted_channel_count=48,
                over_limit_channel_count=4,
                warning_limit_db=2.0,
                total_duration_seconds=180.0,
                start_time="",
                stop_time="",
            ),
            RunSummary(
                run_number=3,
                switch_serial="SW-3",
                tested_by="BK",
                accepted_channel_count=48,
                over_limit_channel_count=0,
                warning_limit_db=2.0,
                total_duration_seconds=0.0,
                start_time="",
                stop_time="",
            ),
        ]

        aggregate = aggregate_run_summaries(summaries)

        self.assertEqual(aggregate.run_count, 3)
        self.assertEqual(aggregate.timed_run_count, 2)
        self.assertEqual(aggregate.average_duration_seconds, 150.0)
        self.assertAlmostEqual(aggregate.average_over_limit_channel_count, 2.0)
        self.assertEqual(
            [item.tested_by for item in aggregate.operator_summaries],
            ["AJ", "BK"],
        )
        self.assertEqual(
            aggregate.operator_summaries[0].fastest_duration_seconds,
            120.0,
        )
        self.assertEqual(
            aggregate.operator_summaries[0].slowest_duration_seconds,
            180.0,
        )


if __name__ == "__main__":
    unittest.main()
