"""Application orchestration for SQL-primary production runs."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Mapping

from application.database_run_read_model import (
    DatabaseRunQueryService,
    DatabaseRunIndexEntry,
    DatabaseRunSnapshot,
    build_database_run_snapshot,
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
    AssignmentResolution,
    UnitSwitchAssignmentResult,
    UnitSwitchAssignmentWorkflow,
)
from domain.unit_switch_assignments import (
    AssignmentChangeRequiredError,
)
from domain.database_records import (
    MeasurementRecord,
    MeasurementWriteSpec,
    RunRecord,
    SwitchSpec,
    UnitSpec,
    utc_now,
)
from domain.effective_replacement_analysis import (
    build_effective_replacement_projection,
)
from domain.limit_profiles import LimitProfile
from infrastructure.database.load_metrics import (
    DatabaseLoadMetrics,
    DatabaseLoadSummary,
    activate_metrics,
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
    effective_projection: object | None = None
    unit_run_index: tuple[DatabaseRunIndexEntry, ...] = ()
    assignment_run_snapshots: tuple[DatabaseRunSnapshot, ...] = ()
    pairing_closed_assignment_ids: tuple[int, ...] = ()
    pairing_stopped_run_ids: tuple[int, ...] = ()
    load_operation_id: str = ""
    load_summary: DatabaseLoadSummary | None = None

    @property
    def run(self) -> RunRecord:
        return self.snapshot.run


class DatabasePrimaryRunWorkflow:
    """Keep Qt and hardware code independent from SQL and connection details."""

    def __init__(self, repositories, readiness_check, support_logger=None) -> None:
        self.repositories = repositories
        self._readiness_check = readiness_check
        self._support_logger = support_logger
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
        allow_new_hardware_pairing: bool = False,
    ) -> DatabaseRunContext:
        readiness = self.check_ready()
        if not getattr(readiness, "ready", False):
            raise DatabaseRunUnavailableError(readiness)
        started = started_at_utc or utc_now()
        pairing_conflict = self.assignments.requires_new_pairing(
            unit_spec, switch_spec
        )
        if (
            pairing_conflict is not None
            and not allow_new_hardware_pairing
            and not str(switch_replacement_reason or "").strip()
        ):
            raise pairing_conflict
        if pairing_conflict is not None and allow_new_hardware_pairing:
            unit = self.repositories.get_or_create(unit_spec)
            switch = self.repositories.get_or_create(switch_spec)
            assignment_spec = self.assignments.build_assignment_spec(
                unit,
                switch,
                installed_at_utc=started,
                installed_by=installed_by,
                initial_channel_map=initial_channel_map,
            )
            pending_run = self.lifecycle.prepare_start_spec(
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
            record, installed, closed, stopped = (
                self.repositories.create_next_with_fresh_pairing(
                    assignment_spec,
                    pending_run,
                    started,
                    installed_by,
                )
            )
            assignment = UnitSwitchAssignmentResult(
                unit,
                switch,
                installed,
                AssignmentResolution.FRESH_PAIRING,
                previous_assignment=closed[0] if closed else None,
                previous_assignments=closed,
                stopped_run_ids=stopped,
            )
        else:
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
        if pairing_conflict is not None and allow_new_hardware_pairing:
            context = self._context(record, assignment)
            return replace(
                context,
                pairing_closed_assignment_ids=tuple(
                    item.assignment_id for item in assignment.previous_assignments
                ),
                pairing_stopped_run_ids=assignment.stopped_run_ids,
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

    def load_for_unit(
        self, main_board_serial: str, run_number: int
    ) -> DatabaseRunContext:
        metrics = self._begin_load("unit_run_number")
        with activate_metrics(metrics):
            try:
                with self._read_session():
                    with self._stage(metrics, "database_readiness"):
                        self._require_ready()
                    with self._stage(metrics, "unit_run_lookup"):
                        unit = self.repositories.get_by_main_board_serial(
                            main_board_serial
                        )
                        if unit is None:
                            raise ValueError(
                                "No database unit matches that main-board serial."
                            )
                        run = self.repositories.get_for_unit_run_number(
                            unit.unit_id, run_number
                        )
                        if run is None:
                            available = self.repositories.list_for_unit(unit.unit_id)
                            numbers = ", ".join(
                                str(item.run_number) for item in available
                            ) or "none"
                            raise ValueError(
                                f"No Run {int(run_number)} was found for this unit. "
                                f"Available runs: {numbers}."
                            )
                    context = self._context(run, load_metrics=metrics)
                return self._complete_load(metrics, context)
            except Exception:
                self._fail_load(metrics)
                raise

    def load_run(
        self, run_id: int, *, load_source: str = "run_id"
    ) -> DatabaseRunContext:
        metrics = self._begin_load(load_source)
        with activate_metrics(metrics):
            try:
                with self._read_session():
                    with self._stage(metrics, "database_readiness"):
                        self._require_ready()
                    with self._stage(metrics, "run_lookup"):
                        run = self.repositories.get(run_id)
                        if run is None:
                            raise ValueError("Run was not found")
                    context = self._context(run, load_metrics=metrics)
                return self._complete_load(metrics, context)
            except Exception:
                self._fail_load(metrics)
                raise

    def refresh(self, run_id: int) -> DatabaseRunContext:
        return self.load_run(run_id, load_source="refresh")

    def list_for_unit(self, unit_id: int) -> tuple[DatabaseRunContext, ...]:
        with self._read_session():
            self._require_ready()
            return tuple(
                self._context(run)
                for run in self.repositories.list_for_unit(int(unit_id))
            )

    def list_for_assignment(
        self, assignment_id: int
    ) -> tuple[DatabaseRunContext, ...]:
        with self._read_session():
            self._require_ready()
            return tuple(
                self._context(run)
                for run in self.repositories.list_for_assignment(int(assignment_id))
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

    def void_run(
        self,
        run_id: int,
        *,
        voided_by: str,
        reason: str,
    ) -> DatabaseRunContext:
        """Permanently exclude a retained run and refresh authoritative state."""
        self._require_ready()
        run = self.lifecycle.void_run(
            run_id,
            voided_by=voided_by,
            reason=reason,
        )
        return self._context(run)

    def build_replacement_projection(
        self,
        run_id: int,
        profile,
        *,
        bottom_spare_count: int = 2,
        load_metrics: DatabaseLoadMetrics | None = None,
        context_run: RunRecord | None = None,
        routing_snapshot: AssignmentRoutingSnapshot | None = None,
    ):
        """Coordinate assignment data for the pure effective-state projector."""
        with self._read_session():
            with self._stage(load_metrics, "projection_source_data"):
                run = context_run or self.repositories.get(int(run_id))
                if run is None:
                    raise ValueError("Run was not found")
                routing = routing_snapshot or self.replacements.load_assignment(
                    run.assignment_id
                )
                runs, histories = self._load_assignment_measurements(
                    run.assignment_id,
                    load_metrics,
                )
        with self._stage(load_metrics, "projection_calculation"):
            return self._build_replacement_projection(
                run,
                runs,
                histories,
                routing,
                profile,
                bottom_spare_count,
            )

    def _load_assignment_measurements(
        self,
        assignment_id: int,
        load_metrics: DatabaseLoadMetrics | None = None,
    ) -> tuple[
        tuple[RunRecord, ...],
        dict[int, tuple[MeasurementRecord, ...]],
    ]:
        """Return all assignment runs and histories through one bulk query."""
        runs = self.repositories.list_for_assignment(int(assignment_id))
        run_ids = tuple(item.run_id for item in runs)
        histories = self.repositories.history_for_runs(run_ids)
        if load_metrics is not None:
            load_metrics.set_count("related_run_count", len(runs))
            load_metrics.set_count(
                "projection_measurement_row_count",
                sum(len(rows) for rows in histories.values()),
            )
            load_metrics.set_count(
                "projection_measurement_query_count",
                1 if run_ids else 0,
            )
        return runs, histories

    @staticmethod
    def _build_replacement_projection(
        run: RunRecord,
        runs: tuple[RunRecord, ...],
        histories: dict[int, tuple[MeasurementRecord, ...]],
        routing: AssignmentRoutingSnapshot,
        profile: LimitProfile,
        bottom_spare_count: int,
    ):
        return build_effective_replacement_projection(
            context_run=run,
            runs=runs,
            measurements_by_run=histories,
            # Rebuild the effective map inside the projection from the assignment
            # baseline plus only replacement records visible to the context run.
            # Passing today's map would leak later replacement activity into a
            # historical analysis.
            effective_channel_map={
                item.logical_channel: item.initial_physical_port
                for item in routing.channel_map
            },
            replacements=routing.replacement_history,
            active_spares=routing.active_spares,
            spare_event_ids=tuple(
                event.spare_event_id for event in routing.spare_history
            ),
            profile=profile,
            bottom_spare_count=bottom_spare_count,
        )

    def _require_ready(self) -> None:
        result = self.check_ready()
        if not getattr(result, "ready", False):
            raise DatabaseRunUnavailableError(result)

    def _context(
        self,
        run: RunRecord,
        assignment_result: UnitSwitchAssignmentResult | None = None,
        load_metrics: DatabaseLoadMetrics | None = None,
    ) -> DatabaseRunContext:
        with self._read_session():
            with self._stage(load_metrics, "hardware_identity"):
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
            with self._stage(load_metrics, "routing_snapshot"):
                routing = self.replacements.load_assignment(assignment.assignment_id)
            with self._stage(load_metrics, "projection_source_data"):
                runs, histories = self._load_assignment_measurements(
                    assignment.assignment_id,
                    load_metrics,
                )
            with self._stage(load_metrics, "measurement_snapshot"):
                assignment_snapshots = tuple(
                    build_database_run_snapshot(
                        related_run,
                        histories.get(related_run.run_id, ()),
                    )
                    for related_run in runs
                )
                snapshot = next(
                    (
                        item
                        for item in assignment_snapshots
                        if item.run.run_id == run.run_id
                    ),
                    None,
                )
                if snapshot is None:
                    raise ValueError("Run was not found in its assignment history")
            projection = None
            try:
                profile = LimitProfile.from_mapping(run.limit_snapshot)
                with self._stage(load_metrics, "projection_calculation"):
                    projection = self._build_replacement_projection(
                        run,
                        runs,
                        histories,
                        routing,
                        profile,
                        2,
                    )
            except (KeyError, TypeError, ValueError):
                pass
            with self._stage(load_metrics, "unit_run_index"):
                unit_run_index = tuple(
                    DatabaseRunIndexEntry.from_record(item)
                    for item in self.repositories.list_for_unit(unit.unit_id)
                )
            with self._stage(load_metrics, "replacement_analysis_history"):
                analysis_history = self.replacement_analyses.history_for_run(run.run_id)
                latest_analysis = analysis_history[0] if analysis_history else None
        context = DatabaseRunContext(
            unit=unit,
            switch=switch,
            assignment=assignment,
            snapshot=snapshot,
            routing=routing,
            replacement_analysis=latest_analysis,
            replacement_analysis_history=analysis_history,
            effective_projection=projection,
            unit_run_index=unit_run_index,
            assignment_run_snapshots=assignment_snapshots,
        )
        if load_metrics is not None:
            load_metrics.set_count(
                "measurement_history_count", len(snapshot.measurement_attempts)
            )
            load_metrics.set_count(
                "current_measurement_count", len(snapshot.measurements)
            )
            load_metrics.set_count(
                "replacement_history_count", len(routing.replacement_history)
            )
            load_metrics.set_count(
                "designated_spare_event_count", len(routing.spare_history)
            )
            load_metrics.set_count("active_spare_count", len(routing.active_spares))
            load_metrics.set_count("persisted_analysis_count", len(analysis_history))
            load_metrics.set_count(
                "persisted_recommendation_count",
                sum(len(item.recommendations) for item in analysis_history),
            )
        return context

    @contextmanager
    def _read_session(self):
        """Use a repository-provided load scope, with fake compatibility."""
        session = getattr(self.repositories, "read_session", None)
        if session is None:
            yield
            return
        with session():
            yield

    @staticmethod
    @contextmanager
    def _stage(metrics: DatabaseLoadMetrics | None, name: str):
        if metrics is None:
            yield
            return
        started = metrics.begin_stage(name)
        try:
            yield
        except Exception:
            metrics.failure_stage = str(name)
            raise
        finally:
            metrics.end_stage(name, started)

    def _begin_load(self, source: str) -> DatabaseLoadMetrics:
        metrics = DatabaseLoadMetrics(str(source))
        if self._support_logger is not None:
            self._support_logger.record(
                "workflow",
                "database.run_load_started",
                operation_id=metrics.operation_id,
                status="started",
                load_source=metrics.source,
            )
        return metrics

    def _complete_load(
        self, metrics: DatabaseLoadMetrics, context: DatabaseRunContext
    ) -> DatabaseRunContext:
        metrics.finish()
        summary = metrics.summary()
        self._record_load_event(
            "database.run_load_completed", metrics, summary, "info"
        )
        return replace(
            context,
            load_operation_id=summary.operation_id,
            load_summary=summary,
        )

    def _fail_load(self, metrics: DatabaseLoadMetrics) -> None:
        metrics.failure_stage = (
            metrics.failure_stage or metrics.current_stage or "unknown"
        )
        metrics.finish()
        summary = metrics.summary()
        self._record_load_event(
            "database.run_load_failed", metrics, summary, "error"
        )

    def _record_load_event(
        self,
        event: str,
        metrics: DatabaseLoadMetrics,
        summary: DatabaseLoadSummary,
        level: str,
    ) -> None:
        if self._support_logger is None:
            return
        fields = summary.support_fields()
        fields["status"] = "failed" if event.endswith("failed") else "success"
        self._support_logger.record(
            "workflow",
            event,
            level=level,
            operation_id=metrics.operation_id,
            **fields,
        )


__all__ = ["DatabasePrimaryRunWorkflow", "DatabaseRunContext"]
