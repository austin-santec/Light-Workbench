"""Validated SQL Server runtime settings."""

from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_DATABASE_SERVER = r"localhost\SQLEXPRESS"
DEFAULT_DATABASE_NAME = "LWBTestDB"
DEFAULT_ODBC_DRIVER = "ODBC Driver 18 for SQL Server"
DEFAULT_DATABASE_AUTHENTICATION = "windows"
SUPPORTED_DATABASE_AUTHENTICATIONS = frozenset({"windows", "sql_password"})


@dataclass(frozen=True)
class DatabaseSettings:
    """Validated per-user SQL Server connection settings.

    SQL-password mode intentionally stores the password in the per-user INI
    file because it is an explicit deployment option.  Callers must never
    include this object, or its password, in logs or error details.
    """

    enabled: bool = True
    server: str = DEFAULT_DATABASE_SERVER
    database: str = DEFAULT_DATABASE_NAME
    driver: str = DEFAULT_ODBC_DRIVER
    authentication: str = DEFAULT_DATABASE_AUTHENTICATION
    username: str = ""
    password: str = field(default="", repr=False)
    encrypt: bool = True
    trust_server_certificate: bool = True
    connection_timeout_seconds: int = 5
    command_timeout_seconds: int = 15

    def __post_init__(self) -> None:
        authentication = str(self.authentication).strip().lower()
        object.__setattr__(self, "authentication", authentication)
        if authentication not in SUPPORTED_DATABASE_AUTHENTICATIONS:
            raise ValueError(
                "Authentication must be one of: "
                + ", ".join(sorted(SUPPORTED_DATABASE_AUTHENTICATIONS))
            )
        username = str(self.username).strip()
        object.__setattr__(self, "username", username)
        if authentication == "sql_password":
            if not username:
                raise ValueError(
                    "SQL-password authentication requires a database username"
                )
            if not str(self.password):
                raise ValueError(
                    "SQL-password authentication requires a database password"
                )
        for value, label in (
            (self.server, "SQL Server instance"),
            (self.database, "database name"),
            (self.driver, "ODBC driver"),
        ):
            if not str(value).strip() or any(char in str(value) for char in ";{}"):
                raise ValueError(f"Invalid {label}")
        if not 1 <= int(self.connection_timeout_seconds) <= 30:
            raise ValueError("Connection timeout must be between 1 and 30 seconds")
        if not 1 <= int(self.command_timeout_seconds) <= 120:
            raise ValueError("Command timeout must be between 1 and 120 seconds")


__all__ = [
    "DEFAULT_DATABASE_AUTHENTICATION",
    "DEFAULT_DATABASE_NAME",
    "DEFAULT_DATABASE_SERVER",
    "DEFAULT_ODBC_DRIVER",
    "DatabaseSettings",
    "SUPPORTED_DATABASE_AUTHENTICATIONS",
]
