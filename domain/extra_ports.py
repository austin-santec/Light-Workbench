"""Domain values for optional direct physical-port testing."""

from dataclasses import dataclass
from enum import Enum


DEFAULT_MAXIMUM_PHYSICAL_PORT_PROBE = 64
MINIMUM_MAXIMUM_PHYSICAL_PORT_PROBE = 49
MAXIMUM_MAXIMUM_PHYSICAL_PORT_PROBE = 512


class PhysicalPortRouteStatus(str, Enum):
    """Confidence assigned to one engineering-interface route attempt."""

    VERIFIED = "verified"
    ACKNOWLEDGED = "acknowledged"
    UNVERIFIED = "unverified"
    FAILED = "failed"


@dataclass(frozen=True)
class PhysicalPortRouteResult:
    """Bounded result of routing one physical port through the CLI."""

    physical_port: int
    status: PhysicalPortRouteStatus
    response: str = ""
    detail: str = ""
    network_address: str = ""
    network_port: int = 2323
    readback_response: str = ""

    @property
    def permits_provisional_measurement(self) -> bool:
        return self.status in {
            PhysicalPortRouteStatus.VERIFIED,
            PhysicalPortRouteStatus.ACKNOWLEDGED,
        }


class ExtraPortPhaseStatus(str, Enum):
    """Lifecycle state for the optional post-front-panel phase."""

    NOT_OFFERED = "not_offered"
    OFFERED = "offered"
    DECLINED = "declined"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"
    END_OF_INSTALLED_PORTS_REPORTED = "end_of_installed_ports_reported"
    SAFETY_CEILING_REACHED = "safety_ceiling_reached"


@dataclass(frozen=True)
class ExtraPortSettings:
    """Administrator-controlled safety settings for sequential probing."""

    maximum_physical_port_probe: int = DEFAULT_MAXIMUM_PHYSICAL_PORT_PROBE

    def validate(self):
        value = int(self.maximum_physical_port_probe)
        if not (
            MINIMUM_MAXIMUM_PHYSICAL_PORT_PROBE
            <= value
            <= MAXIMUM_MAXIMUM_PHYSICAL_PORT_PROBE
        ):
            raise ValueError(
                "Maximum physical-port probe must be from %d through %d."
                % (
                    MINIMUM_MAXIMUM_PHYSICAL_PORT_PROBE,
                    MAXIMUM_MAXIMUM_PHYSICAL_PORT_PROBE,
                )
            )
        return ExtraPortSettings(value)


__all__ = [
    "DEFAULT_MAXIMUM_PHYSICAL_PORT_PROBE",
    "ExtraPortPhaseStatus",
    "ExtraPortSettings",
    "MAXIMUM_MAXIMUM_PHYSICAL_PORT_PROBE",
    "MINIMUM_MAXIMUM_PHYSICAL_PORT_PROBE",
    "PhysicalPortRouteResult",
    "PhysicalPortRouteStatus",
]
