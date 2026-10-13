"""Bounded Windows-authenticated SQL Server connection infrastructure."""

from __future__ import annotations

from contextlib import contextmanager
from enum import Enum
from typing import Any, Callable, Iterator

from config.database_config import DatabaseSettings


class DatabaseErrorCategory(str, Enum):
    CONFIGURATION = "configuration"
    DRIVER_MISSING = "driver_missing"
    AUTHENTICATION = "authentication"
    SERVER_UNAVAILABLE = "server_unavailable"
    TIMEOUT = "timeout"
    DATABASE_MISSING = "database_missing"
    PERMISSION_DENIED = "permission_denied"
    SCHEMA_MISSING = "schema_missing"
    SCHEMA_OUTDATED = "schema_outdated"
    SCHEMA_NEWER = "schema_newer"
    SCHEMA_INVALID = "schema_invalid"
    UNKNOWN = "unknown"


class DatabaseConnectionError(RuntimeError):
    """A classified database failure suitable for operator feedback."""

    def __init__(self, category: DatabaseErrorCategory, message: str, detail: str = ""):
        super().__init__(message)
        self.category = category
        self.operator_message = message
        self.technical_detail = detail


def _safe_odbc_value(value: str, label: str) -> str:
    if not value.strip() or any(character in value for character in ";{}"):
        raise ValueError(f"Invalid {label}")
    return value.strip()


def build_windows_connection_string(
    server: str,
    database: str,
    driver: str,
    trust_server_certificate: bool,
    encrypt: bool = True,
) -> str:
    """Build an encrypted ODBC string that uses Windows Authentication."""

    server = _safe_odbc_value(server, "SQL Server instance")
    database = _safe_odbc_value(database, "database name")
    driver = _safe_odbc_value(driver, "ODBC driver")
    trust_value = "yes" if trust_server_certificate else "no"
    encrypt_value = "yes" if encrypt else "no"
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        "Trusted_Connection=yes;"
        f"Encrypt={encrypt_value};"
        f"TrustServerCertificate={trust_value};"
    )


def classify_database_exception(error: Exception) -> DatabaseConnectionError:
    """Translate ODBC/SQL Server details into a stable, safe category."""
    detail = " ".join(str(item) for item in getattr(error, "args", ()) or (error,))
    upper = detail.upper()
    if "ENCRYPTION NOT SUPPORTED ON THE CLIENT" in upper:
        category = DatabaseErrorCategory.CONFIGURATION
        message = (
            "The SQL Server client encryption configuration is not usable on this "
            "workstation."
        )
    elif "IM002" in upper or "DATA SOURCE NAME NOT FOUND" in upper:
        category = DatabaseErrorCategory.DRIVER_MISSING
        message = "The configured SQL Server ODBC driver is not installed."
    elif "HYT00" in upper or "HYT01" in upper or "TIMEOUT" in upper:
        category = DatabaseErrorCategory.TIMEOUT
        message = "The database connection timed out."
    elif "28000" in upper or "18456" in upper or "LOGIN FAILED" in upper:
        category = DatabaseErrorCategory.AUTHENTICATION
        message = "Windows Authentication was rejected by SQL Server."
    elif "4060" in upper or "CANNOT OPEN DATABASE" in upper:
        category = DatabaseErrorCategory.DATABASE_MISSING
        message = "The configured Light Workbench database is unavailable."
    elif any(token in upper for token in (" 229", " 262", " 916", "PERMISSION")):
        category = DatabaseErrorCategory.PERMISSION_DENIED
        message = "The Windows account does not have the required database permissions."
    elif any(
        token in upper
        for token in ("08001", "08004", "08S01", "10060", "10061", "SERVER DOES NOT EXIST")
    ):
        category = DatabaseErrorCategory.SERVER_UNAVAILABLE
        message = "The configured SQL Server instance could not be reached."
    else:
        category = DatabaseErrorCategory.UNKNOWN
        message = "Light Workbench could not communicate with the database."
    return DatabaseConnectionError(category, message, detail[:2000])


class DatabaseConnectionFactory:
    """Create short-lived connections and transaction-scoped cursors."""

    def __init__(
        self,
        settings: DatabaseSettings,
        connector: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self._connector = connector

    def connect(self):
        connector = self._connector
        if connector is None:
            try:
                import pyodbc
            except ImportError as exc:
                raise DatabaseConnectionError(
                    DatabaseErrorCategory.DRIVER_MISSING,
                    "The SQL Server database adapter is not installed.",
                    str(exc),
                ) from exc
            connector = pyodbc.connect
        connection_string = build_windows_connection_string(
            self.settings.server,
            self.settings.database,
            self.settings.driver,
            self.settings.trust_server_certificate,
            self.settings.encrypt,
        )
        try:
            return connector(
                connection_string,
                timeout=self.settings.connection_timeout_seconds,
                autocommit=False,
            )
        except DatabaseConnectionError:
            raise
        except Exception as exc:
            raise classify_database_exception(exc) from exc

    @contextmanager
    def connection(self) -> Iterator[Any]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        """Yield one parameterized-command cursor and commit atomically."""
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.timeout = self.settings.command_timeout_seconds
            try:
                yield cursor
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()


__all__ = [
    "DatabaseConnectionError",
    "DatabaseConnectionFactory",
    "DatabaseErrorCategory",
    "build_windows_connection_string",
    "classify_database_exception",
]
