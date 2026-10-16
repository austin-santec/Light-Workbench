"""Read-only reporting over authoritative database run projections."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from application.database_run_read_model import (
    DatabaseRunQueryService,
    build_database_run_snapshot,
)
from domain.database_reporting import (
    AssignmentReportRow,
    ChannelReportRow,
    DatabaseReport,
    ReplacementReportRow,
    ReportFilters,
    ReportingSummary,
    RunReportRow,
)
from domain.limit_profiles import LimitProfile
from domain.run_status import RESULT_LABELS, RESULT_NOT_EVALUATED, RESULT_REVIEW


def _contains(candidate, expected) -> bool:
    return not expected or str(expected).casefold() in str(candidate or "").casefold()


def _equals(candidate, expected) -> bool:
    return not expected or str(candidate or "").casefold() == str(expected).casefold()


def _planned_channels(run) -> tuple[int, ...]:
    raw = run.measurement_hardware.get("planned_channels", ())
    try:
        values = tuple(dict.fromkeys(int(value) for value in raw))
    except (TypeError, ValueError):
        values = ()
    if values:
        return values
    if run.front_panel_channel_count:
        return tuple(range(1, int(run.front_panel_channel_count) + 1))
    return ()


class DatabaseReportingService:
    """Build reproducible report rows without exposing SQL to presentation code."""

    def __init__(self, repositories, queries: DatabaseRunQueryService | None = None):
        self._repositories = repositories
        self._queries = queries or DatabaseRunQueryService(repositories, repositories)

    def search(self, filters: ReportFilters | None = None) -> DatabaseReport:
        filters = filters or ReportFilters()
        all_runs = self._repositories.list_report_runs()
        assignments = self._repositories.list_report_assignments()
        units = self._repositories.list_report_units()
        switches = self._repositories.list_report_switches()
        assignments_by_id = {item.assignment_id: item for item in assignments}
        units_by_id = {item.unit_id: item for item in units}
        switches_by_id = {item.switch_id: item for item in switches}

        selected = []
        for run in all_runs:
            assignment = assignments_by_id.get(run.assignment_id)
            if assignment is None:
                continue
            unit = units_by_id.get(assignment.unit_id)
            switch = switches_by_id.get(assignment.switch_id)
            if unit is None or switch is None:
                continue
            if self._matches(run, unit, switch, filters):
                selected.append((run, assignment, unit, switch))

        histories = {}
        for measurement in self._repositories.report_measurements_for_runs(
            tuple(run.run_id for run, _assignment, _unit, _switch in selected)
        ):
            histories.setdefault(measurement.run_id, []).append(measurement)
        replacement_groups = {}
        for replacement in self._repositories.report_replacements_for_assignments(
            tuple(
                dict.fromkeys(
                    assignment.assignment_id
                    for _run, assignment, _unit, _switch in selected
                )
            )
        ):
            replacement_groups.setdefault(replacement.assignment_id, []).append(
                replacement
            )
        if not filters.include_all_records:
            selected_run_ids = {
                run.run_id for run, _assignment, _unit, _switch in selected
            }
            replacement_groups = {
                assignment_id: [
                    replacement
                    for replacement in replacements
                    if replacement.related_run_id in selected_run_ids
                ]
                for assignment_id, replacements in replacement_groups.items()
            }

        run_rows = []
        contexts = []
        for run, assignment, unit, switch in selected:
            snapshot = build_database_run_snapshot(
                run,
                histories.get(run.run_id, ()),
            )
            replacements = tuple(replacement_groups.get(assignment.assignment_id, ()))
            run_rows.append(self._run_row(run, unit, switch, snapshot, replacements))
            contexts.append((run, assignment, unit, switch, snapshot, replacements))

        run_rows.sort(key=lambda row: (row.started_at_utc, row.run_id), reverse=True)
        assignment_ids = {row.assignment_id for row in run_rows}
        assignment_rows = self._assignment_rows(
            assignment_ids,
            all_runs,
            assignments,
            units_by_id,
            switches_by_id,
        )
        replacement_rows = self._replacement_rows(contexts)
        summary = ReportingSummary(
            run_count=len(run_rows),
            current_channel_count=sum(row.current_channel_count for row in run_rows),
            attempt_count=sum(row.attempt_count for row in run_rows),
            retest_attempt_count=sum(row.retest_attempt_count for row in run_rows),
            retested_channel_count=sum(row.retested_channel_count for row in run_rows),
            replacement_count=len(replacement_rows),
        )
        return DatabaseReport(
            filters,
            tuple(assignment_rows),
            tuple(run_rows),
            tuple(replacement_rows),
            summary,
        )

    def channels_for_run(self, run_id: int) -> tuple[ChannelReportRow, ...]:
        snapshot = self._queries.load(run_id)
        assignment = self._repositories.get_assignment(snapshot.run.assignment_id)
        unit = self._repositories.get_unit(assignment.unit_id) if assignment else None
        latest = {
            attempt.channel: attempt.attempt_number
            for attempt in snapshot.measurement_attempts
        }
        rows = []
        for attempt in snapshot.measurement_attempts:
            first, second = attempt.opm_wavelengths_nm
            rows.append(
                ChannelReportRow(
                    run_id=snapshot.run.run_id,
                    run_number=snapshot.run.run_number,
                    main_board_serial=(unit.main_board_serial if unit else ""),
                    logical_channel=attempt.channel,
                    physical_port=attempt.physical_port,
                    attempt_number=attempt.attempt_number,
                    is_current=latest.get(attempt.channel) == attempt.attempt_number,
                    wavelength_1_nm=first,
                    wavelength_1_il_db=float(attempt.losses_by_wavelength[first]),
                    wavelength_2_nm=second,
                    wavelength_2_il_db=float(attempt.losses_by_wavelength[second]),
                    written_at_utc=attempt.accepted_at_utc,
                    written_by=attempt.operator_initials,
                )
            )
        return tuple(
            sorted(rows, key=lambda row: (row.logical_channel, row.attempt_number))
        )

    @staticmethod
    def _matches(run, unit, switch, filters: ReportFilters) -> bool:
        if not filters.include_all_records and not (
            run.run_purpose == "production"
            and run.analysis_status == "included"
            and run.superseded_by_run_id is None
        ):
            return False
        return all(
            (
                _contains(unit.main_board_serial, filters.main_board_serial),
                _contains(switch.switch_serial, filters.switch_serial),
                _equals(switch.switch_model, filters.switch_model),
                _equals(run.wavelength_mode, filters.wavelength_mode),
                _contains(run.tested_by, filters.tested_by),
                filters.station_number is None
                or run.station_number == filters.station_number,
                _equals(run.completion_status, filters.completion_status),
                _equals(run.run_purpose, filters.run_purpose),
                _equals(run.analysis_status, filters.analysis_status),
                filters.started_from_utc is None
                or run.run_started_at_utc >= filters.started_from_utc,
                filters.started_to_utc is None
                or run.run_started_at_utc <= filters.started_to_utc,
            )
        )

    def _run_row(self, run, unit, switch, snapshot, replacements) -> RunReportRow:
        attempts = snapshot.measurement_attempts
        counts = Counter(attempt.channel for attempt in attempts)
        retest_attempts = sum(max(0, count - 1) for count in counts.values())
        retested_channels = sum(1 for count in counts.values() if count > 1)
        profile = None
        try:
            profile = LimitProfile.from_mapping(run.limit_snapshot)
        except (KeyError, TypeError, ValueError):
            pass
        replacement_analysis = None
        if profile is not None and run.front_panel_channel_count:
            try:
                replacement_analysis = snapshot.replacement_analysis(profile)
            except (TypeError, ValueError):
                pass
        if profile is None:
            result_status = RESULT_NOT_EVALUATED
            result_label = RESULT_LABELS[result_status]
            failing_count = 0
            optimization_count = 0
        else:
            try:
                status = snapshot.status(
                    profile=profile,
                    planned_channels=_planned_channels(run),
                    replacement_analysis=replacement_analysis,
                )
                result_status = status.result_status
                result_label = status.result_label
                failing_count = len(status.failing_channels)
                optimization_count = len(status.optimization_channels)
            except (TypeError, ValueError):
                result_status = RESULT_REVIEW
                result_label = RESULT_LABELS[result_status]
                failing_count = 0
                optimization_count = 0
        return RunReportRow(
            run_id=run.run_id,
            assignment_id=run.assignment_id,
            unit_id=unit.unit_id,
            main_board_serial=unit.main_board_serial,
            part_number=run.part_number_snapshot or unit.part_number or "",
            switch_id=switch.switch_id,
            switch_serial=switch.switch_serial,
            switch_model=switch.switch_model,
            run_number=run.run_number,
            started_at_utc=run.run_started_at_utc,
            ended_at_utc=run.run_ended_at_utc,
            tested_by=run.tested_by,
            station_number=run.station_number,
            wavelength_mode=run.wavelength_mode,
            operating_band=run.operating_band,
            completion_status=run.completion_status,
            run_purpose=run.run_purpose,
            analysis_status=run.analysis_status,
            result_status=result_status,
            result_label=result_label,
            current_channel_count=len(snapshot.measurements),
            attempt_count=len(attempts),
            retest_attempt_count=retest_attempts,
            retested_channel_count=retested_channels,
            failing_channel_count=failing_count,
            optimization_channel_count=optimization_count,
            replacement_count=sum(
                1 for replacement in replacements if replacement.related_run_id == run.run_id
            ),
        )

    @staticmethod
    def _assignment_rows(
        included_ids,
        all_runs,
        assignments,
        units_by_id,
        switches_by_id,
    ) -> list[AssignmentReportRow]:
        run_counts = Counter(run.assignment_id for run in all_runs)
        rows = []
        for assignment in assignments:
            if assignment.assignment_id not in included_ids:
                continue
            unit = units_by_id.get(assignment.unit_id)
            switch = switches_by_id.get(assignment.switch_id)
            if unit is None or switch is None:
                continue
            rows.append(
                AssignmentReportRow(
                    assignment.assignment_id,
                    unit.unit_id,
                    unit.main_board_serial,
                    unit.part_number or "",
                    switch.switch_id,
                    switch.switch_serial,
                    switch.switch_model,
                    assignment.installed_at_utc,
                    assignment.installed_by,
                    assignment.removed_at_utc,
                    assignment.removed_by or "",
                    assignment.removal_reason or "",
                    run_counts[assignment.assignment_id],
                )
            )
        return sorted(
            rows,
            key=lambda row: (row.installed_at_utc, row.assignment_id),
            reverse=True,
        )

    def _replacement_rows(self, contexts) -> list[ReplacementReportRow]:
        unique = {}
        run_context = {
            run.run_id: (run, unit, switch, snapshot)
            for run, _assignment, unit, switch, snapshot, _replacements in contexts
        }
        for _run, _assignment, unit, switch, _snapshot, replacements in contexts:
            for replacement in replacements:
                if replacement.replacement_id in unique:
                    continue
                related = run_context.get(replacement.related_run_id)
                related_number = related[0].run_number if related else None
                outcome = self._replacement_outcome(replacement, related)
                unique[replacement.replacement_id] = ReplacementReportRow(
                    replacement.replacement_id,
                    replacement.assignment_id,
                    unit.main_board_serial,
                    switch.switch_serial,
                    switch.switch_model,
                    replacement.logical_channel,
                    replacement.previous_physical_port,
                    replacement.replacement_physical_port,
                    replacement.reason,
                    replacement.replaced_by,
                    replacement.replaced_at_utc,
                    related_number,
                    outcome,
                )
        return sorted(
            unique.values(),
            key=lambda row: (row.replaced_at_utc, row.replacement_id),
            reverse=True,
        )

    @staticmethod
    def _replacement_outcome(replacement, related) -> str:
        if related is None:
            return "Not linked to a filtered run"
        run, _unit, _switch, snapshot = related
        measurement = next(
            (
                item
                for item in snapshot.measurements
                if item.channel == replacement.logical_channel
            ),
            None,
        )
        if measurement is None:
            return "No accepted reading"
        try:
            assessment = LimitProfile.from_mapping(run.limit_snapshot).classify(
                *measurement.ordered_losses,
                measurement.opm_wavelengths_nm,
            )
        except (KeyError, TypeError, ValueError):
            return "Not evaluated"
        if assessment.is_fail:
            return "Failed"
        if assessment.is_too_good:
            return "Review required"
        if assessment.is_optimization:
            return "Pass; optimization available"
        return "Pass"


__all__ = ["DatabaseReportingService"]
