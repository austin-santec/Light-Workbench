"""Database-neutral records and CSV formatting for read-only reporting."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ReportFilters:
    """Optional report filters; normal metrics are production-safe by default."""

    main_board_serial: str = ""
    switch_serial: str = ""
    switch_model: str = ""
    wavelength_mode: str = ""
    tested_by: str = ""
    station_number: int | None = None
    started_from_utc: datetime | None = None
    started_to_utc: datetime | None = None
    completion_status: str = ""
    run_purpose: str = ""
    analysis_status: str = ""
    include_all_records: bool = False


@dataclass(frozen=True)
class AssignmentReportRow:
    assignment_id: int
    unit_id: int
    main_board_serial: str
    part_number: str
    switch_id: int
    switch_serial: str
    switch_model: str
    installed_at_utc: datetime
    installed_by: str
    removed_at_utc: datetime | None
    removed_by: str
    removal_reason: str
    run_count: int


@dataclass(frozen=True)
class RunReportRow:
    run_id: int
    assignment_id: int
    unit_id: int
    main_board_serial: str
    part_number: str
    switch_id: int
    switch_serial: str
    switch_model: str
    run_number: int
    started_at_utc: datetime
    ended_at_utc: datetime | None
    tested_by: str
    station_number: int | None
    wavelength_mode: str
    operating_band: str
    completion_status: str
    run_purpose: str
    analysis_status: str
    result_status: str
    result_label: str
    current_channel_count: int
    attempt_count: int
    retest_attempt_count: int
    retested_channel_count: int
    failing_channel_count: int
    optimization_channel_count: int
    replacement_count: int


@dataclass(frozen=True)
class ChannelReportRow:
    run_id: int
    run_number: int
    main_board_serial: str
    logical_channel: int
    physical_port: int | None
    attempt_number: int
    is_current: bool
    wavelength_1_nm: int
    wavelength_1_il_db: float
    wavelength_2_nm: int
    wavelength_2_il_db: float
    written_at_utc: str
    written_by: str


@dataclass(frozen=True)
class ReplacementReportRow:
    replacement_id: int
    assignment_id: int
    main_board_serial: str
    switch_serial: str
    switch_model: str
    logical_channel: int
    previous_physical_port: int
    replacement_physical_port: int
    reason: str
    replaced_by: str
    replaced_at_utc: datetime
    related_run_number: int | None
    notes: str
    outcome: str


@dataclass(frozen=True)
class ReportingSummary:
    run_count: int
    current_channel_count: int
    attempt_count: int
    retest_attempt_count: int
    retested_channel_count: int
    replacement_count: int

    @property
    def retest_rate_percent(self) -> float:
        if not self.attempt_count:
            return 0.0
        return 100.0 * self.retest_attempt_count / self.attempt_count


@dataclass(frozen=True)
class DatabaseReport:
    filters: ReportFilters
    assignments: tuple[AssignmentReportRow, ...]
    runs: tuple[RunReportRow, ...]
    replacements: tuple[ReplacementReportRow, ...]
    summary: ReportingSummary


def format_report_csv(headers, rows) -> str:
    """Return deterministic UTF-8-ready CSV text from application report rows."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(tuple(headers))
    writer.writerows(tuple(tuple(value for value in row) for row in rows))
    return output.getvalue()


__all__ = [
    "AssignmentReportRow",
    "ChannelReportRow",
    "DatabaseReport",
    "ReplacementReportRow",
    "ReportFilters",
    "ReportingSummary",
    "RunReportRow",
    "format_report_csv",
]
