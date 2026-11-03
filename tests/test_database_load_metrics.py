import unittest

from infrastructure.database.load_metrics import (
    DatabaseLoadMetrics,
    activate_metrics,
    current_metrics,
)
from tools.benchmark_database_run_load import summarize_elapsed


class DatabaseLoadMetricsTests(unittest.TestCase):
    def test_summary_has_nonnegative_timing_and_default_counts(self):
        metrics = DatabaseLoadMetrics("unit_run_number")
        with activate_metrics(metrics):
            metrics.increment("database_connection_count")
            self.assertIs(current_metrics(), metrics)
        metrics.finish()

        summary = metrics.summary()

        self.assertEqual(summary.source, "unit_run_number")
        self.assertGreaterEqual(summary.elapsed_ms, 0)
        self.assertEqual(summary.counts["database_connection_count"], 1)
        self.assertEqual(summary.counts["database_transaction_count"], 0)

    def test_context_activation_does_not_leak(self):
        outer = DatabaseLoadMetrics("outer")
        inner = DatabaseLoadMetrics("inner")

        self.assertIsNone(current_metrics())
        with activate_metrics(outer):
            self.assertIs(current_metrics(), outer)
            with activate_metrics(inner):
                self.assertIs(current_metrics(), inner)
            self.assertIs(current_metrics(), outer)
        self.assertIsNone(current_metrics())

    def test_failure_stage_is_kept_in_summary(self):
        metrics = DatabaseLoadMetrics("run_id")
        metrics.failure_stage = "measurement_snapshot"
        metrics.finish()

        self.assertEqual(metrics.summary().failure_stage, "measurement_snapshot")


class DatabaseLoadBenchmarkTests(unittest.TestCase):
    def test_summary_statistics(self):
        self.assertEqual(
            summarize_elapsed([300, 100, 200]),
            {
                "minimum_ms": 100,
                "median_ms": 200,
                "average_ms": 200,
                "maximum_ms": 300,
            },
        )

    def test_summary_rejects_empty_values(self):
        with self.assertRaises(ValueError):
            summarize_elapsed([])


if __name__ == "__main__":
    unittest.main()
