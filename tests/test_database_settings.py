import tempfile
import unittest
from pathlib import Path

from config.database_config import DatabaseSettings
from infrastructure.database.connection import (
    DatabaseConfigurationError,
    DatabaseErrorCategory,
)
from infrastructure.database.settings_repository import DatabaseSettingsRepository
from infrastructure.database.runtime import build_database_primary_workflow


class _Logger:
    def __init__(self):
        self.records = []

    def record(self, *args, **kwargs):
        self.records.append((args, kwargs))


class DatabaseSettingsTests(unittest.TestCase):
    def test_missing_file_uses_disabled_windows_auth_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = DatabaseSettingsRepository(
                Path(directory) / "database.ini"
            ).load()
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.server, r"localhost\SQLEXPRESS")
        self.assertEqual(settings.database, "LWBTestDB")

    def test_ensure_exists_creates_default_file_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config" / "database.ini"
            repository = DatabaseSettingsRepository(path)

            self.assertTrue(repository.ensure_exists())
            original = path.read_text(encoding="utf-8")
            self.assertFalse(repository.ensure_exists())
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertEqual(repository.load(), DatabaseSettings())
            self.assertIn("[database]", original)
            self.assertIn("server = localhost\\SQLEXPRESS", original)

    def test_existing_file_is_not_rewritten_by_ensure_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "database.ini"
            path.write_text(
                "[database]\nserver = custom\\INSTANCE\n",
                encoding="utf-8",
            )
            repository = DatabaseSettingsRepository(path)
            original = path.read_text(encoding="utf-8")

            self.assertFalse(repository.ensure_exists())
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertEqual(repository.load().server, r"custom\INSTANCE")

    def test_existing_file_without_database_section_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "database.ini"
            path.write_text("[other]\nvalue = 1\n", encoding="utf-8")

            with self.assertRaises(DatabaseConfigurationError) as context:
                DatabaseSettingsRepository(path).load()

        self.assertEqual(
            context.exception.category, DatabaseErrorCategory.CONFIGURATION
        )
        self.assertIn("[database]", context.exception.operator_message)
        self.assertIn(str(path), context.exception.operator_message)

    def test_invalid_boolean_is_rejected_without_falling_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "database.ini"
            path.write_text(
                "[database]\nenabled = maybe\n",
                encoding="utf-8",
            )

            with self.assertRaises(DatabaseConfigurationError) as context:
                DatabaseSettingsRepository(path).load()

        self.assertEqual(
            context.exception.category, DatabaseErrorCategory.CONFIGURATION
        )
        self.assertIn("enabled", context.exception.technical_detail)

    def test_invalid_timeout_names_the_setting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "database.ini"
            path.write_text(
                "[database]\nconnection_timeout_seconds = many\n",
                encoding="utf-8",
            )

            with self.assertRaises(DatabaseConfigurationError) as context:
                DatabaseSettingsRepository(path).load()

        self.assertIn(
            "connection_timeout_seconds", context.exception.technical_detail
        )

    def test_runtime_bootstrap_creates_file_and_logs_configuration_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config" / "database.ini"
            logger = _Logger()

            build_database_primary_workflow(logger, path)

        self.assertEqual(logger.records[0][0][1], "database.configuration_created")
        fields = logger.records[0][1]
        self.assertEqual(fields["database_name"], "LWBTestDB")
        self.assertNotIn("password", fields)
        self.assertNotIn("connection_string", fields)

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
