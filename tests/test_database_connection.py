import unittest

from config.database_config import DatabaseSettings
from infrastructure.database.connection import (
    DatabaseConnectionError,
    DatabaseConnectionFactory,
    DatabaseErrorCategory,
    build_windows_connection_string,
    classify_database_exception,
)


class _Cursor:
    def __init__(self):
        self.timeout = None
        self.closed = False

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self):
        self.cursor_value = _Cursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class DatabaseConnectionTests(unittest.TestCase):
    def test_connection_string_uses_windows_auth_without_credentials(self):
        value = build_windows_connection_string(
            r"localhost\SQLEXPRESS",
            "LWBTestDB",
            "ODBC Driver 18 for SQL Server",
            True,
        )
        self.assertIn("Trusted_Connection=yes", value)
        self.assertNotIn("UID=", value.upper())
        self.assertNotIn("PWD=", value.upper())

    def test_factory_bounds_connection_and_closes_it(self):
        created = _Connection()
        calls = []

        def connector(connection_string, **kwargs):
            calls.append((connection_string, kwargs))
            return created

        settings = DatabaseSettings(connection_timeout_seconds=7)
        factory = DatabaseConnectionFactory(settings, connector)
        with factory.connection() as connection:
            self.assertIs(connection, created)
        self.assertTrue(created.closed)
        self.assertEqual(calls[0][1]["timeout"], 7)
        self.assertFalse(calls[0][1]["autocommit"])

    def test_transaction_commits_and_sets_command_timeout(self):
        created = _Connection()
        factory = DatabaseConnectionFactory(
            DatabaseSettings(command_timeout_seconds=22),
            lambda *_args, **_kwargs: created,
        )
        with factory.transaction() as cursor:
            self.assertIs(cursor, created.cursor_value)
        self.assertEqual(created.commits, 1)
        self.assertEqual(created.rollbacks, 0)
        self.assertEqual(created.cursor_value.timeout, 22)
        self.assertTrue(created.cursor_value.closed)
        self.assertTrue(created.closed)

    def test_transaction_rolls_back_on_failure(self):
        created = _Connection()
        factory = DatabaseConnectionFactory(
            DatabaseSettings(), lambda *_args, **_kwargs: created
        )
        with self.assertRaisesRegex(RuntimeError, "failure"):
            with factory.transaction():
                raise RuntimeError("failure")
        self.assertEqual(created.commits, 0)
        self.assertEqual(created.rollbacks, 1)
        self.assertTrue(created.closed)

    def test_common_odbc_errors_are_classified(self):
        cases = (
            (
                ("08001", "Encryption not supported on the client"),
                DatabaseErrorCategory.CONFIGURATION,
            ),
            (("IM002", "driver missing"), DatabaseErrorCategory.DRIVER_MISSING),
            (("HYT00", "timeout"), DatabaseErrorCategory.TIMEOUT),
            (("28000", "18456 login failed"), DatabaseErrorCategory.AUTHENTICATION),
            (("42000", "4060 cannot open database"), DatabaseErrorCategory.DATABASE_MISSING),
            (("42000", "permission denied 229"), DatabaseErrorCategory.PERMISSION_DENIED),
            (("08001", "10061 refused"), DatabaseErrorCategory.SERVER_UNAVAILABLE),
        )
        for arguments, expected in cases:
            with self.subTest(expected=expected):
                result = classify_database_exception(Exception(*arguments))
                self.assertIsInstance(result, DatabaseConnectionError)
                self.assertEqual(result.category, expected)


if __name__ == "__main__":
    unittest.main()
