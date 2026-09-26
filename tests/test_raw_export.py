import unittest

from domain.models import MeasurementRecord
from domain.raw_export import format_raw_measurements


class RawExportTests(unittest.TestCase):
    def test_formats_written_measurements_as_sorted_excel_tsv(self):
        result = format_raw_measurements(
            [
                MeasurementRecord(2, 1.2, 2.34567),
                MeasurementRecord(1, 0.123456, 0.9),
            ]
        )

        self.assertEqual(
            result,
            "\n".join(
                [
                    "1\t0.1235\t0.9000",
                    "2\t1.2000\t2.3457",
                ]
            ),
        )

    def test_last_duplicate_channel_matches_replacement_semantics(self):
        result = format_raw_measurements(
            [
                MeasurementRecord(1, 2.0, 2.1),
                MeasurementRecord(1, 1.0, 1.1),
            ]
        )

        self.assertTrue(result.endswith("1\t1.0000\t1.1000"))

    def test_empty_measurements_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "completed measurement"):
            format_raw_measurements([])


if __name__ == "__main__":
    unittest.main()
