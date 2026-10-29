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
    PendingRunStartSpec,
    ReplacementAnalysisRecommendationRecord,
    ReplacementAnalysisRecommendationSpec,
    ReplacementAnalysisRecord,
    ReplacementAnalysisSpec,
    ReplacementRecord,
    ReplacementSpec,
    ConfirmedExtraPortRecord,
    MEASUREMENT_ROLE_EXTRA_CANDIDATE,
    MEASUREMENT_ROLE_LOGICAL_CHANNEL,
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


def _void_json(value: RunVoidInfo | None) -> str | None:
    if value is None:
        return None
    return _json(
        {
            "voided_at_utc": value.voided_at_utc.isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            ),
            "voided_by": value.voided_by,
            "reason": value.reason,
        }
    )


def _void_info(value: str | None) -> RunVoidInfo | None:
    if value is None:
        return None
    data = _mapping(value)
    timestamp = str(data["voided_at_utc"]).replace("Z", "+00:00")
    return RunVoidInfo(
        datetime.fromisoformat(timestamp),
        str(data["voided_by"]),
        str(data["reason"]),
    )


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
                        last_reported_scpi_channel_count, notes
                    ) OUTPUT INSERTED.switch_id VALUES (?, ?, ?, ?, ?)
                    """,
                    spec.switch_serial,
                    spec.switch_model,
                    spec.firmware_version,
                    spec.last_reported_scpi_channel_count,
                    spec.notes,
                ).fetchone()[0]
            else:
                switch_id = row[0]
                cursor.execute(
                    """
                    UPDATE dbo.SWITCHES SET
                        switch_model = ?, firmware_version = ?,
                        last_reported_scpi_channel_count = ?, notes = ?,
                        updated_at_utc = SYSUTCDATETIME()
                    WHERE switch_id = ?
                    """,
                    spec.switch_model,
                    spec.firmware_version,
                    spec.last_reported_scpi_channel_count,
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
                    last_reported_scpi_channel_count, firmware_version, notes
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
                    last_reported_scpi_channel_count, firmware_version, notes
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

    def install_fresh_pairing(
        self,
        spec: AssignmentSpec,
        removed_at_utc: datetime,
        removed_by: str,
    ) -> tuple[AssignmentRecord, tuple[AssignmentRecord, ...], tuple[int, ...]]:
        """Atomically close conflicting assignments and install a fresh baseline."""
        channel_map = {str(key): value for key, value in spec.initial_channel_map.items()}
        removed = require_utc(removed_at_utc, "Pairing-change time")
        operator = str(removed_by or "").strip()
        if not operator:
            raise ValueError("Pairing-change operator is required")
        with self._factory.transaction() as cursor:
            unit = cursor.execute(
                """
                SELECT main_board_serial FROM dbo.UNITS WITH (UPDLOCK, HOLDLOCK)
                WHERE unit_id = ?
                """,
                spec.unit_id,
            ).fetchone()
            switch = cursor.execute(
                """
                SELECT switch_serial FROM dbo.SWITCHES WITH (UPDLOCK, HOLDLOCK)
                WHERE switch_id = ?
                """,
                spec.switch_id,
            ).fetchone()
            if unit is None or switch is None:
                raise ValueError("Assignment unit and switch must already exist")
            rows = cursor.execute(
                """
                SELECT assignment_id, unit_id, switch_id, installed_at_utc
                FROM dbo.UNIT_SWITCH_ASSIGNMENTS WITH (UPDLOCK, HOLDLOCK)
                WHERE removed_at_utc IS NULL
                    AND (unit_id = ? OR switch_id = ?)
                ORDER BY assignment_id
                """,
                spec.unit_id,
                spec.switch_id,
            ).fetchall()
            conflicts = tuple(rows)
            for row in conflicts:
                if int(row[1]) == spec.unit_id and int(row[2]) == spec.switch_id:
                    return (
                        self._assignment(
                            cursor.execute(
                                self._ASSIGNMENT_SELECT
                                + " WHERE assignment.assignment_id = ?",
                                row[0],
                            ).fetchone()
                        ),
                        (),
                        (),
                    )
                if removed < _utc(row[3]):
                    raise ValueError("Pairing-change time cannot precede installation")

            assignment_ids = tuple(int(row[0]) for row in conflicts)
            stopped_ids = []
            if assignment_ids:
                placeholders = ", ".join("?" for _ in assignment_ids)
                run_rows = cursor.execute(
                    """
                    SELECT run_id FROM dbo.IL_RUNS WITH (UPDLOCK, HOLDLOCK)
                    WHERE completion_status = 'in_progress'
                        AND assignment_id IN (%s)
                    ORDER BY run_id
                    """ % placeholders,
                    *assignment_ids,
                ).fetchall()
                stopped_ids = [int(row[0]) for row in run_rows]
                cursor.execute(
                    """
                    UPDATE dbo.IL_RUNS SET completion_status = 'stopped',
                        run_ended_at_utc = ?, analysis_status = 'pending',
                        updated_at_utc = SYSUTCDATETIME()
                    WHERE completion_status = 'in_progress'
                        AND assignment_id IN (%s)
                    """ % placeholders,
                    removed,
                    *assignment_ids,
                )
            closed_reasons = {}
            for row in conflicts:
                assignment_id = int(row[0])
                if int(row[1]) == spec.unit_id:
                    reason = "Main board paired with switch %s" % switch[0]
                else:
                    reason = "Switch reassigned to main board %s" % unit[0]
                closed_reasons[assignment_id] = reason
                cursor.execute(
                    """
                    UPDATE dbo.UNIT_SWITCH_ASSIGNMENTS SET
                        removed_at_utc = ?, removed_by = ?, removal_reason = ?,
                        updated_at_utc = SYSUTCDATETIME()
                    WHERE assignment_id = ? AND removed_at_utc IS NULL
                    """,
                    removed,
                    operator,
                    reason,
                    assignment_id,
                )
            new_id = cursor.execute(
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
            installed = self._assignment(
                cursor.execute(
                    self._ASSIGNMENT_SELECT + " WHERE assignment.assignment_id = ?",
                    new_id,
                ).fetchone()
            )
            closed = tuple(
                self._assignment(
                    cursor.execute(
                        self._ASSIGNMENT_SELECT
                        + " WHERE assignment.assignment_id = ?",
                        int(row[0]),
                    ).fetchone()
                )
                for row in conflicts
            )
            return installed, closed, tuple(stopped_ids)

    def create_next_with_fresh_pairing(
        self,
        assignment: AssignmentSpec,
        run: PendingRunStartSpec,
        changed_at_utc: datetime,
        changed_by: str,
    ):
        """Persist pairing transition and the first run in one SQL transaction."""
        channel_map = {str(key): value for key, value in assignment.initial_channel_map.items()}
        removed = require_utc(changed_at_utc, "Pairing-change time")
        operator = str(changed_by or "").strip()
        if not operator:
            raise ValueError("Pairing-change operator is required")
        with self._factory.transaction() as cursor:
            unit = cursor.execute(
                "SELECT main_board_serial FROM dbo.UNITS WITH (UPDLOCK, HOLDLOCK) WHERE unit_id = ?",
                assignment.unit_id,
            ).fetchone()
            switch = cursor.execute(
                "SELECT switch_serial FROM dbo.SWITCHES WITH (UPDLOCK, HOLDLOCK) WHERE switch_id = ?",
                assignment.switch_id,
            ).fetchone()
            if unit is None or switch is None:
                raise ValueError("Assignment unit and switch must already exist")
            conflicts = cursor.execute(
                """
                SELECT assignment_id, unit_id, switch_id, installed_at_utc
                FROM dbo.UNIT_SWITCH_ASSIGNMENTS WITH (UPDLOCK, HOLDLOCK)
                WHERE removed_at_utc IS NULL AND (unit_id = ? OR switch_id = ?)
                ORDER BY assignment_id
                """,
                assignment.unit_id,
                assignment.switch_id,
            ).fetchall()
            if any(
                int(row[1]) == assignment.unit_id
                and int(row[2]) == assignment.switch_id
                for row in conflicts
            ):
                active_id = next(
                    int(row[0])
                    for row in conflicts
                    if int(row[1]) == assignment.unit_id
                    and int(row[2]) == assignment.switch_id
                )
                assignment_record = self._assignment(
                    cursor.execute(
                        self._ASSIGNMENT_SELECT
                        + " WHERE assignment.assignment_id = ?",
                        active_id,
                    ).fetchone()
                )
                target_assignment_id = active_id
                closed = ()
                stopped_ids = ()
            else:
                for row in conflicts:
                    if removed < _utc(row[3]):
                        raise ValueError("Pairing-change time cannot precede installation")
                assignment_ids = tuple(int(row[0]) for row in conflicts)
                stopped_ids_list = []
                if assignment_ids:
                    placeholders = ", ".join("?" for _ in assignment_ids)
                    run_rows = cursor.execute(
                        "SELECT run_id FROM dbo.IL_RUNS WITH (UPDLOCK, HOLDLOCK) "
                        "WHERE completion_status = 'in_progress' AND assignment_id IN (%s) "
                        "ORDER BY run_id" % placeholders,
                        *assignment_ids,
                    ).fetchall()
                    stopped_ids_list = [int(row[0]) for row in run_rows]
                    cursor.execute(
                        "UPDATE dbo.IL_RUNS SET completion_status = 'stopped', "
                        "run_ended_at_utc = ?, analysis_status = 'pending', "
                        "updated_at_utc = SYSUTCDATETIME() "
                        "WHERE completion_status = 'in_progress' AND assignment_id IN (%s)"
                        % placeholders,
                        removed,
                        *assignment_ids,
                    )
                for row in conflicts:
                    reason = (
                        "Main board paired with switch %s" % switch[0]
                        if int(row[1]) == assignment.unit_id
                        else "Switch reassigned to main board %s" % unit[0]
                    )
                    cursor.execute(
                        "UPDATE dbo.UNIT_SWITCH_ASSIGNMENTS SET removed_at_utc = ?, "
                        "removed_by = ?, removal_reason = ?, updated_at_utc = SYSUTCDATETIME() "
                        "WHERE assignment_id = ? AND removed_at_utc IS NULL",
                        removed,
                        operator,
                        reason,
                        int(row[0]),
                    )
                target_assignment_id = cursor.execute(
                    """
                    INSERT INTO dbo.UNIT_SWITCH_ASSIGNMENTS (
                        unit_id, switch_id, installed_at_utc, installed_by,
                        initial_channel_map_json, notes
                    ) OUTPUT INSERTED.assignment_id VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    assignment.unit_id,
                    assignment.switch_id,
                    assignment.installed_at_utc,
                    assignment.installed_by,
                    _json(channel_map),
                    assignment.notes,
                ).fetchone()[0]
                assignment_record = self._assignment(
                    cursor.execute(
                        self._ASSIGNMENT_SELECT
                        + " WHERE assignment.assignment_id = ?",
                        target_assignment_id,
                    ).fetchone()
                )
                closed = tuple(
                    self._assignment(
                        cursor.execute(
                            self._ASSIGNMENT_SELECT
                            + " WHERE assignment.assignment_id = ?",
                            int(row[0]),
                        ).fetchone()
                    )
                    for row in conflicts
                )
                stopped_ids = tuple(stopped_ids_list)
            run_spec = run.with_assignment_id(target_assignment_id)
            existing = cursor.execute(
                self._RUN_SELECT + " WHERE run.client_run_uuid = ?",
                str(run_spec.client_run_uuid),
            ).fetchone()
            if existing is not None:
                record = self._run(existing)
            else:
                run_number = cursor.execute(
                    """
                    SELECT COALESCE(MAX(run.run_number), 0) + 1
                    FROM dbo.IL_RUNS AS run
                    INNER JOIN dbo.UNIT_SWITCH_ASSIGNMENTS AS assignment
                        ON assignment.assignment_id = run.assignment_id
                    WHERE assignment.unit_id = ?
                    """,
                    assignment.unit_id,
                ).fetchone()[0]
                record = self._insert_run(cursor, run_spec.with_run_number(run_number))
            return record, assignment_record, closed, stopped_ids

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
                    analysis_status, void_info_json,
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
                _void_json(spec.void_info),
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
                    last_reported_scpi_channel_count, firmware_version, notes
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
        void_info: RunVoidInfo | None = None,
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
            if analysis_status == "excluded" and void_info is None:
                raise ValueError("Voided runs require run void information")
            changed = cursor.execute(
                """
                UPDATE dbo.IL_RUNS SET completion_status = ?, run_ended_at_utc = ?,
                    analysis_status = COALESCE(?, analysis_status),
                    void_info_json = CASE
                        WHEN ? = 'excluded' THEN ?
                        WHEN ? IS NULL THEN void_info_json
                        ELSE NULL
                    END,
                    updated_at_utc = SYSUTCDATETIME()
                WHERE run_id = ? AND completion_status = 'in_progress'
                """,
                completion_status,
                ended,
                analysis_status,
                analysis_status,
                _void_json(void_info),
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
        elif superseded_by_run_id is not None:
            raise ValueError("Only superseded runs may identify a superseding run")
        void_json = _void_json(void_info) if analysis_status == "excluded" else None
        target = int(superseded_by_run_id) if analysis_status == "superseded" else None
        with self._factory.transaction() as cursor:
            changed = cursor.execute(
                """
                UPDATE dbo.IL_RUNS SET analysis_status = ?,
                    void_info_json = ?, superseded_by_run_id = ?,
                    updated_at_utc = SYSUTCDATETIME()
                WHERE run_id = ?
                """,
                analysis_status,
                void_json,
                target,
                int(run_id),
            ).rowcount
            if changed != 1:
                raise ValueError("Run was not found")
            return self._run_by_id(cursor, run_id)

    def void_run(self, run_id: int, void_info: RunVoidInfo) -> RunRecord:
        """Atomically and permanently mark a retained run as voided."""
        with self._factory.transaction() as cursor:
            changed = cursor.execute(
                """
                UPDATE dbo.IL_RUNS
                SET analysis_status = 'excluded', void_info_json = ?,
                    superseded_by_run_id = NULL, updated_at_utc = SYSUTCDATETIME()
                WHERE run_id = ? AND analysis_status <> 'excluded'
                """,
                _void_json(void_info),
                int(run_id),
            ).rowcount
            if changed != 1:
                raise ValueError("Run was not found or is already voided")
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
                if spec.measurement_role == MEASUREMENT_ROLE_LOGICAL_CHANNEL:
                    identity_sql = "logical_channel = ?"
                    identity_value = spec.logical_channel
                else:
                    identity_sql = "physical_port = ?"
                    identity_value = spec.physical_port
                attempt_number = cursor.execute(
                    "SELECT COALESCE(MAX(attempt_number), 0) + 1 "
                    "FROM dbo.IL_MEASUREMENTS WHERE run_id = ? "
                    "AND measurement_role = ? AND " + identity_sql,
                    spec.run_id,
                    spec.measurement_role,
                    identity_value,
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
            SELECT wavelength_mode, completion_status, front_panel_channel_count
            FROM dbo.IL_RUNS WITH (UPDLOCK, HOLDLOCK)
            WHERE run_id = ?
            """,
            spec.run_id,
        ).fetchone()
        if row is None:
            raise ValueError("Measurement run does not exist")
        mode, completion_status, front_panel_channel_count = row
        if completion_status != "in_progress":
            raise ValueError("Measurements may only be written to an in-progress run")
        expected = (1310, 1550) if mode == "SM" else (850, 1300)
        actual = (int(spec.wavelength_1_nm), int(spec.wavelength_2_nm))
        if actual != expected:
            raise ValueError(
                f"{mode} measurements require wavelengths "
                f"{expected[0]} nm and {expected[1]} nm"
            )
        if front_panel_channel_count is not None:
            boundary = int(front_panel_channel_count)
            if spec.measurement_role == MEASUREMENT_ROLE_LOGICAL_CHANNEL:
                if int(spec.logical_channel) > boundary:
                    raise ValueError("Logical channel exceeds the front-panel channel count")
            elif int(spec.physical_port) <= boundary:
                raise ValueError("Extra-candidate physical port must exceed the front-panel channel count")

    def _insert_measurement(self, cursor, spec: MeasurementSpec) -> MeasurementRecord:
        measurement_id = cursor.execute(
            """
            INSERT INTO dbo.IL_MEASUREMENTS (
                measurement_uuid, run_id, logical_channel, physical_port,
                measurement_role,
                attempt_number, wavelength_1_nm, wavelength_1_il_db,
                wavelength_2_nm, wavelength_2_il_db,
                reference_snapshot_json, written_at_utc, written_by
            ) OUTPUT INSERTED.measurement_id
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            str(spec.measurement_uuid),
            spec.run_id,
            spec.logical_channel,
            spec.physical_port,
            spec.measurement_role,
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
                + " WHERE measurement.run_id = ? ORDER BY measurement.measurement_role, "
                "COALESCE(measurement.logical_channel, measurement.physical_port)",
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
                + " WHERE measurement.run_id = ? ORDER BY measurement.measurement_role, "
                "COALESCE(measurement.logical_channel, measurement.physical_port)",
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

    def append_analysis(self, spec, recommendations):
        with self._factory.transaction() as cursor:
            existing = cursor.execute(
                self._ANALYSIS_SELECT + " WHERE analysis.analysis_uuid = ?",
                str(spec.analysis_uuid),
            ).fetchone()
            if existing is not None:
                return self._analysis_bundle(cursor, existing[0])
            run = cursor.execute(
                "SELECT assignment_id FROM dbo.IL_RUNS WHERE run_id = ?",
                spec.run_id,
            ).fetchone()
            if run is None:
                raise ValueError("Replacement analysis run does not exist")
            self._validate_analysis_source_snapshot(
                cursor,
                context_run_id=spec.run_id,
                assignment_id=int(run[0]),
                snapshot=spec.result_details.get("source_snapshot", {}),
                high_watermark=spec.source_measurement_high_watermark_id,
            )
            analysis_id = cursor.execute(
                """
                INSERT INTO dbo.REPLACEMENT_ANALYSES (
                    analysis_uuid, run_id, analyzed_at_utc, analyzed_by,
                    application_version, source_measurement_high_watermark_id,
                    front_panel_channel_count, wavelengths_json, criteria_json,
                    result_status, result_details_json
                ) OUTPUT INSERTED.analysis_id
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                str(spec.analysis_uuid),
                spec.run_id,
                spec.analyzed_at_utc,
                spec.analyzed_by,
                spec.application_version,
                spec.source_measurement_high_watermark_id,
                spec.front_panel_channel_count,
                _json(spec.wavelengths),
                _json(spec.criteria),
                spec.result_status,
                _json(spec.result_details),
            ).fetchone()[0]
            for item in recommendations:
                if item.analysis_id not in (None, int(analysis_id)):
                    raise ValueError("Recommendation analysis ID does not match")
                if item.current_measurement_id is not None:
                    current_evidence = cursor.execute(
                        """
                        SELECT measurement.logical_channel, measurement.physical_port,
                            run.assignment_id, measurement.measurement_role
                        FROM dbo.IL_MEASUREMENTS AS measurement
                        INNER JOIN dbo.IL_RUNS AS run ON run.run_id = measurement.run_id
                        WHERE measurement.measurement_id = ?
                        """,
                        item.current_measurement_id,
                    ).fetchone()
                    if (
                        current_evidence is None
                        or int(current_evidence[0]) != int(item.logical_channel)
                        or int(current_evidence[1]) != int(item.current_physical_port)
                        or int(current_evidence[2]) != int(run[0])
                        or current_evidence[3] != MEASUREMENT_ROLE_LOGICAL_CHANNEL
                    ):
                        raise ValueError("Recommendation current measurement evidence is invalid")
                if item.candidate_measurement_id is not None:
                    candidate_evidence = cursor.execute(
                        "SELECT assignment_id, physical_port FROM dbo.vw_ConfirmedExtraPorts "
                        "WHERE measurement_id = ?",
                        item.candidate_measurement_id,
                    ).fetchone()
                    if (
                        candidate_evidence is None
                        or int(candidate_evidence[0]) != int(run[0])
                        or int(candidate_evidence[1]) != int(item.candidate_physical_port)
                    ):
                        raise ValueError("Recommendation candidate measurement evidence is invalid")
                cursor.execute(
                    """
                    INSERT INTO dbo.REPLACEMENT_ANALYSIS_RECOMMENDATIONS (
                        analysis_id, recommendation_rank, category,
                        logical_channel, current_physical_port,
                        candidate_physical_port, current_wavelength_1_il_db,
                        current_wavelength_2_il_db, candidate_wavelength_1_il_db,
                        candidate_wavelength_2_il_db, current_worst_loss_db,
                        candidate_worst_loss_db, improvement_db,
                        current_measurement_id, candidate_measurement_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
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
            return self._analysis_bundle(cursor, analysis_id)

    def _validate_analysis_source_snapshot(
        self,
        cursor,
        *,
        context_run_id,
        assignment_id,
        snapshot,
        high_watermark,
    ):
        """Validate legacy or assignment-scoped analysis source evidence."""
        if not isinstance(snapshot, Mapping) or not snapshot.get(
            "considered_measurement_ids"
        ):
            source = cursor.execute(
                "SELECT run_id FROM dbo.IL_MEASUREMENTS WHERE measurement_id = ?",
                high_watermark,
            ).fetchone()
            if source is None or int(source[0]) != int(context_run_id):
                raise ValueError("Analysis source measurement does not belong to the run")
            current_max = cursor.execute(
                "SELECT MAX(measurement_id) FROM dbo.IL_MEASUREMENTS WHERE run_id = ?",
                context_run_id,
            ).fetchone()[0]
            if current_max is None or int(current_max) != int(high_watermark):
                raise ValueError("Analysis source measurements are no longer current")
            return

        snapshot_assignment_id = int(snapshot.get("assignment_id", 0))
        snapshot_context_run_id = int(snapshot.get("context_run_id", 0))
        included_run_ids = tuple(
            sorted({int(value) for value in snapshot.get("included_run_ids", ())})
        )
        considered_ids = tuple(
            sorted(
                {int(value) for value in snapshot.get("considered_measurement_ids", ())}
            )
        )
        if (
            snapshot_assignment_id != int(assignment_id)
            or snapshot_context_run_id != int(context_run_id)
            or int(context_run_id) not in included_run_ids
            or not considered_ids
            or int(high_watermark) != max(considered_ids)
        ):
            raise ValueError("Analysis source snapshot is inconsistent")

        placeholders = ",".join("?" for _ in included_run_ids)
        run_rows = cursor.execute(
            "SELECT run_id, assignment_id, analysis_status, superseded_by_run_id "
            "FROM dbo.IL_RUNS WHERE run_id IN (%s)" % placeholders,
            *included_run_ids,
        ).fetchall()
        if len(run_rows) != len(included_run_ids) or any(
            int(row[1]) != int(assignment_id) for row in run_rows
        ):
            raise ValueError("Analysis source runs do not belong to the assignment")
        states = {
            int(item["run_id"]): (
                str(item.get("analysis_status") or ""),
                item.get("superseded_by_run_id"),
            )
            for item in snapshot.get("included_run_states", ())
            if isinstance(item, Mapping) and item.get("run_id") is not None
        }
        for row in run_rows:
            if states and states.get(int(row[0])) != (str(row[2] or ""), row[3]):
                raise ValueError("Analysis source run state is no longer current")

        current_measurement_ids = tuple(
            int(row[0])
            for row in cursor.execute(
                "SELECT measurement_id FROM dbo.IL_MEASUREMENTS "
                "WHERE run_id IN (%s) ORDER BY measurement_id" % placeholders,
                *included_run_ids,
            ).fetchall()
        )
        if current_measurement_ids != considered_ids:
            raise ValueError("Analysis source measurements are no longer current")

        replacement_rows = cursor.execute(
            "SELECT replacement_id FROM dbo.CHANNEL_REPLACEMENTS "
            "WHERE assignment_id = ? AND (related_run_id IS NULL OR related_run_id IN (%s)) "
            "ORDER BY replacement_id" % placeholders,
            assignment_id,
            *included_run_ids,
        ).fetchall()
        if tuple(int(row[0]) for row in replacement_rows) != tuple(
            sorted(int(value) for value in snapshot.get("replacement_ids", ()))
        ):
            raise ValueError("Analysis source replacements are no longer current")
        spare_rows = cursor.execute(
            "SELECT spare_event_id FROM dbo.DESIGNATED_SPARES "
            "WHERE assignment_id = ? ORDER BY spare_event_id",
            assignment_id,
        ).fetchall()
        if tuple(int(row[0]) for row in spare_rows) != tuple(
            sorted(int(value) for value in snapshot.get("spare_event_ids", ()))
        ):
            raise ValueError("Analysis source spare history is no longer current")

    def latest_analysis_for_run(self, run_id):
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                self._ANALYSIS_SELECT
                + " WHERE analysis.run_id = ? "
                "ORDER BY analysis.analyzed_at_utc DESC, analysis.analysis_id DESC",
                run_id,
            ).fetchone()
            return None if row is None else self._analysis_bundle(cursor, row[0])

    def analysis_history_for_run(self, run_id):
        with self._factory.transaction() as cursor:
            rows = cursor.execute(
                self._ANALYSIS_SELECT
                + " WHERE analysis.run_id = ? "
                "ORDER BY analysis.analyzed_at_utc DESC, analysis.analysis_id DESC",
                run_id,
            ).fetchall()
            return tuple(self._analysis_bundle(cursor, row[0]) for row in rows)

    def current_measurement_high_watermark(self, run_id):
        with self._factory.transaction() as cursor:
            row = cursor.execute(
                "SELECT MAX(measurement_id) FROM dbo.IL_MEASUREMENTS "
                "WHERE run_id = ?",
                run_id,
            ).fetchone()
            return None if row is None or row[0] is None else int(row[0])

    def _analysis_bundle(self, cursor, analysis_id):
        row = cursor.execute(
            self._ANALYSIS_SELECT + " WHERE analysis.analysis_id = ?",
            analysis_id,
        ).fetchone()
        if row is None:
            raise ValueError("Replacement analysis does not exist")
        recommendation_rows = cursor.execute(
            self._ANALYSIS_RECOMMENDATION_SELECT
            + " WHERE recommendation.analysis_id = ? "
            "ORDER BY recommendation.recommendation_rank, recommendation.recommendation_id",
            analysis_id,
        ).fetchall()
        return self._analysis(row), tuple(
            self._analysis_recommendation(item) for item in recommendation_rows
        )

    def append(self, spec: ReplacementSpec) -> ReplacementRecord:
        with self._factory.transaction() as cursor:
            return self._append_replacement(cursor, spec)

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
            return self._append_spare_event(cursor, spec)

    def apply_routing_changes(self, replacement_specs, spare_event_specs):
        """Validate and append one operator approval as a single transaction."""
        specs = tuple(replacement_specs)
        spare_specs = tuple(spare_event_specs)
        assignment_ids = {
            spec.assignment_id for spec in (*specs, *spare_specs)
        }
        if len(assignment_ids) != 1:
            raise ValueError("Routing changes must target one assignment")
        assignment_id = next(iter(assignment_ids))
        with self._factory.transaction() as cursor:
            self._routing_context(cursor, assignment_id, require_active=True)
            for spec in specs:
                self._append_replacement(cursor, spec)
            for spec in spare_specs:
                self._append_spare_event(cursor, spec)
            return self._routing_snapshot(cursor, assignment_id)

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
            return self._routing_snapshot(cursor, assignment_id)

    def _append_replacement(self, cursor, spec: ReplacementSpec):
        context = self._routing_context(cursor, spec.assignment_id, require_active=True)
        channel_map = {
            item.logical_channel: item
            for item in self._current_channel_map(cursor, spec.assignment_id)
        }
        route = channel_map.get(spec.logical_channel)
        if route is None:
            raise ValueError("Replacement logical channel is not in the assignment")
        if route.effective_physical_port != spec.previous_physical_port:
            raise ValueError("Previous physical port does not match the current channel map")
        if any(
            item.logical_channel != spec.logical_channel
            and item.effective_physical_port == spec.replacement_physical_port
            for item in channel_map.values()
        ):
            raise ValueError("Replacement physical port is already in use")
        confirmed = None
        if not spec.is_correction:
            confirmed = cursor.execute(
                "SELECT measurement_id FROM dbo.vw_ConfirmedExtraPorts "
                "WHERE assignment_id = ? AND physical_port = ?",
                spec.assignment_id,
                spec.replacement_physical_port,
            ).fetchone()
            if confirmed is None:
                raise ValueError(
                    "Replacement physical port has no valid committed extra-port "
                    "measurement for this assignment"
                )
        if spec.related_run_id is not None:
            related = cursor.execute(
                "SELECT assignment_id FROM dbo.IL_RUNS WHERE run_id = ?",
                spec.related_run_id,
            ).fetchone()
            if related is None or int(related[0]) != spec.assignment_id:
                raise ValueError("Related run does not belong to this assignment")
        if spec.source_recommendation_id is not None:
            recommendation = cursor.execute(
                """
                SELECT recommendation.analysis_id, recommendation.logical_channel,
                    recommendation.candidate_physical_port, analysis.run_id,
                    analysis.source_measurement_high_watermark_id,
                    recommendation.candidate_measurement_id,
                    analysis.result_details_json
                FROM dbo.REPLACEMENT_ANALYSIS_RECOMMENDATIONS AS recommendation
                INNER JOIN dbo.REPLACEMENT_ANALYSES AS analysis
                    ON analysis.analysis_id = recommendation.analysis_id
                WHERE recommendation.recommendation_id = ?
                """,
                spec.source_recommendation_id,
            ).fetchone()
            if recommendation is None:
                raise ValueError("Source replacement recommendation does not exist")
            source_assignment = cursor.execute(
                "SELECT assignment_id FROM dbo.IL_RUNS WHERE run_id = ?",
                recommendation[3],
            ).fetchone()
            if source_assignment is None or int(source_assignment[0]) != int(
                spec.assignment_id
            ):
                raise ValueError(
                    "Source replacement recommendation belongs to another assignment"
                )
            try:
                self._validate_analysis_source_snapshot(
                    cursor,
                    context_run_id=int(recommendation[3]),
                    assignment_id=int(source_assignment[0]),
                    snapshot=_mapping(recommendation[6]).get(
                        "source_snapshot", {}
                    ),
                    high_watermark=int(recommendation[4]),
                )
            except ValueError as error:
                raise ValueError(
                    "Source replacement recommendation is stale"
                ) from error
            if (
                int(recommendation[1]) != int(spec.logical_channel)
                or int(recommendation[2]) != int(spec.replacement_physical_port)
            ):
                raise ValueError("Source recommendation does not match the replacement")
            if recommendation[5] is not None and (
                confirmed is None or int(recommendation[5]) != int(confirmed[0])
            ):
                raise ValueError("Source recommendation candidate evidence is stale")
            used = cursor.execute(
                "SELECT 1 FROM dbo.CHANNEL_REPLACEMENTS "
                "WHERE source_recommendation_id = ?",
                spec.source_recommendation_id,
            ).fetchone()
            if used is not None:
                raise ValueError("Source replacement recommendation was already used")
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
                replaced_at_utc, related_run_id, notes, source_recommendation_id
            ) OUTPUT INSERTED.replacement_id
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            spec.source_recommendation_id,
        ).fetchone()[0]
        row = cursor.execute(
            self._REPLACEMENT_SELECT + " WHERE replacement.replacement_id = ?",
            replacement_id,
        ).fetchone()
        return self._replacement(row)

    def _append_spare_event(self, cursor, spec: SpareEventSpec):
        context = self._routing_context(cursor, spec.assignment_id, require_active=True)
        if spec.action == "designated":
            confirmed = cursor.execute(
                "SELECT 1 FROM dbo.vw_ConfirmedExtraPorts "
                "WHERE assignment_id = ? AND physical_port = ?",
                spec.assignment_id,
                spec.physical_port,
            ).fetchone()
            if confirmed is None:
                raise ValueError(
                    "Spare physical port has no valid committed extra-port "
                    "measurement for this assignment"
                )
            if cursor.execute(
                self._CURRENT_CHANNEL_MAP_SELECT
                + " WHERE channel_map.assignment_id = ? "
                "AND channel_map.effective_physical_port = ?",
                spec.assignment_id,
                spec.physical_port,
            ).fetchone() is not None:
                raise ValueError("Mapped physical port cannot be designated as a spare")
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

    def _routing_snapshot(self, cursor, assignment_id: int):
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

    def confirmed_extra_ports_for_assignment(
        self, assignment_id: int
    ) -> tuple[ConfirmedExtraPortRecord, ...]:
        with self._factory.transaction() as cursor:
            self._routing_context(cursor, assignment_id)
            rows = cursor.execute(
                self._CONFIRMED_EXTRA_SELECT
                + " WHERE extra.assignment_id = ? ORDER BY extra.physical_port",
                assignment_id,
            ).fetchall()
            return tuple(self._confirmed_extra(row) for row in rows)

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
            "switch.last_reported_scpi_channel_count "
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
                last_reported_scpi_channel_count, firmware_version, notes
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
            analysis_status=row[12], void_info=_void_info(row[13]),
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
            written_by=row[12], measurement_role=row[13],
        )

    @staticmethod
    def _confirmed_extra(row) -> ConfirmedExtraPortRecord:
        measurement = MeasurementRecord(
            measurement_id=row[2], measurement_uuid=UUID(str(row[3])), run_id=row[1],
            logical_channel=None, physical_port=row[4], attempt_number=row[5],
            wavelength_1_nm=row[6], wavelength_1_il_db=Decimal(row[7]),
            wavelength_2_nm=row[8], wavelength_2_il_db=Decimal(row[9]),
            reference_snapshot=_mapping(row[10]), written_at_utc=_utc(row[11]),
            written_by=row[12], measurement_role=MEASUREMENT_ROLE_EXTRA_CANDIDATE,
        )
        return ConfirmedExtraPortRecord(row[0], row[1], measurement, row[14])

    @staticmethod
    def _replacement(row) -> ReplacementRecord:
        return ReplacementRecord(
            row[0], row[1], row[2], row[3], row[4], row[5], row[6],
            _utc(row[7]), row[8], row[9], row[10],
        )

    @staticmethod
    def _analysis(row) -> ReplacementAnalysisRecord:
        return ReplacementAnalysisRecord(
            analysis_id=row[0],
            analysis_uuid=UUID(str(row[1])),
            run_id=row[2],
            analyzed_at_utc=_utc(row[3]),
            analyzed_by=row[4],
            application_version=row[5],
            source_measurement_high_watermark_id=row[6],
            front_panel_channel_count=row[7],
            wavelengths=_mapping(row[8]),
            criteria=_mapping(row[9]),
            result_status=row[10],
            result_details=_mapping(row[11]),
        )

    @staticmethod
    def _analysis_recommendation(row) -> ReplacementAnalysisRecommendationRecord:
        return ReplacementAnalysisRecommendationRecord(
            recommendation_id=row[0],
            analysis_id=row[1],
            recommendation_rank=row[2],
            category=row[3],
            logical_channel=row[4],
            current_physical_port=row[5],
            candidate_physical_port=row[6],
            current_wavelength_1_il_db=Decimal(row[7]),
            current_wavelength_2_il_db=Decimal(row[8]),
            candidate_wavelength_1_il_db=Decimal(row[9]),
            candidate_wavelength_2_il_db=Decimal(row[10]),
            current_worst_loss_db=Decimal(row[11]),
            candidate_worst_loss_db=Decimal(row[12]),
            improvement_db=Decimal(row[13]),
            current_measurement_id=row[14],
            candidate_measurement_id=row[15],
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
            run.void_info_json, run.superseded_by_run_id,
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
            measurement.written_by, measurement.measurement_role
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
            replacement.related_run_id, replacement.notes,
            replacement.source_recommendation_id
        FROM dbo.CHANNEL_REPLACEMENTS AS replacement
    """
    _ANALYSIS_SELECT = """
        SELECT analysis.analysis_id, analysis.analysis_uuid, analysis.run_id,
            analysis.analyzed_at_utc, analysis.analyzed_by,
            analysis.application_version,
            analysis.source_measurement_high_watermark_id,
            analysis.front_panel_channel_count, analysis.wavelengths_json,
            analysis.criteria_json, analysis.result_status,
            analysis.result_details_json
        FROM dbo.REPLACEMENT_ANALYSES AS analysis
    """
    _ANALYSIS_RECOMMENDATION_SELECT = """
        SELECT recommendation.recommendation_id, recommendation.analysis_id,
            recommendation.recommendation_rank, recommendation.category,
            recommendation.logical_channel, recommendation.current_physical_port,
            recommendation.candidate_physical_port,
            recommendation.current_wavelength_1_il_db,
            recommendation.current_wavelength_2_il_db,
            recommendation.candidate_wavelength_1_il_db,
            recommendation.candidate_wavelength_2_il_db,
            recommendation.current_worst_loss_db,
            recommendation.candidate_worst_loss_db,
            recommendation.improvement_db,
            recommendation.current_measurement_id,
            recommendation.candidate_measurement_id
        FROM dbo.REPLACEMENT_ANALYSIS_RECOMMENDATIONS AS recommendation
    """
    _CONFIRMED_EXTRA_SELECT = """
        SELECT extra.assignment_id, extra.run_id, extra.measurement_id,
            extra.measurement_uuid, extra.physical_port, extra.attempt_number,
            extra.wavelength_1_nm, extra.wavelength_1_il_db,
            extra.wavelength_2_nm, extra.wavelength_2_il_db,
            extra.reference_snapshot_json, extra.written_at_utc,
            extra.written_by, extra.analysis_status,
            extra.front_panel_channel_count
        FROM dbo.vw_ConfirmedExtraPorts AS extra
    """
    _SPARE_SELECT = """
        SELECT spare.spare_event_id, spare.assignment_id, spare.physical_port,
            spare.action, spare.recorded_by, spare.recorded_at_utc, spare.notes
        FROM dbo.DESIGNATED_SPARES AS spare
    """


__all__ = ["SqlRepositories"]
