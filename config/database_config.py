"""Validated, non-secret SQL Server runtime settings."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_DATABASE_SERVER = r"localhost\SQLEXPRESS"
DEFAULT_DATABASE_NAME = "LWBTestDB"
DEFAULT_ODBC_DRIVER = "ODBC Driver 18 for SQL Server"


@dataclass(frozen=True)
class DatabaseSettings:
    """Connection policy safe to persist in a per-user INI file.

    Credentials are intentionally absent because Light Workbench uses the
    Windows identity of the signed-in operator.
    """

    enabled: bool = False
    server: str = DEFAULT_DATABASE_SERVER
    database: str = DEFAULT_DATABASE_NAME
    driver: str = DEFAULT_ODBC_DRIVER
    encrypt: bool = True
    trust_server_certificate: bool = True
    connection_timeout_seconds: int = 5
    command_timeout_seconds: int = 15

    def __post_init__(self) -> None:
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
    "DEFAULT_DATABASE_NAME",
    "DEFAULT_DATABASE_SERVER",
    "DEFAULT_ODBC_DRIVER",
    "DatabaseSettings",
]
