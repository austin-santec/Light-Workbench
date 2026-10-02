"""Vendor-neutral hardware connection and readiness concepts."""

from dataclasses import dataclass
from enum import Enum

from domain.models import ConnectionState, DeviceCategory, DeviceInfo


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

    @property
    def connected(self) -> bool:
        return self.device_info.state in {
            ConnectionState.CONNECTED,
            ConnectionState.IN_USE,
        }

    @property
    def available(self) -> bool:
        return self.device_info.state == ConnectionState.CONNECTED and not self.owner


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
    "disconnected_device_info",
]
