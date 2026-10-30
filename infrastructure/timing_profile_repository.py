"""INI persistence for administrator-controlled timing profiles."""

from __future__ import annotations

import configparser
import os
from pathlib import Path
import tempfile

from config.app_config import default_timing_profile_path
from domain.measurement_timing import (
    MeasurementTimingProfile,
    default_measurement_timing_profiles,
)


class TimingProfileRepository:
    """Load and atomically save production measurement timing profiles."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_timing_profile_path()

    def load(self):
        defaults = default_measurement_timing_profiles()
        if not self.path.is_file():
            return defaults, "standard"

        parser = configparser.ConfigParser()
        try:
            parser.read(self.path, encoding="utf-8")
        except (OSError, configparser.Error, UnicodeError):
            return defaults, "standard"

        profiles = dict(defaults)
        for section in parser.sections():
            if not section.startswith("profile:"):
                continue
            profile_id = section.split(":", 1)[1].strip()
            try:
                profile = MeasurementTimingProfile(
                    profile_id=profile_id,
                    name=parser.get(section, "name"),
                    revision=parser.getint(section, "revision", fallback=1),
                    wavelength_settling_ms=parser.getint(
                        section, "opm_wavelength_settling_ms"
                    ),
                    source_settling_ms=parser.getint(
                        section, "laser_source_settling_ms"
                    ),
                    live_update_pause_ms=parser.getint(
                        section, "live_update_pause_ms"
                    ),
                ).validate()
            except (configparser.Error, TypeError, ValueError):
                continue
            profiles[profile.profile_id] = profile

        active_id = parser.get("active", "profile_id", fallback="standard").strip()
        if active_id not in profiles:
            active_id = "standard"
        return profiles, active_id

    def save(self, profiles, active_profile_id: str):
        validated = {}
        for profile in dict(profiles).values():
            normalized = profile.validate()
            validated[normalized.profile_id] = normalized
        if "standard" not in validated:
            validated["standard"] = default_measurement_timing_profiles()["standard"]
        active_id = str(active_profile_id or "standard").strip().lower()
        if active_id not in validated:
            raise ValueError("The selected timing profile does not exist.")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        parser = configparser.ConfigParser()
        parser["active"] = {"profile_id": active_id}
        for profile_id, profile in sorted(validated.items()):
            profile = profile.validate()
            parser["profile:%s" % profile_id] = {
                "name": profile.name,
                "revision": str(profile.revision),
                "opm_wavelength_settling_ms": str(profile.wavelength_settling_ms),
                "laser_source_settling_ms": str(profile.source_settling_ms),
                "live_update_pause_ms": str(profile.live_update_pause_ms),
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


__all__ = ["TimingProfileRepository"]
