import unittest

from domain.limit_profiles import (
    LimitProfile,
    default_limit_profiles,
    legacy_limit_profile,
    resolve_loaded_run_profile,
)


class LimitProfileTests(unittest.TestCase):
    def test_defaults_match_model_rules(self):
        profiles = default_limit_profiles()
        self.assertEqual(
            set(profiles),
            {"OSX-100/SM", "OSX-100/MM", "OSX-150/SM", "OSX-150/MM"},
        )
        self.assertEqual(profiles["OSX-100"].warning_enabled, False)
        self.assertEqual(profiles["OSX-100"].fail_above_db, 0.8)
        self.assertEqual(profiles["OSX-100/MM"].fail_above_db, 0.8)
        self.assertEqual(profiles["OSX-150"].warning_above_db, 2.25)
        self.assertEqual(profiles["OSX-150"].fail_above_db, 2.5)
        self.assertEqual(profiles["OSX-150/MM"].warning_above_db, 2.25)
        self.assertEqual(
            profiles["OSX-100/SM"].minimum_replacement_improvement_db,
            0.2,
        )
        self.assertEqual(
            profiles["OSX-150/MM"].minimum_replacement_improvement_db,
            0.2,
        )

    def test_model_and_mode_profiles_are_independent(self):
        profiles = default_limit_profiles()
        self.assertNotEqual(profiles["OSX-150/SM"].wavelength_mode, profiles["OSX-150/MM"].wavelength_mode)
        self.assertNotEqual(profiles["OSX-100/SM"].wavelength_mode, profiles["OSX-100/MM"].wavelength_mode)

    def test_legacy_model_lookup_aliases_only_the_sm_profile(self):
        profiles = default_limit_profiles()
        self.assertIn("OSX-100", profiles)
        self.assertIs(profiles["OSX-100"], profiles["OSX-100/SM"])
        self.assertIsNot(profiles["OSX-100"], profiles["OSX-100/MM"])

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
        self.assertEqual(profile.minimum_replacement_improvement_db, 0.2)

    def test_old_profile_mapping_uses_default_minimum_improvement(self):
        values = default_limit_profiles()["OSX-150/SM"].as_dict()
        values.pop("minimum_replacement_improvement_db")
        profile = LimitProfile.from_mapping(values)
        self.assertEqual(profile.minimum_replacement_improvement_db, 0.2)

    def test_loaded_osx100_mm_snapshot_uses_the_saved_mm_profile(self):
        profiles = default_limit_profiles()
        criteria = profiles["OSX-100/MM"].as_dict()
        resolution = resolve_loaded_run_profile(
            criteria,
            {"Part number": "OSX-100-1A-048-09-FA-00B-3H"},
            "MM",
            profiles,
            criteria_present=True,
        )

        self.assertEqual(resolution.source, "saved_snapshot")
        self.assertEqual(resolution.profile.model, "OSX-100")
        self.assertEqual(resolution.profile.wavelength_mode, "MM")
        self.assertEqual(resolution.profile.too_good_below_db, 0.2)
        self.assertEqual(resolution.profile.fail_above_db, 0.8)
        self.assertFalse(resolution.profile.classify(0.36, 0.42, (850, 1300)).is_too_good)

    def test_legacy_loaded_mm_run_infers_model_from_part_number(self):
        profiles = default_limit_profiles()
        resolution = resolve_loaded_run_profile(
            None,
            {"Part number": "OSX-100-1A-048-09-FA-00B-3H"},
            "MM",
            profiles,
        )

        self.assertEqual(resolution.source, "persisted_identity")
        self.assertEqual(resolution.profile.model, "OSX-100")
        self.assertEqual(resolution.profile.wavelength_mode, "MM")

    def test_loaded_mode_mismatch_does_not_fall_back_to_another_model(self):
        profiles = default_limit_profiles()
        criteria = profiles["OSX-100/SM"].as_dict()
        resolution = resolve_loaded_run_profile(
            criteria,
            {"Part number": "OSX-100-1A-048-09-FA-00B-3H"},
            "MM",
            profiles,
            criteria_present=True,
        )

        self.assertIsNone(resolution.profile)
        self.assertIn("does not match", resolution.reason)

    def test_unknown_legacy_mm_run_has_no_unsafe_default_profile(self):
        resolution = resolve_loaded_run_profile(
            None,
            {},
            "MM",
            default_limit_profiles(),
        )

        self.assertIsNone(resolution.profile)
        self.assertIn("could not be determined", resolution.reason)


if __name__ == "__main__":
    unittest.main()
