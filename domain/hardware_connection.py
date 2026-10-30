"""Vendor-neutral hardware connection and readiness concepts."""

from dataclasses import dataclass
from enum import Enum

from domain.models import ConnectionState, DeviceCategory, DeviceInfo


class RemoteControlState(str, Enum):
    """Transient remote/local control state for a connected instrument."""

    REMOTE = "remote"
    LOCAL = "local"
    CHANGING = "changing"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RemoteModeTransitionResult:
    """Result of one requested remote/local transition."""

    requested_remote: bool
    state: RemoteControlState
    error: str = ""


class HardwareCapability(str, Enum):
    """Independently connectable capabilities used by application workflows."""

    MEASUREMENT = "measurement"
    LASER_SOURCE = "laser_source"
    OPTICAL_SWITCH = "optical_switch"


class HardwareConnectionError(RuntimeError):
    """Base error for managed connection and ownership failures."""


class HardwareNotReadyError(HardwareConnectionError):
    """Raised when a workflow requires hardware that is not connected."""


class HardwareBusyError(HardwareConnectionError):
    """Raised when another workflow owns the requested hardware."""


@dataclass(frozen=True)
class HardwareConnectionSnapshot:
    """Immutable application view of one managed hardware capability."""

    capability: HardwareCapability
    device_info: DeviceInfo
    owner: str = ""
    remote_control_state: RemoteControlState | None = None

    @property
    def connected(self) -> bool:
        return self.device_info.state in {
            ConnectionState.CONNECTED,
            ConnectionState.IN_USE,
        }

    @property
    def available(self) -> bool:
        return self.device_info.state == ConnectionState.CONNECTED and not self.owner

    @property
    def remote_control_supported(self) -> bool:
        """Return whether this capability exposes remote/local control."""
        return self.remote_control_state is not None

    @property
    def remote_ready(self) -> bool:
        """Return whether remote-controlled operations may be issued."""
        return (
            not self.remote_control_supported
            or self.remote_control_state == RemoteControlState.REMOTE
        )


def disconnected_device_info(capability: HardwareCapability) -> DeviceInfo:
    """Create the neutral initial status for one capability."""
    category = {
        HardwareCapability.MEASUREMENT: DeviceCategory.POWER_METER,
        HardwareCapability.LASER_SOURCE: DeviceCategory.LASER_SOURCE,
        HardwareCapability.OPTICAL_SWITCH: DeviceCategory.OPTICAL_SWITCH,
    }[capability]
    return DeviceInfo(category=category, state=ConnectionState.DISCONNECTED)


__all__ = [
    "HardwareBusyError",
    "HardwareCapability",
    "HardwareConnectionError",
    "HardwareConnectionSnapshot",
    "HardwareNotReadyError",
    "RemoteControlState",
    "RemoteModeTransitionResult",
    "disconnected_device_info",
]
