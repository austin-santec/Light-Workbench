import unittest

from domain.diagnostic_analysis import (
    DiagnosticReading,
    MANUAL_METHOD,
    MONITORING_METHOD,
    analyze_diagnostic_readings,
    calculate_variation_statistics,
)


def reading(number, method, first, second):
    return DiagnosticReading(
        reading_number=number,
        timestamp="2026-09-29 12:00:0%d.000" % number,
        method=method,
        channel=None,
        physical_port=None,
        measured_1310=0.0,
        reference_1310=0.0,
        insertion_loss_1310=first,
        measured_1550=0.0,
        reference_1550=0.0,
        insertion_loss_1550=second,
    )


class DiagnosticAnalysisTests(unittest.TestCase):
    def test_statistics_calculate_expected_variation(self):
        result = calculate_variation_statistics(
            [
                reading(1, MANUAL_METHOD, 0.90, 0.60),
                reading(2, MANUAL_METHOD, 0.92, 0.64),
                reading(3, MANUAL_METHOD, 0.91, 0.62),
            ],
            1310,
        )

        self.assertEqual(result.count, 3)
        self.assertAlmostEqual(result.average, 0.91)
        self.assertAlmostEqual(result.minimum, 0.90)
        self.assertAlmostEqual(result.maximum, 0.92)
        self.assertAlmostEqual(result.value_range, 0.02)
        self.assertAlmostEqual(result.first_to_last, 0.01)
        self.assertAlmostEqual(result.standard_deviation, 0.01)

    def test_analysis_separates_manual_and_monitoring_samples(self):
        result = analyze_diagnostic_readings(
            [
                reading(1, MANUAL_METHOD, 0.90, 0.60),
                reading(2, MANUAL_METHOD, 0.92, 0.64),
                reading(3, MONITORING_METHOD, 1.10, 0.80),
                reading(4, MONITORING_METHOD, 1.11, 0.81),
            ],
            MONITORING_METHOD,
        )

        self.assertEqual(result.count, 2)
        self.assertAlmostEqual(result.by_wavelength[1310].average, 1.105)
        self.assertAlmostEqual(result.by_wavelength[1550].average, 0.805)

    def test_analysis_requires_two_samples(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            analyze_diagnostic_readings(
                [reading(1, MANUAL_METHOD, 0.90, 0.60)],
                MANUAL_METHOD,
            )


if __name__ == "__main__":
    unittest.main()
