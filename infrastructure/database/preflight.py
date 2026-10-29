"""Read-only SQL Server connectivity and schema compatibility checks."""

from __future__ import annotations

import time
from dataclasses import dataclass

from config.app_info import APP_VERSION
from infrastructure.database.connection import (
    DatabaseConnectionError,
    DatabaseConnectionFactory,
    DatabaseErrorCategory,
    classify_database_exception,
)
from infrastructure.database.migrations import (
    MigrationChecksumError,
    MigrationHistoryError,
    MigrationRunner,
    UnsupportedSchemaVersionError,
    discover_migrations,
)


@dataclass(frozen=True)
class DatabasePreflightResult:
    ready: bool
    category: DatabaseErrorCategory | None
    operator_message: str
    technical_detail: str
    current_schema_version: int | None
    expected_schema_version: int
    elapsed_ms: int


def check_database_preflight(
    factory: DatabaseConnectionFactory,
) -> DatabasePreflightResult:
    """Check connectivity and migration history without changing the database."""
    started = time.monotonic()
    migrations = discover_migrations()
    expected = max(item.migration_id for item in migrations)
    try:
        with factory.connection() as connection:
            try:
                connection.timeout = factory.settings.command_timeout_seconds
            except (AttributeError, TypeError):
                pass
            runner = MigrationRunner(connection, migrations, APP_VERSION)
            pending = runner.pending_migrations()
            current = expected - len(pending)
            if pending:
                return _result(
                    started,
                    expected,
                    current,
                    DatabaseErrorCategory.SCHEMA_OUTDATED,
                    "The database schema must be migrated before Light Workbench can use it.",
                    "Pending migration IDs: "
                    + ", ".join(str(item.migration_id) for item in pending),
                )
    except UnsupportedSchemaVersionError as exc:
        return _result(
            started,
            expected,
            None,
            DatabaseErrorCategory.SCHEMA_NEWER,
            "The database schema is newer than this Light Workbench version supports.",
            str(exc),
        )
    except (MigrationChecksumError, MigrationHistoryError) as exc:
        return _result(
            started,
            expected,
            None,
            DatabaseErrorCategory.SCHEMA_INVALID,
            "The database migration history is invalid and requires administrator review.",
            str(exc),
        )
    except DatabaseConnectionError as exc:
        return _result(
            started,
            expected,
            None,
            exc.category,
            exc.operator_message,
            exc.technical_detail,
        )
    except Exception as exc:
        classified = classify_database_exception(exc)
        return _result(
            started,
            expected,
            None,
            classified.category,
            classified.operator_message,
            classified.technical_detail,
        )
    return DatabasePreflightResult(
        ready=True,
        category=None,
        operator_message="The database connection and schema are ready.",
        technical_detail="",
        current_schema_version=expected,
        expected_schema_version=expected,
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )


def _result(
    started: float,
    expected: int,
    current: int | None,
    category: DatabaseErrorCategory,
    message: str,
    detail: str,
) -> DatabasePreflightResult:
    return DatabasePreflightResult(
        ready=False,
        category=category,
        operator_message=message,
        technical_detail=detail[:2000],
        current_schema_version=current,
        expected_schema_version=expected,
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )


__all__ = ["DatabasePreflightResult", "check_database_preflight"]
