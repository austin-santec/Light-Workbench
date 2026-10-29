import unittest
from pathlib import Path

from infrastructure.database.maintenance import (
    INTEGRATION_DATABASE_NAME,
    DatabaseMaintenanceError,
    quote_database_identifier,
    reset_integration_database,
    temporary_backup_path,
    validate_integration_target,
)


class _MaintenanceCursor:
    def __init__(self, database_exists=True, data_directory=r"C:\SQL\Data"):
        self.database_exists = database_exists
        self.data_directory = data_directory
        self.executed = []
        self.rows = []

    def execute(self, sql, *parameters):
        self.executed.append((sql, parameters))
        normalized = " ".join(sql.split()).upper()
        if normalized.startswith("SELECT DB_ID"):
            self.rows = [(5 if self.database_exists else None,)]
        elif "INSTANCEDEFAULTDATAPATH" in normalized:
            self.rows = [(self.data_directory,)]
        else:
            self.rows = []
        return self

    def fetchone(self):
        return self.rows[0]

    def close(self):
        return None


class _MaintenanceConnection:
    def __init__(self, cursor):
        self.maintenance_cursor = cursor

    def cursor(self):
        return self.maintenance_cursor


class DatabaseMaintenanceSafetyTests(unittest.TestCase):
    def test_identifier_quoting_rejects_sql_fragments(self):
        self.assertEqual(
            quote_database_identifier(INTEGRATION_DATABASE_NAME),
            "[LWBTestDB_Integration]",
        )
        for unsafe in ("LWBTestDB; DROP DATABASE master", "name]", "", "a-b"):
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(DatabaseMaintenanceError):
                    quote_database_identifier(unsafe)

    def test_development_database_cannot_be_reset(self):
        with self.assertRaisesRegex(DatabaseMaintenanceError, "restricted"):
            validate_integration_target("LWBTestDB", "LWBTestDB")

    def test_confirmation_must_match_exactly(self):
        with self.assertRaisesRegex(DatabaseMaintenanceError, "confirmation"):
            validate_integration_target(INTEGRATION_DATABASE_NAME, "integration")

    def test_reset_drops_and_recreates_only_confirmed_integration_database(self):
        cursor = _MaintenanceCursor(database_exists=True)
        connection = _MaintenanceConnection(cursor)

        reset_integration_database(
            connection,
            INTEGRATION_DATABASE_NAME,
            INTEGRATION_DATABASE_NAME,
        )

        statements = [sql for sql, _parameters in cursor.executed]
        self.assertIn(
            "ALTER DATABASE [LWBTestDB_Integration] SET SINGLE_USER "
            "WITH ROLLBACK IMMEDIATE",
            statements,
        )
        self.assertIn("DROP DATABASE [LWBTestDB_Integration]", statements)
        self.assertIn("CREATE DATABASE [LWBTestDB_Integration]", statements)
        self.assertFalse(any("[LWBTestDB]" in sql for sql in statements))

    def test_reset_rejects_wrong_target_before_opening_cursor(self):
        class _UnexpectedConnection:
            def cursor(self):
                raise AssertionError("SQL should not be reached")

        with self.assertRaises(DatabaseMaintenanceError):
            reset_integration_database(
                _UnexpectedConnection(),
                "LWBTestDB",
                "LWBTestDB",
            )

    def test_temporary_backup_path_uses_sql_server_data_directory(self):
        cursor = _MaintenanceCursor()
        connection = _MaintenanceConnection(cursor)

        path = temporary_backup_path(connection, INTEGRATION_DATABASE_NAME)

        self.assertEqual(path.parent, Path(r"C:\SQL\Data"))
        self.assertTrue(path.name.startswith("LWBTestDB_Integration_"))
        self.assertEqual(path.suffix, ".bak")


if __name__ == "__main__":
    unittest.main()
