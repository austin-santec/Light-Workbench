"""Reusable, repository-neutral sample data seeding for the SQL database.

This module deliberately knows nothing about SQL Server.  It turns a small,
declarative scenario file into the same application workflow calls used by a
real run, which keeps sample data useful without creating a second persistence
model.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping
from uuid import UUID, uuid5

from domain.database_records import SwitchSpec, UnitSpec
from domain.limit_profiles import LimitProfile
from domain.reference import ReferenceSnapshot
from domain.run_purpose import normalize_run_purpose


SAMPLE_UUID_NAMESPACE = UUID("2f3e4d2a-92d0-4a4d-9e0b-4b3e1c0e5f1b")
SCENARIO_MARKER_PREFIX = "Light Workbench sample scenario: "


class SampleScenarioError(ValueError):
    """Raised when a scenario is invalid or conflicts with existing data."""


@dataclass(frozen=True)
class SampleRun:
    number: int
    purpose: str
    completion_status: str
    analysis_status: str
    analysis_exclusion_reason: str | None
    started_at_utc: datetime
    ended_at_utc: datetime
    reference_snapshot: Mapping[str, object]
    limit_snapshot: Mapping[str, object]
    explicit_measurements: tuple[Mapping[str, object], ...]
    generated_measurements: Mapping[str, object] | None
    notes: str | None


@dataclass(frozen=True)
class SampleScenario:
    scenario_id: str
    description: str
    unit: UnitSpec
    switch: SwitchSpec
    initial_channel_map: Mapping[int, int]
    installed_at_utc: datetime
    installed_by: str
    spares: tuple[int, ...]
    replacements: tuple[Mapping[str, object], ...]
    runs: tuple[SampleRun, ...]
    application_version: str
    tag: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "SampleScenario":
        try:
            scenario_id = str(values["scenario_id"]).strip()
            unit_values = dict(values["unit"])
            switch_values = dict(values["switch"])
            assignment_values = dict(values["assignment"])
            runs_values = values["runs"]
        except (KeyError, TypeError, ValueError) as error:
            raise SampleScenarioError("Scenario is missing a required section.") from error

        if not scenario_id.startswith("SAMPLE-"):
            raise SampleScenarioError("Scenario IDs must start with SAMPLE-.")
        unit_serial = str(unit_values.get("main_board_serial", "")).strip()
        switch_serial = str(switch_values.get("switch_serial", "")).strip()
        if not unit_serial.startswith("SAMPLE-") or not switch_serial.startswith("SAMPLE-"):
            raise SampleScenarioError(
                "Sample unit and switch serials must start with SAMPLE-."
            )
        try:
            unit = UnitSpec(
                main_board_serial=unit_serial,
                part_number=str(unit_values["part_number"]),
                front_panel_channel_count=int(unit_values["front_panel_channel_count"]),
                unit_model=str(unit_values["unit_model"]),
                notes=str(unit_values.get("notes") or "").strip() or None,
            )
            switch = SwitchSpec(
                switch_serial=switch_serial,
                switch_model=str(switch_values["switch_model"]),
                physical_channel_count=int(switch_values["physical_channel_count"]),
                firmware_version=str(switch_values.get("firmware_version") or "").strip()
                or None,
                notes=str(switch_values.get("notes") or "").strip() or None,
            )
            initial_map = {
                int(logical): int(physical)
                for logical, physical in dict(
                    assignment_values["initial_channel_map"]
                ).items()
            }
            installed_at = _parse_utc(assignment_values["installed_at_utc"])
            installed_by = str(assignment_values["installed_by"]).strip()
        except (KeyError, TypeError, ValueError) as error:
            raise SampleScenarioError("Scenario unit, switch, or assignment is invalid.") from error

        if unit.front_panel_channel_count != len(initial_map):
            raise SampleScenarioError(
                "The initial channel map must contain every front-panel channel."
            )
        if set(initial_map) != set(range(1, unit.front_panel_channel_count + 1)):
            raise SampleScenarioError("The initial channel map must start at logical channel 1.")

        try:
            runs = tuple(_parse_run(item) for item in runs_values)
        except (TypeError, ValueError, KeyError) as error:
            raise SampleScenarioError("One or more scenario runs are invalid.") from error
        if not runs or tuple(run.number for run in runs) != tuple(range(1, len(runs) + 1)):
            raise SampleScenarioError("Scenario run numbers must be consecutive starting at 1.")

        replacements = tuple(dict(item) for item in values.get("replacements", ()))
        spares = tuple(int(item) for item in values.get("spares", ()))
        scenario = cls(
            scenario_id=scenario_id,
            description=str(values.get("description") or "").strip(),
            unit=unit,
            switch=switch,
            initial_channel_map=initial_map,
            installed_at_utc=installed_at,
            installed_by=installed_by,
            spares=spares,
            replacements=replacements,
            runs=runs,
            application_version=str(values.get("application_version") or "sample-data"),
            tag=SCENARIO_MARKER_PREFIX + scenario_id,
        )
        scenario.validate()
        return scenario

    def validate(self) -> None:
        if self.unit.unit_model not in {"OSX-100", "OSX-150"}:
            raise SampleScenarioError("Sample switch model must be OSX-100 or OSX-150.")
        if self.switch.switch_model != self.unit.unit_model:
            raise SampleScenarioError("Sample unit and switch models must match.")
        if self.switch.physical_channel_count < self.unit.front_panel_channel_count:
            raise SampleScenarioError("The sample switch must have enough physical ports.")
        if len(set(self.spares)) != len(self.spares):
            raise SampleScenarioError("Sample spare ports must be unique.")
        if any(port < 1 or port > self.switch.physical_channel_count for port in self.spares):
            raise SampleScenarioError("A sample spare port is outside switch capacity.")
        for replacement in self.replacements:
            required = {
                "logical_channel",
                "previous_physical_port",
                "replacement_physical_port",
                "reason",
                "replaced_by",
                "replaced_at_utc",
            }
            if not required.issubset(replacement):
                raise SampleScenarioError("A replacement record is missing a required field.")
            if int(replacement["logical_channel"]) not in self.initial_channel_map:
                raise SampleScenarioError("A replacement references an unknown logical channel.")
            if int(replacement["replacement_physical_port"]) > self.switch.physical_channel_count:
                raise SampleScenarioError("A replacement port exceeds switch capacity.")
        if self.runs[-1].purpose not in {"production", "engineering", "training", "calibration"}:
            raise SampleScenarioError("The final run has an invalid purpose.")

    def measurement_rows(self, run: SampleRun) -> tuple[dict[str, object], ...]:
        """Return deterministic, normalized two-wavelength measurement rows."""
        if run.explicit_measurements:
            rows = [dict(item) for item in run.explicit_measurements]
        else:
            generation = dict(run.generated_measurements or {})
            channels = [int(item) for item in generation.get("channels", ())]
            seed = int(generation.get("seed", 0))
            first = dict(generation.get("wavelength_1", {}))
            second = dict(generation.get("wavelength_2", {}))
            rng = random.Random(seed)
            rows = []
            for channel in channels:
                first_value = float(first.get("base", 1.0)) + rng.uniform(
                    -float(first.get("spread", 0.0)), float(first.get("spread", 0.0))
                )
                second_value = float(second.get("base", 1.0)) + rng.uniform(
                    -float(second.get("spread", 0.0)), float(second.get("spread", 0.0))
                )
                rows.append(
                    {
                        "logical_channel": channel,
                        "wavelength_1_il_db": round(first_value, 4),
                        "wavelength_2_il_db": round(second_value, 4),
                    }
                )
            for key, override in dict(generation.get("overrides", {})).items():
                channel = int(key)
                match = next((row for row in rows if int(row["logical_channel"]) == channel), None)
                if match is None:
                    raise SampleScenarioError(
                        f"Measurement override references channel {channel} not in generated channels."
                    )
                if isinstance(override, Mapping):
                    match.update(dict(override))
                else:
                    match["wavelength_1_il_db"] = override[0]
                    match["wavelength_2_il_db"] = override[1]
        mode = str(run.reference_snapshot.get("wavelength_mode", "SM")).upper()
        expected_wavelengths = (1310, 1550) if mode == "SM" else (850, 1300)
        normalized = []
        for row in rows:
            item = dict(row)
            item.setdefault("attempt_number", 1)
            item.setdefault("wavelength_1_nm", expected_wavelengths[0])
            item.setdefault("wavelength_2_nm", expected_wavelengths[1])
            normalized.append(item)
        return tuple(normalized)

    def run_uuid(self, run: SampleRun) -> UUID:
        return uuid5(SAMPLE_UUID_NAMESPACE, f"{self.scenario_id}|run|{run.number}")

    def measurement_uuid(self, run: SampleRun, row: Mapping[str, object]) -> UUID:
        return uuid5(
            SAMPLE_UUID_NAMESPACE,
            f"{self.scenario_id}|run|{run.number}|channel|{int(row['logical_channel'])}|attempt|{int(row.get('attempt_number', 1))}",
        )


@dataclass(frozen=True)
class SeedResult:
    scenario_id: str
    action: str
    unit_id: int | None
    run_ids: tuple[int, ...] = ()
    measurement_count: int = 0
    replacement_count: int = 0
    spare_count: int = 0


def load_scenario(path: Path) -> SampleScenario:
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            values = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise SampleScenarioError(f"Could not read scenario {path}: {error}") from error
    if not isinstance(values, Mapping):
        raise SampleScenarioError("Scenario root must be a JSON object.")
    return SampleScenario.from_mapping(values)


def scenario_summary(scenario: SampleScenario) -> dict[str, object]:
    return {
        "scenario_id": scenario.scenario_id,
        "description": scenario.description,
        "unit_serial": scenario.unit.main_board_serial,
        "switch_serial": scenario.switch.switch_serial,
        "model": scenario.unit.unit_model,
        "runs": len(scenario.runs),
        "measurements": sum(len(scenario.measurement_rows(run)) for run in scenario.runs),
        "replacements": len(scenario.replacements),
        "spares": len(scenario.spares),
    }


class SampleDatabaseSeeder:
    """Apply one validated scenario through ``DatabasePrimaryRunWorkflow``."""

    def __init__(self, workflow) -> None:
        self.workflow = workflow
        self.repositories = workflow.repositories

    def seed(self, scenario: SampleScenario) -> SeedResult:
        readiness = self.workflow.check_ready()
        if not getattr(readiness, "ready", False):
            raise SampleScenarioError(
                getattr(readiness, "operator_message", "Database is not ready.")
            )
        existing = self._existing_state(scenario)
        if existing == "complete":
            unit = self.repositories.get_by_main_board_serial(scenario.unit.main_board_serial)
            return SeedResult(
                scenario.scenario_id,
                "no-op",
                unit.unit_id if unit else None,
                measurement_count=sum(len(scenario.measurement_rows(run)) for run in scenario.runs),
                replacement_count=len(scenario.replacements),
                spare_count=len(scenario.spares),
            )
        if existing == "conflict":
            raise SampleScenarioError(
                f"Existing data conflicts with sample scenario {scenario.scenario_id}; "
                "the seeder will not modify or delete it."
            )

        assignment = self.workflow.assignments.resolve(
            scenario.unit,
            scenario.switch,
            installed_at_utc=scenario.installed_at_utc,
            installed_by=scenario.installed_by,
            initial_channel_map=scenario.initial_channel_map,
            notes=scenario.tag,
        )
        assignment_id = assignment.assignment.assignment_id
        for port in scenario.spares:
            self.workflow.replacements.designate_spare(
                assignment_id,
                port,
                scenario.installed_by,
                notes=scenario.tag,
                recorded_at_utc=scenario.installed_at_utc,
            )

        current_map = dict(scenario.initial_channel_map)
        run_ids = []
        measurement_count = 0
        for run in scenario.runs:
            run = self._validate_run_snapshot(scenario, run)
            record = self.workflow.lifecycle.start_run(
                assignment_id=assignment_id,
                tested_by=scenario.installed_by,
                wavelength_mode=str(run.reference_snapshot.get("wavelength_mode", "SM")),
                operating_band="O band",
                application_version=scenario.application_version,
                measurement_hardware={
                    "ilm": {"model": "OP815", "serial": "SAMPLE-OP815"},
                    "switch": {"model": scenario.switch.switch_model, "serial": scenario.switch.switch_serial},
                    "sample_scenario": scenario.scenario_id,
                },
                limit_snapshot=run.limit_snapshot,
                part_number_snapshot=scenario.unit.part_number,
                front_panel_channel_count=scenario.unit.front_panel_channel_count,
                run_purpose=run.purpose,
                analysis_status=run.analysis_status,
                analysis_exclusion_reason=run.analysis_exclusion_reason,
                notes=scenario.tag,
                client_run_uuid=scenario.run_uuid(run),
                started_at_utc=run.started_at_utc,
            )
            if record.run_number != run.number:
                raise SampleScenarioError(
                    f"Expected sample Run {run.number}, but the database allocated Run {record.run_number}."
                )
            run_ids.append(record.run_id)
            for replacement in scenario.replacements:
                if int(replacement.get("related_run_number", 0)) != run.number:
                    continue
                logical = int(replacement["logical_channel"])
                self.workflow.replacements.record_replacement(
                    assignment_id=assignment_id,
                    logical_channel=logical,
                    previous_physical_port=current_map[logical],
                    replacement_physical_port=int(replacement["replacement_physical_port"]),
                    reason=str(replacement["reason"]),
                    replaced_by=str(replacement["replaced_by"]),
                    related_run_id=record.run_id,
                    notes=scenario.tag,
                    replaced_at_utc=_parse_utc(replacement["replaced_at_utc"]),
                )
                current_map[logical] = int(replacement["replacement_physical_port"])
            for row in scenario.measurement_rows(run):
                logical = int(row["logical_channel"])
                pending = self.workflow.measurements.prepare_measurement(
                    run_id=record.run_id,
                    logical_channel=logical,
                    physical_port=int(row.get("physical_port", current_map[logical])),
                    wavelength_1_nm=int(row["wavelength_1_nm"]),
                    wavelength_1_il_db=Decimal(str(row["wavelength_1_il_db"])),
                    wavelength_2_nm=int(row["wavelength_2_nm"]),
                    wavelength_2_il_db=Decimal(str(row["wavelength_2_il_db"])),
                    reference_snapshot=run.reference_snapshot,
                    written_by=scenario.installed_by,
                    written_at_utc=run.started_at_utc
                    + timedelta(seconds=logical),
                    measurement_uuid=scenario.measurement_uuid(run, row),
                )
                self.workflow.commit_measurement(pending)
                measurement_count += 1
            self.workflow.lifecycle.finish_run(
                record.run_id,
                run.completion_status,
                run.ended_at_utc,
            )
            if run.analysis_status != "included":
                self.workflow.lifecycle.set_analysis_status(
                    record.run_id,
                    run.analysis_status,
                    exclusion_reason=run.analysis_exclusion_reason,
                )
        self.verify(scenario)
        return SeedResult(
            scenario.scenario_id,
            "seeded",
            assignment.unit.unit_id,
            tuple(run_ids),
            measurement_count,
            len(scenario.replacements),
            len(scenario.spares),
        )

    def verify(self, scenario: SampleScenario) -> None:
        unit = self.repositories.get_by_main_board_serial(scenario.unit.main_board_serial)
        switch = self.repositories.get_by_serial(scenario.switch.switch_serial)
        if unit is None or switch is None:
            raise SampleScenarioError("Verification could not find the seeded unit or switch.")
        assignment = self.repositories.get_active(unit.unit_id)
        if assignment is None or assignment.switch_id != switch.switch_id:
            raise SampleScenarioError("Verification could not find the active sample assignment.")
        runs = self.repositories.list_for_assignment(assignment.assignment_id)
        if len(runs) != len(scenario.runs):
            raise SampleScenarioError("Verification found an unexpected number of sample runs.")
        current_map = dict(scenario.initial_channel_map)
        for expected in scenario.runs:
            actual = next((item for item in runs if item.run_number == expected.number), None)
            if actual is None or actual.notes != scenario.tag:
                raise SampleScenarioError(f"Verification could not find sample Run {expected.number}.")
            if (
                actual.completion_status != expected.completion_status
                or actual.run_purpose != expected.purpose
                or actual.analysis_status != expected.analysis_status
            ):
                raise SampleScenarioError(f"Sample Run {expected.number} has the wrong status or purpose.")
            for replacement in scenario.replacements:
                if int(replacement.get("related_run_number", 0)) == expected.number:
                    current_map[int(replacement["logical_channel"])] = int(
                        replacement["replacement_physical_port"]
                    )
            measurements = self.repositories.history_for_run(actual.run_id)
            expected_rows = scenario.measurement_rows(expected)
            if len(measurements) != len(expected_rows):
                raise SampleScenarioError(f"Sample Run {expected.number} has the wrong measurement count.")
            for row in expected_rows:
                logical = int(row["logical_channel"])
                match = next((item for item in measurements if item.logical_channel == logical), None)
                if match is None or match.attempt_number != int(row.get("attempt_number", 1)):
                    raise SampleScenarioError(f"Sample Run {expected.number} is missing channel {logical}.")
                if match.physical_port != int(row.get("physical_port", current_map[logical])):
                    raise SampleScenarioError(f"Sample Run {expected.number} has an unexpected physical port.")
        snapshot = self.repositories.routing_snapshot_for_assignment(assignment.assignment_id)
        replacement_records = snapshot[1]
        if len(replacement_records) != len(scenario.replacements):
            raise SampleScenarioError("Verification found the wrong replacement history count.")
        if tuple(snapshot[3]) != tuple(sorted(scenario.spares)):
            raise SampleScenarioError("Verification found the wrong active spare ports.")

    def _existing_state(self, scenario: SampleScenario) -> str:
        unit = self.repositories.get_by_main_board_serial(scenario.unit.main_board_serial)
        switch = self.repositories.get_by_serial(scenario.switch.switch_serial)
        if unit is None and switch is None:
            return "new"
        if unit is None or switch is None:
            return "conflict"
        runs = self.repositories.list_for_unit(unit.unit_id)
        marked = [item for item in runs if item.notes == scenario.tag]
        if not runs and not marked:
            return "conflict"
        if len(marked) == len(scenario.runs):
            try:
                self.verify(scenario)
            except SampleScenarioError:
                return "conflict"
            return "complete"
        return "conflict"

    @staticmethod
    def _validate_run_snapshot(scenario: SampleScenario, run: SampleRun) -> SampleRun:
        try:
            ReferenceSnapshot.from_mapping(run.reference_snapshot)
            LimitProfile.from_mapping(run.limit_snapshot)
        except (KeyError, TypeError, ValueError) as error:
            raise SampleScenarioError(
                f"Run {run.number} has an invalid reference or limit snapshot."
            ) from error
        rows = scenario.measurement_rows(run)
        channels = {int(item["logical_channel"]) for item in rows}
        if len(channels) != len(rows):
            raise SampleScenarioError(f"Run {run.number} contains duplicate logical channels.")
        if any(channel not in scenario.initial_channel_map for channel in channels):
            raise SampleScenarioError(f"Run {run.number} contains an unknown logical channel.")
        return run


def _parse_run(values: Mapping[str, object]) -> SampleRun:
    reference = dict(values["reference_snapshot"])
    limit = dict(values["limit_snapshot"])
    explicit = tuple(dict(item) for item in values.get("measurements", ()))
    generated = values.get("generated_measurements")
    purpose = normalize_run_purpose(values.get("run_purpose", "production"))
    analysis_status = str(values.get("analysis_status", "excluded"))
    if analysis_status not in {"pending", "included", "excluded", "superseded"}:
        raise ValueError("Invalid sample analysis status")
    return SampleRun(
        number=int(values["run_number"]),
        purpose=purpose,
        completion_status=str(values.get("completion_status", "complete")),
        analysis_status=analysis_status,
        analysis_exclusion_reason=(
            str(values.get("analysis_exclusion_reason") or "").strip() or None
        ),
        started_at_utc=_parse_utc(values["started_at_utc"]),
        ended_at_utc=_parse_utc(values["ended_at_utc"]),
        reference_snapshot=reference,
        limit_snapshot=limit,
        explicit_measurements=explicit,
        generated_measurements=dict(generated) if generated is not None else None,
        notes=str(values.get("notes") or "").strip() or None,
    )


def _parse_utc(value: object) -> datetime:
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Scenario timestamps must include a UTC offset")
    return parsed.astimezone(timezone.utc)


__all__ = [
    "SampleDatabaseSeeder",
    "SampleScenario",
    "SampleScenarioError",
    "SeedResult",
    "load_scenario",
    "scenario_summary",
]
