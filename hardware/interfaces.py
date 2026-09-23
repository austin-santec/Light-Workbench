"""Application-facing contracts for optical test hardware.

These protocols intentionally describe capabilities rather than vendors.  An
integrated ILM can implement ``PowerMeter`` while a future OPM plus separate
laser can implement ``PowerMeter`` and ``LaserSource`` independently.  The
application workflow should depend on these contracts, not on ctypes, VISA,
or a particular instrument model.
"""

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable


WAVELENGTHS_NM: tuple[int, ...] = (1310, 1550)


@runtime_checkable
class PowerMeter(Protocol):
    """Capability for measuring optical power at configured wavelengths."""

    description: str | None
    usb_serial: str | None

    def connect(self) -> None:
        """Connect to the meter and prepare it for measurements."""

    def measure_both_wavelengths(self) -> Mapping[int, float]:
        """Return absolute dBm readings keyed by wavelength in nanometers."""

    def measure_reference_wavelengths(self) -> Mapping[int, float]:
        """Return stabilized readings suitable for reference calculation."""

    def close(self) -> None:
        """Stop measurement activity and release the meter."""


@runtime_checkable
class LaserSource(Protocol):
    """Capability for a laser used separately from an optical power meter."""

    description: str | None
    serial_number: str | None

    def connect(self) -> None:
        """Connect to the laser source."""

    def set_wavelength(self, wavelength_nm: int) -> None:
        """Set the output wavelength in nanometers."""

    def set_output(self, enabled: bool) -> None:
        """Enable or disable the optical output."""

    def close(self) -> None:
        """Disable output and release the laser."""


@runtime_checkable
class OpticalSwitch(Protocol):
    """Capability for routing an optical channel to the measurement path."""

    def connect(self) -> None:
        """Connect to the switch."""

    def configured_channel_count(self) -> int:
        """Return the number of logical channels configured for the test."""

    def set_channel(self, channel: int) -> int:
        """Select a logical channel and return its physical port."""

    def close(self) -> None:
        """Release the switch connection."""


class ChannelRouter(OpticalSwitch, Protocol):
    """Alias for code that wants to emphasize routing rather than switching."""

    pass


def validate_wavelength_readings(
    readings: Mapping[int, float],
    wavelengths: Sequence[int] = WAVELENGTHS_NM,
) -> None:
    """Validate the minimum reading contract shared by meter adapters.

    Vendor adapters may expose additional wavelengths, but the current IL
    workflow requires both 1310 nm and 1550 nm.  Keeping this check in one
    place prevents each future adapter from implementing subtly different
    validation rules.
    """

    missing = set(wavelengths) - set(readings)
    if missing:
        formatted = ", ".join(str(wavelength) for wavelength in sorted(missing))
        raise ValueError("Reading is missing wavelength(s): %s" % formatted)
