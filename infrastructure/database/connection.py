"""Bounded SQL Server connection infrastructure."""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import Enum
from threading import get_ident
from typing import Any, Callable, Iterator

from config.database_config import DatabaseSettings
from infrastructure.database.load_metrics import (
    measure_active_stage,
    record_connection,
    record_transaction,
)


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


class DatabaseConfigurationError(DatabaseConnectionError):
    """A database INI file is malformed or contains invalid settings."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(DatabaseErrorCategory.CONFIGURATION, message, detail)


@dataclass
class _ReadSessionState:
    """One context-local connection owned by a read-only workflow."""

    connection: Any
    owner_thread_id: int


def _safe_odbc_value(value: str, label: str) -> str:
    if not value.strip() or any(character in value for character in ";{}"):
        raise ValueError(f"Invalid {label}")
    return value.strip()


def _odbc_quoted_value(value: str) -> str:
    """Quote an ODBC value, including embedded closing braces safely."""

    return "{" + str(value).replace("}", "}}") + "}"


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


def build_sql_password_connection_string(
    server: str,
    database: str,
    driver: str,
    username: str,
    password: str,
    trust_server_certificate: bool,
    encrypt: bool = True,
) -> str:
    """Build an encrypted ODBC string using SQL Server Authentication."""

    server = _safe_odbc_value(server, "SQL Server instance")
    database = _safe_odbc_value(database, "database name")
    driver = _safe_odbc_value(driver, "ODBC driver")
    if not str(username).strip():
        raise ValueError("SQL-password authentication requires a database username")
    if not str(password):
        raise ValueError("SQL-password authentication requires a database password")
    trust_value = "yes" if trust_server_certificate else "no"
    encrypt_value = "yes" if encrypt else "no"
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={_odbc_quoted_value(username.strip())};"
        f"PWD={_odbc_quoted_value(password)};"
        f"Encrypt={encrypt_value};"
        f"TrustServerCertificate={trust_value};"
    )


def build_connection_string(settings: DatabaseSettings) -> str:
    """Build the runtime connection string for the configured auth mode."""

    if settings.authentication == "windows":
        return build_windows_connection_string(
            settings.server,
            settings.database,
            settings.driver,
            settings.trust_server_certificate,
            settings.encrypt,
        )
    if settings.authentication == "sql_password":
        return build_sql_password_connection_string(
            settings.server,
            settings.database,
            settings.driver,
            settings.username,
            settings.password,
            settings.trust_server_certificate,
            settings.encrypt,
        )
    raise ValueError(f"Unsupported database authentication: {settings.authentication}")


def _redact_database_detail(detail: str, secrets: tuple[str, ...] = ()) -> str:
    """Remove credentials before a driver detail reaches logs or UI."""

    for secret in secrets:
        if secret:
            detail = detail.replace(secret, "<redacted>")
    return re.sub(
        r"(?i)(password|pwd)\s*=\s*([^;\s]*)",
        r"\1=<redacted>",
        detail,
    )


def classify_database_exception(
    error: Exception,
    secrets: tuple[str, ...] = (),
) -> DatabaseConnectionError:
    """Translate ODBC/SQL Server details into a stable, safe category."""
    detail = _redact_database_detail(
        " ".join(str(item) for item in getattr(error, "args", ()) or (error,)),
        secrets,
    )
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
        message = "The configured database authentication was rejected by SQL Server."
    elif "4060" in upper or "CANNOT OPEN DATABASE" in upper:
        category = DatabaseErrorCategory.DATABASE_MISSING
        message = "The configured Light Workbench database is unavailable."
    elif any(token in upper for token in (" 229", " 262", " 916", "PERMISSION")):
        category = DatabaseErrorCategory.PERMISSION_DENIED
        message = "The configured database identity does not have the required permissions."
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
        self._read_session_state: ContextVar[_ReadSessionState | None] = ContextVar(
            "light_workbench_database_read_session_%x" % id(self),
            default=None,
        )

    def _active_read_session(self) -> _ReadSessionState | None:
        state = self._read_session_state.get()
        if state is not None and state.owner_thread_id != get_ident():
            raise RuntimeError(
                "Database read sessions cannot be shared between threads"
            )
        return state

    def _set_command_timeout(self, target: Any) -> None:
        try:
            target.timeout = self.settings.command_timeout_seconds
        except (AttributeError, TypeError):
            pass

    def connect(self):
        record_connection()
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
        connection_string = build_connection_string(self.settings)
        try:
            return connector(
                connection_string,
                timeout=self.settings.connection_timeout_seconds,
                autocommit=False,
            )
        except DatabaseConnectionError:
            raise
        except Exception as exc:
            raise classify_database_exception(
                exc,
                (
                    (self.settings.password,)
                    if self.settings.authentication == "sql_password"
                    else ()
                ),
            ) from exc

    @contextmanager
    def connection(self) -> Iterator[Any]:
        active = self._active_read_session()
        if active is not None:
            yield active.connection
            return
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def read_session(self) -> Iterator[Any]:
        """Reuse one connection for a bounded read workflow and never commit it.

        Nested repository transaction scopes receive independent cursors on this
        connection.  The outer scope rolls the transaction back even after a
        successful load, which keeps the boundary read-only if a future caller
        accidentally invokes a mutating repository method.
        """

        active = self._active_read_session()
        if active is not None:
            yield active.connection
            return

        with measure_active_stage("connection_open"):
            connection = self.connect()
        self._set_command_timeout(connection)
        state = _ReadSessionState(connection, get_ident())
        token = self._read_session_state.set(state)
        record_transaction()
        operation_failed = False
        try:
            yield connection
        except BaseException:
            operation_failed = True
            raise
        finally:
            cleanup_error = None
            with measure_active_stage("read_session_cleanup"):
                try:
                    connection.rollback()
                except Exception as error:
                    cleanup_error = error
                self._read_session_state.reset(token)
                try:
                    connection.close()
                except Exception as error:
                    cleanup_error = cleanup_error or error
                if cleanup_error is not None and not operation_failed:
                    raise cleanup_error

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        """Yield one parameterized-command cursor and commit atomically."""
        active = self._active_read_session()
        if active is not None:
            cursor = active.connection.cursor()
            self._set_command_timeout(cursor)
            operation_failed = False
            try:
                yield cursor
            except BaseException:
                operation_failed = True
                raise
            finally:
                try:
                    cursor.close()
                except Exception:
                    if not operation_failed:
                        raise
            return

        record_transaction()
        with self.connection() as connection:
            self._set_command_timeout(connection)
            cursor = connection.cursor()
            # pyodbc exposes query timeout on Connection; lightweight test
            # doubles and some DB-API drivers expose it on Cursor instead.
            self._set_command_timeout(cursor)
            try:
                yield cursor
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()


__all__ = [
    "DatabaseConfigurationError",
    "DatabaseConnectionError",
    "DatabaseConnectionFactory",
    "DatabaseErrorCategory",
    "build_connection_string",
    "build_sql_password_connection_string",
    "build_windows_connection_string",
    "classify_database_exception",
]
