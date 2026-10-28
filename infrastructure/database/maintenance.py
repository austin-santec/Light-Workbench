"""Guarded reset, backup, and restore operations for SQL integration testing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INTEGRATION_DATABASE_NAME = "LWBTestDB_Integration"
RESTORE_VERIFICATION_DATABASE_NAME = "LWBTestDB_RestoreVerification"
_SAFE_DATABASE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")


class DatabaseMaintenanceError(RuntimeError):
    """Raised when a guarded database-maintenance operation cannot complete."""


@dataclass(frozen=True)
class BackupVerificationResult:
    """Results collected from a successful backup/restore verification."""

    backup_path: Path
    migration_count: int
    table_count: int
    view_count: int


def quote_database_identifier(database: str) -> str:
    """Validate and quote a database identifier used in maintenance SQL."""

    if _SAFE_DATABASE_NAME.fullmatch(database) is None:
        raise DatabaseMaintenanceError(f"Unsafe database name: {database!r}")
    return f"[{database}]"


def _quote_sql_text(value: str) -> str:
    """Quote internally generated maintenance text as a Unicode SQL literal."""

    return "N'" + value.replace("'", "''") + "'"


def validate_integration_target(database: str, confirmation: str) -> None:
    """Require the exact disposable database name and matching confirmation."""

    if database != INTEGRATION_DATABASE_NAME:
        raise DatabaseMaintenanceError(
            "Reset and verification operations are restricted to "
            f"{INTEGRATION_DATABASE_NAME}; received {database!r}"
        )
    if confirmation != database:
        raise DatabaseMaintenanceError(
            "Database confirmation does not exactly match the integration target"
        )


def reset_integration_database(
    master_connection: Any,
    database: str,
    confirmation: str,
) -> None:
    """Drop and recreate only the explicitly confirmed integration database."""

    validate_integration_target(database, confirmation)
    quoted_database = quote_database_identifier(database)
    cursor = master_connection.cursor()
    try:
        exists = cursor.execute("SELECT DB_ID(?)", database).fetchone()[0]
        if exists is not None:
            cursor.execute(
                f"ALTER DATABASE {quoted_database} SET SINGLE_USER "
                "WITH ROLLBACK IMMEDIATE"
            )
            cursor.execute(f"DROP DATABASE {quoted_database}")
        cursor.execute(f"CREATE DATABASE {quoted_database}")
        cursor.execute(f"ALTER DATABASE {quoted_database} SET RECOVERY SIMPLE")
    except Exception as exc:
        raise DatabaseMaintenanceError(
            f"Could not reset integration database {database}: {exc}"
        ) from exc
    finally:
        cursor.close()


def temporary_backup_path(master_connection: Any, database: str) -> Path:
    """Return a unique .bak path in SQL Server's existing data directory."""

    validate_integration_target(database, database)
    cursor = master_connection.cursor()
    try:
        directory = cursor.execute(
            """
            SELECT CONVERT(nvarchar(4000),
                           SERVERPROPERTY('InstanceDefaultDataPath'))
            """
        ).fetchone()[0]
    finally:
        cursor.close()
    if not directory:
        raise DatabaseMaintenanceError(
            "SQL Server did not report its default data directory"
        )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(str(directory)) / f"{database}_{timestamp}.bak"


def delete_temporary_backup(master_connection: Any, backup_path: Path) -> None:
    """Delete one verified integration backup through the SQL Server service."""

    cursor = master_connection.cursor()
    try:
        data_directory = cursor.execute(
            """
            SELECT CONVERT(nvarchar(4000),
                           SERVERPROPERTY('InstanceDefaultDataPath'))
            """
        ).fetchone()[0]
        expected_parent = Path(str(data_directory)).resolve()
        actual_path = backup_path.resolve()
        if (
            actual_path.parent != expected_parent
            or actual_path.suffix.lower() != ".bak"
            or not actual_path.name.startswith(f"{INTEGRATION_DATABASE_NAME}_")
        ):
            raise DatabaseMaintenanceError(
                f"Refusing to delete unrecognized backup path: {backup_path}"
            )
        cursor.execute(
            "EXEC master.dbo.xp_delete_file 0, "
            f"{_quote_sql_text(str(actual_path))}, N'bak'"
        )
        _drain_results(cursor)
        exists = cursor.execute(
            "EXEC master.dbo.xp_fileexist "
            f"{_quote_sql_text(str(actual_path))}"
        ).fetchone()[0]
        if exists:
            raise DatabaseMaintenanceError(
                f"SQL Server did not delete temporary backup: {actual_path}"
            )
    finally:
        cursor.close()


def verify_backup_restore(
    master_connection: Any,
    source_database: str,
    confirmation: str,
    backup_path: Path,
) -> BackupVerificationResult:
    """Back up the integration DB, restore a temporary copy, and validate it."""

    validate_integration_target(source_database, confirmation)
    if not backup_path.is_absolute() or backup_path.suffix.lower() != ".bak":
        raise DatabaseMaintenanceError("Backup path must be an absolute .bak file")

    source = quote_database_identifier(source_database)
    restore_database = RESTORE_VERIFICATION_DATABASE_NAME
    restored = quote_database_identifier(restore_database)
    backup_literal = _quote_sql_text(str(backup_path))
    cursor = master_connection.cursor()
    result: BackupVerificationResult | None = None
    failure: DatabaseMaintenanceError | None = None
    try:
        if cursor.execute("SELECT DB_ID(?)", source_database).fetchone()[0] is None:
            raise DatabaseMaintenanceError(
                f"Source database does not exist: {source_database}"
            )

        _drop_database_if_present(cursor, restore_database)
        cursor.execute(
            f"BACKUP DATABASE {source} TO DISK = {backup_literal} "
            "WITH COPY_ONLY, INIT, CHECKSUM"
        )
        _drain_results(cursor)
        cursor.execute(
            f"RESTORE VERIFYONLY FROM DISK = {backup_literal} WITH CHECKSUM"
        )
        _drain_results(cursor)
        file_rows = cursor.execute(
            f"RESTORE FILELISTONLY FROM DISK = {backup_literal}"
        ).fetchall()
        _drain_results(cursor)
        data_logical_name, log_logical_name = _logical_file_names(file_rows)

        data_directory, log_directory = cursor.execute(
            """
            SELECT
                CONVERT(nvarchar(4000), SERVERPROPERTY('InstanceDefaultDataPath')),
                CONVERT(nvarchar(4000), SERVERPROPERTY('InstanceDefaultLogPath'))
            """
        ).fetchone()
        if not data_directory or not log_directory:
            raise DatabaseMaintenanceError(
                "SQL Server did not report default data and log directories"
            )
        unique_suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        data_path = Path(str(data_directory)) / (
            f"{restore_database}_{unique_suffix}.mdf"
        )
        log_path = Path(str(log_directory)) / (
            f"{restore_database}_{unique_suffix}_log.ldf"
        )

        cursor.execute(
            f"RESTORE DATABASE {restored} FROM DISK = {backup_literal} "
            f"WITH MOVE {_quote_sql_text(data_logical_name)} "
            f"TO {_quote_sql_text(str(data_path))}, "
            f"MOVE {_quote_sql_text(log_logical_name)} "
            f"TO {_quote_sql_text(str(log_path))}, RECOVERY"
        )
        _drain_results(cursor)
        cursor.execute(f"DBCC CHECKDB ({restored}) WITH NO_INFOMSGS")
        _drain_results(cursor)

        migration_count = int(
            cursor.execute(
                f"SELECT COUNT(*) FROM {restored}.dbo.SCHEMA_MIGRATIONS"
            ).fetchone()[0]
        )
        table_count = int(
            cursor.execute(
                f"SELECT COUNT(*) FROM {restored}.sys.tables "
                "WHERE is_ms_shipped = 0"
            ).fetchone()[0]
        )
        view_count = int(
            cursor.execute(
                f"SELECT COUNT(*) FROM {restored}.sys.views "
                "WHERE is_ms_shipped = 0"
            ).fetchone()[0]
        )
        if migration_count < 1 or table_count != 10 or view_count != 4:
            raise DatabaseMaintenanceError(
                "Restored schema validation failed: "
                f"migrations={migration_count}, tables={table_count}, "
                f"views={view_count}"
            )
        result = BackupVerificationResult(
            backup_path=backup_path,
            migration_count=migration_count,
            table_count=table_count,
            view_count=view_count,
        )
    except DatabaseMaintenanceError as exc:
        failure = exc
    except Exception as exc:
        failure = DatabaseMaintenanceError(
            f"Backup/restore verification failed: {exc}"
        )
        failure.__cause__ = exc
    finally:
        try:
            _drop_database_if_present(cursor, restore_database)
        except Exception as cleanup_exc:
            if failure is None:
                failure = DatabaseMaintenanceError(
                    "Backup was checked, but the temporary restored database "
                    f"could not be removed: {cleanup_exc}"
                )
                failure.__cause__ = cleanup_exc
            else:
                failure.add_note(
                    "Temporary restore cleanup also failed: "
                    f"{cleanup_exc}"
                )
        finally:
            cursor.close()
    if failure is not None:
        raise failure
    if result is None:
        raise DatabaseMaintenanceError("Backup verification produced no result")
    return result


def _drop_database_if_present(cursor: Any, database: str) -> None:
    quoted_database = quote_database_identifier(database)
    if cursor.execute("SELECT DB_ID(?)", database).fetchone()[0] is not None:
        cursor.execute(
            f"ALTER DATABASE {quoted_database} SET SINGLE_USER "
            "WITH ROLLBACK IMMEDIATE"
        )
        cursor.execute(f"DROP DATABASE {quoted_database}")


def _logical_file_names(file_rows: Any) -> tuple[str, str]:
    data_names = [str(row[0]) for row in file_rows if str(row[2]).upper() == "D"]
    log_names = [str(row[0]) for row in file_rows if str(row[2]).upper() == "L"]
    if len(data_names) != 1 or len(log_names) != 1:
        raise DatabaseMaintenanceError(
            "Expected exactly one data file and one log file in integration backup"
        )
    return data_names[0], log_names[0]


def _drain_results(cursor: Any) -> None:
    """Consume SQL Server completion result sets before the next command."""

    nextset = getattr(cursor, "nextset", None)
    if nextset is None:
        return
    try:
        while nextset():
            pass
    except Exception as exc:
        if "No results.  Previous SQL was not a query." not in str(exc):
            raise
