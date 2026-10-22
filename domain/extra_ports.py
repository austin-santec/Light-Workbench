"""Domain values for optional direct physical-port testing."""

from dataclasses import dataclass
from enum import Enum


# Emergency guard against an unbounded sequence of direct register writes.
# This is deliberately not operator- or administrator-configurable and is not
# interpreted as installed switch capacity.
EXTRA_PORT_HARD_SAFETY_LIMIT = 512


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


__all__ = [
    "EXTRA_PORT_HARD_SAFETY_LIMIT",
    "ExtraPortPhaseStatus",
    "PhysicalPortRouteResult",
    "PhysicalPortRouteStatus",
]
