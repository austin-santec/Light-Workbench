"""State for the operator-facing portion of a hardware run.

The worker/controller own the instrument lifecycle. This small session object
holds the UI workflow state that is produced by worker signals and consumed by
the read/write controls. Keeping it together prevents the main window from
accumulating unrelated booleans and partially populated pending-reading data.
"""

from dataclasses import dataclass

from application.hardware_planning import HardwareRunPlan
from domain.extra_ports import ExtraPortPhaseStatus


HardwareReading = tuple[int, int, float, float]


@dataclass
class HardwareRunSession:
    """Mutable UI state for one active or recently completed hardware run."""

    retest: bool = False
    manual_channel_order: bool = False
    full_pass: bool = False
    configured_channel_count: int | None = None
    pending_reading: HardwareReading | None = None
    pending_channel: int | None = None
    pending_physical_port: int | None = None
    extra_port_phase_status: str = ExtraPortPhaseStatus.NOT_OFFERED.value
    extra_port_candidate: int | None = None
    highest_confirmed_extra_port: int | None = None

    def begin(self, *, retest: bool, plan: HardwareRunPlan | None) -> None:
        """Start a fresh UI session from a normalized run plan."""
        self.retest = bool(retest)
        self.manual_channel_order = bool(plan and plan.manual_channel_order)
        self.full_pass = bool(plan and plan.full_pass)
        self.configured_channel_count = None
        self.extra_port_phase_status = ExtraPortPhaseStatus.NOT_OFFERED.value
        self.extra_port_candidate = None
        self.highest_confirmed_extra_port = None
        self.clear_pending()

    @property
    def extra_port_active(self) -> bool:
        return self.extra_port_phase_status == ExtraPortPhaseStatus.IN_PROGRESS.value

    def set_extra_port_phase(self, status, candidate=None, highest_confirmed=None):
        self.extra_port_phase_status = str(status)
        self.extra_port_candidate = int(candidate) if candidate is not None else None
        if highest_confirmed is not None:
            self.highest_confirmed_extra_port = int(highest_confirmed)

    def set_configured_channel_count(self, channel_count: int) -> None:
        """Record the switch capacity reported by the worker."""
        self.configured_channel_count = int(channel_count)

    def set_pending_channel(self, channel: int, physical_port: int) -> None:
        """Record the channel currently waiting for an operator reading."""
        self.pending_channel = int(channel)
        self.pending_physical_port = int(physical_port)
        self.pending_reading = None

    def set_pending_reading(
        self,
        channel: int,
        physical_port: int,
        loss_1310: float,
        loss_1550: float,
    ) -> None:
        """Record the latest reading without marking it as written."""
        self.pending_reading = (
            int(channel),
            int(physical_port),
            float(loss_1310),
            float(loss_1550),
        )

    def clear_pending(self) -> None:
        """Discard an unread or uncommitted reading and channel selection."""
        self.pending_reading = None
        self.pending_channel = None
        self.pending_physical_port = None

