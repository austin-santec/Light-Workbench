import tempfile
import unittest
from pathlib import Path

from domain.limit_profiles import default_limit_profiles
from infrastructure.limit_profile_repository import LimitProfileRepository


class LimitProfileRepositoryTests(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            profiles = LimitProfileRepository(Path(directory) / "limits.ini").load_profiles()
            self.assertEqual(profiles["OSX-100"].fail_above_db, 0.8)

    def test_profiles_round_trip_to_ini(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = LimitProfileRepository(Path(directory) / "limits.ini")
            profiles = default_limit_profiles()
            repository.save_profiles(profiles)
            loaded = repository.load_profiles()
            self.assertEqual(loaded["OSX-150"].warning_above_db, 2.25)
            self.assertTrue(repository.path.is_file())

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


if __name__ == "__main__":
    unittest.main()
