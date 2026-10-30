"""SQL Server infrastructure for the database-backed Light Workbench branch."""

from infrastructure.database.connection import (
    DatabaseConfigurationError,
    DatabaseConnectionError,
    DatabaseConnectionFactory,
    DatabaseErrorCategory,
    build_connection_string,
    build_sql_password_connection_string,
    build_windows_connection_string,
    classify_database_exception,
)
from infrastructure.database.preflight import (
    DatabasePreflightResult,
    check_database_preflight,
)
from infrastructure.database.settings_repository import DatabaseSettingsRepository
from infrastructure.database.memory_repositories import InMemoryRepositories
from infrastructure.database.sql_repositories import SqlRepositories
from infrastructure.database.maintenance import (
    INTEGRATION_DATABASE_NAME,
    RESTORE_VERIFICATION_DATABASE_NAME,
    BackupVerificationResult,
    DatabaseMaintenanceError,
    delete_temporary_backup,
    reset_integration_database,
    temporary_backup_path,
    verify_backup_restore,
)
from infrastructure.database.migrations import (
    DEFAULT_MIGRATIONS_PATH,
    Migration,
    MigrationChecksumError,
    MigrationError,
    MigrationHistoryError,
    MigrationResult,
    MigrationRunner,
    UnsupportedSchemaVersionError,
    discover_migrations,
)

__all__ = [
    "BackupVerificationResult",
    "DEFAULT_MIGRATIONS_PATH",
    "DatabaseMaintenanceError",
    "DatabaseConnectionError",
    "DatabaseConfigurationError",
    "DatabaseConnectionFactory",
    "DatabaseErrorCategory",
    "DatabasePreflightResult",
    "DatabaseSettingsRepository",
    "INTEGRATION_DATABASE_NAME",
    "InMemoryRepositories",
    "Migration",
    "MigrationChecksumError",
    "MigrationError",
    "MigrationHistoryError",
    "MigrationResult",
    "MigrationRunner",
    "RESTORE_VERIFICATION_DATABASE_NAME",
    "SqlRepositories",
    "UnsupportedSchemaVersionError",
    "build_connection_string",
    "build_sql_password_connection_string",
    "build_windows_connection_string",
    "check_database_preflight",
    "classify_database_exception",
    "delete_temporary_backup",
    "discover_migrations",
    "reset_integration_database",
    "temporary_backup_path",
    "verify_backup_restore",
]
