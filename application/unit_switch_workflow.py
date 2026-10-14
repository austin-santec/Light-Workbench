"""Application workflow for resolving unit/switch installation identity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Mapping

from domain.database_records import (
    AssignmentRecord,
    AssignmentSpec,
    SwitchRecord,
    SwitchSpec,
    UnitRecord,
    UnitSpec,
    require_text,
    require_utc,
)
from domain.unit_switch_assignments import (
    AssignmentChangeRequiredError,
    SwitchAlreadyAssignedError,
    validate_initial_channel_map,
)


class AssignmentResolution(str, Enum):
    INSTALLED = "installed"
    REUSED = "reused"
    REPLACED = "replaced"


@dataclass(frozen=True)
class UnitSwitchAssignmentResult:
    unit: UnitRecord
    switch: SwitchRecord
    assignment: AssignmentRecord
    resolution: AssignmentResolution
    previous_assignment: AssignmentRecord | None = None


class UnitSwitchAssignmentWorkflow:
    """Resolve hardware identity without exposing SQL to callers."""

    def __init__(
        self,
        unit_repository,
        switch_repository,
        assignment_repository,
    ) -> None:
        self._units = unit_repository
        self._switches = switch_repository
        self._assignments = assignment_repository

    def resolve(
        self,
        unit_spec: UnitSpec,
        switch_spec: SwitchSpec,
        *,
        installed_at_utc: datetime,
        installed_by: str,
        initial_channel_map: Mapping[int, int],
        notes: str | None = None,
    ) -> UnitSwitchAssignmentResult:
        """Reuse the matching active assignment or install a new one."""
        unit = self._units.get_or_create(unit_spec)
        switch = self._switches.get_or_create(switch_spec)
        active_for_unit = self._assignments.get_active(unit.unit_id)
        if active_for_unit is not None:
            if active_for_unit.switch_id == switch.switch_id:
                return UnitSwitchAssignmentResult(
                    unit, switch, active_for_unit, AssignmentResolution.REUSED
                )
            raise AssignmentChangeRequiredError(
                "This unit already has a different active switch. Record an explicit "
                "switch replacement before starting a run."
            )
        self._reject_switch_owned_by_another_unit(switch.switch_id, unit.unit_id)
        assignment = self._assignments.install(
            self._assignment_spec(
                unit,
                switch,
                installed_at_utc,
                installed_by,
                initial_channel_map,
                notes,
            )
        )
        return UnitSwitchAssignmentResult(
            unit, switch, assignment, AssignmentResolution.INSTALLED
        )

    def replace_switch(
        self,
        unit_spec: UnitSpec,
        switch_spec: SwitchSpec,
        *,
        changed_at_utc: datetime,
        changed_by: str,
        removal_reason: str,
        initial_channel_map: Mapping[int, int],
        notes: str | None = None,
    ) -> UnitSwitchAssignmentResult:
        """Atomically close a unit's old assignment and install a new switch."""
        changed_at = require_utc(changed_at_utc, "Switch-change time")
        operator = require_text(changed_by, "Switch-change operator")
        reason = require_text(removal_reason, "Switch removal reason")
        unit = self._units.get_or_create(unit_spec)
        switch = self._switches.get_or_create(switch_spec)
        previous = self._assignments.get_active(unit.unit_id)
        if previous is None:
            raise AssignmentChangeRequiredError(
                "This unit has no active switch assignment to replace."
            )
        if previous.switch_id == switch.switch_id:
            return UnitSwitchAssignmentResult(
                unit, switch, previous, AssignmentResolution.REUSED
            )
        self._reject_switch_owned_by_another_unit(switch.switch_id, unit.unit_id)
        assignment = self._assignments.replace_active(
            previous.assignment_id,
            self._assignment_spec(
                unit,
                switch,
                changed_at,
                operator,
                initial_channel_map,
                notes,
            ),
            changed_at,
            operator,
            reason,
        )
        return UnitSwitchAssignmentResult(
            unit,
            switch,
            assignment,
            AssignmentResolution.REPLACED,
            previous_assignment=previous,
        )

    def _assignment_spec(
        self,
        unit: UnitRecord,
        switch: SwitchRecord,
        installed_at_utc: datetime,
        installed_by: str,
        initial_channel_map: Mapping[int, int],
        notes: str | None,
    ) -> AssignmentSpec:
        channel_map = validate_initial_channel_map(
            initial_channel_map,
            front_panel_channel_count=unit.front_panel_channel_count,
            physical_channel_count=switch.physical_channel_count,
        )
        return AssignmentSpec(
            unit.unit_id,
            switch.switch_id,
            installed_at_utc,
            installed_by,
            channel_map,
            notes,
        )

    def _reject_switch_owned_by_another_unit(
        self, switch_id: int, requested_unit_id: int
    ) -> None:
        active = self._assignments.get_active_for_switch(switch_id)
        if active is not None and active.unit_id != requested_unit_id:
            raise SwitchAlreadyAssignedError(
                "This switch is already assigned to another active unit."
            )


__all__ = [
    "AssignmentResolution",
    "UnitSwitchAssignmentResult",
    "UnitSwitchAssignmentWorkflow",
]
