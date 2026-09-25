import unittest

from domain.comparison import comparison_values, index_measurements
from domain.models import MeasurementRecord


class ComparisonDomainTests(unittest.TestCase):
    def test_comparison_values_are_indexed_and_formatted(self):
        records = index_measurements(
            [MeasurementRecord(1, 1.23456, 2.34567)]
        )

        self.assertEqual(comparison_values(records, 1), ("1.2346", "2.3457"))
        self.assertEqual(comparison_values(records, 2), ("-", "-"))


if __name__ == "__main__":
    unittest.main()
