"""Validated production measurement timing profiles."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re


DEFAULT_WAVELENGTH_SETTLING_MS = 100
DEFAULT_SOURCE_SETTLING_MS = 500
DEFAULT_LIVE_UPDATE_PAUSE_MS = 250
MAX_TIMING_MS = 10_000


def _profile_id(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if not text:
        raise ValueError("Timing profile ID is required.")
    return text


@dataclass(frozen=True)
class MeasurementTimingProfile:
    """One administrator-controlled production timing profile."""

    profile_id: str
    name: str
    revision: int = 1
    wavelength_settling_ms: int = DEFAULT_WAVELENGTH_SETTLING_MS
    source_settling_ms: int = DEFAULT_SOURCE_SETTLING_MS
    live_update_pause_ms: int = DEFAULT_LIVE_UPDATE_PAUSE_MS

    def validate(self) -> "MeasurementTimingProfile":
        profile_id = _profile_id(self.profile_id)
        name = str(self.name or "").strip()
        if not name:
            raise ValueError("Timing profile name is required.")
        try:
            revision = int(self.revision)
        except (TypeError, ValueError) as error:
            raise ValueError("Timing profile revision must be an integer.") from error
        if revision < 1:
            raise ValueError("Timing profile revision must be positive.")

        values = (
            self.wavelength_settling_ms,
            self.source_settling_ms,
            self.live_update_pause_ms,
        )
        normalized = []
        for value in values:
            try:
                numeric = float(value)
            except (TypeError, ValueError) as error:
                raise ValueError("Timing values must be finite milliseconds.") from error
            if not math.isfinite(numeric) or numeric < 0 or numeric > MAX_TIMING_MS:
                raise ValueError(
                    "Timing values must be between 0 and %d ms." % MAX_TIMING_MS
                )
            if int(numeric) != numeric:
                raise ValueError("Timing values must be whole milliseconds.")
            normalized.append(int(numeric))

        return MeasurementTimingProfile(
            profile_id=profile_id,
            name=name,
            revision=revision,
            wavelength_settling_ms=normalized[0],
            source_settling_ms=normalized[1],
            live_update_pause_ms=normalized[2],
        )

    @property
    def wavelength_settling_seconds(self) -> float:
        return self.wavelength_settling_ms / 1000.0

    @property
    def source_settling_seconds(self) -> float:
        return self.source_settling_ms / 1000.0

    @property
    def live_update_pause_seconds(self) -> float:
        return self.live_update_pause_ms / 1000.0

    def as_dict(self) -> dict[str, object]:
        profile = self.validate()
        return {
            "profile_id": profile.profile_id,
            "profile_name": profile.name,
            "profile_revision": profile.revision,
            "opm_wavelength_settling_ms": profile.wavelength_settling_ms,
            "laser_source_settling_ms": profile.source_settling_ms,
            "live_update_pause_ms": profile.live_update_pause_ms,
        }


def default_measurement_timing_profiles() -> dict[str, MeasurementTimingProfile]:
    """Return the shipped profiles without sharing mutable state."""
    profiles = (
        MeasurementTimingProfile(
            "standard",
            "Standard",
            wavelength_settling_ms=100,
            source_settling_ms=500,
            live_update_pause_ms=250,
        ),
        MeasurementTimingProfile(
            "conservative",
            "Conservative",
            wavelength_settling_ms=250,
            source_settling_ms=1000,
            live_update_pause_ms=500,
        ),
        MeasurementTimingProfile(
            "fast_experimental",
            "Fast Experimental",
            wavelength_settling_ms=50,
            source_settling_ms=250,
            live_update_pause_ms=100,
        ),
    )
    return {profile.profile_id: profile.validate() for profile in profiles}


__all__ = [
    "DEFAULT_LIVE_UPDATE_PAUSE_MS",
    "DEFAULT_SOURCE_SETTLING_MS",
    "DEFAULT_WAVELENGTH_SETTLING_MS",
    "MAX_TIMING_MS",
    "MeasurementTimingProfile",
    "default_measurement_timing_profiles",
]
