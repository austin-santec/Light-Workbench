import unittest

from domain.measurement import (
    calculate_insertion_loss,
    validate_insertion_loss,
    validate_reference_measurements,
)


class MeasurementDomainTests(unittest.TestCase):
    def test_calculates_loss_for_both_workflow_wavelengths(self):
        losses = calculate_insertion_loss(
            {1310: 0.72, 1550: 0.28},
            {1310: -1.0, 1550: -1.1},
        )

        self.assertAlmostEqual(losses[1310], 1.72)
        self.assertAlmostEqual(losses[1550], 1.38)

    def test_missing_reference_is_reported_at_domain_boundary(self):
        with self.assertRaisesRegex(ValueError, "Reference.*1550"):
            calculate_insertion_loss({1310: 0.72}, {1310: -1.0, 1550: -1.1})

    def test_missing_measurement_is_reported_at_domain_boundary(self):
        with self.assertRaisesRegex(ValueError, "Measurement.*1550"):
            calculate_insertion_loss({1310: 0.72, 1550: 0.28}, {1310: -1.0})

    def test_dark_reference_threshold_is_strictly_less_than_minus_forty(self):
        self.assertTrue(
            validate_reference_measurements(
                {1310: -40.0, 1550: -0.1}
            ).valid
        )
        validation = validate_reference_measurements(
            {1310: -40.0001, 1550: -41.0}
        )
        self.assertFalse(validation.valid)
        self.assertEqual(validation.invalid_wavelengths, (1310, 1550))

    def test_negative_loss_uses_four_decimal_precision(self):
        self.assertTrue(
            validate_insertion_loss({1310: -0.00004, 1550: 0.0}).valid
        )
        validation = validate_insertion_loss({1310: -0.0001, 1550: 0.0})
        self.assertFalse(validation.valid)
        self.assertEqual(validation.invalid_wavelengths, (1310,))

    def test_valid_loss_requires_both_wavelengths_to_be_non_negative(self):
        validation = validate_insertion_loss({1310: 0.1, 1550: -0.2})
        self.assertFalse(validation.valid)
        self.assertEqual(validation.invalid_wavelengths, (1550,))


if __name__ == "__main__":
    unittest.main()
