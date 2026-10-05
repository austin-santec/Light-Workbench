import unittest

from domain.limit_profiles import LimitProfile, default_limit_profiles, legacy_limit_profile


class LimitProfileTests(unittest.TestCase):
    def test_defaults_match_model_rules(self):
        profiles = default_limit_profiles()
        self.assertEqual(profiles["OSX-100"].warning_enabled, False)
        self.assertEqual(profiles["OSX-100"].fail_above_db, 0.8)
        self.assertEqual(profiles["OSX-150"].warning_above_db, 2.25)
        self.assertEqual(profiles["OSX-150"].fail_above_db, 2.5)

    def test_boundaries_are_not_triggered(self):
        profile = default_limit_profiles()["OSX-150"]
        assessment = profile.classify(0.5, 2.25)
        self.assertFalse(assessment.is_too_good)
        self.assertFalse(assessment.is_optimization)
        self.assertFalse(assessment.is_fail)

    def test_osx150_classifies_independent_wavelengths(self):
        assessment = default_limit_profiles()["OSX-150"].classify(0.49, 2.4)
        self.assertTrue(assessment.is_too_good)
        self.assertTrue(assessment.is_optimization)
        self.assertFalse(assessment.is_fail)
        self.assertEqual(assessment.too_good_wavelengths, (1310,))
        self.assertEqual(assessment.optimization_wavelengths, (1550,))

    def test_osx100_has_no_optimization_warning(self):
        assessment = default_limit_profiles()["OSX-100"].classify(0.19, 0.81)
        self.assertTrue(assessment.is_too_good)
        self.assertTrue(assessment.is_fail)
        self.assertFalse(assessment.is_optimization)

    def test_osx100_rejects_an_enabled_warning_profile(self):
        with self.assertRaises(ValueError):
            LimitProfile("OSX-100", "bad", "1", 0.2, True, 0.5, 0.8).validate()

    def test_legacy_limit_remains_valid_for_old_runs(self):
        profile = legacy_limit_profile(2.0)
        self.assertTrue(profile.classify(2.01, 1.0).is_fail)


if __name__ == "__main__":
    unittest.main()
