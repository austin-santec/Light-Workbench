"""In-memory implementations of database repository contracts for tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from threading import RLock

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
        self._next_ids: dict[str, int] = {}
        self._lock = RLock()

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
        count = require_positive(spec.physical_channel_count, "Physical channel count")
        existing = next(
            (item for item in self.switches.values() if item.switch_serial == serial),
            None,
        )
        if existing is not None:
            updated = replace(
                existing,
                switch_model=model,
                physical_channel_count=count,
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
            analysis_exclusion_reason=spec.analysis_exclusion_reason,
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
        analysis_exclusion_reason: str | None = None,
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
            analysis_exclusion_reason=(
                analysis_exclusion_reason
                if analysis_status == "excluded"
                else None
                if analysis_status is not None
                else current.analysis_exclusion_reason
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
        exclusion_reason: str | None = None,
        superseded_by_run_id: int | None = None,
    ) -> RunRecord:
        if analysis_status not in {"pending", "included", "excluded", "superseded"}:
            raise ValueError("Invalid analysis status")
        if analysis_status == "excluded" and not str(exclusion_reason or "").strip():
            raise ValueError("Excluded runs require an analysis exclusion reason")
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
            analysis_exclusion_reason=(
                str(exclusion_reason).strip() if analysis_status == "excluded" else None
            ),
            superseded_by_run_id=(
                int(superseded_by_run_id) if analysis_status == "superseded" else None
            ),
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
                and item.logical_channel == spec.logical_channel
                and item.attempt_number == spec.attempt_number
                for item in self.measurements.values()
            ):
                raise ValueError("Measurement attempt number already exists")
            record = MeasurementRecord(
                measurement_id=self._next("measurement"),
                measurement_uuid=spec.measurement_uuid,
                run_id=spec.run_id,
                logical_channel=require_positive(spec.logical_channel, "Logical channel"),
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
                    and item.logical_channel == spec.logical_channel
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
        return run

    def current_for_run(self, run_id: int) -> tuple[MeasurementRecord, ...]:
        current: dict[int, MeasurementRecord] = {}
        for item in self.history_for_run(run_id):
            prior = current.get(item.logical_channel)
            if prior is None or item.attempt_number > prior.attempt_number:
                current[item.logical_channel] = item
        return tuple(current[channel] for channel in sorted(current))

    def history_for_run(self, run_id: int) -> tuple[MeasurementRecord, ...]:
        return tuple(
            sorted(
                (item for item in self.measurements.values() if item.run_id == int(run_id)),
                key=lambda item: item.measurement_id,
            )
        )

    def snapshot_for_run(
        self, run_id: int
    ) -> tuple[tuple[MeasurementRecord, ...], tuple[MeasurementRecord, ...]]:
        with self._lock:
            history = self.history_for_run(run_id)
            current: dict[int, MeasurementRecord] = {}
            for item in history:
                prior = current.get(item.logical_channel)
                if prior is None or item.attempt_number > prior.attempt_number:
                    current[item.logical_channel] = item
            latest = tuple(current[channel] for channel in sorted(current))
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
            if spec.replacement_physical_port > switch.physical_channel_count:
                raise ValueError("Replacement physical port exceeds switch capacity")
            if any(
                item.logical_channel != spec.logical_channel
                and item.effective_physical_port == spec.replacement_physical_port
                for item in channel_map.values()
            ):
                raise ValueError("Replacement physical port is already in use")
            if spec.related_run_id is not None:
                run = self.runs.get(spec.related_run_id)
                if run is None or run.assignment_id != spec.assignment_id:
                    raise ValueError("Related run does not belong to this assignment")
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
            )
            self.replacements[record.replacement_id] = record
            return record

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

    def append_event(self, spec: SpareEventSpec) -> SpareEventRecord:
        with self._lock:
            assignment, switch = self._routing_context(
                spec.assignment_id, require_active=True
            )
            if spec.physical_port > switch.physical_channel_count:
                raise ValueError("Spare physical port exceeds switch capacity")
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
