import unittest

from application.database_diagnostics import DatabaseDiagnosticsService
from config.database_config import DatabaseSettings
from infrastructure.database.connection import DatabaseErrorCategory
from infrastructure.database.migrations import AppliedMigration, discover_migrations
from infrastructure.database.preflight import check_database_preflight


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def execute(self, sql, *_parameters):
        normalized = " ".join(sql.split()).upper()
        if "SELECT OBJECT_ID" in normalized:
            self.rows = [(1 if self.connection.table_exists else None,)]
        elif normalized.startswith("SELECT MIGRATION_ID"):
            self.rows = [
                (item.migration_id, item.name, item.checksum)
                for item in self.connection.applied
            ]
        return self

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


class _Connection:
    def __init__(self, applied=(), table_exists=True):
        self.applied = tuple(applied)
        self.table_exists = table_exists
        self.closed = False
        self.timeout = None

    def cursor(self):
        return _Cursor(self)

    def close(self):
        self.closed = True


class _Factory:
    def __init__(self, connection):
        self.settings = DatabaseSettings()
        self._connection = connection

    def connection(self):
        connection = self._connection

        class Context:
            def __enter__(self):
                return connection

            def __exit__(self, *_args):
                connection.close()

        return Context()


class _Logger:
    def __init__(self):
        self.records = []

    def record(self, *args, **kwargs):
        self.records.append((args, kwargs))


class DatabasePreflightTests(unittest.TestCase):
    def test_current_schema_is_ready_and_connection_is_closed(self):
        migrations = discover_migrations()
        connection = _Connection(
            [
                AppliedMigration(item.migration_id, item.name, item.checksum)
                for item in migrations
            ]
        )
        result = check_database_preflight(_Factory(connection))
        self.assertTrue(result.ready)
        self.assertEqual(result.current_schema_version, 6)
        self.assertTrue(connection.closed)

    def test_missing_schema_is_reported_as_outdated_without_mutation(self):
        connection = _Connection(table_exists=False)
        result = check_database_preflight(_Factory(connection))
        self.assertFalse(result.ready)
        self.assertEqual(result.category, DatabaseErrorCategory.SCHEMA_OUTDATED)
        self.assertEqual(result.current_schema_version, 0)

    def test_checksum_change_is_invalid_schema(self):
        migration = discover_migrations()[0]
        connection = _Connection(
            [AppliedMigration(migration.migration_id, migration.name, "0" * 64)]
        )
        result = check_database_preflight(_Factory(connection))
        self.assertEqual(result.category, DatabaseErrorCategory.SCHEMA_INVALID)

    def test_diagnostic_log_contains_no_credentials_or_connection_string(self):
        migrations = discover_migrations()
        connection = _Connection(
            [
                AppliedMigration(item.migration_id, item.name, item.checksum)
                for item in migrations
            ]
        )
        logger = _Logger()

        class FactoryType:
            def __init__(self, _settings):
                self.settings = _settings

            def connection(self):
                return _Factory(connection).connection()

        result = DatabaseDiagnosticsService(logger, FactoryType).check(
            DatabaseSettings(enabled=True)
        )
        self.assertTrue(result.ready)
        fields = logger.records[0][1]
        self.assertNotIn("password", fields)
        self.assertNotIn("connection_string", fields)
        self.assertEqual(fields["status"], "ready")

    def test_quiet_health_preflight_does_not_emit_standard_preflight_event(self):
        migrations = discover_migrations()
        connection = _Connection(
            [
                AppliedMigration(item.migration_id, item.name, item.checksum)
                for item in migrations
            ]
        )
        logger = _Logger()

        class FactoryType:
            def __init__(self, _settings):
                self.settings = _settings

            def connection(self):
                return _Factory(connection).connection()

        result = DatabaseDiagnosticsService(logger, FactoryType).check(
            DatabaseSettings(enabled=True),
            record_event=False,
        )

        self.assertTrue(result.ready)
        self.assertEqual(logger.records, [])


if __name__ == "__main__":
    unittest.main()
