"""Backward-compatible INI persistence for extra-port safety settings."""

import configparser
import os
import tempfile
from pathlib import Path

from config.app_config import default_extra_port_settings_path
from domain.extra_ports import ExtraPortSettings


class ExtraPortSettingsRepository:
    """Load and atomically save administrator-controlled probe limits."""

    SECTION = "extra_port_testing"

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_extra_port_settings_path()

    def load(self) -> ExtraPortSettings:
        defaults = ExtraPortSettings()
        if not self.path.is_file():
            return defaults
        parser = configparser.ConfigParser()
        parser.read(self.path, encoding="utf-8")
        value = parser.get(
            self.SECTION,
            "maximum_physical_port_probe",
            fallback=str(defaults.maximum_physical_port_probe),
        )
        return ExtraPortSettings(int(value)).validate()

    def save(self, settings: ExtraPortSettings) -> None:
        settings = settings.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        parser = configparser.ConfigParser()
        parser[self.SECTION] = {
            "maximum_physical_port_probe": str(
                settings.maximum_physical_port_probe
            )
        }
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=self.path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                parser.write(stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()


__all__ = ["ExtraPortSettingsRepository"]
