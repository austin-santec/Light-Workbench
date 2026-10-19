import tempfile
import unittest
from pathlib import Path

from domain.extra_ports import ExtraPortSettings
from infrastructure.extra_port_settings_repository import ExtraPortSettingsRepository


class ExtraPortSettingsRepositoryTests(unittest.TestCase):
    def test_missing_file_uses_conservative_default(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = ExtraPortSettingsRepository(
                Path(directory) / "extra.ini"
            ).load()
        self.assertEqual(settings.maximum_physical_port_probe, 64)

    def test_setting_round_trips_without_affecting_limit_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "extra.ini"
            repository = ExtraPortSettingsRepository(path)
            repository.save(ExtraPortSettings(72))
            self.assertEqual(repository.load().maximum_physical_port_probe, 72)


if __name__ == "__main__":
    unittest.main()
