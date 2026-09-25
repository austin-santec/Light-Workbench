import unittest

from domain.measurement import calculate_insertion_loss


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


if __name__ == "__main__":
    unittest.main()
