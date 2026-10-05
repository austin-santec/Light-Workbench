"""Pure preparation helpers for starting a hardware measurement run."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from application.hardware_planning import HardwareRunPlan, build_hardware_run_plan
from application.run_controller import HardwareRunRequest
from application.timing import LIVE_WRITE_INTERVAL_SECONDS
from hardware.interfaces import OpticalSwitch, PowerMeter


@dataclass(frozen=True)
class HardwareRunPreparation:
    """Normalized run choices passed from the UI to the run controller."""

    channels: Sequence[int] | None
    plan: HardwareRunPlan | None
    full_pass: bool
    manual_channel_order: bool


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
    )


__all__ = [
    "HardwareRunPreparation",
    "build_hardware_run_request",
    "prepare_hardware_run",
]
