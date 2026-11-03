"""In-memory implementations of database repository contracts for tests."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from threading import RLock
from uuid import UUID

from domain.database_records import (
    AssignmentRecord,
    AssignmentSpec,
    ChannelMapRecord,
    ConfirmedExtraPortRecord,
    MeasurementRecord,
    MeasurementSpec,
    MeasurementWriteSpec,
    MEASUREMENT_ROLE_EXTRA_CANDIDATE,
    MEASUREMENT_ROLE_LOGICAL_CHANNEL,
    PendingRunStartSpec,
    ReplacementAnalysisRecommendationRecord,
    ReplacementAnalysisRecommendationSpec,
    ReplacementAnalysisRecord,
    ReplacementAnalysisSpec,
    ReplacementRecord,
    ReplacementSpec,
    RunRecord,
    RunStartSpec,
    RunSpec,
    RunVoidInfo,
    SpareEventRecord,
    SpareEventSpec,
    SwitchRecord,
    SwitchSpec,
    UnitRecord,
    UnitSpec,
    require_positive,
    require_text,
    require_utc,
)
from domain.run_purpose import VALID_RUN_PURPOSES


class InMemoryRepositories:
    """One shared in-memory store satisfying every repository protocol."""

    def __init__(self) -> None:
        self.units: dict[int, UnitRecord] = {}
        self.switches: dict[int, SwitchRecord] = {}
        self.assignments: dict[int, AssignmentRecord] = {}
        self.runs: dict[int, RunRecord] = {}
        self.measurements: dict[int, MeasurementRecord] = {}
        self.replacements: dict[int, ReplacementRecord] = {}
        self.spare_events: dict[int, SpareEventRecord] = {}
        self.replacement_analyses: dict[int, ReplacementAnalysisRecord] = {}
        self.replacement_analysis_recommendations: dict[
            int, ReplacementAnalysisRecommendationRecord
        ] = {}
        self._next_ids: dict[str, int] = {}
        self._lock = RLock()

    @contextmanager
    def read_session(self):
        """Match the SQL load-session contract without adding persistence."""
        yield self

    def _next(self, name: str) -> int:
        value = self._next_ids.get(name, 0) + 1
        self._next_ids[name] = value
        return value

    def get_or_create(self, spec):
        if isinstance(spec, UnitSpec):
            return self._get_or_create_unit(spec)
        if isinstance(spec, SwitchSpec):
            return self._get_or_create_switch(spec)
        raise TypeError("get_or_create requires UnitSpec or SwitchSpec")

    def _get_or_create_unit(self, spec: UnitSpec) -> UnitRecord:
        serial = require_text(spec.main_board_serial, "Main-board serial")
        count = spec.front_panel_channel_count
        if count is not None:
            count = require_positive(count, "Front-panel channel count")
        existing = next(
            (item for item in self.units.values() if item.main_board_serial == serial),
            None,
        )
        if existing is not None:
            updated = replace(
                existing,
                part_number=spec.part_number,
                front_panel_channel_count=count,
                unit_model=spec.unit_model,
                notes=spec.notes,
            )
            self.units[existing.unit_id] = updated
            return updated
        record = UnitRecord(
            self._next("unit"),
            serial,
            spec.part_number,
            count,
            spec.unit_model,
            spec.notes,
        )
        self.units[record.unit_id] = record
        return record

    def get_by_main_board_serial(self, main_board_serial: str) -> UnitRecord | None:
        serial = str(main_board_serial or "").strip()
        return next(
            (item for item in self.units.values() if item.main_board_serial == serial),
            None,
        )

    def get_by_serial(self, switch_serial: str) -> SwitchRecord | None:
        serial = str(switch_serial or "").strip()
        return next(
            (item for item in self.switches.values() if item.switch_serial == serial),
            None,
        )

    def get_unit(self, unit_id: int) -> UnitRecord | None:
        return self.units.get(int(unit_id))

    def get_switch(self, switch_id: int) -> SwitchRecord | None:
        return self.switches.get(int(switch_id))

    def get_assignment(self, assignment_id: int) -> AssignmentRecord | None:
        return self.assignments.get(int(assignment_id))

    def _get_or_create_switch(self, spec: SwitchSpec) -> SwitchRecord:
        serial = require_text(spec.switch_serial, "Switch serial")
        model = require_text(spec.switch_model, "Switch model")
        count = require_positive(
            spec.last_reported_scpi_channel_count,
            "Last reported SCPI channel count",
        )
        existing = next(
            (item for item in self.switches.values() if item.switch_serial == serial),
            None,
        )
        if existing is not None:
            updated = replace(
                existing,
                switch_model=model,
                last_reported_scpi_channel_count=count,
                firmware_version=spec.firmware_version,
                notes=spec.notes,
            )
            self.switches[existing.switch_id] = updated
            return updated
        record = SwitchRecord(
            self._next("switch"),
            serial,
            model,
            count,
            spec.firmware_version,
            spec.notes,
        )
        self.switches[record.switch_id] = record
        return record

    def get_active(self, unit_id: int) -> AssignmentRecord | None:
        return next(
            (
                item
                for item in self.assignments.values()
                if item.unit_id == int(unit_id) and item.removed_at_utc is None
            ),
            None,
        )

    def get_active_for_switch(self, switch_id: int) -> AssignmentRecord | None:
        return next(
            (
                item
                for item in self.assignments.values()
                if item.switch_id == int(switch_id) and item.removed_at_utc is None
            ),
            None,
        )

    def history_for_unit(self, unit_id: int) -> tuple[AssignmentRecord, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self.assignments.values()
                    if item.unit_id == int(unit_id)
                ),
                key=lambda item: (item.installed_at_utc, item.assignment_id),
            )
        )

    def install(self, spec: AssignmentSpec) -> AssignmentRecord:
        if spec.unit_id not in self.units or spec.switch_id not in self.switches:
            raise ValueError("Assignment unit and switch must already exist")
        if self.get_active(spec.unit_id) is not None:
            raise ValueError("The unit already has an active switch assignment")
        if any(
            item.switch_id == spec.switch_id and item.removed_at_utc is None
            for item in self.assignments.values()
        ):
            raise ValueError("The switch already has an active unit assignment")
        channel_map = {
            require_positive(logical, "Logical channel"): require_positive(
                physical, "Physical port"
            )
            for logical, physical in spec.initial_channel_map.items()
        }
        record = AssignmentRecord(
            self._next("assignment"),
            spec.unit_id,
            spec.switch_id,
            require_utc(spec.installed_at_utc, "Installation time"),
            require_text(spec.installed_by, "Installer"),
            channel_map,
            notes=spec.notes,
        )
        self.assignments[record.assignment_id] = record
        return record

    def remove(
        self,
        assignment_id: int,
        removed_at_utc: datetime,
        removed_by: str,
        removal_reason: str,
    ) -> AssignmentRecord:
        current = self.assignments[int(assignment_id)]
        removed = require_utc(removed_at_utc, "Removal time")
        if current.removed_at_utc is not None:
            raise ValueError("The assignment has already been removed")
        if removed < current.installed_at_utc:
            raise ValueError("Removal time cannot precede installation")
        updated = replace(
            current,
            removed_at_utc=removed,
            removed_by=require_text(removed_by, "Removal operator"),
            removal_reason=require_text(removal_reason, "Removal reason"),
        )
        self.assignments[updated.assignment_id] = updated
        return updated

    def replace_active(
        self,
        assignment_id: int,
        replacement: AssignmentSpec,
        removed_at_utc: datetime,
        removed_by: str,
        removal_reason: str,
    ) -> AssignmentRecord:
        current = self.assignments[int(assignment_id)]
        removed = require_utc(removed_at_utc, "Removal time")
        if current.removed_at_utc is not None:
            raise ValueError("The assignment has already been removed")
        if replacement.unit_id != current.unit_id:
            raise ValueError("A replacement assignment must belong to the same unit")
        if replacement.switch_id == current.switch_id:
            raise ValueError("A replacement assignment must use a different switch")
        if removed < current.installed_at_utc or replacement.installed_at_utc < removed:
            raise ValueError("Replacement timing cannot precede the active assignment")
        existing_switch_assignment = self.get_active_for_switch(replacement.switch_id)
        if existing_switch_assignment is not None:
            raise ValueError("The replacement switch already has an active assignment")

        closed = replace(
            current,
            removed_at_utc=removed,
            removed_by=require_text(removed_by, "Removal operator"),
            removal_reason=require_text(removal_reason, "Removal reason"),
        )
        installed = AssignmentRecord(
            self._next("assignment"),
            replacement.unit_id,
            replacement.switch_id,
            replacement.installed_at_utc,
            replacement.installed_by,
            replacement.initial_channel_map,
            notes=replacement.notes,
        )
        self.assignments[closed.assignment_id] = closed
        self.assignments[installed.assignment_id] = installed
        return installed

    def install_fresh_pairing(
        self,
        spec: AssignmentSpec,
        removed_at_utc: datetime,
        removed_by: str,
    ) -> tuple[AssignmentRecord, tuple[AssignmentRecord, ...], tuple[int, ...]]:
        """Close both sides of a conflicting pair and install a clean assignment."""
        with self._lock:
            removed = require_utc(removed_at_utc, "Pairing-change time")
            operator = require_text(removed_by, "Pairing-change operator")
            if spec.unit_id not in self.units or spec.switch_id not in self.switches:
                raise ValueError("Assignment unit and switch must already exist")
            active_for_unit = self.get_active(spec.unit_id)
            active_for_switch = self.get_active_for_switch(spec.switch_id)
            conflicts = []
            for item in (active_for_unit, active_for_switch):
                if item is not None and item.assignment_id not in {
                    value.assignment_id for value in conflicts
                }:
                    conflicts.append(item)
            if any(
                item.unit_id == spec.unit_id and item.switch_id == spec.switch_id
                for item in conflicts
            ):
                return conflicts[0], (), ()
            for item in conflicts:
                if removed < item.installed_at_utc:
                    raise ValueError("Pairing-change time cannot precede installation")

            before_assignments = dict(self.assignments)
            before_runs = dict(self.runs)
            before_next_ids = dict(self._next_ids)
            try:
                stopped_ids = []
                for item in conflicts:
                    reason = (
                        "Main board paired with switch %s"
                        % self.switches[spec.switch_id].switch_serial
                        if item.unit_id == spec.unit_id
                        else "Switch reassigned to main board %s"
                        % self.units[spec.unit_id].main_board_serial
                    )
                    closed = replace(
                        item,
                        removed_at_utc=removed,
                        removed_by=operator,
                        removal_reason=reason,
                    )
                    self.assignments[item.assignment_id] = closed
                    for run in tuple(self.runs.values()):
                        if (
                            run.assignment_id == item.assignment_id
                            and run.completion_status == "in_progress"
                        ):
                            self.runs[run.run_id] = replace(
                                run,
                                completion_status="stopped",
                                run_ended_at_utc=removed,
                                analysis_status="pending",
                            )
                            stopped_ids.append(run.run_id)
                installed = AssignmentRecord(
                    self._next("assignment"),
                    spec.unit_id,
                    spec.switch_id,
                    require_utc(spec.installed_at_utc, "Installation time"),
                    require_text(spec.installed_by, "Installer"),
                    spec.initial_channel_map,
                    notes=spec.notes,
                )
                self.assignments[installed.assignment_id] = installed
                closed_records = tuple(
                    self.assignments[item.assignment_id] for item in conflicts
                )
                return installed, closed_records, tuple(sorted(stopped_ids))
            except Exception:
                self.assignments = before_assignments
                self.runs = before_runs
                self._next_ids = before_next_ids
                raise

    def create_next_with_fresh_pairing(
        self,
        assignment: AssignmentSpec,
        run: PendingRunStartSpec,
        changed_at_utc: datetime,
        changed_by: str,
    ):
        with self._lock:
            before_assignments = dict(self.assignments)
            before_runs = dict(self.runs)
            before_next_ids = dict(self._next_ids)
            try:
                installed, closed, stopped = self.install_fresh_pairing(
                    assignment, changed_at_utc, changed_by
                )
                record = self.create_next(
                    run.with_assignment_id(installed.assignment_id)
                )
                return record, installed, closed, stopped
            except Exception:
                self.assignments = before_assignments
                self.runs = before_runs
                self._next_ids = before_next_ids
                raise

    def create(self, spec: RunSpec) -> RunRecord:
        existing = self.get_by_uuid(spec.client_run_uuid)
        if existing is not None:
            return existing
        if spec.assignment_id not in self.assignments:
            raise ValueError("Run assignment does not exist")
        mode = str(spec.wavelength_mode).upper()
        if mode not in {"SM", "MM"}:
            raise ValueError("Wavelength mode must be SM or MM")
        if spec.run_purpose not in VALID_RUN_PURPOSES:
            raise ValueError("Invalid run purpose")
        record = RunRecord(
            run_id=self._next("run"),
            assignment_id=spec.assignment_id,
            run_number=require_positive(spec.run_number, "Run number"),
            client_run_uuid=spec.client_run_uuid,
            run_started_at_utc=require_utc(spec.run_started_at_utc, "Run start time"),
            tested_by=require_text(spec.tested_by, "Tested by"),
            station_number=spec.station_number,
            wavelength_mode=mode,
            operating_band=require_text(spec.operating_band, "Operating band"),
            application_version=require_text(spec.application_version, "Application version"),
            measurement_hardware=spec.measurement_hardware,
            limit_snapshot=spec.limit_snapshot,
            run_purpose=spec.run_purpose,
            analysis_status=spec.analysis_status,
            void_info=spec.void_info,
            part_number_snapshot=spec.part_number_snapshot,
            front_panel_channel_count=spec.front_panel_channel_count,
            notes=spec.notes,
        )
        self.runs[record.run_id] = record
        return record

    def create_next(self, spec: RunStartSpec) -> RunRecord:
        existing = self.get_by_uuid(spec.client_run_uuid)
        if existing is not None:
            return existing
        assignment = self.assignments.get(spec.assignment_id)
        if assignment is None:
            raise ValueError("Run assignment does not exist")
        if assignment.removed_at_utc is not None:
            raise ValueError("A new run requires an active assignment")
        unit_assignment_ids = {
            item.assignment_id
            for item in self.assignments.values()
            if item.unit_id == assignment.unit_id
        }
        run_number = 1 + max(
            (
                item.run_number
                for item in self.runs.values()
                if item.assignment_id in unit_assignment_ids
            ),
            default=0,
        )
        return self.create(spec.with_run_number(run_number))

    def get(self, run_id: int) -> RunRecord | None:
        return self.runs.get(int(run_id))

    def get_by_uuid(self, client_run_uuid) -> RunRecord | None:
        return next(
            (item for item in self.runs.values() if item.client_run_uuid == client_run_uuid),
            None,
        )

    def list_for_assignment(self, assignment_id: int) -> tuple[RunRecord, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self.runs.values()
                    if item.assignment_id == int(assignment_id)
                ),
                key=lambda item: (item.run_number, item.run_id),
            )
        )

    def list_report_runs(self) -> tuple[RunRecord, ...]:
        return tuple(
            sorted(
                self.runs.values(),
                key=lambda item: (item.run_started_at_utc, item.run_id),
            )
        )

    def list_report_assignments(self) -> tuple[AssignmentRecord, ...]:
        return tuple(
            sorted(
                self.assignments.values(),
                key=lambda item: (item.installed_at_utc, item.assignment_id),
            )
        )

    def list_report_units(self) -> tuple[UnitRecord, ...]:
        return tuple(sorted(self.units.values(), key=lambda item: item.unit_id))

    def list_report_switches(self) -> tuple[SwitchRecord, ...]:
        return tuple(sorted(self.switches.values(), key=lambda item: item.switch_id))

    def report_measurements_for_runs(
        self, run_ids: tuple[int, ...]
    ) -> tuple[MeasurementRecord, ...]:
        selected = {int(value) for value in run_ids}
        return tuple(
            sorted(
                (
                    item
                    for item in self.measurements.values()
                    if item.run_id in selected
                ),
                key=lambda item: item.measurement_id,
            )
        )

    def report_replacements_for_assignments(
        self, assignment_ids: tuple[int, ...]
    ) -> tuple[ReplacementRecord, ...]:
        selected = {int(value) for value in assignment_ids}
        return tuple(
            sorted(
                (
                    item
                    for item in self.replacements.values()
                    if item.assignment_id in selected
                ),
                key=lambda item: item.replacement_id,
            )
        )

    def list_for_unit(self, unit_id: int) -> tuple[RunRecord, ...]:
        assignment_ids = {
            item.assignment_id
            for item in self.assignments.values()
            if item.unit_id == int(unit_id)
        }
        return tuple(
            sorted(
                (
                    item
                    for item in self.runs.values()
                    if item.assignment_id in assignment_ids
                ),
                key=lambda item: (item.run_number, item.run_id),
            )
        )

    def get_for_unit_run_number(
        self, unit_id: int, run_number: int
    ) -> RunRecord | None:
        return next(
            (
                item
                for item in self.list_for_unit(unit_id)
                if item.run_number == int(run_number)
            ),
            None,
        )

    def finish(
        self,
        run_id: int,
        completion_status: str,
        run_ended_at_utc: datetime,
        *,
        analysis_status: str | None = None,
        void_info: RunVoidInfo | None = None,
    ) -> RunRecord:
        if completion_status not in {"complete", "stopped", "failed"}:
            raise ValueError("Invalid terminal completion status")
        current = self.runs[int(run_id)]
        if current.completion_status != "in_progress":
            if current.completion_status == completion_status:
                return current
            raise ValueError("Run already has a different terminal status")
        ended = require_utc(run_ended_at_utc, "Run end time")
        if ended < current.run_started_at_utc:
            raise ValueError("Run end time cannot precede its start")
        updated = replace(
            current,
            completion_status=completion_status,
            run_ended_at_utc=ended,
            analysis_status=analysis_status or current.analysis_status,
            void_info=(
                void_info
                if analysis_status == "excluded"
                else None
                if analysis_status is not None
                else current.void_info
            ),
        )
        self.runs[updated.run_id] = updated
        return updated

    def resume(self, run_id: int) -> RunRecord:
        current = self.runs[int(run_id)]
        if current.completion_status == "in_progress":
            return current
        updated = replace(
            current,
            completion_status="in_progress",
            run_ended_at_utc=None,
        )
        self.runs[updated.run_id] = updated
        return updated

    def set_analysis_status(
        self,
        run_id: int,
        analysis_status: str,
        void_info: RunVoidInfo | None = None,
        superseded_by_run_id: int | None = None,
    ) -> RunRecord:
        if analysis_status not in {"pending", "included", "excluded", "superseded"}:
            raise ValueError("Invalid analysis status")
        if analysis_status == "excluded" and void_info is None:
            raise ValueError("Voided runs require run void information")
        if analysis_status == "superseded":
            if superseded_by_run_id is None or int(superseded_by_run_id) == int(run_id):
                raise ValueError("Superseded runs require a different replacement run")
            if int(superseded_by_run_id) not in self.runs:
                raise ValueError("The superseding run does not exist")
        elif superseded_by_run_id is not None:
            raise ValueError("Only superseded runs may identify a superseding run")
        current = self.runs[int(run_id)]
        updated = replace(
            current,
            analysis_status=analysis_status,
            void_info=(void_info if analysis_status == "excluded" else None),
            superseded_by_run_id=(
                int(superseded_by_run_id) if analysis_status == "superseded" else None
            ),
        )
        self.runs[updated.run_id] = updated
        return updated

    def void_run(self, run_id: int, void_info: RunVoidInfo) -> RunRecord:
        current = self.runs[int(run_id)]
        if current.analysis_status == "excluded":
            raise ValueError("Run is already voided")
        updated = replace(
            current,
            analysis_status="excluded",
            void_info=void_info,
            superseded_by_run_id=None,
        )
        self.runs[updated.run_id] = updated
        return updated

    def find_stale_in_progress(self, before_utc: datetime) -> tuple[RunRecord, ...]:
        cutoff = require_utc(before_utc, "Stale-run cutoff")
        return tuple(
            sorted(
                (
                    item
                    for item in self.runs.values()
                    if item.completion_status == "in_progress"
                    and item.run_started_at_utc < cutoff
                ),
                key=lambda item: item.run_started_at_utc,
            )
        )

    def append_attempt(self, spec: MeasurementSpec) -> MeasurementRecord:
        with self._lock:
            existing = self.get_measurement_by_uuid(spec.measurement_uuid)
            if existing is not None:
                return existing
            self._validate_measurement_run(spec)
            if any(
                item.run_id == spec.run_id
                and item.measurement_role == spec.measurement_role
                and (
                    item.logical_channel == spec.logical_channel
                    if spec.measurement_role == MEASUREMENT_ROLE_LOGICAL_CHANNEL
                    else item.physical_port == spec.physical_port
                )
                and item.attempt_number == spec.attempt_number
                for item in self.measurements.values()
            ):
                raise ValueError("Measurement attempt number already exists")
            record = MeasurementRecord(
                measurement_id=self._next("measurement"),
                measurement_uuid=spec.measurement_uuid,
                run_id=spec.run_id,
                logical_channel=spec.logical_channel,
                attempt_number=require_positive(spec.attempt_number, "Attempt number"),
                wavelength_1_nm=require_positive(spec.wavelength_1_nm, "First wavelength"),
                wavelength_1_il_db=Decimal(spec.wavelength_1_il_db),
                wavelength_2_nm=require_positive(spec.wavelength_2_nm, "Second wavelength"),
                wavelength_2_il_db=Decimal(spec.wavelength_2_il_db),
                reference_snapshot=spec.reference_snapshot,
                written_at_utc=require_utc(spec.written_at_utc, "Write time"),
                written_by=require_text(spec.written_by, "Write operator"),
                physical_port=(
                    require_positive(spec.physical_port, "Physical port")
                    if spec.physical_port is not None
                    else None
                ),
                measurement_role=spec.measurement_role,
            )
            self.measurements[record.measurement_id] = record
            return record

    def append_next(self, spec: MeasurementWriteSpec) -> MeasurementRecord:
        with self._lock:
            existing = self.get_measurement_by_uuid(spec.measurement_uuid)
            if existing is not None:
                return existing
            self._validate_measurement_run(spec)
            attempt_number = 1 + max(
                (
                    item.attempt_number
                    for item in self.measurements.values()
                    if item.run_id == spec.run_id
                    and item.measurement_role == spec.measurement_role
                    and (
                        item.logical_channel == spec.logical_channel
                        if spec.measurement_role == MEASUREMENT_ROLE_LOGICAL_CHANNEL
                        else item.physical_port == spec.physical_port
                    )
                ),
                default=0,
            )
            return self.append_attempt(spec.with_attempt_number(attempt_number))

    def get_measurement_by_uuid(self, measurement_uuid) -> MeasurementRecord | None:
        return next(
            (
                item
                for item in self.measurements.values()
                if item.measurement_uuid == measurement_uuid
            ),
            None,
        )

    def _validate_measurement_run(self, spec) -> RunRecord:
        run = self.runs.get(int(spec.run_id))
        if run is None:
            raise ValueError("Measurement run does not exist")
        if run.completion_status != "in_progress":
            raise ValueError("Measurements may only be written to an in-progress run")
        expected = (1310, 1550) if run.wavelength_mode == "SM" else (850, 1300)
        actual = (int(spec.wavelength_1_nm), int(spec.wavelength_2_nm))
        if actual != expected:
            raise ValueError(
                f"{run.wavelength_mode} measurements require wavelengths "
                f"{expected[0]} nm and {expected[1]} nm"
            )
        if run.front_panel_channel_count is not None:
            boundary = int(run.front_panel_channel_count)
            if spec.measurement_role == MEASUREMENT_ROLE_LOGICAL_CHANNEL:
                if int(spec.logical_channel) > boundary:
                    raise ValueError("Logical channel exceeds the front-panel channel count")
            elif int(spec.physical_port) <= boundary:
                raise ValueError("Extra-candidate physical port must exceed the front-panel channel count")
        return run

    def current_for_run(self, run_id: int) -> tuple[MeasurementRecord, ...]:
        current: dict[tuple[str, int], MeasurementRecord] = {}
        for item in self.history_for_run(run_id):
            identity = (
                item.measurement_role,
                int(item.logical_channel if item.logical_channel is not None else item.physical_port),
            )
            prior = current.get(identity)
            if prior is None or item.attempt_number > prior.attempt_number:
                current[identity] = item
        return tuple(current[identity] for identity in sorted(current))

    def history_for_run(self, run_id: int) -> tuple[MeasurementRecord, ...]:
        return tuple(
            sorted(
                (item for item in self.measurements.values() if item.run_id == int(run_id)),
                key=lambda item: item.measurement_id,
            )
        )

    def history_for_runs(
        self, run_ids: tuple[int, ...]
    ) -> dict[int, tuple[MeasurementRecord, ...]]:
        return {
            run_id: self.history_for_run(run_id)
            for run_id in dict.fromkeys(int(value) for value in run_ids)
        }

    def snapshot_for_run(
        self, run_id: int
    ) -> tuple[tuple[MeasurementRecord, ...], tuple[MeasurementRecord, ...]]:
        with self._lock:
            history = self.history_for_run(run_id)
            current: dict[tuple[str, int], MeasurementRecord] = {}
            for item in history:
                identity = (
                    item.measurement_role,
                    int(item.logical_channel if item.logical_channel is not None else item.physical_port),
                )
                prior = current.get(identity)
                if prior is None or item.attempt_number > prior.attempt_number:
                    current[identity] = item
            latest = tuple(current[identity] for identity in sorted(current))
            return latest, history

    def append(self, spec: ReplacementSpec) -> ReplacementRecord:
        with self._lock:
            assignment, switch = self._routing_context(
                spec.assignment_id, require_active=True
            )
            channel_map = {
                item.logical_channel: item
                for item in self.current_channel_map(spec.assignment_id)
            }
            route = channel_map.get(spec.logical_channel)
            if route is None:
                raise ValueError("Replacement logical channel is not in the assignment")
            if route.effective_physical_port != spec.previous_physical_port:
                raise ValueError(
                    "Previous physical port does not match the current channel map"
                )
            if any(
                item.logical_channel != spec.logical_channel
                and item.effective_physical_port == spec.replacement_physical_port
                for item in channel_map.values()
            ):
                raise ValueError("Replacement physical port is already in use")
            confirmed = {
                item.physical_port: item
                for item in self.confirmed_extra_ports_for_assignment(spec.assignment_id)
            }
            if not spec.is_correction and spec.replacement_physical_port not in confirmed:
                raise ValueError(
                    "Replacement physical port has no valid committed extra-port "
                    "measurement for this assignment"
                )
            if spec.related_run_id is not None:
                run = self.runs.get(spec.related_run_id)
                if run is None or run.assignment_id != spec.assignment_id:
                    raise ValueError("Related run does not belong to this assignment")
            if spec.source_recommendation_id is not None:
                recommendation = self.replacement_analysis_recommendations.get(
                    int(spec.source_recommendation_id)
                )
                if recommendation is None:
                    raise ValueError("Source replacement recommendation does not exist")
                analysis = self.replacement_analyses[recommendation.analysis_id]
                source_run = self.runs.get(analysis.run_id)
                if source_run is None or source_run.assignment_id != spec.assignment_id:
                    raise ValueError(
                        "Source replacement recommendation belongs to another assignment"
                    )
                try:
                    self._validate_analysis_source_snapshot(
                        source_run,
                        analysis.result_details.get("source_snapshot", {}),
                        analysis.source_measurement_high_watermark_id,
                    )
                except ValueError as error:
                    raise ValueError(
                        "Source replacement recommendation is stale"
                    ) from error
                if (
                    recommendation.logical_channel != spec.logical_channel
                    or recommendation.candidate_physical_port
                    != spec.replacement_physical_port
                ):
                    raise ValueError(
                        "Source recommendation does not match the replacement"
                    )
                evidence_id = recommendation.candidate_measurement_id
                if evidence_id is not None and (
                    spec.replacement_physical_port not in confirmed
                    or confirmed[spec.replacement_physical_port].measurement.measurement_id
                    != evidence_id
                ):
                    raise ValueError("Source recommendation candidate evidence is stale")
                if any(
                    item.source_recommendation_id == spec.source_recommendation_id
                    for item in self.replacements.values()
                ):
                    raise ValueError("Source replacement recommendation was already used")
            history = self.replacement_history_for_assignment(spec.assignment_id)
            prior = [
                item for item in history if item.logical_channel == spec.logical_channel
            ]
            if spec.replaced_at_utc < assignment.installed_at_utc or (
                prior and spec.replaced_at_utc < prior[-1].replaced_at_utc
            ):
                raise ValueError("Replacement time precedes its assignment history")
            record = ReplacementRecord(
                self._next("replacement"),
                spec.assignment_id,
                spec.logical_channel,
                spec.previous_physical_port,
                spec.replacement_physical_port,
                spec.reason,
                spec.replaced_by,
                spec.replaced_at_utc,
                spec.related_run_id,
                spec.notes,
                spec.source_recommendation_id,
            )
            self.replacements[record.replacement_id] = record
            return record

    def append_analysis(self, spec, recommendations):
        with self._lock:
            existing = next(
                (
                    item
                    for item in self.replacement_analyses.values()
                    if item.analysis_uuid == spec.analysis_uuid
                ),
                None,
            )
            if existing is not None:
                return self._analysis_bundle(existing.analysis_id)
            run = self.runs.get(spec.run_id)
            if run is None:
                raise ValueError("Replacement analysis run does not exist")
            self._validate_analysis_source_snapshot(
                run,
                spec.result_details.get("source_snapshot", {}),
                spec.source_measurement_high_watermark_id,
            )
            analysis_id = self._next("replacement_analysis")
            record = ReplacementAnalysisRecord(
                analysis_id,
                spec.analysis_uuid,
                spec.run_id,
                spec.analyzed_at_utc,
                spec.analyzed_by,
                spec.application_version,
                spec.source_measurement_high_watermark_id,
                spec.front_panel_channel_count,
                spec.wavelengths,
                spec.criteria,
                spec.result_status,
                spec.result_details,
            )
            inserted = []
            try:
                self.replacement_analyses[analysis_id] = record
                for item in recommendations:
                    if item.analysis_id not in (None, analysis_id):
                        raise ValueError("Recommendation analysis ID does not match")
                    if item.current_measurement_id is not None:
                        current_evidence = self.measurements.get(
                            int(item.current_measurement_id)
                        )
                        current_run = (
                            self.runs.get(current_evidence.run_id)
                            if current_evidence is not None
                            else None
                        )
                        if (
                            current_evidence is None
                            or current_run is None
                            or current_run.assignment_id != run.assignment_id
                            or current_evidence.measurement_role
                            != MEASUREMENT_ROLE_LOGICAL_CHANNEL
                            or current_evidence.logical_channel != item.logical_channel
                            or current_evidence.physical_port
                            != item.current_physical_port
                        ):
                            raise ValueError(
                                "Recommendation current measurement evidence is invalid"
                            )
                    if item.candidate_measurement_id is not None:
                        confirmed = {
                            evidence.measurement.measurement_id: evidence
                            for evidence in self.confirmed_extra_ports_for_assignment(
                                run.assignment_id
                            )
                        }.get(int(item.candidate_measurement_id))
                        if (
                            confirmed is None
                            or confirmed.physical_port
                            != item.candidate_physical_port
                        ):
                            raise ValueError(
                                "Recommendation candidate measurement evidence is invalid"
                            )
                    recommendation_id = self._next("replacement_recommendation")
                    inserted_record = ReplacementAnalysisRecommendationRecord(
                        recommendation_id,
                        analysis_id,
                        item.recommendation_rank,
                        item.category,
                        item.logical_channel,
                        item.current_physical_port,
                        item.candidate_physical_port,
                        item.current_wavelength_1_il_db,
                        item.current_wavelength_2_il_db,
                        item.candidate_wavelength_1_il_db,
                        item.candidate_wavelength_2_il_db,
                        item.current_worst_loss_db,
                        item.candidate_worst_loss_db,
                        item.improvement_db,
                        item.current_measurement_id,
                        item.candidate_measurement_id,
                    )
                    self.replacement_analysis_recommendations[
                        recommendation_id
                    ] = inserted_record
                    inserted.append(recommendation_id)
            except Exception:
                self.replacement_analyses.pop(analysis_id, None)
                for recommendation_id in inserted:
                    self.replacement_analysis_recommendations.pop(
                        recommendation_id, None
                    )
                raise
            return record, tuple(
                self.replacement_analysis_recommendations[item]
                for item in inserted
            )

    def _validate_analysis_source_snapshot(self, context_run, snapshot, high_watermark):
        """Validate legacy or assignment-scoped analysis source evidence."""
        if not isinstance(snapshot, Mapping) or not snapshot.get(
            "considered_measurement_ids"
        ):
            measurement = self.measurements.get(int(high_watermark))
            if measurement is None or measurement.run_id != context_run.run_id:
                raise ValueError("Analysis source measurement does not belong to the run")
            if int(high_watermark) != self.current_measurement_high_watermark(
                context_run.run_id
            ):
                raise ValueError("Analysis source measurements are no longer current")
            return

        assignment_id = int(snapshot.get("assignment_id", 0))
        context_run_id = int(snapshot.get("context_run_id", 0))
        included_run_ids = tuple(
            sorted({int(value) for value in snapshot.get("included_run_ids", ())})
        )
        considered_ids = tuple(
            sorted(
                {int(value) for value in snapshot.get("considered_measurement_ids", ())}
            )
        )
        if (
            assignment_id != context_run.assignment_id
            or context_run_id != context_run.run_id
            or context_run.run_id not in included_run_ids
            or not considered_ids
            or int(high_watermark) != max(considered_ids)
        ):
            raise ValueError("Analysis source snapshot is inconsistent")
        included_runs = [self.runs.get(run_id) for run_id in included_run_ids]
        if any(
            run is None or run.assignment_id != assignment_id
            for run in included_runs
        ):
            raise ValueError("Analysis source runs do not belong to the assignment")
        current_measurement_ids = tuple(
            sorted(
                item.measurement_id
                for item in self.measurements.values()
                if item.run_id in included_run_ids
            )
        )
        if current_measurement_ids != considered_ids:
            raise ValueError("Analysis source measurements are no longer current")
        states = {
            int(item["run_id"]): (
                str(item.get("analysis_status") or ""),
                item.get("superseded_by_run_id"),
            )
            for item in snapshot.get("included_run_states", ())
            if isinstance(item, Mapping) and item.get("run_id") is not None
        }
        for run in included_runs:
            if states and states.get(run.run_id) != (
                run.analysis_status,
                run.superseded_by_run_id,
            ):
                raise ValueError("Analysis source run state is no longer current")
        replacement_ids = tuple(
            sorted(
                item.replacement_id
                for item in self.replacements.values()
                if item.assignment_id == assignment_id
                and (
                    item.related_run_id is None
                    or item.related_run_id in included_run_ids
                )
            )
        )
        if replacement_ids != tuple(
            sorted(int(value) for value in snapshot.get("replacement_ids", ()))
        ):
            raise ValueError("Analysis source replacements are no longer current")
        spare_event_ids = tuple(
            sorted(
                item.spare_event_id
                for item in self.spare_events.values()
                if item.assignment_id == assignment_id
            )
        )
        if spare_event_ids != tuple(
            sorted(int(value) for value in snapshot.get("spare_event_ids", ()))
        ):
            raise ValueError("Analysis source spare history is no longer current")

    def latest_analysis_for_run(self, run_id):
        analyses = [
            item for item in self.replacement_analyses.values() if item.run_id == int(run_id)
        ]
        if not analyses:
            return None
        analysis = max(analyses, key=lambda item: (item.analyzed_at_utc, item.analysis_id))
        return self._analysis_bundle(analysis.analysis_id)

    def analysis_history_for_run(self, run_id):
        analyses = sorted(
            (
                item
                for item in self.replacement_analyses.values()
                if item.run_id == int(run_id)
            ),
            key=lambda item: (item.analyzed_at_utc, item.analysis_id),
            reverse=True,
        )
        return tuple(self._analysis_bundle(item.analysis_id) for item in analyses)

    def current_measurement_high_watermark(self, run_id):
        values = [
            item.measurement_id
            for item in self.measurements.values()
            if item.run_id == int(run_id)
        ]
        return max(values) if values else None

    def _analysis_bundle(self, analysis_id):
        analysis = self.replacement_analyses[int(analysis_id)]
        recommendations = tuple(
            sorted(
                (
                    item
                    for item in self.replacement_analysis_recommendations.values()
                    if item.analysis_id == analysis.analysis_id
                ),
                key=lambda item: (item.recommendation_rank, item.recommendation_id),
            )
        )
        return analysis, recommendations

    def replacement_history_for_assignment(
        self, assignment_id: int
    ) -> tuple[ReplacementRecord, ...]:
        with self._lock:
            self._routing_context(assignment_id)
            return tuple(
                sorted(
                    (
                        item
                        for item in self.replacements.values()
                        if item.assignment_id == int(assignment_id)
                    ),
                    key=lambda item: item.replacement_id,
                )
            )

    def current_channel_map(
        self, assignment_id: int
    ) -> tuple[ChannelMapRecord, ...]:
        with self._lock:
            assignment, _switch = self._routing_context(assignment_id)
            latest = {}
            for replacement in self.replacement_history_for_assignment(assignment_id):
                prior = latest.get(replacement.logical_channel)
                if prior is None or (
                    replacement.replaced_at_utc,
                    replacement.replacement_id,
                ) > (prior.replaced_at_utc, prior.replacement_id):
                    latest[replacement.logical_channel] = replacement
            rows = []
            for logical_channel, initial_port in sorted(
                assignment.initial_channel_map.items()
            ):
                replacement = latest.get(logical_channel)
                rows.append(
                    ChannelMapRecord(
                        assignment.assignment_id,
                        assignment.unit_id,
                        assignment.switch_id,
                        logical_channel,
                        initial_port,
                        (
                            replacement.replacement_physical_port
                            if replacement is not None
                            else initial_port
                        ),
                        replacement is not None,
                        replacement.replacement_id if replacement is not None else None,
                        replacement.replaced_at_utc if replacement is not None else None,
                    )
                )
            return tuple(rows)

    def confirmed_extra_ports_for_assignment(
        self, assignment_id: int
    ) -> tuple[ConfirmedExtraPortRecord, ...]:
        with self._lock:
            self._routing_context(assignment_id)
            eligible_runs = {
                run.run_id: run
                for run in self.runs.values()
                if run.assignment_id == int(assignment_id)
                and run.analysis_status not in {"excluded", "superseded"}
            }
            latest: dict[int, MeasurementRecord] = {}
            for measurement in self.measurements.values():
                run = eligible_runs.get(measurement.run_id)
                if (
                    run is None
                    or measurement.measurement_role
                    != MEASUREMENT_ROLE_EXTRA_CANDIDATE
                    or run.front_panel_channel_count is None
                    or int(measurement.physical_port)
                    <= int(run.front_panel_channel_count)
                ):
                    continue
                port = int(measurement.physical_port)
                prior = latest.get(port)
                if prior is None or (
                    measurement.written_at_utc,
                    measurement.attempt_number,
                    measurement.measurement_id,
                ) > (
                    prior.written_at_utc,
                    prior.attempt_number,
                    prior.measurement_id,
                ):
                    latest[port] = measurement
            return tuple(
                ConfirmedExtraPortRecord(
                    int(assignment_id),
                    measurement.run_id,
                    measurement,
                    int(eligible_runs[measurement.run_id].front_panel_channel_count),
                )
                for _port, measurement in sorted(latest.items())
            )

    def append_event(self, spec: SpareEventSpec) -> SpareEventRecord:
        with self._lock:
            assignment, switch = self._routing_context(
                spec.assignment_id, require_active=True
            )
            if spec.action == "designated":
                confirmed = {
                    item.physical_port
                    for item in self.confirmed_extra_ports_for_assignment(
                        spec.assignment_id
                    )
                }
                if spec.physical_port not in confirmed:
                    raise ValueError(
                        "Spare physical port has no valid committed extra-port "
                        "measurement for this assignment"
                    )
                if spec.physical_port in {
                    item.effective_physical_port
                    for item in self.current_channel_map(spec.assignment_id)
                }:
                    raise ValueError("Mapped physical port cannot be designated as a spare")
            history = self.spare_history_for_assignment(spec.assignment_id)
            prior = [item for item in history if item.physical_port == spec.physical_port]
            current_action = prior[-1].action if prior else "undesignated"
            if current_action == spec.action:
                raise ValueError(f"Physical port is already {spec.action}")
            if spec.recorded_at_utc < assignment.installed_at_utc or (
                prior and spec.recorded_at_utc < prior[-1].recorded_at_utc
            ):
                raise ValueError("Spare event time precedes its assignment history")
            record = SpareEventRecord(
                self._next("spare_event"),
                spec.assignment_id,
                spec.physical_port,
                spec.action,
                spec.recorded_by,
                spec.recorded_at_utc,
                spec.notes,
            )
            self.spare_events[record.spare_event_id] = record
            return record

    def spare_history_for_assignment(
        self, assignment_id: int
    ) -> tuple[SpareEventRecord, ...]:
        with self._lock:
            self._routing_context(assignment_id)
            return tuple(
                sorted(
                    (
                        item
                        for item in self.spare_events.values()
                        if item.assignment_id == int(assignment_id)
                    ),
                    key=lambda item: item.spare_event_id,
                )
            )

    def active_spares_for_assignment(self, assignment_id: int) -> tuple[int, ...]:
        with self._lock:
            latest = {}
            for event in self.spare_history_for_assignment(assignment_id):
                latest[event.physical_port] = event
            return tuple(
                sorted(
                    port
                    for port, event in latest.items()
                    if event.action == "designated"
                )
            )

    def routing_snapshot_for_assignment(self, assignment_id: int):
        with self._lock:
            return (
                self.current_channel_map(assignment_id),
                self.replacement_history_for_assignment(assignment_id),
                self.spare_history_for_assignment(assignment_id),
                self.active_spares_for_assignment(assignment_id),
            )

    def apply_routing_changes(self, replacement_specs, spare_event_specs):
        """Apply one replacement approval atomically for hardware-free workflows."""
        specs = tuple(replacement_specs)
        spare_specs = tuple(spare_event_specs)
        assignment_ids = {
            spec.assignment_id for spec in (*specs, *spare_specs)
        }
        if len(assignment_ids) != 1:
            raise ValueError("Routing changes must target one assignment")
        assignment_id = next(iter(assignment_ids))
        with self._lock:
            replacements_before = dict(self.replacements)
            spares_before = dict(self.spare_events)
            ids_before = dict(self._next_ids)
            try:
                for spec in specs:
                    self.append(spec)
                for spec in spare_specs:
                    self.append_event(spec)
            except Exception:
                self.replacements = replacements_before
                self.spare_events = spares_before
                self._next_ids = ids_before
                raise
            return self.routing_snapshot_for_assignment(assignment_id)

    def _routing_context(self, assignment_id: int, *, require_active: bool = False):
        assignment = self.assignments.get(int(assignment_id))
        if assignment is None:
            raise ValueError("Routing assignment does not exist")
        if require_active and assignment.removed_at_utc is not None:
            raise ValueError("Routing changes require an active assignment")
        switch = self.switches.get(assignment.switch_id)
        if switch is None:
            raise ValueError("Assignment switch does not exist")
        return assignment, switch


__all__ = ["InMemoryRepositories"]
