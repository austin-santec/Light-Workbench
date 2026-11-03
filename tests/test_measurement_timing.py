import configparser
import tempfile
import unittest
from pathlib import Path

from domain.measurement_timing import (
    MeasurementTimingProfile,
    default_measurement_timing_profiles,
)
from infrastructure.timing_profile_repository import TimingProfileRepository


class MeasurementTimingProfileTests(unittest.TestCase):
    def test_default_profiles_match_approved_values(self):
        profiles = default_measurement_timing_profiles()

        self.assertEqual(
            (
                profiles["standard"].wavelength_settling_ms,
                profiles["standard"].source_settling_ms,
                profiles["standard"].live_update_pause_ms,
            ),
            (100, 500, 250),
        )
        self.assertEqual(
            (
                profiles["conservative"].wavelength_settling_ms,
                profiles["conservative"].source_settling_ms,
                profiles["conservative"].live_update_pause_ms,
            ),
            (250, 1000, 500),
        )
        self.assertEqual(
            (
                profiles["fast_experimental"].wavelength_settling_ms,
                profiles["fast_experimental"].source_settling_ms,
                profiles["fast_experimental"].live_update_pause_ms,
            ),
            (50, 250, 100),
        )

    def test_validation_normalizes_ids_and_rejects_invalid_values(self):
        profile = MeasurementTimingProfile(
            " Fast Experimental ", "Fast", wavelength_settling_ms="50"
        ).validate()
        self.assertEqual(profile.profile_id, "fast_experimental")
        with self.assertRaises(ValueError):
            MeasurementTimingProfile("bad", "Bad", source_settling_ms=10001).validate()
        with self.assertRaises(ValueError):
            MeasurementTimingProfile(
                "bad", "Bad", power_sample_offsets_ms=(0, 1.5)
            ).validate()
        with self.assertRaises(ValueError):
            MeasurementTimingProfile(
                "bad", "Bad", power_sample_offsets_ms=(100, 50)
            ).validate()

    def test_power_sample_offsets_round_trip_and_legacy_default(self):
        profile = MeasurementTimingProfile(
            "custom", "Custom", power_sample_offsets_ms=(0, 200, 350)
        ).validate()

        self.assertEqual(
            profile.as_dict()["power_sample_offsets_ms"], [0, 200, 350]
        )
        restored = MeasurementTimingProfile.from_dict(profile.as_dict())
        self.assertEqual(restored.power_sample_offsets_ms, (0, 200, 350))
        legacy = MeasurementTimingProfile.from_dict(
            {"profile_id": "legacy", "profile_name": "Legacy"}
        )
        self.assertEqual(legacy.power_sample_offsets_ms, (0,))

    def test_repository_round_trip_preserves_custom_profile_and_active_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timing_profiles.ini"
            repository = TimingProfileRepository(path)
            profiles = default_measurement_timing_profiles()
            profiles["custom"] = MeasurementTimingProfile(
                "custom", "Custom", revision=2, wavelength_settling_ms=125,
                source_settling_ms=625, live_update_pause_ms=300,
                power_sample_offsets_ms=(0, 200, 350),
            )

            repository.save(profiles, "custom")
            loaded, active_id = repository.load()

            self.assertEqual(active_id, "custom")
            self.assertEqual(loaded["custom"].revision, 2)
            self.assertEqual(loaded["custom"].source_settling_ms, 625)
            self.assertEqual(loaded["custom"].power_sample_offsets_ms, (0, 200, 350))

    def test_malformed_profile_is_ignored_and_standard_remains_active(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timing_profiles.ini"
            parser = configparser.ConfigParser()
            parser["active"] = {"profile_id": "missing"}
            parser["profile:broken"] = {
                "name": "Broken",
                "revision": "1",
                "opm_wavelength_settling_ms": "not-a-number",
                "laser_source_settling_ms": "500",
                "live_update_pause_ms": "250",
            }
            with path.open("w", encoding="utf-8") as stream:
                parser.write(stream)

            profiles, active_id = TimingProfileRepository(path).load()

            self.assertEqual(active_id, "standard")
            self.assertNotIn("broken", profiles)


if __name__ == "__main__":
    unittest.main()
