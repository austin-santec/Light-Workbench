import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from config.app_info import APP_VERSION
from infrastructure.database.connection import build_windows_connection_string
from infrastructure.database.migrations import (
    DEFAULT_MIGRATIONS_PATH,
    AppliedMigration,
    Migration,
    MigrationChecksumError,
    MigrationHistoryError,
    MigrationRunner,
    UnsupportedSchemaVersionError,
    discover_migrations,
    split_sql_batches,
)


class _FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def execute(self, sql, *parameters):
        normalized = " ".join(sql.split()).upper()
        if "SELECT OBJECT_ID" in normalized:
            self.rows = [(1 if self.connection.tracking_table_exists else None,)]
        elif normalized.startswith("SELECT MIGRATION_ID"):
            self.rows = [
                (item.migration_id, item.name, item.checksum)
                for item in sorted(
                    self.connection.applied.values(),
                    key=lambda migration: migration.migration_id,
                )
            ]
        elif normalized.startswith("INSERT INTO DBO.SCHEMA_MIGRATIONS"):
            migration_id, name, checksum, _application_version = parameters
            self.connection.applied[migration_id] = AppliedMigration(
                migration_id=migration_id,
                name=name,
                checksum=checksum,
            )
        else:
            if self.connection.fail_on and self.connection.fail_on in sql:
                raise RuntimeError("simulated SQL failure")
            self.connection.executed_batches.append(sql)
            if "CREATE TABLE dbo.SCHEMA_MIGRATIONS" in sql:
                self.connection.tracking_table_exists = True
        return self

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return list(self.rows)

    def close(self):
        return None


class _FakeConnection:
    def __init__(self, applied=(), fail_on=None):
        self.applied = {item.migration_id: item for item in applied}
        self.tracking_table_exists = bool(self.applied)
        self.fail_on = fail_on
        self.executed_batches = []
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


def _migration(script="CREATE TABLE dbo.SCHEMA_MIGRATIONS (id INT);", checksum="a" * 64):
    return Migration(
        migration_id=1,
        name="initial_schema",
        script=script,
        checksum=checksum,
        path=Path("0001_initial_schema.sql"),
    )


class MigrationDiscoveryTests(unittest.TestCase):
    def test_bundled_migrations_are_discovered(self):
        migrations = discover_migrations()

        self.assertEqual([item.migration_id for item in migrations], [1, 2, 3, 4, 5])
        self.assertEqual(migrations[0].name, "initial_schema")
        self.assertEqual(migrations[1].name, "nonnegative_measurement_losses")
        self.assertEqual(migrations[-1].name, "iterative_replacement_analysis")
        self.assertIn("void_info_json", migrations[-1].script)
        self.assertIn("FOR JSON PATH, WITHOUT_ARRAY_WRAPPER", migrations[-1].script)
        self.assertIn("DROP COLUMN analysis_exclusion_reason", migrations[-1].script)
        self.assertIn("CK_IL_RUNS_void_info_json", migrations[-1].script)
        self.assertIn("ISJSON(void_info_json) = 1", migrations[-1].script)
        self.assertIn("verification_required", migrations[-1].script)
        self.assertIn("review_required", migrations[-1].script)
        self.assertTrue(all(len(item.checksum) == 64 for item in migrations))

    def test_migration_ids_must_be_contiguous(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "0002_second.sql").write_text("SELECT 1;", encoding="utf-8")

            with self.assertRaisesRegex(MigrationHistoryError, "contiguous"):
                discover_migrations(path)

    def test_go_lines_split_batches_without_splitting_words(self):
        batches = split_sql_batches(
            "SELECT 'GO stays here';\nGO\nSELECT 2;\ngo -- separator\nSELECT 3;"
        )

        self.assertEqual(
            batches,
            ("SELECT 'GO stays here';", "SELECT 2;", "SELECT 3;"),
        )


class MigrationRunnerTests(unittest.TestCase):
    def test_apply_records_migration_and_second_run_is_no_op(self):
        connection = _FakeConnection()
        runner = MigrationRunner(connection, [_migration()], "1.2.3")

        first = runner.apply()
        second = runner.apply()

        self.assertEqual(first.applied_ids, (1,))
        self.assertEqual(second.applied_ids, ())
        self.assertEqual(connection.commit_count, 1)
        self.assertIn(1, connection.applied)

    def test_modified_applied_migration_is_rejected(self):
        migration = _migration()
        connection = _FakeConnection(
            [AppliedMigration(1, migration.name, migration.checksum)]
        )
        changed = replace(migration, checksum="b" * 64)

        with self.assertRaises(MigrationChecksumError):
            MigrationRunner(connection, [changed], "1.2.3").pending_migrations()

    def test_newer_database_schema_is_rejected(self):
        connection = _FakeConnection(
            [AppliedMigration(2, "future_schema", "f" * 64)]
        )

        with self.assertRaises(UnsupportedSchemaVersionError):
            MigrationRunner(connection, [_migration()], "1.2.3").pending_migrations()

    def test_failed_migration_rolls_back(self):
        connection = _FakeConnection(fail_on="BROKEN")
        runner = MigrationRunner(
            connection,
            [_migration("CREATE TABLE dbo.SCHEMA_MIGRATIONS (id INT);\nGO\nBROKEN")],
            "1.2.3",
        )

        with self.assertRaisesRegex(RuntimeError, "Failed to apply"):
            runner.apply()

        self.assertEqual(connection.commit_count, 0)
        self.assertEqual(connection.rollback_count, 1)


class DatabaseMigrationConfigurationTests(unittest.TestCase):
    def test_connection_string_uses_windows_authentication_and_encryption(self):
        value = build_windows_connection_string(
            r"localhost\SQLEXPRESS",
            "LWBTestDB_Integration",
            "ODBC Driver 18 for SQL Server",
            True,
        )

        self.assertIn("Trusted_Connection=yes", value)
        self.assertIn("Encrypt=yes", value)
        self.assertIn("TrustServerCertificate=yes", value)
        self.assertNotIn("UID=", value)
        self.assertNotIn("PWD=", value)

    def test_connection_values_cannot_inject_odbc_properties(self):
        with self.assertRaises(ValueError):
            build_windows_connection_string(
                "server;UID=unexpected",
                "database",
                "ODBC Driver 18 for SQL Server",
                False,
            )


@unittest.skipUnless(
    os.environ.get("LWB_TEST_SQL_CONNECTION_STRING"),
    "Set LWB_TEST_SQL_CONNECTION_STRING to run SQL Server integration tests",
)
class SqlServerMigrationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pyodbc

        cls.pyodbc = pyodbc
        cls.connection = pyodbc.connect(
            os.environ["LWB_TEST_SQL_CONNECTION_STRING"], timeout=10
        )
        cls.migrations = discover_migrations(DEFAULT_MIGRATIONS_PATH)
        MigrationRunner(cls.connection, cls.migrations, APP_VERSION).apply()

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def tearDown(self):
        self.connection.rollback()

    def _create_assignment(self, suffix):
        cursor = self.connection.cursor()
        unit_id = cursor.execute(
            """
            INSERT INTO dbo.UNITS (main_board_serial)
            OUTPUT INSERTED.unit_id
            VALUES (?)
            """,
            f"integration-unit-{suffix}",
        ).fetchval()
        switch_id = cursor.execute(
            """
            INSERT INTO dbo.SWITCHES (
                switch_serial,
                switch_model,
                physical_channel_count
            )
            OUTPUT INSERTED.switch_id
            VALUES (?, ?, ?)
            """,
            f"integration-switch-{suffix}",
            "OSX-150",
            48,
        ).fetchval()
        assignment_id = cursor.execute(
            """
            INSERT INTO dbo.UNIT_SWITCH_ASSIGNMENTS (
                unit_id,
                switch_id,
                installed_at_utc,
                installed_by,
                initial_channel_map_json
            )
            OUTPUT INSERTED.assignment_id
            VALUES (?, ?, SYSUTCDATETIME(), ?, ?)
            """,
            unit_id,
            switch_id,
            "integration-test",
            '{"1": 1, "2": 2}',
        ).fetchval()
        cursor.close()
        return unit_id, switch_id, assignment_id

    def _create_run(self, assignment_id, client_run_uuid):
        cursor = self.connection.cursor()
        run_id = cursor.execute(
            """
            INSERT INTO dbo.IL_RUNS (
                assignment_id,
                run_number,
                client_run_uuid,
                run_started_at_utc,
                tested_by,
                wavelength_mode,
                operating_band,
                application_version,
                measurement_hardware_json,
                limit_snapshot_json
            )
            OUTPUT INSERTED.run_id
            VALUES (?, 1, ?, SYSUTCDATETIME(), ?, 'SM', 'O band', ?, '{}', '{}')
            """,
            assignment_id,
            client_run_uuid,
            "integration-test",
            APP_VERSION,
        ).fetchval()
        cursor.close()
        return run_id

    def test_expected_tables_views_and_roles_exist(self):
        cursor = self.connection.cursor()
        tables = {
            row[0]
            for row in cursor.execute(
                "SELECT name FROM sys.tables WHERE is_ms_shipped = 0"
            ).fetchall()
        }
        views = {
            row[0]
            for row in cursor.execute(
                "SELECT name FROM sys.views WHERE is_ms_shipped = 0"
            ).fetchall()
        }
        roles = {
            row[0]
            for row in cursor.execute(
                "SELECT name FROM sys.database_principals WHERE type = 'R'"
            ).fetchall()
        }
        cursor.close()

        self.assertEqual(
            tables,
            {
                "SCHEMA_MIGRATIONS",
                "UNITS",
                "SWITCHES",
                "UNIT_SWITCH_ASSIGNMENTS",
                "IL_RUNS",
                "IL_MEASUREMENTS",
                "CHANNEL_REPLACEMENTS",
                "DESIGNATED_SPARES",
                "REPLACEMENT_ANALYSES",
                "REPLACEMENT_ANALYSIS_RECOMMENDATIONS",
            },
        )
        self.assertEqual(
            views,
            {
                "vw_CurrentILMeasurements",
                "vw_CurrentChannelMap",
                "vw_ReplacementRecommendationUsage",
            },
        )
        self.assertIn("lwb_app_writer", roles)
        self.assertIn("lwb_report_reader", roles)

    def test_reapplying_migrations_is_idempotent(self):
        result = MigrationRunner(
            self.connection, self.migrations, APP_VERSION
        ).apply()

        self.assertEqual(result.applied_ids, ())
        self.assertEqual(result.current_version, 5)

    def test_invalid_json_and_nonpositive_counts_are_rejected(self):
        cursor = self.connection.cursor()
        with self.assertRaises(Exception):
            cursor.execute(
                """
                INSERT INTO dbo.UNITS (
                    main_board_serial,
                    front_panel_channel_count
                ) VALUES (?, ?)
                """,
                "integration-invalid-count",
                0,
            )
        self.connection.rollback()

        unit_id = cursor.execute(
            """
            INSERT INTO dbo.UNITS (main_board_serial)
            OUTPUT INSERTED.unit_id
            VALUES (?)
            """,
            "integration-invalid-json-unit",
        ).fetchval()
        switch_id = cursor.execute(
            """
            INSERT INTO dbo.SWITCHES (
                switch_serial,
                switch_model,
                physical_channel_count
            )
            OUTPUT INSERTED.switch_id
            VALUES (?, ?, ?)
            """,
            "integration-invalid-json-switch",
            "OSX-150",
            48,
        ).fetchval()
        with self.assertRaises(Exception):
            cursor.execute(
                """
                INSERT INTO dbo.UNIT_SWITCH_ASSIGNMENTS (
                    unit_id,
                    switch_id,
                    installed_at_utc,
                    installed_by,
                    initial_channel_map_json
                ) VALUES (?, ?, SYSUTCDATETIME(), ?, ?)
                """,
                unit_id,
                switch_id,
                "integration-test",
                "not json",
            )
        self.connection.rollback()
        cursor.close()

    def test_invalid_status_and_duplicate_run_uuid_are_rejected(self):
        import uuid

        _unit_id, _switch_id, assignment_id = self._create_assignment("run-rules")
        cursor = self.connection.cursor()
        with self.assertRaises(self.pyodbc.IntegrityError):
            cursor.execute(
                """
                INSERT INTO dbo.IL_RUNS (
                    assignment_id,
                    run_number,
                    client_run_uuid,
                    run_started_at_utc,
                    tested_by,
                    wavelength_mode,
                    operating_band,
                    application_version,
                    completion_status,
                    measurement_hardware_json,
                    limit_snapshot_json
                ) VALUES (?, 1, ?, SYSUTCDATETIME(), ?, 'SM', 'O band', ?, ?, '{}', '{}')
                """,
                assignment_id,
                str(uuid.uuid4()),
                "integration-test",
                APP_VERSION,
                "not-a-status",
            )
        self.connection.rollback()

        _unit_id, _switch_id, assignment_id = self._create_assignment(
            "duplicate-run-uuid"
        )
        duplicate_uuid = str(uuid.uuid4())
        self._create_run(assignment_id, duplicate_uuid)
        with self.assertRaises(self.pyodbc.IntegrityError):
            self._create_run(assignment_id, duplicate_uuid)
        cursor.close()

    def test_only_one_active_assignment_per_unit_and_switch_is_allowed(self):
        cursor = self.connection.cursor()
        unit_id, switch_id, _assignment_id = self._create_assignment(
            "active-assignment"
        )
        second_switch_id = cursor.execute(
            """
            INSERT INTO dbo.SWITCHES (
                switch_serial,
                switch_model,
                physical_channel_count
            )
            OUTPUT INSERTED.switch_id
            VALUES (?, 'OSX-150', 48)
            """,
            "integration-second-switch",
        ).fetchval()
        with self.assertRaises(self.pyodbc.IntegrityError):
            cursor.execute(
                """
                INSERT INTO dbo.UNIT_SWITCH_ASSIGNMENTS (
                    unit_id,
                    switch_id,
                    installed_at_utc,
                    installed_by,
                    initial_channel_map_json
                ) VALUES (?, ?, SYSUTCDATETIME(), ?, '{}')
                """,
                unit_id,
                second_switch_id,
                "integration-test",
            )
        self.connection.rollback()

        second_unit_id = cursor.execute(
            """
            INSERT INTO dbo.UNITS (main_board_serial)
            OUTPUT INSERTED.unit_id
            VALUES (?)
            """,
            "integration-second-unit",
        ).fetchval()
        unit_id, switch_id, _assignment_id = self._create_assignment(
            "active-switch"
        )
        with self.assertRaises(self.pyodbc.IntegrityError):
            cursor.execute(
                """
                INSERT INTO dbo.UNIT_SWITCH_ASSIGNMENTS (
                    unit_id,
                    switch_id,
                    installed_at_utc,
                    installed_by,
                    initial_channel_map_json
                ) VALUES (?, ?, SYSUTCDATETIME(), ?, '{}')
                """,
                second_unit_id,
                switch_id,
                "integration-test",
            )
        cursor.close()

    def test_measurement_requires_complete_pair_and_unique_retry_identity(self):
        import uuid

        _unit_id, _switch_id, assignment_id = self._create_assignment(
            "measurement-rules"
        )
        run_id = self._create_run(assignment_id, str(uuid.uuid4()))
        cursor = self.connection.cursor()
        with self.assertRaises(self.pyodbc.IntegrityError):
            cursor.execute(
                """
                INSERT INTO dbo.IL_MEASUREMENTS (
                    measurement_uuid,
                    run_id,
                    logical_channel,
                    attempt_number,
                    wavelength_1_nm,
                    wavelength_1_il_db,
                    reference_snapshot_json,
                    written_at_utc,
                    written_by
                ) VALUES (?, ?, 1, 1, 1310, 0.5000, '{}', SYSUTCDATETIME(), ?)
                """,
                str(uuid.uuid4()),
                run_id,
                "integration-test",
            )
        self.connection.rollback()

        _unit_id, _switch_id, assignment_id = self._create_assignment(
            "measurement-uuid"
        )
        run_id = self._create_run(assignment_id, str(uuid.uuid4()))
        measurement_uuid = str(uuid.uuid4())
        insert_sql = """
            INSERT INTO dbo.IL_MEASUREMENTS (
                measurement_uuid,
                run_id,
                logical_channel,
                attempt_number,
                wavelength_1_nm,
                wavelength_1_il_db,
                wavelength_2_nm,
                wavelength_2_il_db,
                reference_snapshot_json,
                written_at_utc,
                written_by
            ) VALUES (?, ?, ?, 1, 1310, 0.5000, 1550, 0.6000, '{}',
                      SYSUTCDATETIME(), ?)
        """
        cursor.execute(
            insert_sql, measurement_uuid, run_id, 1, "integration-test"
        )
        with self.assertRaises(self.pyodbc.IntegrityError):
            cursor.execute(
                insert_sql, measurement_uuid, run_id, 2, "integration-test"
            )
        cursor.close()

    def test_negative_measurement_losses_are_rejected(self):
        import uuid

        _unit_id, _switch_id, assignment_id = self._create_assignment(
            "negative-measurement"
        )
        run_id = self._create_run(assignment_id, str(uuid.uuid4()))
        cursor = self.connection.cursor()
        with self.assertRaises(self.pyodbc.IntegrityError):
            cursor.execute(
                """
                INSERT INTO dbo.IL_MEASUREMENTS (
                    measurement_uuid,
                    run_id,
                    logical_channel,
                    attempt_number,
                    wavelength_1_nm,
                    wavelength_1_il_db,
                    wavelength_2_nm,
                    wavelength_2_il_db,
                    reference_snapshot_json,
                    written_at_utc,
                    written_by
                ) VALUES (?, ?, 1, 1, 1310, -0.1000, 1550, 0.5000, '{}',
                          SYSUTCDATETIME(), ?)
                """,
                str(uuid.uuid4()),
                run_id,
                "integration-test",
            )
        cursor.close()

    def test_current_views_select_latest_attempt_and_replacement(self):
        import uuid

        _unit_id, _switch_id, assignment_id = self._create_assignment("views")
        run_id = self._create_run(assignment_id, str(uuid.uuid4()))
        cursor = self.connection.cursor()
        for attempt_number, loss in ((1, 0.9), (2, 0.7)):
            cursor.execute(
                """
                INSERT INTO dbo.IL_MEASUREMENTS (
                    measurement_uuid,
                    run_id,
                    logical_channel,
                    physical_port,
                    attempt_number,
                    wavelength_1_nm,
                    wavelength_1_il_db,
                    wavelength_2_nm,
                    wavelength_2_il_db,
                    reference_snapshot_json,
                    written_at_utc,
                    written_by
                ) VALUES (?, ?, 1, 1, ?, 1310, ?, 1550, ?, '{}',
                          SYSUTCDATETIME(), ?)
                """,
                str(uuid.uuid4()),
                run_id,
                attempt_number,
                loss,
                loss,
                "integration-test",
            )
        cursor.execute(
            """
            INSERT INTO dbo.CHANNEL_REPLACEMENTS (
                assignment_id,
                logical_channel,
                previous_physical_port,
                replacement_physical_port,
                reason,
                replaced_by,
                replaced_at_utc
            ) VALUES (?, 1, 1, 41, ?, ?, SYSUTCDATETIME())
            """,
            assignment_id,
            "integration test",
            "integration-test",
        )

        attempt_number, current_loss = cursor.execute(
            """
            SELECT attempt_number, wavelength_1_il_db
            FROM dbo.vw_CurrentILMeasurements
            WHERE run_id = ? AND logical_channel = 1
            """,
            run_id,
        ).fetchone()
        effective_port, is_replaced = cursor.execute(
            """
            SELECT effective_physical_port, is_replaced
            FROM dbo.vw_CurrentChannelMap
            WHERE assignment_id = ? AND logical_channel = 1
            """,
            assignment_id,
        ).fetchone()
        cursor.close()

        self.assertEqual(attempt_number, 2)
        self.assertEqual(float(current_loss), 0.7)
        self.assertEqual(effective_port, 41)
        self.assertTrue(is_replaced)


if __name__ == "__main__":
    unittest.main()
