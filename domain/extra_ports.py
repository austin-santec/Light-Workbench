"""Domain values for optional direct physical-port testing."""

from dataclasses import dataclass
from enum import Enum


# Emergency guard against an unbounded sequence of direct register writes.
# This is deliberately not operator- or administrator-configurable and is not
# interpreted as installed switch capacity.
EXTRA_PORT_HARD_SAFETY_LIMIT = 512


class ExtraChannelRoutingMethod(str, Enum):
    """Supported ways to route channels beyond the front-panel count."""

    SCPI_MAPPED = "scpi_mapped"
    CLI_DIRECT = "cli_direct"

    @classmethod
    def parse(cls, value) -> "ExtraChannelRoutingMethod":
        """Normalize persisted/UI values and reject unknown routing methods."""
        if isinstance(value, cls):
            return value
        normalized = str(value or cls.SCPI_MAPPED.value).strip().lower()
        try:
            return cls(normalized)
        except ValueError as error:
            raise ValueError(
                "Extra-channel routing must be 'scpi_mapped' or 'cli_direct'."
            ) from error

    @property
    def label(self) -> str:
        if self is self.CLI_DIRECT:
            return "CLI direct physical ports (Experimental)"
        return "SCPI mapped channels"


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
    "ExtraChannelRoutingMethod",
    "ExtraPortPhaseStatus",
    "PhysicalPortRouteResult",
    "PhysicalPortRouteStatus",
]
