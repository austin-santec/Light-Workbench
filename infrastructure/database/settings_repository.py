"""INI persistence for non-secret database endpoint settings."""

from __future__ import annotations

import configparser
from pathlib import Path

from config.database_config import DatabaseSettings


class DatabaseSettingsRepository:
    """Load and save SQL settings without ever handling credentials."""

    SECTION = "database"

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> DatabaseSettings:
        if not self.path.is_file():
            return DatabaseSettings()
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(self.path, encoding="utf-8")
        section = parser[self.SECTION] if parser.has_section(self.SECTION) else {}
        defaults = DatabaseSettings()
        return DatabaseSettings(
            enabled=self._boolean(section, "enabled", defaults.enabled),
            server=section.get("server", defaults.server),
            database=section.get("database", defaults.database),
            driver=section.get("driver", defaults.driver),
            encrypt=self._boolean(section, "encrypt", defaults.encrypt),
            trust_server_certificate=self._boolean(
                section,
                "trust_server_certificate",
                defaults.trust_server_certificate,
            ),
            connection_timeout_seconds=int(
                section.get(
                    "connection_timeout_seconds",
                    defaults.connection_timeout_seconds,
                )
            ),
            command_timeout_seconds=int(
                section.get("command_timeout_seconds", defaults.command_timeout_seconds)
            ),
        )

    def save(self, settings: DatabaseSettings) -> None:
        parser = configparser.ConfigParser(interpolation=None)
        parser[self.SECTION] = {
            "enabled": str(settings.enabled).lower(),
            "server": settings.server,
            "database": settings.database,
            "driver": settings.driver,
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


__all__ = ["DatabaseSettingsRepository"]
