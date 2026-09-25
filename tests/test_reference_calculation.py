import unittest

from domain.reference import calculate_reference_offsets as domain_calculate_reference_offsets
from reference_calculation import calculate_reference_offsets


class ReferenceCalculationTests(unittest.TestCase):
    def test_legacy_import_reexports_domain_service(self):
        self.assertIs(calculate_reference_offsets, domain_calculate_reference_offsets)

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
