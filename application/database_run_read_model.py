"""Shared database-backed projections for run display and analysis consumers."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from application.database_repositories import MeasurementRepository, RunRepository
from domain.coc_preparation import CocSourceRun
from domain.database_records import (
    MeasurementRecord as DatabaseMeasurementRecord,
    RunRecord,
)
from domain.measurement_attempts import MeasurementAttempt
from domain.models import MeasurementRecord
from domain.raw_export import format_raw_measurements
from domain.replacements import ReplacementReading, analyze_replacements
from domain.run_data import analyze_measurements_with_profile
from domain.run_status import (
    COMPLETION_INCOMPLETE,
    COMPLETION_INTERRUPTED,
    assess_run_status,
)


def _timestamp(value) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _measurement_context(run: RunRecord) -> tuple[str, tuple[int, int], tuple[int, int]]:
    hardware = run.measurement_hardware
    classification = str(hardware.get("measurement_classification") or "native")
    default_wavelengths = (1310, 1550) if run.wavelength_mode == "SM" else (850, 1300)
    raw_wavelengths = hardware.get("source_wavelengths_nm", default_wavelengths)
    raw_source_ids = hardware.get("source_ids", (0, 1))
    try:
        source_wavelengths = tuple(int(value) for value in raw_wavelengths)
        source_ids = tuple(int(value) for value in raw_source_ids)
    except (TypeError, ValueError):
        source_wavelengths = default_wavelengths
        source_ids = (0, 1)
    if len(source_wavelengths) != 2 or len(source_ids) != 2:
        source_wavelengths = default_wavelengths
        source_ids = (0, 1)
    return classification, source_wavelengths, source_ids


def _domain_measurement(
    run: RunRecord,
    record: DatabaseMeasurementRecord,
) -> MeasurementRecord:
    classification, source_wavelengths, source_ids = _measurement_context(run)
    return MeasurementRecord.from_wavelengths(
        record.logical_channel,
        {
            record.wavelength_1_nm: float(record.wavelength_1_il_db),
            record.wavelength_2_nm: float(record.wavelength_2_il_db),
        },
        physical_port=record.physical_port,
        reference_snapshot=dict(record.reference_snapshot),
        wavelength_mode=run.wavelength_mode,
        measurement_classification=classification,
        source_wavelengths_nm=source_wavelengths,
        source_ids=source_ids,
    )


def _history_attempts(
    run: RunRecord,
    records: Sequence[DatabaseMeasurementRecord],
) -> tuple[MeasurementAttempt, ...]:
    classification, source_wavelengths, source_ids = _measurement_context(run)
    attempt_ids = {
        (record.logical_channel, record.attempt_number): str(record.measurement_uuid)
        for record in records
    }
    attempts = []
    for record in records:
        losses = {
            record.wavelength_1_nm: float(record.wavelength_1_il_db),
            record.wavelength_2_nm: float(record.wavelength_2_il_db),
        }
        attempt_id = str(record.measurement_uuid)
        attempts.append(
            MeasurementAttempt(
                attempt_id=attempt_id,
                run_id=str(run.client_run_uuid),
                channel=record.logical_channel,
                physical_port=record.physical_port,
                attempt_number=record.attempt_number,
                loss_1310_db=losses.get(1310),
                loss_1550_db=losses.get(1550),
                accepted_at_utc=_timestamp(record.written_at_utc),
                operator_initials=record.written_by,
                write_context=(
                    "initial" if record.attempt_number == 1 else "retest"
                ),
                replaces_attempt_id=attempt_ids.get(
                    (record.logical_channel, record.attempt_number - 1)
                ),
                reference_snapshot=dict(record.reference_snapshot),
                wavelength_mode=run.wavelength_mode,
                losses_by_wavelength=losses,
                measurement_classification=classification,
                opm_wavelengths_nm=(
                    record.wavelength_1_nm,
                    record.wavelength_2_nm,
                ),
                source_wavelengths_nm=source_wavelengths,
                source_ids=source_ids,
            )
        )
    return tuple(attempts)


@dataclass(frozen=True)
class DatabaseRunSnapshot:
    """One consistent latest/history projection for every run-data consumer."""

    run: RunRecord
    measurements: tuple[MeasurementRecord, ...]
    measurement_attempts: tuple[MeasurementAttempt, ...]

    @property
    def metadata(self) -> Mapping[str, str]:
        values = {
            "Run number": str(self.run.run_number),
            "Tested by": self.run.tested_by,
            "Station number": (
                str(self.run.station_number)
                if self.run.station_number is not None
                else ""
            ),
            "Wavelength mode": self.run.wavelength_mode,
            "Operating band": self.run.operating_band,
            "Part number": self.run.part_number_snapshot or "",
            "completion_status": self.run.completion_status,
            "run_purpose": self.run.run_purpose,
            "analysis_status": self.run.analysis_status,
        }
        if self.run.front_panel_channel_count is not None:
            values["Front panel channel count"] = str(
                self.run.front_panel_channel_count
            )
        model = str(self.run.limit_snapshot.get("model") or "")
        if model:
            values["Switch model"] = model
        return values

    @property
    def criteria_snapshot(self) -> Mapping:
        return self.run.limit_snapshot

    def table_records(
        self,
        predicate: Callable[[MeasurementRecord], bool] | None = None,
    ) -> tuple[MeasurementRecord, ...]:
        if predicate is None:
            return self.measurements
        return tuple(record for record in self.measurements if predicate(record))

    def copy_raw_data(self) -> str:
        """Format every current reading, independent of any table predicate."""
        return format_raw_measurements(self.measurements)

    def comparison_records(self) -> dict[int, MeasurementRecord]:
        return {record.channel: record for record in self.measurements}

    def analysis(self, profile) -> dict:
        return analyze_measurements_with_profile(self.measurements, profile)

    def status(
        self,
        *,
        profile=None,
        planned_channels: Sequence[int] | None = None,
        replacement_analysis: Mapping[str, object] | None = None,
        composite_result=None,
        compatible_run_numbers: Sequence[int] = (),
    ):
        terminal_status = None
        if self.run.completion_status == "stopped":
            terminal_status = COMPLETION_INCOMPLETE
        elif self.run.completion_status == "failed":
            terminal_status = COMPLETION_INTERRUPTED
        return assess_run_status(
            self.measurements,
            planned_channels=planned_channels,
            active=self.run.completion_status == "in_progress",
            terminal_status=terminal_status,
            profile=profile,
            front_panel_channel_count=self.run.front_panel_channel_count,
            replacement_analysis=replacement_analysis,
            composite_result=composite_result,
            compatible_run_numbers=compatible_run_numbers,
            completed_at_utc=(
                _timestamp(self.run.run_ended_at_utc)
                if self.run.run_ended_at_utc is not None
                else ""
            ),
            legacy=False,
        )

    def coc_source(self) -> CocSourceRun:
        return CocSourceRun(
            run_number=self.run.run_number,
            source_path=None,
            source_identifier=f"database-run:{self.run.run_id}",
            measurements=self.measurements,
            metadata=self.metadata,
            criteria=dict(self.run.limit_snapshot),
            run_purpose=self.run.run_purpose,
        )

    def replacement_analysis(
        self,
        profile,
        *,
        minimum_improvement: float = 0.05,
        bottom_spare_count: int = 2,
    ) -> dict:
        count = self.run.front_panel_channel_count
        if count is None:
            raise ValueError("Front-panel channel count is required")
        production = tuple(
            record for record in self.measurements if record.channel <= count
        )
        extras = tuple(
            ReplacementReading(
                record.physical_port or record.channel,
                record.ordered_losses[0],
                record.ordered_losses[1],
            )
            for record in self.measurements
            if record.channel > count
        )
        optimization_limit = (
            profile.warning_above_db
            if profile.warning_enabled and profile.warning_above_db is not None
            else profile.fail_above_db
        )
        return analyze_replacements(
            production,
            extras,
            count,
            optimization_limit,
            minimum_improvement=minimum_improvement,
            bottom_spare_count=bottom_spare_count,
            fail_limit=profile.fail_above_db,
            model=profile.model,
            too_good_limit=profile.too_good_below_db,
            wavelengths=(
                (1310, 1550) if self.run.wavelength_mode == "SM" else (850, 1300)
            ),
        )


def build_database_run_snapshot(
    run: RunRecord,
    history_rows: Sequence[DatabaseMeasurementRecord],
) -> DatabaseRunSnapshot:
    """Build current/history projections from one accepted-attempt snapshot."""
    current_by_channel = {}
    for record in history_rows:
        prior = current_by_channel.get(record.logical_channel)
        if prior is None or record.attempt_number > prior.attempt_number:
            current_by_channel[record.logical_channel] = record
    current = tuple(
        _domain_measurement(run, current_by_channel[channel])
        for channel in sorted(current_by_channel)
    )
    return DatabaseRunSnapshot(run, current, _history_attempts(run, history_rows))


class DatabaseRunQueryService:
    """Load current and historical rows through repository contracts."""

    def __init__(
        self,
        run_repository: RunRepository,
        measurement_repository: MeasurementRepository,
    ) -> None:
        self._runs = run_repository
        self._measurements = measurement_repository

    def load(self, run_id: int) -> DatabaseRunSnapshot:
        run = self._runs.get(run_id)
        if run is None:
            raise ValueError("Run was not found")
        _current_rows, history_rows = self._measurements.snapshot_for_run(run_id)
        return build_database_run_snapshot(run, history_rows)

    def list_for_assignment(self, assignment_id: int) -> tuple[DatabaseRunSnapshot, ...]:
        return tuple(
            self.load(run.run_id)
            for run in self._runs.list_for_assignment(assignment_id)
        )

    def list_for_unit(self, unit_id: int) -> tuple[DatabaseRunSnapshot, ...]:
        return tuple(self.load(run.run_id) for run in self._runs.list_for_unit(unit_id))


__all__ = [
    "DatabaseRunQueryService",
    "DatabaseRunSnapshot",
    "build_database_run_snapshot",
]
