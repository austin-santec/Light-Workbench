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
    NewHardwarePairingConfirmationRequired,
    SwitchAlreadyAssignedError,
    validate_initial_channel_map,
)


class AssignmentResolution(str, Enum):
    INSTALLED = "installed"
    REUSED = "reused"
    REPLACED = "replaced"
    FRESH_PAIRING = "fresh_pairing"


@dataclass(frozen=True)
class UnitSwitchAssignmentResult:
    unit: UnitRecord
    switch: SwitchRecord
    assignment: AssignmentRecord
    resolution: AssignmentResolution
    previous_assignment: AssignmentRecord | None = None
    previous_assignments: tuple[AssignmentRecord, ...] = ()
    stopped_run_ids: tuple[int, ...] = ()


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
        allow_new_pairing: bool = False,
    ) -> UnitSwitchAssignmentResult:
        """Reuse an active pair or install a validated fresh hardware pair."""
        self._validate_spec_map(unit_spec, switch_spec, initial_channel_map)
        conflict = self._new_pairing_conflict(unit_spec, switch_spec)
        if conflict is not None and not allow_new_pairing:
            raise conflict
        unit = self._units.get_or_create(unit_spec)
        switch = self._switches.get_or_create(switch_spec)
        active_for_unit = self._assignments.get_active(unit.unit_id)
        if active_for_unit is not None:
            if active_for_unit.switch_id == switch.switch_id:
                return UnitSwitchAssignmentResult(
                    unit, switch, active_for_unit, AssignmentResolution.REUSED
                )
            if not allow_new_pairing:
                raise AssignmentChangeRequiredError(
                    "This unit already has a different active switch."
                )
        if allow_new_pairing and conflict is not None:
            assignment, closed, stopped = self._assignments.install_fresh_pairing(
                self._assignment_spec(
                    unit,
                    switch,
                    installed_at_utc,
                    installed_by,
                    initial_channel_map,
                    notes,
                ),
                installed_at_utc,
                installed_by,
            )
            return UnitSwitchAssignmentResult(
                unit,
                switch,
                assignment,
                AssignmentResolution.FRESH_PAIRING,
                previous_assignment=closed[0] if closed else None,
                previous_assignments=closed,
                stopped_run_ids=stopped,
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

    def requires_new_pairing(
        self, unit_spec: UnitSpec, switch_spec: SwitchSpec
    ) -> NewHardwarePairingConfirmationRequired | None:
        """Preview whether this identity would replace active hardware."""
        return self._new_pairing_conflict(unit_spec, switch_spec)

    def build_assignment_spec(
        self,
        unit: UnitRecord,
        switch: SwitchRecord,
        *,
        installed_at_utc: datetime,
        installed_by: str,
        initial_channel_map: Mapping[int, int],
        notes: str | None = None,
    ) -> AssignmentSpec:
        """Build the validated baseline used by an atomic pairing operation."""
        return self._assignment_spec(
            unit,
            switch,
            installed_at_utc,
            installed_by,
            initial_channel_map,
            notes,
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
            scpi_configured_channel_count=(
                switch.last_reported_scpi_channel_count
            ),
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

    @staticmethod
    def _validate_spec_map(
        unit_spec: UnitSpec,
        switch_spec: SwitchSpec,
        initial_channel_map: Mapping[int, int],
    ) -> None:
        validate_initial_channel_map(
            initial_channel_map,
            front_panel_channel_count=unit_spec.front_panel_channel_count,
            scpi_configured_channel_count=(
                switch_spec.last_reported_scpi_channel_count
            ),
        )

    def _new_pairing_conflict(
        self, unit_spec: UnitSpec, switch_spec: SwitchSpec
    ) -> NewHardwarePairingConfirmationRequired | None:
        unit = self._units.get_by_main_board_serial(unit_spec.main_board_serial)
        switch = self._switches.get_by_serial(switch_spec.switch_serial)
        active_for_unit = (
            self._assignments.get_active(unit.unit_id) if unit is not None else None
        )
        active_for_switch = (
            self._assignments.get_active_for_switch(switch.switch_id)
            if switch is not None
            else None
        )
        if active_for_unit is not None and active_for_unit.switch_id == (
            switch.switch_id if switch is not None else -1
        ):
            return None
        if active_for_unit is None and active_for_switch is None:
            return None
        source_unit = (
            self._units.get_unit(active_for_switch.unit_id)
            if active_for_switch is not None
            else None
        )
        destination_switch = (
            self._switches.get_switch(active_for_unit.switch_id)
            if active_for_unit is not None
            else None
        )
        return NewHardwarePairingConfirmationRequired(
            destination_main_board_serial=unit_spec.main_board_serial,
            requested_switch_serial=switch_spec.switch_serial,
            source_main_board_serial=(
                source_unit.main_board_serial if source_unit is not None else None
            ),
            destination_switch_serial=(
                destination_switch.switch_serial
                if destination_switch is not None
                else None
            ),
            source_assignment_id=(
                active_for_switch.assignment_id
                if active_for_switch is not None
                else None
            ),
            destination_assignment_id=(
                active_for_unit.assignment_id
                if active_for_unit is not None
                else None
            ),
        )


__all__ = [
    "AssignmentResolution",
    "UnitSwitchAssignmentResult",
    "UnitSwitchAssignmentWorkflow",
]
