"""Parameterized SQL Server implementations of database repository contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
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
    require_utc,
)
from infrastructure.database.connection import DatabaseConnectionFactory


def _json(value) -> str:
    serializable = dict(value) if isinstance(value, Mapping) else value
    return json.dumps(serializable, sort_keys=True, separators=(",", ":"))


def _mapping(value: str) -> dict:
    loaded = json.loads(value)
    if not isinstance(loaded, dict):
        raise ValueError("Stored JSON snapshot must be an object")
    return loaded


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SqlRepositories:
    """One SQL-backed provider satisfying all approved repository protocols."""

    def __init__(self, factory: DatabaseConnectionFactory) -> None:
        self._factory = factory

    def get_or_create(self, spec):
        if isinstance(spec, UnitSpec):
            return self._get_or_create_unit(spec)
        if isinstance(spec, SwitchSpec):
            return self._get_or_create_switch(spec)
        raise TypeError("get_or_create requires UnitSpec or SwitchSpec")

    def _get_or_create_unit(self, spec: UnitSpec) -> UnitRecord:
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                "SELECT unit_id FROM dbo.UNITS WHERE main_board_serial = ?",
                spec.main_board_serial,
            ).fetchone()
            if row is None:
                unit_id = cursor.execute(
                    """
                    INSERT INTO dbo.UNITS (
                        main_board_serial, part_number, front_panel_channel_count,
                        unit_model, notes
                    ) OUTPUT INSERTED.unit_id VALUES (?, ?, ?, ?, ?)
                    """,
                    spec.main_board_serial,
                    spec.part_number,
                    spec.front_panel_channel_count,
                    spec.unit_model,
                    spec.notes,
                ).fetchone()[0]
            else:
                unit_id = row[0]
                cursor.execute(
                    """
                    UPDATE dbo.UNITS SET
                        part_number = ?, front_panel_channel_count = ?,
                        unit_model = ?, notes = ?, updated_at_utc = SYSUTCDATETIME()
                    WHERE unit_id = ?
                    """,
                    spec.part_number,
                    spec.front_panel_channel_count,
                    spec.unit_model,
                    spec.notes,
                    unit_id,
                )
            return self._unit_by_id(cursor, unit_id)

    def _get_or_create_switch(self, spec: SwitchSpec) -> SwitchRecord:
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                "SELECT switch_id FROM dbo.SWITCHES WHERE switch_serial = ?",
                spec.switch_serial,
            ).fetchone()
            if row is None:
                switch_id = cursor.execute(
                    """
                    INSERT INTO dbo.SWITCHES (
                        switch_serial, switch_model, firmware_version,
                        physical_channel_count, notes
                    ) OUTPUT INSERTED.switch_id VALUES (?, ?, ?, ?, ?)
                    """,
                    spec.switch_serial,
                    spec.switch_model,
                    spec.firmware_version,
                    spec.physical_channel_count,
                    spec.notes,
                ).fetchone()[0]
            else:
                switch_id = row[0]
                cursor.execute(
                    """
                    UPDATE dbo.SWITCHES SET
                        switch_model = ?, firmware_version = ?,
                        physical_channel_count = ?, notes = ?,
                        updated_at_utc = SYSUTCDATETIME()
                    WHERE switch_id = ?
                    """,
                    spec.switch_model,
                    spec.firmware_version,
                    spec.physical_channel_count,
                    spec.notes,
                    switch_id,
                )
            return self._switch_by_id(cursor, switch_id)

    def get_unit(self, unit_id: int) -> UnitRecord | None:
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                """
                SELECT unit_id, main_board_serial, part_number,
                    front_panel_channel_count, unit_model, notes
                FROM dbo.UNITS WHERE unit_id = ?
                """,
                int(unit_id),
            ).fetchone()
            return UnitRecord(*row) if row is not None else None

    def get_by_main_board_serial(self, main_board_serial: str) -> UnitRecord | None:
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                """
                SELECT unit_id, main_board_serial, part_number,
                    front_panel_channel_count, unit_model, notes
                FROM dbo.UNITS WHERE main_board_serial = ?
                """,
                str(main_board_serial or "").strip(),
            ).fetchone()
            return UnitRecord(*row) if row is not None else None

    def get_switch(self, switch_id: int) -> SwitchRecord | None:
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                """
                SELECT switch_id, switch_serial, switch_model,
                    physical_channel_count, firmware_version, notes
                FROM dbo.SWITCHES WHERE switch_id = ?
                """,
                int(switch_id),
            ).fetchone()
            return SwitchRecord(*row) if row is not None else None

    def get_by_serial(self, switch_serial: str) -> SwitchRecord | None:
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                """
                SELECT switch_id, switch_serial, switch_model,
                    physical_channel_count, firmware_version, notes
                FROM dbo.SWITCHES WHERE switch_serial = ?
                """,
                str(switch_serial or "").strip(),
            ).fetchone()
            return SwitchRecord(*row) if row is not None else None

    def get_assignment(self, assignment_id: int) -> AssignmentRecord | None:
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                self._ASSIGNMENT_SELECT
                + " WHERE assignment.assignment_id = ?",
                int(assignment_id),
            ).fetchone()
            return self._assignment(row) if row is not None else None

    def get_active(self, unit_id: int) -> AssignmentRecord | None:
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                self._ASSIGNMENT_SELECT
                + " WHERE assignment.unit_id = ? AND assignment.removed_at_utc IS NULL",
                unit_id,
            ).fetchone()
            return self._assignment(row) if row is not None else None

    def get_active_for_switch(self, switch_id: int) -> AssignmentRecord | None:
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                self._ASSIGNMENT_SELECT
                + " WHERE assignment.switch_id = ? "
                "AND assignment.removed_at_utc IS NULL",
                switch_id,
            ).fetchone()
            return self._assignment(row) if row is not None else None

    def history_for_unit(self, unit_id: int) -> tuple[AssignmentRecord, ...]:
        with self._factory.transaction() as cursor:
            rows = cursor.execute(
                self._ASSIGNMENT_SELECT
                + " WHERE assignment.unit_id = ? "
                "ORDER BY assignment.installed_at_utc, assignment.assignment_id",
                unit_id,
            ).fetchall()
            return tuple(self._assignment(row) for row in rows)

    def install(self, spec: AssignmentSpec) -> AssignmentRecord:
        channel_map = {str(key): value for key, value in spec.initial_channel_map.items()}
        with self._factory.transaction() as cursor:
            assignment_id = cursor.execute(
                """
                INSERT INTO dbo.UNIT_SWITCH_ASSIGNMENTS (
                    unit_id, switch_id, installed_at_utc, installed_by,
                    initial_channel_map_json, notes
                ) OUTPUT INSERTED.assignment_id VALUES (?, ?, ?, ?, ?, ?)
                """,
                spec.unit_id,
                spec.switch_id,
                spec.installed_at_utc,
                spec.installed_by,
                _json(channel_map),
                spec.notes,
            ).fetchone()[0]
            row = cursor.execute(
                self._ASSIGNMENT_SELECT + " WHERE assignment.assignment_id = ?",
                assignment_id,
            ).fetchone()
            return self._assignment(row)

    def remove(
        self,
        assignment_id: int,
        removed_at_utc: datetime,
        removed_by: str,
        removal_reason: str,
    ) -> AssignmentRecord:
        with self._factory.transaction() as cursor:
            changed = cursor.execute(
                """
                UPDATE dbo.UNIT_SWITCH_ASSIGNMENTS SET
                    removed_at_utc = ?, removed_by = ?, removal_reason = ?,
                    updated_at_utc = SYSUTCDATETIME()
                WHERE assignment_id = ? AND removed_at_utc IS NULL
                """,
                removed_at_utc,
                removed_by,
                removal_reason,
                assignment_id,
            ).rowcount
            if changed != 1:
                raise ValueError("Active assignment was not found")
            row = cursor.execute(
                self._ASSIGNMENT_SELECT + " WHERE assignment.assignment_id = ?",
                assignment_id,
            ).fetchone()
            return self._assignment(row)

    def replace_active(
        self,
        assignment_id: int,
        replacement: AssignmentSpec,
        removed_at_utc: datetime,
        removed_by: str,
        removal_reason: str,
    ) -> AssignmentRecord:
        channel_map = {
            str(key): value for key, value in replacement.initial_channel_map.items()
        }
        with self._factory.transaction() as cursor:
            current = cursor.execute(
                """
                SELECT assignment_id, unit_id, switch_id, installed_at_utc
                FROM dbo.UNIT_SWITCH_ASSIGNMENTS WITH (UPDLOCK, HOLDLOCK)
                WHERE assignment_id = ? AND removed_at_utc IS NULL
                """,
                assignment_id,
            ).fetchone()
            if current is None:
                raise ValueError("Active assignment was not found")
            if int(current[1]) != replacement.unit_id:
                raise ValueError("A replacement assignment must belong to the same unit")
            if int(current[2]) == replacement.switch_id:
                raise ValueError("A replacement assignment must use a different switch")
            if removed_at_utc < _utc(current[3]):
                raise ValueError("Removal time cannot precede installation")
            conflict = cursor.execute(
                """
                SELECT assignment_id
                FROM dbo.UNIT_SWITCH_ASSIGNMENTS WITH (UPDLOCK, HOLDLOCK)
                WHERE switch_id = ? AND removed_at_utc IS NULL
                """,
                replacement.switch_id,
            ).fetchone()
            if conflict is not None:
                raise ValueError("The replacement switch already has an active assignment")

            cursor.execute(
                """
                UPDATE dbo.UNIT_SWITCH_ASSIGNMENTS SET
                    removed_at_utc = ?, removed_by = ?, removal_reason = ?,
                    updated_at_utc = SYSUTCDATETIME()
                WHERE assignment_id = ?
                """,
                removed_at_utc,
                removed_by,
                removal_reason,
                assignment_id,
            )
            new_id = cursor.execute(
                """
                INSERT INTO dbo.UNIT_SWITCH_ASSIGNMENTS (
                    unit_id, switch_id, installed_at_utc, installed_by,
                    initial_channel_map_json, notes
                ) OUTPUT INSERTED.assignment_id VALUES (?, ?, ?, ?, ?, ?)
                """,
                replacement.unit_id,
                replacement.switch_id,
                replacement.installed_at_utc,
                replacement.installed_by,
                _json(channel_map),
                replacement.notes,
            ).fetchone()[0]
            row = cursor.execute(
                self._ASSIGNMENT_SELECT + " WHERE assignment.assignment_id = ?",
                new_id,
            ).fetchone()
            return self._assignment(row)

    def create(self, spec: RunSpec) -> RunRecord:
        try:
            with self._factory.transaction() as cursor:
                row = cursor.execute(
                    self._RUN_SELECT + " WHERE run.client_run_uuid = ?",
                    str(spec.client_run_uuid),
                ).fetchone()
                if row is not None:
                    return self._run(row)
                return self._insert_run(cursor, spec)
        except Exception:
            existing = self.get_by_uuid(spec.client_run_uuid)
            if existing is not None:
                return existing
            raise

    def create_next(self, spec: RunStartSpec) -> RunRecord:
        """Allocate a per-unit run number and insert the run atomically."""
        try:
            with self._factory.transaction() as cursor:
                row = cursor.execute(
                    self._RUN_SELECT + " WHERE run.client_run_uuid = ?",
                    str(spec.client_run_uuid),
                ).fetchone()
                if row is not None:
                    return self._run(row)

                assignment = cursor.execute(
                    """
                    SELECT unit.unit_id
                    FROM dbo.UNITS AS unit WITH (UPDLOCK, HOLDLOCK)
                    INNER JOIN dbo.UNIT_SWITCH_ASSIGNMENTS AS assignment
                        ON assignment.unit_id = unit.unit_id
                    WHERE assignment.assignment_id = ?
                        AND assignment.removed_at_utc IS NULL
                    """,
                    spec.assignment_id,
                ).fetchone()
                if assignment is None:
                    raise ValueError("A new run requires an active assignment")
                unit_id = assignment[0]
                run_number = cursor.execute(
                    """
                    SELECT COALESCE(MAX(run.run_number), 0) + 1
                    FROM dbo.IL_RUNS AS run
                    INNER JOIN dbo.UNIT_SWITCH_ASSIGNMENTS AS assignment
                        ON assignment.assignment_id = run.assignment_id
                    WHERE assignment.unit_id = ?
                    """,
                    unit_id,
                ).fetchone()[0]
                return self._insert_run(cursor, spec.with_run_number(run_number))
        except Exception:
            existing = self.get_by_uuid(spec.client_run_uuid)
            if existing is not None:
                return existing
            raise

    def _insert_run(self, cursor, spec: RunSpec) -> RunRecord:
        run_id = cursor.execute(
                """
                INSERT INTO dbo.IL_RUNS (
                    assignment_id, run_number, client_run_uuid,
                    run_started_at_utc, tested_by, wavelength_mode,
                    operating_band, application_version, run_purpose,
                    analysis_status, analysis_exclusion_reason,
                    part_number_snapshot, front_panel_channel_count,
                    station_number,
                    measurement_hardware_json, limit_snapshot_json, notes
                ) OUTPUT INSERTED.run_id
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                spec.assignment_id,
                spec.run_number,
                str(spec.client_run_uuid),
                spec.run_started_at_utc,
                spec.tested_by,
                spec.wavelength_mode,
                spec.operating_band,
                spec.application_version,
                spec.run_purpose,
                spec.analysis_status,
                spec.analysis_exclusion_reason,
                spec.part_number_snapshot,
                spec.front_panel_channel_count,
                spec.station_number,
                _json(spec.measurement_hardware),
                _json(spec.limit_snapshot),
                spec.notes,
            ).fetchone()[0]
        return self._run_by_id(cursor, run_id)

    def get(self, run_id: int) -> RunRecord | None:
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                self._RUN_SELECT + " WHERE run.run_id = ?", int(run_id)
            ).fetchone()
            return self._run(row) if row is not None else None

    def get_by_uuid(self, client_run_uuid: UUID) -> RunRecord | None:
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                self._RUN_SELECT + " WHERE run.client_run_uuid = ?",
                str(client_run_uuid),
            ).fetchone()
            return self._run(row) if row is not None else None

    def list_for_assignment(self, assignment_id: int) -> tuple[RunRecord, ...]:
        with self._factory.transaction() as cursor:
            rows = cursor.execute(
                self._RUN_SELECT
                + " WHERE run.assignment_id = ? ORDER BY run.run_number, run.run_id",
                int(assignment_id),
            ).fetchall()
            return tuple(self._run(row) for row in rows)

    def list_report_runs(self) -> tuple[RunRecord, ...]:
        with self._factory.transaction() as cursor:
            rows = cursor.execute(
                self._RUN_SELECT + " ORDER BY run.run_started_at_utc, run.run_id"
            ).fetchall()
            return tuple(self._run(row) for row in rows)

    def list_report_assignments(self) -> tuple[AssignmentRecord, ...]:
        with self._factory.transaction() as cursor:
            rows = cursor.execute(
                self._ASSIGNMENT_SELECT
                + " ORDER BY assignment.installed_at_utc, assignment.assignment_id"
            ).fetchall()
            return tuple(self._assignment(row) for row in rows)

    def list_report_units(self) -> tuple[UnitRecord, ...]:
        with self._factory.transaction() as cursor:
            rows = cursor.execute(
                """
                SELECT unit_id, main_board_serial, part_number,
                    front_panel_channel_count, unit_model, notes
                FROM dbo.UNITS ORDER BY unit_id
                """
            ).fetchall()
            return tuple(UnitRecord(*row) for row in rows)

    def list_report_switches(self) -> tuple[SwitchRecord, ...]:
        with self._factory.transaction() as cursor:
            rows = cursor.execute(
                """
                SELECT switch_id, switch_serial, switch_model,
                    physical_channel_count, firmware_version, notes
                FROM dbo.SWITCHES ORDER BY switch_id
                """
            ).fetchall()
            return tuple(SwitchRecord(*row) for row in rows)

    def report_measurements_for_runs(
        self, run_ids: tuple[int, ...]
    ) -> tuple[MeasurementRecord, ...]:
        rows = self._report_rows_for_ids(
            self._MEASUREMENT_SELECT,
            "measurement.run_id",
            run_ids,
            "measurement.measurement_id",
        )
        return tuple(self._measurement(row) for row in rows)

    def report_replacements_for_assignments(
        self, assignment_ids: tuple[int, ...]
    ) -> tuple[ReplacementRecord, ...]:
        rows = self._report_rows_for_ids(
            self._REPLACEMENT_SELECT,
            "replacement.assignment_id",
            assignment_ids,
            "replacement.replacement_id",
        )
        return tuple(self._replacement(row) for row in rows)

    def _report_rows_for_ids(self, select_sql, id_column, identifiers, order_column):
        values = tuple(dict.fromkeys(int(value) for value in identifiers))
        if not values:
            return ()
        rows = []
        with self._factory.transaction() as cursor:
            # SQL Server accepts at most 2,100 parameters per statement.
            for start in range(0, len(values), 1000):
                chunk = values[start : start + 1000]
                placeholders = ", ".join("?" for _value in chunk)
                rows.extend(
                    cursor.execute(
                        select_sql
                        + f" WHERE {id_column} IN ({placeholders})"
                        + f" ORDER BY {order_column}",
                        *chunk,
                    ).fetchall()
                )
        return tuple(rows)

    def list_for_unit(self, unit_id: int) -> tuple[RunRecord, ...]:
        with self._factory.transaction() as cursor:
            rows = cursor.execute(
                self._RUN_SELECT
                + " INNER JOIN dbo.UNIT_SWITCH_ASSIGNMENTS AS lookup_assignment "
                "ON lookup_assignment.assignment_id = run.assignment_id "
                "WHERE lookup_assignment.unit_id = ? "
                "ORDER BY run.run_number, run.run_id",
                int(unit_id),
            ).fetchall()
            return tuple(self._run(row) for row in rows)

    def get_for_unit_run_number(
        self, unit_id: int, run_number: int
    ) -> RunRecord | None:
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                self._RUN_SELECT
                + " INNER JOIN dbo.UNIT_SWITCH_ASSIGNMENTS AS lookup_assignment "
                "ON lookup_assignment.assignment_id = run.assignment_id "
                "WHERE lookup_assignment.unit_id = ? AND run.run_number = ?",
                int(unit_id),
                int(run_number),
            ).fetchone()
            return self._run(row) if row is not None else None

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
        ended = require_utc(run_ended_at_utc, "Run end time")
        with self._factory.transaction() as cursor:
            current_row = cursor.execute(
                self._RUN_SELECT + " WHERE run.run_id = ?", int(run_id)
            ).fetchone()
            if current_row is None:
                raise ValueError("Run was not found")
            current = self._run(current_row)
            if current.completion_status != "in_progress":
                if current.completion_status == completion_status:
                    return current
                raise ValueError("Run already has a different terminal status")
            if ended < current.run_started_at_utc:
                raise ValueError("Run end time cannot precede its start")
            if analysis_status not in {None, "pending", "included", "excluded", "superseded"}:
                raise ValueError("Invalid analysis status")
            if analysis_status == "excluded" and not str(analysis_exclusion_reason or "").strip():
                raise ValueError("Excluded runs require an analysis exclusion reason")
            changed = cursor.execute(
                """
                UPDATE dbo.IL_RUNS SET completion_status = ?, run_ended_at_utc = ?,
                    analysis_status = COALESCE(?, analysis_status),
                    analysis_exclusion_reason = CASE
                        WHEN ? = 'excluded' THEN ?
                        WHEN ? IS NULL THEN analysis_exclusion_reason
                        ELSE NULL
                    END,
                    updated_at_utc = SYSUTCDATETIME()
                WHERE run_id = ? AND completion_status = 'in_progress'
                """,
                completion_status,
                ended,
                analysis_status,
                analysis_status,
                analysis_exclusion_reason,
                analysis_status,
                run_id,
            ).rowcount
            if changed != 1:
                raise ValueError("In-progress run was not found")
            return self._run_by_id(cursor, run_id)

    def resume(self, run_id: int) -> RunRecord:
        with self._factory.transaction() as cursor:
            current_row = cursor.execute(
                self._RUN_SELECT + " WHERE run.run_id = ?", int(run_id)
            ).fetchone()
            if current_row is None:
                raise ValueError("Run was not found")
            current = self._run(current_row)
            if current.completion_status == "in_progress":
                return current
            changed = cursor.execute(
                """
                UPDATE dbo.IL_RUNS SET completion_status = 'in_progress',
                    run_ended_at_utc = NULL, updated_at_utc = SYSUTCDATETIME()
                WHERE run_id = ? AND completion_status IN ('complete', 'stopped', 'failed')
                """,
                int(run_id),
            ).rowcount
            if changed != 1:
                raise ValueError("Closed run could not be resumed")
            return self._run_by_id(cursor, run_id)

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
        elif superseded_by_run_id is not None:
            raise ValueError("Only superseded runs may identify a superseding run")
        reason = str(exclusion_reason).strip() if analysis_status == "excluded" else None
        target = int(superseded_by_run_id) if analysis_status == "superseded" else None
        with self._factory.transaction() as cursor:
            changed = cursor.execute(
                """
                UPDATE dbo.IL_RUNS SET analysis_status = ?,
                    analysis_exclusion_reason = ?, superseded_by_run_id = ?,
                    updated_at_utc = SYSUTCDATETIME()
                WHERE run_id = ?
                """,
                analysis_status,
                reason,
                target,
                int(run_id),
            ).rowcount
            if changed != 1:
                raise ValueError("Run was not found")
            return self._run_by_id(cursor, run_id)

    def find_stale_in_progress(self, before_utc: datetime) -> tuple[RunRecord, ...]:
        with self._factory.transaction() as cursor:
            rows = cursor.execute(
                self._RUN_SELECT
                + " WHERE run.completion_status = 'in_progress' "
                "AND run.run_started_at_utc < ? ORDER BY run.run_started_at_utc",
                before_utc,
            ).fetchall()
            return tuple(self._run(row) for row in rows)

    def append_attempt(self, spec: MeasurementSpec) -> MeasurementRecord:
        try:
            with self._factory.transaction() as cursor:
                existing = self._measurement_by_uuid(cursor, spec.measurement_uuid)
                if existing is not None:
                    return existing
                self._validate_measurement_run(cursor, spec)
                return self._insert_measurement(cursor, spec)
        except Exception:
            existing = self.get_measurement_by_uuid(spec.measurement_uuid)
            if existing is not None:
                return existing
            raise

    def append_next(self, spec: MeasurementWriteSpec) -> MeasurementRecord:
        """Allocate the next channel attempt and insert both wavelengths atomically."""
        try:
            with self._factory.transaction() as cursor:
                existing = self._measurement_by_uuid(cursor, spec.measurement_uuid)
                if existing is not None:
                    return existing
                self._validate_measurement_run(cursor, spec)
                attempt_number = cursor.execute(
                    """
                    SELECT COALESCE(MAX(attempt_number), 0) + 1
                    FROM dbo.IL_MEASUREMENTS
                    WHERE run_id = ? AND logical_channel = ?
                    """,
                    spec.run_id,
                    spec.logical_channel,
                ).fetchone()[0]
                return self._insert_measurement(
                    cursor,
                    spec.with_attempt_number(attempt_number),
                )
        except Exception:
            existing = self.get_measurement_by_uuid(spec.measurement_uuid)
            if existing is not None:
                return existing
            raise

    def get_measurement_by_uuid(self, measurement_uuid: UUID) -> MeasurementRecord | None:
        with self._factory.transaction() as cursor:
            return self._measurement_by_uuid(cursor, measurement_uuid)

    def _measurement_by_uuid(self, cursor, measurement_uuid: UUID):
        row = cursor.execute(
            self._MEASUREMENT_SELECT + " WHERE measurement.measurement_uuid = ?",
            str(measurement_uuid),
        ).fetchone()
        return self._measurement(row) if row is not None else None

    def _validate_measurement_run(self, cursor, spec) -> None:
        row = cursor.execute(
            """
            SELECT wavelength_mode, completion_status
            FROM dbo.IL_RUNS WITH (UPDLOCK, HOLDLOCK)
            WHERE run_id = ?
            """,
            spec.run_id,
        ).fetchone()
        if row is None:
            raise ValueError("Measurement run does not exist")
        mode, completion_status = row
        if completion_status != "in_progress":
            raise ValueError("Measurements may only be written to an in-progress run")
        expected = (1310, 1550) if mode == "SM" else (850, 1300)
        actual = (int(spec.wavelength_1_nm), int(spec.wavelength_2_nm))
        if actual != expected:
            raise ValueError(
                f"{mode} measurements require wavelengths "
                f"{expected[0]} nm and {expected[1]} nm"
            )

    def _insert_measurement(self, cursor, spec: MeasurementSpec) -> MeasurementRecord:
        measurement_id = cursor.execute(
            """
            INSERT INTO dbo.IL_MEASUREMENTS (
                measurement_uuid, run_id, logical_channel, physical_port,
                attempt_number, wavelength_1_nm, wavelength_1_il_db,
                wavelength_2_nm, wavelength_2_il_db,
                reference_snapshot_json, written_at_utc, written_by
            ) OUTPUT INSERTED.measurement_id
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            str(spec.measurement_uuid),
            spec.run_id,
            spec.logical_channel,
            spec.physical_port,
            spec.attempt_number,
            spec.wavelength_1_nm,
            spec.wavelength_1_il_db,
            spec.wavelength_2_nm,
            spec.wavelength_2_il_db,
            _json(spec.reference_snapshot),
            spec.written_at_utc,
            spec.written_by,
        ).fetchone()[0]
        row = cursor.execute(
            self._MEASUREMENT_SELECT + " WHERE measurement.measurement_id = ?",
            measurement_id,
        ).fetchone()
        return self._measurement(row)

    def current_for_run(self, run_id: int) -> tuple[MeasurementRecord, ...]:
        with self._factory.transaction() as cursor:
            rows = cursor.execute(
                self._CURRENT_MEASUREMENT_SELECT
                + " WHERE measurement.run_id = ? ORDER BY measurement.logical_channel",
                run_id,
            ).fetchall()
            return tuple(self._measurement(row) for row in rows)

    def history_for_run(self, run_id: int) -> tuple[MeasurementRecord, ...]:
        with self._factory.transaction() as cursor:
            rows = cursor.execute(
                self._MEASUREMENT_SELECT
                + " WHERE measurement.run_id = ? "
                "ORDER BY measurement.measurement_id",
                run_id,
            ).fetchall()
            return tuple(self._measurement(row) for row in rows)

    def snapshot_for_run(
        self, run_id: int
    ) -> tuple[tuple[MeasurementRecord, ...], tuple[MeasurementRecord, ...]]:
        """Return latest and append-only rows from one stable transaction."""
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                "SELECT run_id FROM dbo.IL_RUNS WITH (UPDLOCK, HOLDLOCK) "
                "WHERE run_id = ?",
                run_id,
            ).fetchone()
            if row is None:
                raise ValueError("Measurement run does not exist")
            current_rows = cursor.execute(
                self._CURRENT_MEASUREMENT_SELECT
                + " WHERE measurement.run_id = ? ORDER BY measurement.logical_channel",
                run_id,
            ).fetchall()
            history_rows = cursor.execute(
                self._MEASUREMENT_SELECT
                + " WHERE measurement.run_id = ? ORDER BY measurement.measurement_id",
                run_id,
            ).fetchall()
            return (
                tuple(self._measurement(item) for item in current_rows),
                tuple(self._measurement(item) for item in history_rows),
            )

    def append(self, spec: ReplacementSpec) -> ReplacementRecord:
        with self._factory.transaction() as cursor:
            context = self._routing_context(
                cursor, spec.assignment_id, require_active=True
            )
            channel_map = {
                item.logical_channel: item
                for item in self._current_channel_map(cursor, spec.assignment_id)
            }
            route = channel_map.get(spec.logical_channel)
            if route is None:
                raise ValueError("Replacement logical channel is not in the assignment")
            if route.effective_physical_port != spec.previous_physical_port:
                raise ValueError(
                    "Previous physical port does not match the current channel map"
                )
            if spec.replacement_physical_port > context[4]:
                raise ValueError("Replacement physical port exceeds switch capacity")
            if any(
                item.logical_channel != spec.logical_channel
                and item.effective_physical_port == spec.replacement_physical_port
                for item in channel_map.values()
            ):
                raise ValueError("Replacement physical port is already in use")
            if spec.related_run_id is not None:
                related = cursor.execute(
                    "SELECT assignment_id FROM dbo.IL_RUNS WHERE run_id = ?",
                    spec.related_run_id,
                ).fetchone()
                if related is None or int(related[0]) != spec.assignment_id:
                    raise ValueError("Related run does not belong to this assignment")
            prior = cursor.execute(
                """
                SELECT TOP (1) replaced_at_utc
                FROM dbo.CHANNEL_REPLACEMENTS
                WHERE assignment_id = ? AND logical_channel = ?
                ORDER BY replaced_at_utc DESC, replacement_id DESC
                """,
                spec.assignment_id,
                spec.logical_channel,
            ).fetchone()
            if spec.replaced_at_utc < context[2] or (
                prior is not None and spec.replaced_at_utc < _utc(prior[0])
            ):
                raise ValueError("Replacement time precedes its assignment history")
            replacement_id = cursor.execute(
                """
                INSERT INTO dbo.CHANNEL_REPLACEMENTS (
                    assignment_id, logical_channel, previous_physical_port,
                    replacement_physical_port, reason, replaced_by,
                    replaced_at_utc, related_run_id, notes
                ) OUTPUT INSERTED.replacement_id
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                spec.assignment_id,
                spec.logical_channel,
                spec.previous_physical_port,
                spec.replacement_physical_port,
                spec.reason,
                spec.replaced_by,
                spec.replaced_at_utc,
                spec.related_run_id,
                spec.notes,
            ).fetchone()[0]
            row = cursor.execute(
                self._REPLACEMENT_SELECT + " WHERE replacement.replacement_id = ?",
                replacement_id,
            ).fetchone()
            return self._replacement(row)

    def replacement_history_for_assignment(
        self, assignment_id: int
    ) -> tuple[ReplacementRecord, ...]:
        with self._factory.transaction() as cursor:
            self._routing_context(cursor, assignment_id)
            rows = cursor.execute(
                self._REPLACEMENT_SELECT
                + " WHERE replacement.assignment_id = ? "
                "ORDER BY replacement.replacement_id",
                assignment_id,
            ).fetchall()
            return tuple(self._replacement(row) for row in rows)

    def current_channel_map(
        self, assignment_id: int
    ) -> tuple[ChannelMapRecord, ...]:
        with self._factory.transaction() as cursor:
            self._routing_context(cursor, assignment_id)
            return self._current_channel_map(cursor, assignment_id)

    def append_event(self, spec: SpareEventSpec) -> SpareEventRecord:
        with self._factory.transaction() as cursor:
            context = self._routing_context(
                cursor, spec.assignment_id, require_active=True
            )
            if spec.physical_port > context[4]:
                raise ValueError("Spare physical port exceeds switch capacity")
            prior = cursor.execute(
                """
                SELECT TOP (1) action, recorded_at_utc
                FROM dbo.DESIGNATED_SPARES
                WHERE assignment_id = ? AND physical_port = ?
                ORDER BY spare_event_id DESC
                """,
                spec.assignment_id,
                spec.physical_port,
            ).fetchone()
            current_action = prior[0] if prior is not None else "undesignated"
            if current_action == spec.action:
                raise ValueError(f"Physical port is already {spec.action}")
            if spec.recorded_at_utc < context[2] or (
                prior is not None and spec.recorded_at_utc < _utc(prior[1])
            ):
                raise ValueError("Spare event time precedes its assignment history")
            event_id = cursor.execute(
                """
                INSERT INTO dbo.DESIGNATED_SPARES (
                    assignment_id, physical_port, action, recorded_by,
                    recorded_at_utc, notes
                ) OUTPUT INSERTED.spare_event_id VALUES (?, ?, ?, ?, ?, ?)
                """,
                spec.assignment_id,
                spec.physical_port,
                spec.action,
                spec.recorded_by,
                spec.recorded_at_utc,
                spec.notes,
            ).fetchone()[0]
            row = cursor.execute(
                self._SPARE_SELECT + " WHERE spare.spare_event_id = ?",
                event_id,
            ).fetchone()
            return self._spare(row)

    def spare_history_for_assignment(
        self, assignment_id: int
    ) -> tuple[SpareEventRecord, ...]:
        with self._factory.transaction() as cursor:
            self._routing_context(cursor, assignment_id)
            return self._spare_history(cursor, assignment_id)

    def active_spares_for_assignment(self, assignment_id: int) -> tuple[int, ...]:
        with self._factory.transaction() as cursor:
            self._routing_context(cursor, assignment_id)
            return self._active_spares(cursor, assignment_id)

    def routing_snapshot_for_assignment(self, assignment_id: int):
        with self._factory.transaction() as cursor:
            self._routing_context(cursor, assignment_id, lock=True)
            replacements = cursor.execute(
                self._REPLACEMENT_SELECT
                + " WHERE replacement.assignment_id = ? "
                "ORDER BY replacement.replacement_id",
                assignment_id,
            ).fetchall()
            spare_history = self._spare_history(cursor, assignment_id)
            return (
                self._current_channel_map(cursor, assignment_id),
                tuple(self._replacement(row) for row in replacements),
                spare_history,
                self._active_spares_from_history(spare_history),
            )

    def _routing_context(
        self,
        cursor,
        assignment_id: int,
        *,
        require_active: bool = False,
        lock: bool = False,
    ):
        hint = " WITH (UPDLOCK, HOLDLOCK)" if require_active or lock else ""
        row = cursor.execute(
            "SELECT assignment.assignment_id, assignment.switch_id, "
            "assignment.installed_at_utc, assignment.removed_at_utc, "
            "switch.physical_channel_count "
            "FROM dbo.UNIT_SWITCH_ASSIGNMENTS AS assignment"
            + hint
            + " INNER JOIN dbo.SWITCHES AS switch "
            "ON switch.switch_id = assignment.switch_id "
            "WHERE assignment.assignment_id = ?",
            assignment_id,
        ).fetchone()
        if row is None:
            raise ValueError("Routing assignment does not exist")
        if require_active and row[3] is not None:
            raise ValueError("Routing changes require an active assignment")
        return row[0], row[1], _utc(row[2]), _utc(row[3]), int(row[4])

    def _current_channel_map(self, cursor, assignment_id: int):
        rows = cursor.execute(
            self._CURRENT_CHANNEL_MAP_SELECT
            + " WHERE channel_map.assignment_id = ? "
            "ORDER BY channel_map.logical_channel",
            assignment_id,
        ).fetchall()
        return tuple(self._channel_map(row) for row in rows)

    def _spare_history(self, cursor, assignment_id: int):
        rows = cursor.execute(
            self._SPARE_SELECT
            + " WHERE spare.assignment_id = ? ORDER BY spare.spare_event_id",
            assignment_id,
        ).fetchall()
        return tuple(self._spare(row) for row in rows)

    @staticmethod
    def _active_spares_from_history(history):
        latest = {}
        for event in history:
            latest[event.physical_port] = event
        return tuple(
            sorted(
                port for port, event in latest.items() if event.action == "designated"
            )
        )

    def _active_spares(self, cursor, assignment_id: int):
        return self._active_spares_from_history(
            self._spare_history(cursor, assignment_id)
        )

    @staticmethod
    def _unit_by_id(cursor, unit_id: int) -> UnitRecord:
        row = cursor.execute(
            """
            SELECT unit_id, main_board_serial, part_number,
                front_panel_channel_count, unit_model, notes
            FROM dbo.UNITS WHERE unit_id = ?
            """,
            unit_id,
        ).fetchone()
        return UnitRecord(*row)

    @staticmethod
    def _switch_by_id(cursor, switch_id: int) -> SwitchRecord:
        row = cursor.execute(
            """
            SELECT switch_id, switch_serial, switch_model,
                physical_channel_count, firmware_version, notes
            FROM dbo.SWITCHES WHERE switch_id = ?
            """,
            switch_id,
        ).fetchone()
        return SwitchRecord(*row)

    @staticmethod
    def _assignment(row) -> AssignmentRecord:
        mapping = {int(key): int(value) for key, value in _mapping(row[5]).items()}
        return AssignmentRecord(
            row[0], row[1], row[2], _utc(row[3]), row[4], mapping,
            _utc(row[6]), row[7], row[8], row[9],
        )

    def _run_by_id(self, cursor, run_id: int) -> RunRecord:
        return self._run(
            cursor.execute(self._RUN_SELECT + " WHERE run.run_id = ?", run_id).fetchone()
        )

    @staticmethod
    def _run(row) -> RunRecord:
        return RunRecord(
            run_id=row[0], assignment_id=row[1], run_number=row[2],
            client_run_uuid=UUID(str(row[3])), run_started_at_utc=_utc(row[4]),
            tested_by=row[5], wavelength_mode=row[6], operating_band=row[7],
            application_version=row[8], measurement_hardware=_mapping(row[19]),
            limit_snapshot=_mapping(row[20]), station_number=row[17], completion_status=row[9],
            run_ended_at_utc=_utc(row[10]), run_purpose=row[11],
            analysis_status=row[12], analysis_exclusion_reason=row[13],
            superseded_by_run_id=row[14], part_number_snapshot=row[15],
            front_panel_channel_count=row[16], notes=row[18],
        )

    @staticmethod
    def _measurement(row) -> MeasurementRecord:
        return MeasurementRecord(
            measurement_id=row[0], measurement_uuid=UUID(str(row[1])), run_id=row[2],
            logical_channel=row[3], physical_port=row[4], attempt_number=row[5],
            wavelength_1_nm=row[6], wavelength_1_il_db=Decimal(row[7]),
            wavelength_2_nm=row[8], wavelength_2_il_db=Decimal(row[9]),
            reference_snapshot=_mapping(row[10]), written_at_utc=_utc(row[11]),
            written_by=row[12],
        )

    @staticmethod
    def _replacement(row) -> ReplacementRecord:
        return ReplacementRecord(
            row[0], row[1], row[2], row[3], row[4], row[5], row[6],
            _utc(row[7]), row[8], row[9],
        )

    @staticmethod
    def _spare(row) -> SpareEventRecord:
        return SpareEventRecord(row[0], row[1], row[2], row[3], row[4], _utc(row[5]), row[6])

    @staticmethod
    def _channel_map(row) -> ChannelMapRecord:
        return ChannelMapRecord(
            row[0], row[1], row[2], row[3], row[4], row[5], bool(row[6]),
            row[7], _utc(row[8]),
        )

    _ASSIGNMENT_SELECT = """
        SELECT assignment.assignment_id, assignment.unit_id, assignment.switch_id,
            assignment.installed_at_utc, assignment.installed_by,
            assignment.initial_channel_map_json, assignment.removed_at_utc,
            assignment.removed_by, assignment.removal_reason, assignment.notes
        FROM dbo.UNIT_SWITCH_ASSIGNMENTS AS assignment
    """
    _RUN_SELECT = """
        SELECT run.run_id, run.assignment_id, run.run_number, run.client_run_uuid,
            run.run_started_at_utc, run.tested_by, run.wavelength_mode,
            run.operating_band, run.application_version, run.completion_status,
            run.run_ended_at_utc, run.run_purpose, run.analysis_status,
            run.analysis_exclusion_reason, run.superseded_by_run_id,
            run.part_number_snapshot, run.front_panel_channel_count,
            run.station_number, run.notes,
            run.measurement_hardware_json, run.limit_snapshot_json
        FROM dbo.IL_RUNS AS run
    """
    _MEASUREMENT_SELECT = """
        SELECT measurement.measurement_id, measurement.measurement_uuid,
            measurement.run_id, measurement.logical_channel,
            measurement.physical_port, measurement.attempt_number,
            measurement.wavelength_1_nm, measurement.wavelength_1_il_db,
            measurement.wavelength_2_nm, measurement.wavelength_2_il_db,
            measurement.reference_snapshot_json, measurement.written_at_utc,
            measurement.written_by
        FROM dbo.IL_MEASUREMENTS AS measurement
    """
    _CURRENT_MEASUREMENT_SELECT = _MEASUREMENT_SELECT.replace(
        "dbo.IL_MEASUREMENTS", "dbo.vw_CurrentILMeasurements"
    )
    _CURRENT_CHANNEL_MAP_SELECT = """
        SELECT channel_map.assignment_id, channel_map.unit_id,
            channel_map.switch_id, channel_map.logical_channel,
            channel_map.initial_physical_port,
            channel_map.effective_physical_port, channel_map.is_replaced,
            channel_map.latest_replacement_id,
            channel_map.latest_replaced_at_utc
        FROM dbo.vw_CurrentChannelMap AS channel_map
    """
    _REPLACEMENT_SELECT = """
        SELECT replacement.replacement_id, replacement.assignment_id,
            replacement.logical_channel, replacement.previous_physical_port,
            replacement.replacement_physical_port, replacement.reason,
            replacement.replaced_by, replacement.replaced_at_utc,
            replacement.related_run_id, replacement.notes
        FROM dbo.CHANNEL_REPLACEMENTS AS replacement
    """
    _SPARE_SELECT = """
        SELECT spare.spare_event_id, spare.assignment_id, spare.physical_port,
            spare.action, spare.recorded_by, spare.recorded_at_utc, spare.notes
        FROM dbo.DESIGNATED_SPARES AS spare
    """


__all__ = ["SqlRepositories"]
