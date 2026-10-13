import tempfile
import unittest
from pathlib import Path

from config.database_config import DatabaseSettings
from infrastructure.database.settings_repository import DatabaseSettingsRepository


class DatabaseSettingsTests(unittest.TestCase):
    def test_missing_file_uses_disabled_windows_auth_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = DatabaseSettingsRepository(
                Path(directory) / "database.ini"
            ).load()
        self.assertFalse(settings.enabled)
        self.assertEqual(settings.server, r"localhost\SQLEXPRESS")
        self.assertEqual(settings.database, "LWBTestDB")

    def test_non_secret_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config" / "database.ini"
            repository = DatabaseSettingsRepository(path)
            expected = DatabaseSettings(
                enabled=True,
                server=r"server\instance",
                database="LightWorkbench",
                connection_timeout_seconds=8,
                command_timeout_seconds=30,
            )
            repository.save(expected)
            actual = repository.load()
            text = path.read_text(encoding="utf-8").lower()
        self.assertEqual(actual, expected)
        self.assertNotIn("password", text)
        self.assertNotIn("username", text)
        self.assertNotIn("trusted_connection", text)

    def test_invalid_timeout_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Connection timeout"):
            DatabaseSettings(connection_timeout_seconds=0)

    def test_connection_string_delimiters_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "database name"):
            DatabaseSettings(database="db;UID=unexpected")


if __name__ == "__main__":
    unittest.main()
