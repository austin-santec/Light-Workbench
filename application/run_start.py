"""Pure preparation helpers for starting a hardware measurement run."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from application.hardware_planning import HardwareRunPlan, build_hardware_run_plan
from application.run_controller import HardwareRunRequest
from application.timing import LIVE_WRITE_INTERVAL_SECONDS
from domain.extra_ports import ExtraChannelRoutingMethod
from domain.models import ChannelMode
from hardware.interfaces import OpticalSwitch, PowerMeter
from domain.wavelengths import MeasurementConfiguration


@dataclass(frozen=True)
class HardwareRunPreparation:
    """Normalized run choices passed from the UI to the run controller."""

    channels: Sequence[int] | None
    plan: HardwareRunPlan | None
    full_pass: bool
    manual_channel_order: bool

    @property
    def extra_only(self) -> bool:
        return bool(
            self.plan is not None
            and self.plan.mode is ChannelMode.EXTRA_CHANNELS_ONLY
        )


@dataclass(frozen=True)
class ExtraPortOfferEligibility:
    """Policy decision for enabling the optional extra-port phase."""

    eligible: bool
    reason: str


def evaluate_extra_port_offer_eligibility(
    *,
    full_pass: bool,
    manual_channel_order: bool = False,
    extra_only: bool = False,
    retest: bool,
    run_mode: str,
    has_part_number: bool,
    supports_extra_channels: bool = True,
) -> ExtraPortOfferEligibility:
    """Evaluate run-level conditions for offering extra physical ports.

    Front-panel coverage is verified by the worker after the pass completes;
    this decision covers the run configuration and required metadata.
    """

    if not full_pass and not extra_only:
        return ExtraPortOfferEligibility(False, "not_a_full_pass")
    if manual_channel_order and not extra_only:
        return ExtraPortOfferEligibility(False, "manual_channel_order")
    if retest:
        return ExtraPortOfferEligibility(False, "selected_retest")
    if run_mode not in {"new", "continue"}:
        return ExtraPortOfferEligibility(False, "unsupported_run_mode")
    if not has_part_number:
        return ExtraPortOfferEligibility(False, "missing_part_number")
    if not supports_extra_channels:
        return ExtraPortOfferEligibility(False, "switch_model_has_no_spares")
    return ExtraPortOfferEligibility(True, "eligible")


def prepare_hardware_run(
    *,
    retest: bool,
    requested_channels: Sequence[int] | None,
    channel_mode,
    single_channel: int = 1,
    channel_ranges: str = "",
    manual_channel_order: bool = False,
) -> HardwareRunPreparation:
    """Normalize UI selections without connecting to hardware.

    Retests reuse their selected table channels. Normal runs use the shared
    channel planner, which keeps full-pass discovery separate from explicit
    single/specific-channel selections.
    """
    if retest:
        return HardwareRunPreparation(
            channels=requested_channels,
            plan=None,
            full_pass=False,
            manual_channel_order=False,
        )

    plan = build_hardware_run_plan(
        channel_mode,
        single_channel=single_channel,
        channel_ranges=channel_ranges,
        manual_channel_order=manual_channel_order,
    )
    return HardwareRunPreparation(
        channels=plan.worker_channels(),
        plan=plan,
        full_pass=plan.full_pass,
        manual_channel_order=plan.manual_channel_order,
    )


def build_hardware_run_request(
    preparation: HardwareRunPreparation,
    *,
    meter: PowerMeter,
    switch: OpticalSwitch,
    reference_powers: Mapping[int, float],
    existing_channels: Sequence[int] | None,
    resume_existing: bool,
    live_write_mode: bool,
    live_write_interval: float = LIVE_WRITE_INTERVAL_SECONDS,
    support_logger=None,
    workflow_id: str = "",
    reference_snapshot: Mapping[str, object] | None = None,
    measurement_configuration: MeasurementConfiguration | None = None,
    front_panel_channel_count: int | None = None,
    offer_extra_ports: bool = False,
    run_mode: str = "new",
    retest: bool = False,
    existing_extra_physical_ports: Sequence[int] | None = None,
    existing_extra_logical_channels: Sequence[int] | None = None,
    extra_channel_routing_method: ExtraChannelRoutingMethod | str = (
        ExtraChannelRoutingMethod.SCPI_MAPPED
    ),
    persistence_run_id: int | None = None,
) -> HardwareRunRequest:
    """Create a controller request for already-created hardware adapters."""
    return HardwareRunRequest(
        # The controller owns these adapters for the duration of the run.
        power_meter_factory=lambda meter=meter: meter,
        switch_factory=lambda switch=switch: switch,
        channels=preparation.channels,
        reference_powers=dict(reference_powers),
        manual_channel_order=preparation.manual_channel_order,
        existing_channels=existing_channels,
        resume_existing=resume_existing,
        resume_full_pass=resume_existing
        and preparation.full_pass
        and not preparation.manual_channel_order,
        live_write_mode=live_write_mode,
        live_write_interval=live_write_interval,
        support_logger=support_logger,
        workflow_id=workflow_id,
        reference_snapshot=dict(reference_snapshot) if reference_snapshot else None,
        measurement_configuration=measurement_configuration,
        front_panel_channel_count=front_panel_channel_count,
        offer_extra_ports=offer_extra_ports,
        extra_only=preparation.extra_only,
        run_mode=run_mode,
        retest=retest,
        existing_extra_physical_ports=existing_extra_physical_ports,
        existing_extra_logical_channels=existing_extra_logical_channels,
        extra_channel_routing_method=ExtraChannelRoutingMethod.parse(
            extra_channel_routing_method
        ),
        persistence_run_id=persistence_run_id,
    )


__all__ = [
    "HardwareRunPreparation",
    "ExtraPortOfferEligibility",
    "build_hardware_run_request",
    "evaluate_extra_port_offer_eligibility",
    "prepare_hardware_run",
]
