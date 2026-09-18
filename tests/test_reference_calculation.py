import unittest

from reference_calculation import calculate_reference_offsets


class ReferenceCalculationTests(unittest.TestCase):
    def test_zero_reference_il_readings_become_positive_offsets(self):
        self.assertEqual(
            calculate_reference_offsets({1310: 0.724, 1550: 0.276}),
            (0.72, 0.28),
        )

    def test_both_wavelengths_are_required(self):
        with self.assertRaises(ValueError):
            calculate_reference_offsets({1310: -0.72})


if __name__ == "__main__":
    unittest.main()
