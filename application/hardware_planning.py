"""Pure planning helpers for choosing channels for a hardware run.

This module deliberately has no Qt or vendor-driver dependencies. The UI can
translate its widgets into a :class:`HardwareRunPlan`, while the controller
and worker receive the same normalized channel information regardless of how
the operator selected it.
"""

from dataclasses import dataclass
from typing import Union

from domain.models import ChannelMode


ChannelModeInput = Union[ChannelMode, str, int]


@dataclass(frozen=True)
class HardwareRunPlan:
    """Normalized channel-selection decisions for one hardware run."""

    mode: ChannelMode
    channels: tuple[int, ...] | None
    full_pass: bool
    manual_channel_order: bool = False

    def worker_channels(self) -> list[int] | None:
        """Return the mutable sequence shape expected by the legacy worker."""
        return None if self.channels is None else list(self.channels)


def parse_hardware_channels(value: str) -> list[int]:
    """Expand positive channel numbers and inclusive ranges in entered order."""
    if not value.strip():
        raise ValueError("Enter at least one channel or range.")

    channels = []
    seen = set()
    for entry in value.split(","):
        entry = entry.strip()
        if not entry:
            raise ValueError("Empty entries are not allowed between commas.")
        if "-" in entry:
            parts = entry.split("-")
            if len(parts) != 2:
                raise ValueError("Invalid range %r." % entry)
            try:
                first, last = (int(part.strip()) for part in parts)
            except ValueError:
                raise ValueError("Range ends must be numeric: %s" % entry)
            if first < 1 or first > last:
                raise ValueError("Invalid range %r." % entry)
            candidates = range(first, last + 1)
        else:
            try:
                candidates = (int(entry),)
            except ValueError:
                raise ValueError("Invalid channel %r." % entry)

        for channel in candidates:
            if channel < 1:
                raise ValueError("Channels must be 1 or greater.")
            if channel not in seen:
                channels.append(channel)
                seen.add(channel)
    return channels


def _normalise_mode(mode: ChannelModeInput) -> ChannelMode:
    """Accept domain values plus the legacy combo-box index/text shapes."""
    if isinstance(mode, ChannelMode):
        return mode
    if isinstance(mode, int):
        modes = tuple(ChannelMode)
        try:
            return modes[mode]
        except IndexError:
            raise ValueError("Unknown hardware channel mode index: %s" % mode)
    try:
        return ChannelMode(str(mode).strip())
    except ValueError:
        raise ValueError("Unknown hardware channel mode: %s" % mode)


def build_hardware_run_plan(
    mode: ChannelModeInput,
    *,
    single_channel: int = 1,
    channel_ranges: str = "",
    manual_channel_order: bool = False,
) -> HardwareRunPlan:
    """Normalize UI channel choices into a worker-independent run plan.

    Full configured passes intentionally use ``channels=None`` so the worker
    can discover the switch's configured channel count. Manual ordering is a
    full-pass option only; it is ignored for the single/specific-channel modes
    because those modes already explicitly choose the next channel.
    """
    normalized_mode = _normalise_mode(mode)
    if normalized_mode is ChannelMode.FULL_CONFIGURED_PASS:
        return HardwareRunPlan(
            mode=normalized_mode,
            channels=None,
            full_pass=True,
            manual_channel_order=bool(manual_channel_order),
        )

    if normalized_mode is ChannelMode.SINGLE_CHANNEL:
        try:
            channel = int(single_channel)
        except (TypeError, ValueError):
            raise ValueError("Single channel must be numeric.")
        if channel < 1:
            raise ValueError("Channels must be 1 or greater.")
        return HardwareRunPlan(
            mode=normalized_mode,
            channels=(channel,),
            full_pass=False,
        )

    return HardwareRunPlan(
        mode=normalized_mode,
        channels=tuple(parse_hardware_channels(channel_ranges)),
        full_pass=False,
    )
