"""Application-facing contracts for optical test hardware.

These protocols intentionally describe capabilities rather than vendors.  An
integrated ILM can implement ``PowerMeter`` while a future OPM plus separate
laser can implement ``PowerMeter`` and ``LaserSource`` independently.  The
application workflow should depend on these contracts, not on ctypes, VISA,
or a particular instrument model.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from domain.hardware_connection import RemoteControlState
from domain.models import ConnectionState, DeviceInfo


WAVELENGTHS_NM: tuple[int, ...] = (1310, 1550)


@dataclass(frozen=True)
class LogicalChannelRouteResult:
    """Confirmation that a requested SCPI logical channel became active.

    ``CLOSe?`` is a logical-channel query on approved firmware.  This result
    deliberately contains no physical-port field so callers cannot mistake a
    route acknowledgement for evidence of the switch's internal mapping.
    """

    requested_logical_channel: int
    reported_logical_channel: int

    def __post_init__(self) -> None:
        requested = int(self.requested_logical_channel)
        reported = int(self.reported_logical_channel)
        if requested < 1 or reported < 1:
            raise ValueError("Logical channel values must be positive")
        object.__setattr__(self, "requested_logical_channel", requested)
        object.__setattr__(self, "reported_logical_channel", reported)

    @property
    def confirmed(self) -> bool:
        return self.requested_logical_channel == self.reported_logical_channel


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
class RemoteControllable(Protocol):
    """Optional capability for meters that support local/remote control."""

    remote_control_state: RemoteControlState

    def set_remote_control(self, enabled: bool) -> RemoteControlState:
        """Select local or remote control without closing the session."""


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

    def current_logical_channel(self) -> int:
        """Return the logical channel reported by the switch."""

    def set_channel(self, channel: int) -> LogicalChannelRouteResult:
        """Select and confirm a logical channel without inferring its mapping."""

    def close(self) -> None:
        """Release the switch connection."""


@runtime_checkable
class DeviceIdentifiable(Protocol):
    """Optional identity capability shared by hardware adapters."""

    def get_device_info(
        self,
        state: ConnectionState = ConnectionState.DISCONNECTED,
        error: str = "",
    ) -> DeviceInfo:
        """Return transient identity and connection state."""


class ChannelRouter(OpticalSwitch, Protocol):
    """Alias for code that wants to emphasize routing rather than switching."""

    pass


@runtime_checkable
class OpticalSwitchNetworkInfo(Protocol):
    """Optional capability for switches that expose a LAN address query."""

    def get_ip_address(self) -> str:
        """Return the configured network address without changing routing."""


@runtime_checkable
class DirectPhysicalPortRouter(Protocol):
    """Optional engineering capability for routing an unconfigured port."""

    def set_physical_port(self, physical_port: int):
        """Route a physical port and return a structured route result."""


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
