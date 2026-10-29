"""INI persistence for per-user database endpoint and authentication settings."""

from __future__ import annotations

import configparser
import os
from io import StringIO
from pathlib import Path

from config.database_config import DatabaseSettings
from infrastructure.database.connection import DatabaseConfigurationError


class DatabaseSettingsRepository:
    """Load and save the explicit per-user database configuration."""

    SECTION = "database"

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> DatabaseSettings:
        if not self.path.is_file():
            return DatabaseSettings()
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(self.path, encoding="utf-8")
        except (configparser.Error, OSError, UnicodeError) as error:
            raise self._configuration_error(
                "Could not read the database configuration file.", error
            ) from error
        if not parser.has_section(self.SECTION):
            raise self._configuration_error(
                "The database configuration file is missing its [database] section."
            )
        section = parser[self.SECTION]
        defaults = DatabaseSettings()
        try:
            return DatabaseSettings(
                enabled=self._boolean(section, "enabled", defaults.enabled),
                server=section.get("server", defaults.server),
                database=section.get("database", defaults.database),
                driver=section.get("driver", defaults.driver),
                authentication=section.get(
                    "authentication", defaults.authentication
                ),
                username=section.get("username", defaults.username),
                password=section.get("password", defaults.password),
                encrypt=self._boolean(section, "encrypt", defaults.encrypt),
                trust_server_certificate=self._boolean(
                    section,
                    "trust_server_certificate",
                    defaults.trust_server_certificate,
                ),
                connection_timeout_seconds=self._integer(
                    section,
                    "connection_timeout_seconds",
                    defaults.connection_timeout_seconds,
                ),
                command_timeout_seconds=self._integer(
                    section, "command_timeout_seconds", defaults.command_timeout_seconds
                ),
            )
        except (TypeError, ValueError) as error:
            raise self._configuration_error(
                "The database configuration contains an invalid setting.", error
            ) from error

    def ensure_exists(self) -> bool:
        """Create the default file if absent, without replacing an existing file."""
        if self.path.is_file():
            return False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("x", encoding="utf-8", newline="") as stream:
                stream.write(self._serialize(DatabaseSettings()))
                stream.flush()
                os.fsync(stream.fileno())
            return True
        except FileExistsError:
            if self.path.is_file():
                return False
            raise self._configuration_error(
                "The database configuration path exists but is not a file."
            )
        except (OSError, ValueError) as error:
            raise self._configuration_error(
                "Could not create the default database configuration file.", error
            ) from error

    def save(self, settings: DatabaseSettings) -> None:
        parser = configparser.ConfigParser(interpolation=None)
        parser[self.SECTION] = {
            "enabled": str(settings.enabled).lower(),
            "server": settings.server,
            "database": settings.database,
            "driver": settings.driver,
            "authentication": settings.authentication,
            "username": settings.username,
            "password": settings.password,
            "encrypt": str(settings.encrypt).lower(),
            "trust_server_certificate": str(
                settings.trust_server_certificate
            ).lower(),
            "connection_timeout_seconds": str(settings.connection_timeout_seconds),
            "command_timeout_seconds": str(settings.command_timeout_seconds),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as stream:
            parser.write(stream)

    @staticmethod
    def _serialize(settings: DatabaseSettings) -> str:
        parser = configparser.ConfigParser(interpolation=None)
        parser[DatabaseSettingsRepository.SECTION] = {
            "enabled": str(settings.enabled).lower(),
            "server": settings.server,
            "database": settings.database,
            "driver": settings.driver,
            "authentication": settings.authentication,
            "username": settings.username,
            "password": settings.password,
            "encrypt": str(settings.encrypt).lower(),
            "trust_server_certificate": str(
                settings.trust_server_certificate
            ).lower(),
            "connection_timeout_seconds": str(settings.connection_timeout_seconds),
            "command_timeout_seconds": str(settings.command_timeout_seconds),
        }
        stream = StringIO()
        parser.write(stream)
        return stream.getvalue()

    def _configuration_error(self, message: str, detail: object = ""):
        return DatabaseConfigurationError(
            "%s Path: %s" % (message, self.path),
            str(detail),
        )

    @staticmethod
    def _boolean(section, key: str, default: bool) -> bool:
        raw = section.get(key)
        if raw is None:
            return default
        normalized = str(raw).strip().lower()
        if normalized in {"1", "yes", "true", "on"}:
            return True
        if normalized in {"0", "no", "false", "off"}:
            return False
        raise ValueError(f"Invalid boolean database setting: {key}")

    @staticmethod
    def _integer(section, key: str, default: int) -> int:
        raw = section.get(key, default)
        try:
            return int(raw)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid integer database setting: {key}") from error


__all__ = ["DatabaseSettingsRepository"]
