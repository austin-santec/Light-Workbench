"""Pure validation rules for unit-to-switch installation records."""

from __future__ import annotations

from typing import Mapping


class AssignmentConflictError(ValueError):
    """Raised when requested hardware conflicts with an active assignment."""


class AssignmentChangeRequiredError(AssignmentConflictError):
    """Raised when a unit's active switch must be explicitly replaced."""


class SwitchAlreadyAssignedError(AssignmentConflictError):
    """Raised when a switch is already active in another unit."""


class NewHardwarePairingConfirmationRequired(
    AssignmentChangeRequiredError, SwitchAlreadyAssignedError
):
    """Raised before a conflicting hardware pairing is changed."""

    def __init__(
        self,
        *,
        destination_main_board_serial: str,
        requested_switch_serial: str,
        source_main_board_serial: str | None = None,
        destination_switch_serial: str | None = None,
        source_assignment_id: int | None = None,
        destination_assignment_id: int | None = None,
    ) -> None:
        self.destination_main_board_serial = destination_main_board_serial
        self.requested_switch_serial = requested_switch_serial
        self.source_main_board_serial = source_main_board_serial
        self.destination_switch_serial = destination_switch_serial
        self.source_assignment_id = source_assignment_id
        self.destination_assignment_id = destination_assignment_id
        details = [
            "A new main-board/switch hardware pairing is required.",
            f"Main board: {destination_main_board_serial}.",
            f"Switch: {requested_switch_serial}.",
        ]
        if source_main_board_serial:
            details.append(
                f"The switch is currently assigned to main board {source_main_board_serial}."
            )
        if destination_switch_serial:
            details.append(
                f"The destination main board is currently paired with switch "
                f"{destination_switch_serial}; this unit has a different active "
                f"switch."
            )
        super().__init__(" ".join(details))

def validate_initial_channel_map(
    channel_map: Mapping[int, int],
    *,
    front_panel_channel_count: int | None,
    scpi_configured_channel_count: int,
) -> dict[int, int]:
    """Validate a baseline map inside the switch's reported SCPI range."""
    if front_panel_channel_count is None or int(front_panel_channel_count) <= 0:
        raise ValueError(
            "A front-panel channel count is required before assigning a switch."
        )
    configured_count = int(scpi_configured_channel_count)
    if configured_count <= 0:
        raise ValueError("The switch SCPI-configured channel count must be positive.")

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
    invalid_ports = sorted(port for port in ports if port > configured_count)
    if invalid_ports:
        raise ValueError(
            "Baseline channel-map ports exceed the switch SCPI-configured range: "
            + ", ".join(map(str, invalid_ports))
        )
    return normalized


__all__ = [
    "AssignmentChangeRequiredError",
    "AssignmentConflictError",
    "NewHardwarePairingConfirmationRequired",
    "SwitchAlreadyAssignedError",
    "validate_initial_channel_map",
]
