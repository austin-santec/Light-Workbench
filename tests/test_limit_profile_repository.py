import tempfile
import unittest
from pathlib import Path

from domain.extra_ports import ExtraChannelRoutingMethod
from domain.limit_profiles import default_limit_profiles
from infrastructure.limit_profile_repository import LimitProfileRepository


class LimitProfileRepositoryTests(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            profiles = LimitProfileRepository(Path(directory) / "limits.ini").load_profiles()
            self.assertEqual(profiles["OSX-100"].fail_above_db, 0.8)

    def test_missing_routing_setting_defaults_to_scpi_mapped(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = LimitProfileRepository(Path(directory) / "limits.ini")
            self.assertEqual(
                repository.load_extra_channel_routing_method(),
                ExtraChannelRoutingMethod.SCPI_MAPPED,
            )

    def test_profiles_round_trip_to_ini(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = LimitProfileRepository(Path(directory) / "limits.ini")
            profiles = default_limit_profiles()
            repository.save_profiles(profiles)
            loaded = repository.load_profiles()
            self.assertEqual(loaded["OSX-150"].warning_above_db, 2.25)
            self.assertEqual(
                loaded["OSX-150"].minimum_replacement_improvement_db,
                0.2,
            )
            self.assertTrue(repository.path.is_file())

    def test_extra_channel_routing_method_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = LimitProfileRepository(Path(directory) / "limits.ini")
            repository.save_profiles(
                default_limit_profiles(),
                ExtraChannelRoutingMethod.CLI_DIRECT,
            )

            self.assertEqual(
                repository.load_extra_channel_routing_method(),
                ExtraChannelRoutingMethod.CLI_DIRECT,
            )

            repository.save_profiles(default_limit_profiles())
            self.assertEqual(
                repository.load_extra_channel_routing_method(),
                ExtraChannelRoutingMethod.CLI_DIRECT,
            )

    def test_invalid_extra_channel_routing_method_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "limits.ini"
            path.write_text(
                "[hardware-routing]\n"
                "osx_150_extra_channel_method=automatic_fallback\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Extra-channel routing"):
                LimitProfileRepository(path).load_extra_channel_routing_method()

    def test_invalid_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "limits.ini"
            path.write_text(
                "[OSX-100]\nmodel=OSX-100\nprofile_name=x\nrevision=1\n"
                "too_good_below_db=1\nwarning_enabled=false\nfail_above_db=0.8\n"
                "[OSX-150]\nmodel=OSX-150\nprofile_name=x\nrevision=1\n"
                "too_good_below_db=0.5\nwarning_enabled=true\nwarning_above_db=2.25\nfail_above_db=2.5\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                LimitProfileRepository(path).load_profiles()

    def test_legacy_model_sections_migrate_to_sm_and_copy_to_mm_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "limits.ini"
            path.write_text(
                "[OSX-100]\nmodel=OSX-100\nprofile_name=custom 100\nrevision=7\n"
                "too_good_below_db=0.1\nwarning_enabled=false\nfail_above_db=0.7\n"
                "[OSX-150]\nmodel=OSX-150\nprofile_name=custom 150\nrevision=8\n"
                "too_good_below_db=0.4\nwarning_enabled=true\nwarning_above_db=2.1\nfail_above_db=2.4\n",
                encoding="utf-8",
            )
            repository = LimitProfileRepository(path)
            profiles = repository.load_profiles()
            self.assertEqual(profiles["OSX-150/SM"].fail_above_db, 2.4)
            self.assertEqual(profiles["OSX-150/MM"].fail_above_db, 2.4)

            mm = profiles["OSX-150/MM"]
            repository.save_profiles({**profiles, "OSX-150/MM": mm.__class__(
                mm.model, mm.profile_name, mm.revision, mm.too_good_below_db,
                mm.warning_enabled, 2.2, mm.fail_above_db, "MM"
            ).validate()})
            reloaded = repository.load_profiles()
            self.assertEqual(reloaded["OSX-150/MM"].warning_above_db, 2.2)
            self.assertEqual(reloaded["OSX-150/SM"].warning_above_db, 2.1)


if __name__ == "__main__":
    unittest.main()
