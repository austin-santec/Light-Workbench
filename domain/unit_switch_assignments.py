"""Pure validation rules for unit-to-switch installation records."""

from __future__ import annotations

from typing import Mapping


class AssignmentConflictError(ValueError):
    """Raised when requested hardware conflicts with an active assignment."""


class AssignmentChangeRequiredError(AssignmentConflictError):
    """Raised when a unit's active switch must be explicitly replaced."""


class SwitchAlreadyAssignedError(AssignmentConflictError):
    """Raised when a switch is already active in another unit."""


def validate_initial_channel_map(
    channel_map: Mapping[int, int],
    *,
    front_panel_channel_count: int | None,
    physical_channel_count: int,
) -> dict[int, int]:
    """Validate a complete, one-to-one baseline map for an installation."""
    if front_panel_channel_count is None or int(front_panel_channel_count) <= 0:
        raise ValueError(
            "A front-panel channel count is required before assigning a switch."
        )
    physical_count = int(physical_channel_count)
    if physical_count <= 0:
        raise ValueError("The switch physical-channel count must be positive.")

    normalized: dict[int, int] = {}
    for logical_channel, physical_port in dict(channel_map or {}).items():
        logical = int(logical_channel)
        physical = int(physical_port)
        if logical <= 0 or physical <= 0:
            raise ValueError("Channel-map entries must be positive integers.")
        normalized[logical] = physical

    expected = set(range(1, int(front_panel_channel_count) + 1))
    actual = set(normalized)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        details = []
        if missing:
            details.append("missing logical channels: " + ", ".join(map(str, missing)))
        if extra:
            details.append("unexpected logical channels: " + ", ".join(map(str, extra)))
        raise ValueError("The initial channel map is incomplete (" + "; ".join(details) + ").")

    ports = tuple(normalized.values())
    if len(set(ports)) != len(ports):
        raise ValueError("Each logical channel must map to a unique physical port.")
    invalid_ports = sorted(port for port in ports if port > physical_count)
    if invalid_ports:
        raise ValueError(
            "Channel-map physical ports exceed the switch capacity: "
            + ", ".join(map(str, invalid_ports))
        )
    return normalized


__all__ = [
    "AssignmentChangeRequiredError",
    "AssignmentConflictError",
    "SwitchAlreadyAssignedError",
    "validate_initial_channel_map",
]
