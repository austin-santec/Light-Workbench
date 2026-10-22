"""Repository contracts for database-backed Light Workbench workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from domain.database_records import (
    AssignmentRecord,
    AssignmentSpec,
    ChannelMapRecord,
    MeasurementRecord,
    MeasurementSpec,
    MeasurementWriteSpec,
    ReplacementRecord,
    ReplacementSpec,
    RunRecord,
    RunStartSpec,
    RunSpec,
    SpareEventRecord,
    SpareEventSpec,
    SwitchRecord,
    SwitchSpec,
    UnitRecord,
    UnitSpec,
)


class UnitRepository(Protocol):
    def get_or_create(self, spec: UnitSpec) -> UnitRecord: ...

    def get_unit(self, unit_id: int) -> UnitRecord | None: ...

    def get_by_main_board_serial(self, main_board_serial: str) -> UnitRecord | None: ...


class SwitchRepository(Protocol):
    def get_or_create(self, spec: SwitchSpec) -> SwitchRecord: ...

    def get_switch(self, switch_id: int) -> SwitchRecord | None: ...

    def get_by_serial(self, switch_serial: str) -> SwitchRecord | None: ...


class AssignmentRepository(Protocol):
    def get_assignment(self, assignment_id: int) -> AssignmentRecord | None: ...

    def get_active(self, unit_id: int) -> AssignmentRecord | None: ...

    def get_active_for_switch(self, switch_id: int) -> AssignmentRecord | None: ...

    def history_for_unit(self, unit_id: int) -> tuple[AssignmentRecord, ...]: ...

    def install(self, spec: AssignmentSpec) -> AssignmentRecord: ...

    def remove(
        self,
        assignment_id: int,
        removed_at_utc: datetime,
        removed_by: str,
        removal_reason: str,
    ) -> AssignmentRecord: ...

    def replace_active(
        self,
        assignment_id: int,
        replacement: AssignmentSpec,
        removed_at_utc: datetime,
        removed_by: str,
        removal_reason: str,
    ) -> AssignmentRecord: ...


class RunRepository(Protocol):
    def create(self, spec: RunSpec) -> RunRecord: ...

    def create_next(self, spec: RunStartSpec) -> RunRecord: ...

    def get(self, run_id: int) -> RunRecord | None: ...

    def finish(
        self,
        run_id: int,
        completion_status: str,
        run_ended_at_utc: datetime,
        *,
        analysis_status: str | None = None,
        analysis_exclusion_reason: str | None = None,
    ) -> RunRecord: ...

    def resume(self, run_id: int) -> RunRecord: ...

    def find_stale_in_progress(self, before_utc: datetime) -> tuple[RunRecord, ...]: ...

    def get_by_uuid(self, client_run_uuid: UUID) -> RunRecord | None: ...

    def list_for_assignment(self, assignment_id: int) -> tuple[RunRecord, ...]: ...

    def list_for_unit(self, unit_id: int) -> tuple[RunRecord, ...]: ...

    def get_for_unit_run_number(
        self, unit_id: int, run_number: int
    ) -> RunRecord | None: ...

    def set_analysis_status(
        self,
        run_id: int,
        analysis_status: str,
        exclusion_reason: str | None = None,
        superseded_by_run_id: int | None = None,
    ) -> RunRecord: ...


class MeasurementRepository(Protocol):
    def append_attempt(self, spec: MeasurementSpec) -> MeasurementRecord: ...

    def append_next(self, spec: MeasurementWriteSpec) -> MeasurementRecord: ...

    def get_measurement_by_uuid(
        self, measurement_uuid: UUID
    ) -> MeasurementRecord | None: ...

    def current_for_run(self, run_id: int) -> tuple[MeasurementRecord, ...]: ...

    def history_for_run(self, run_id: int) -> tuple[MeasurementRecord, ...]: ...

    def snapshot_for_run(
        self, run_id: int
    ) -> tuple[tuple[MeasurementRecord, ...], tuple[MeasurementRecord, ...]]: ...


class ReplacementRepository(Protocol):
    def append(self, spec: ReplacementSpec) -> ReplacementRecord: ...

    def replacement_history_for_assignment(
        self, assignment_id: int
    ) -> tuple[ReplacementRecord, ...]: ...

    def current_channel_map(
        self, assignment_id: int
    ) -> tuple[ChannelMapRecord, ...]: ...


class SpareRepository(Protocol):
    def append_event(self, spec: SpareEventSpec) -> SpareEventRecord: ...

    def spare_history_for_assignment(
        self, assignment_id: int
    ) -> tuple[SpareEventRecord, ...]: ...

    def active_spares_for_assignment(self, assignment_id: int) -> tuple[int, ...]: ...


class RoutingRepository(ReplacementRepository, SpareRepository, Protocol):
    def apply_routing_changes(
        self,
        replacement_specs: tuple[ReplacementSpec, ...],
        spare_event_specs: tuple[SpareEventSpec, ...],
    ) -> tuple[
        tuple[ChannelMapRecord, ...],
        tuple[ReplacementRecord, ...],
        tuple[SpareEventRecord, ...],
        tuple[int, ...],
    ]: ...

    def routing_snapshot_for_assignment(
        self, assignment_id: int
    ) -> tuple[
        tuple[ChannelMapRecord, ...],
        tuple[ReplacementRecord, ...],
        tuple[SpareEventRecord, ...],
        tuple[int, ...],
    ]: ...


class ReportingRepository(Protocol):
    """Read-only enumeration used by reporting; no report method may mutate."""

    def list_report_runs(self) -> tuple[RunRecord, ...]: ...

    def list_report_assignments(self) -> tuple[AssignmentRecord, ...]: ...

    def list_report_units(self) -> tuple[UnitRecord, ...]: ...

    def list_report_switches(self) -> tuple[SwitchRecord, ...]: ...

    def report_measurements_for_runs(
        self, run_ids: tuple[int, ...]
    ) -> tuple[MeasurementRecord, ...]: ...

    def report_replacements_for_assignments(
        self, assignment_ids: tuple[int, ...]
    ) -> tuple[ReplacementRecord, ...]: ...


__all__ = [name for name in globals() if name.endswith("Repository")]
