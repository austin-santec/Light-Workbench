"""Application orchestration for SQL-primary production runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from application.database_run_read_model import (
    DatabaseRunQueryService,
    DatabaseRunSnapshot,
)
from application.database_reporting import DatabaseReportingService
from application.measurement_persistence_workflow import MeasurementPersistenceWorkflow
from application.replacement_persistence_workflow import (
    AssignmentRoutingSnapshot,
    ReplacementPersistenceWorkflow,
)
from application.replacement_analysis_persistence import (
    ReplacementAnalysisPersistenceWorkflow,
)
from application.run_lifecycle_workflow import (
    DatabaseRunUnavailableError,
    RunLifecycleWorkflow,
)
from application.unit_switch_workflow import (
    UnitSwitchAssignmentResult,
    UnitSwitchAssignmentWorkflow,
)
from domain.unit_switch_assignments import AssignmentChangeRequiredError
from domain.database_records import (
    MeasurementRecord,
    MeasurementWriteSpec,
    RunRecord,
    SwitchSpec,
    UnitSpec,
    utc_now,
)


@dataclass(frozen=True)
class DatabaseRunContext:
    """Identity, routing, and latest accepted values for one persisted run."""

    unit: object
    switch: object
    assignment: object
    snapshot: DatabaseRunSnapshot
    routing: AssignmentRoutingSnapshot
    replacement_analysis: object | None = None
    replacement_analysis_history: tuple[object, ...] = ()

    @property
    def run(self) -> RunRecord:
        return self.snapshot.run


class DatabasePrimaryRunWorkflow:
    """Keep Qt and hardware code independent from SQL and connection details."""

    def __init__(self, repositories, readiness_check) -> None:
        self.repositories = repositories
        self._readiness_check = readiness_check
        self.assignments = UnitSwitchAssignmentWorkflow(
            repositories, repositories, repositories
        )
        self.lifecycle = RunLifecycleWorkflow(repositories, readiness_check)
        self.measurements = MeasurementPersistenceWorkflow(repositories)
        self.queries = DatabaseRunQueryService(repositories, repositories)
        self.reporting = DatabaseReportingService(repositories, self.queries)
        self.replacements = ReplacementPersistenceWorkflow(repositories)
        self.replacement_analyses = ReplacementAnalysisPersistenceWorkflow(repositories)

    def check_ready(self):
        return self._readiness_check()

    def start_new_run(
        self,
        *,
        unit_spec: UnitSpec,
        switch_spec: SwitchSpec,
        installed_by: str,
        initial_channel_map: Mapping[int, int],
        tested_by: str,
        wavelength_mode: str,
        operating_band: str,
        application_version: str,
        measurement_hardware: Mapping,
        limit_snapshot: Mapping,
        part_number_snapshot: str | None,
        front_panel_channel_count: int | None,
        station_number: int | None = None,
        run_purpose: str = "production",
        started_at_utc: datetime | None = None,
        switch_replacement_reason: str | None = None,
    ) -> DatabaseRunContext:
        readiness = self.check_ready()
        if not getattr(readiness, "ready", False):
            raise DatabaseRunUnavailableError(readiness)
        started = started_at_utc or utc_now()
        try:
            assignment = self.assignments.resolve(
                unit_spec,
                switch_spec,
                installed_at_utc=started,
                installed_by=installed_by,
                initial_channel_map=initial_channel_map,
            )
        except AssignmentChangeRequiredError:
            if not str(switch_replacement_reason or "").strip():
                raise
            assignment = self.assignments.replace_switch(
                unit_spec,
                switch_spec,
                changed_at_utc=started,
                changed_by=installed_by,
                removal_reason=str(switch_replacement_reason).strip(),
                initial_channel_map=initial_channel_map,
            )
        run = self.lifecycle.start_run(
            assignment_id=assignment.assignment.assignment_id,
            tested_by=tested_by,
            wavelength_mode=wavelength_mode,
            operating_band=operating_band,
            application_version=application_version,
            measurement_hardware=measurement_hardware,
            limit_snapshot=limit_snapshot,
            part_number_snapshot=part_number_snapshot,
            front_panel_channel_count=front_panel_channel_count,
            station_number=station_number,
            run_purpose=run_purpose,
            started_at_utc=started,
        )
        return self._context(run, assignment)

    def load_for_unit(self, main_board_serial: str, run_number: int) -> DatabaseRunContext:
        self._require_ready()
        unit = self.repositories.get_by_main_board_serial(main_board_serial)
        if unit is None:
            raise ValueError("No database unit matches that main-board serial.")
        run = self.repositories.get_for_unit_run_number(unit.unit_id, run_number)
        if run is None:
            available = self.repositories.list_for_unit(unit.unit_id)
            numbers = ", ".join(str(item.run_number) for item in available) or "none"
            raise ValueError(
                f"No Run {int(run_number)} was found for this unit. "
                f"Available runs: {numbers}."
            )
        return self._context(run)

    def load_run(self, run_id: int) -> DatabaseRunContext:
        self._require_ready()
        run = self.repositories.get(run_id)
        if run is None:
            raise ValueError("Run was not found")
        return self._context(run)

    def refresh(self, run_id: int) -> DatabaseRunContext:
        return self.load_run(run_id)

    def list_for_unit(self, unit_id: int) -> tuple[DatabaseRunContext, ...]:
        self._require_ready()
        return tuple(
            self._context(run)
            for run in self.repositories.list_for_unit(int(unit_id))
        )

    def commit_measurement(
        self, pending: MeasurementWriteSpec
    ) -> tuple[MeasurementRecord, DatabaseRunContext]:
        record = self.measurements.commit(pending)
        return record, self.refresh(record.run_id)

    def finish_run(self, run_id: int, status: str) -> DatabaseRunContext:
        run = self.lifecycle.finish_run(run_id, status)
        return self._context(run)

    def resume_run(self, run_id: int) -> DatabaseRunContext:
        self._require_ready()
        run = self.lifecycle.resume_run(run_id)
        return self._context(run)

    def _require_ready(self) -> None:
        result = self.check_ready()
        if not getattr(result, "ready", False):
            raise DatabaseRunUnavailableError(result)

    def _context(
        self,
        run: RunRecord,
        assignment_result: UnitSwitchAssignmentResult | None = None,
    ) -> DatabaseRunContext:
        if assignment_result is None:
            assignment = self.repositories.get_assignment(run.assignment_id)
            if assignment is None:
                raise ValueError("Run assignment was not found")
            unit = self.repositories.get_unit(assignment.unit_id)
            switch = self.repositories.get_switch(assignment.switch_id)
        else:
            assignment = assignment_result.assignment
            unit = assignment_result.unit
            switch = assignment_result.switch
        if unit is None or switch is None:
            raise ValueError("Run hardware identity is incomplete")
        return DatabaseRunContext(
            unit,
            switch,
            assignment,
            self.queries.load(run.run_id),
            self.replacements.load_assignment(assignment.assignment_id),
            self.replacement_analyses.latest_for_run(run.run_id),
            self.replacement_analyses.history_for_run(run.run_id),
        )


__all__ = ["DatabasePrimaryRunWorkflow", "DatabaseRunContext"]
