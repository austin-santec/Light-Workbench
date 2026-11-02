"""Validated production measurement timing profiles."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from collections.abc import Mapping, Sequence


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
    power_sample_offsets_ms: tuple[int, ...] = (0,)

    @staticmethod
    def _normalize_power_sample_offsets(value) -> tuple[int, ...]:
        if isinstance(value, str):
            value = tuple(
                part.strip() for part in value.split(",") if part.strip()
            )
        elif value is None:
            value = (0,)
        elif not isinstance(value, Sequence):
            raise ValueError("Power sample offsets must be a sequence.")

        offsets = []
        for item in value:
            try:
                numeric = float(item)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "Power sample offsets must be whole milliseconds."
                ) from error
            if not math.isfinite(numeric) or int(numeric) != numeric:
                raise ValueError("Power sample offsets must be whole milliseconds.")
            offsets.append(int(numeric))
        offsets = tuple(offsets)
        if not 1 <= len(offsets) <= 3:
            raise ValueError("Power sample offsets must contain 1 to 3 values.")
        if any(offset < 0 or offset > MAX_TIMING_MS for offset in offsets):
            raise ValueError(
                "Power sample offsets must be between 0 and %d ms."
                % MAX_TIMING_MS
            )
        if tuple(sorted(offsets)) != offsets or len(set(offsets)) != len(offsets):
            raise ValueError("Power sample offsets must be strictly increasing.")
        return offsets

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

        power_sample_offsets_ms = self._normalize_power_sample_offsets(
            self.power_sample_offsets_ms
        )

        return MeasurementTimingProfile(
            profile_id=profile_id,
            name=name,
            revision=revision,
            wavelength_settling_ms=normalized[0],
            source_settling_ms=normalized[1],
            live_update_pause_ms=normalized[2],
            power_sample_offsets_ms=power_sample_offsets_ms,
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
            "power_sample_offsets_ms": list(profile.power_sample_offsets_ms),
        }

    @classmethod
    def from_dict(cls, values, *, fallback=None) -> "MeasurementTimingProfile":
        """Rebuild a profile snapshot while tolerating legacy fields."""
        if not isinstance(values, Mapping):
            if fallback is not None:
                return fallback.validate()
            raise ValueError("Timing profile snapshot must be an object.")
        fallback = fallback.validate() if fallback is not None else None
        profile = cls(
            profile_id=values.get(
                "profile_id", fallback.profile_id if fallback else "standard"
            ),
            name=values.get("profile_name", fallback.name if fallback else "Standard"),
            revision=values.get(
                "profile_revision", fallback.revision if fallback else 1
            ),
            wavelength_settling_ms=values.get(
                "opm_wavelength_settling_ms",
                fallback.wavelength_settling_ms if fallback else DEFAULT_WAVELENGTH_SETTLING_MS,
            ),
            source_settling_ms=values.get(
                "laser_source_settling_ms",
                fallback.source_settling_ms if fallback else DEFAULT_SOURCE_SETTLING_MS,
            ),
            live_update_pause_ms=values.get(
                "live_update_pause_ms",
                fallback.live_update_pause_ms if fallback else DEFAULT_LIVE_UPDATE_PAUSE_MS,
            ),
            power_sample_offsets_ms=values.get("power_sample_offsets_ms", (0,)),
        )
        return profile.validate()


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
