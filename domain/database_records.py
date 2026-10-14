"""Database-neutral records for future authoritative run persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from types import MappingProxyType
from typing import Mapping
from uuid import UUID


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def require_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a UTC offset")
    return value.astimezone(timezone.utc)


def require_text(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def require_positive(value: int, label: str) -> int:
    result = int(value)
    if result <= 0:
        raise ValueError(f"{label} must be positive")
    return result


def immutable_mapping(value: Mapping | None) -> Mapping:
    return MappingProxyType(dict(value or {}))


LOSS_QUANTUM = Decimal("0.0001")


def require_loss(value, label: str) -> Decimal:
    if value is None:
        raise ValueError(f"{label} is required")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    if result < 0:
        raise ValueError(f"{label} cannot be negative")
    return result.quantize(LOSS_QUANTUM, rounding=ROUND_HALF_UP)


def require_snapshot(value: Mapping | None, label: str) -> Mapping:
    snapshot = immutable_mapping(value)
    if not snapshot:
        raise ValueError(f"{label} is required")
    return snapshot


@dataclass(frozen=True)
class UnitRecord:
    unit_id: int
    main_board_serial: str
    part_number: str | None = None
    front_panel_channel_count: int | None = None
    unit_model: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class SwitchRecord:
    switch_id: int
    switch_serial: str
    switch_model: str
    physical_channel_count: int
    firmware_version: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class AssignmentRecord:
    assignment_id: int
    unit_id: int
    switch_id: int
    installed_at_utc: datetime
    installed_by: str
    initial_channel_map: Mapping[int, int]
    removed_at_utc: datetime | None = None
    removed_by: str | None = None
    removal_reason: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "initial_channel_map", immutable_mapping(self.initial_channel_map))


@dataclass(frozen=True)
class RunRecord:
    run_id: int
    assignment_id: int
    run_number: int
    client_run_uuid: UUID
    run_started_at_utc: datetime
    tested_by: str
    wavelength_mode: str
    operating_band: str
    application_version: str
    measurement_hardware: Mapping
    limit_snapshot: Mapping
    completion_status: str = "in_progress"
    run_ended_at_utc: datetime | None = None
    run_purpose: str = "production"
    analysis_status: str = "pending"
    analysis_exclusion_reason: str | None = None
    superseded_by_run_id: int | None = None
    part_number_snapshot: str | None = None
    front_panel_channel_count: int | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "measurement_hardware",
            immutable_mapping(self.measurement_hardware),
        )
        object.__setattr__(self, "limit_snapshot", immutable_mapping(self.limit_snapshot))


@dataclass(frozen=True)
class MeasurementRecord:
    measurement_id: int
    measurement_uuid: UUID
    run_id: int
    logical_channel: int
    attempt_number: int
    wavelength_1_nm: int
    wavelength_1_il_db: Decimal
    wavelength_2_nm: int
    wavelength_2_il_db: Decimal
    reference_snapshot: Mapping
    written_at_utc: datetime
    written_by: str
    physical_port: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "wavelength_1_il_db",
            require_loss(self.wavelength_1_il_db, "First insertion loss"),
        )
        object.__setattr__(
            self,
            "wavelength_2_il_db",
            require_loss(self.wavelength_2_il_db, "Second insertion loss"),
        )
        object.__setattr__(
            self,
            "reference_snapshot",
            require_snapshot(self.reference_snapshot, "Reference snapshot"),
        )


@dataclass(frozen=True)
class ReplacementRecord:
    replacement_id: int
    assignment_id: int
    logical_channel: int
    previous_physical_port: int
    replacement_physical_port: int
    reason: str
    replaced_by: str
    replaced_at_utc: datetime
    related_run_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True)
class SpareEventRecord:
    spare_event_id: int
    assignment_id: int
    physical_port: int
    action: str
    recorded_by: str
    recorded_at_utc: datetime
    notes: str | None = None


@dataclass(frozen=True)
class ChannelMapRecord:
    """One baseline/effective logical-channel route for an assignment."""

    assignment_id: int
    unit_id: int
    switch_id: int
    logical_channel: int
    initial_physical_port: int
    effective_physical_port: int
    is_replaced: bool
    latest_replacement_id: int | None = None
    latest_replaced_at_utc: datetime | None = None


@dataclass(frozen=True)
class UnitSpec:
    main_board_serial: str
    part_number: str | None = None
    front_panel_channel_count: int | None = None
    unit_model: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "main_board_serial", require_text(self.main_board_serial, "Main-board serial")
        )
        if self.front_panel_channel_count is not None:
            require_positive(self.front_panel_channel_count, "Front-panel channel count")


@dataclass(frozen=True)
class SwitchSpec:
    switch_serial: str
    switch_model: str
    physical_channel_count: int
    firmware_version: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "switch_serial", require_text(self.switch_serial, "Switch serial")
        )
        object.__setattr__(
            self, "switch_model", require_text(self.switch_model, "Switch model")
        )
        require_positive(self.physical_channel_count, "Physical channel count")


@dataclass(frozen=True)
class AssignmentSpec:
    unit_id: int
    switch_id: int
    installed_at_utc: datetime
    installed_by: str
    initial_channel_map: Mapping[int, int]
    notes: str | None = None

    def __post_init__(self) -> None:
        require_positive(self.unit_id, "Unit ID")
        require_positive(self.switch_id, "Switch ID")
        object.__setattr__(
            self, "installed_at_utc", require_utc(self.installed_at_utc, "Installation time")
        )
        object.__setattr__(self, "installed_by", require_text(self.installed_by, "Installer"))
        channel_map = {
            require_positive(logical, "Logical channel"): require_positive(
                physical, "Physical port"
            )
            for logical, physical in self.initial_channel_map.items()
        }
        object.__setattr__(self, "initial_channel_map", immutable_mapping(channel_map))


@dataclass(frozen=True)
class RunSpec:
    assignment_id: int
    run_number: int
    client_run_uuid: UUID
    run_started_at_utc: datetime
    tested_by: str
    wavelength_mode: str
    operating_band: str
    application_version: str
    measurement_hardware: Mapping = field(default_factory=dict)
    limit_snapshot: Mapping = field(default_factory=dict)
    run_purpose: str = "production"
    analysis_status: str = "pending"
    analysis_exclusion_reason: str | None = None
    part_number_snapshot: str | None = None
    front_panel_channel_count: int | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        require_positive(self.assignment_id, "Assignment ID")
        require_positive(self.run_number, "Run number")
        object.__setattr__(
            self, "run_started_at_utc", require_utc(self.run_started_at_utc, "Run start time")
        )
        object.__setattr__(self, "tested_by", require_text(self.tested_by, "Tested by"))
        mode = str(self.wavelength_mode).upper()
        if mode not in {"SM", "MM"}:
            raise ValueError("Wavelength mode must be SM or MM")
        object.__setattr__(self, "wavelength_mode", mode)
        require_text(self.operating_band, "Operating band")
        require_text(self.application_version, "Application version")
        if self.run_purpose not in {"production", "engineering", "training", "calibration"}:
            raise ValueError("Invalid run purpose")
        if self.analysis_status not in {"pending", "included", "excluded", "superseded"}:
            raise ValueError("Invalid analysis status")
        if self.analysis_status == "excluded" and not str(
            self.analysis_exclusion_reason or ""
        ).strip():
            raise ValueError("Excluded runs require an analysis exclusion reason")
        if self.front_panel_channel_count is not None:
            require_positive(self.front_panel_channel_count, "Front-panel channel count")
        object.__setattr__(
            self,
            "measurement_hardware",
            immutable_mapping(self.measurement_hardware),
        )
        object.__setattr__(self, "limit_snapshot", immutable_mapping(self.limit_snapshot))


@dataclass(frozen=True)
class RunStartSpec:
    """Run context before the repository allocates its per-unit run number."""

    assignment_id: int
    client_run_uuid: UUID
    run_started_at_utc: datetime
    tested_by: str
    wavelength_mode: str
    operating_band: str
    application_version: str
    measurement_hardware: Mapping = field(default_factory=dict)
    limit_snapshot: Mapping = field(default_factory=dict)
    run_purpose: str = "production"
    analysis_status: str = "pending"
    analysis_exclusion_reason: str | None = None
    part_number_snapshot: str | None = None
    front_panel_channel_count: int | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        validated = self.with_run_number(1)
        if validated.analysis_status == "superseded":
            raise ValueError("A new run cannot begin in superseded analysis state")
        for name in (
            "run_started_at_utc",
            "tested_by",
            "wavelength_mode",
            "measurement_hardware",
            "limit_snapshot",
        ):
            object.__setattr__(self, name, getattr(validated, name))

    def with_run_number(self, run_number: int) -> RunSpec:
        return RunSpec(
            assignment_id=self.assignment_id,
            run_number=run_number,
            client_run_uuid=self.client_run_uuid,
            run_started_at_utc=self.run_started_at_utc,
            tested_by=self.tested_by,
            wavelength_mode=self.wavelength_mode,
            operating_band=self.operating_band,
            application_version=self.application_version,
            measurement_hardware=self.measurement_hardware,
            limit_snapshot=self.limit_snapshot,
            run_purpose=self.run_purpose,
            analysis_status=self.analysis_status,
            analysis_exclusion_reason=self.analysis_exclusion_reason,
            part_number_snapshot=self.part_number_snapshot,
            front_panel_channel_count=self.front_panel_channel_count,
            notes=self.notes,
        )


@dataclass(frozen=True)
class MeasurementSpec:
    measurement_uuid: UUID
    run_id: int
    logical_channel: int
    attempt_number: int
    wavelength_1_nm: int
    wavelength_1_il_db: Decimal
    wavelength_2_nm: int
    wavelength_2_il_db: Decimal
    reference_snapshot: Mapping
    written_at_utc: datetime
    written_by: str
    physical_port: int | None = None

    def __post_init__(self) -> None:
        require_positive(self.run_id, "Run ID")
        require_positive(self.logical_channel, "Logical channel")
        require_positive(self.attempt_number, "Attempt number")
        require_positive(self.wavelength_1_nm, "First wavelength")
        require_positive(self.wavelength_2_nm, "Second wavelength")
        if self.wavelength_1_nm == self.wavelength_2_nm:
            raise ValueError("Measurement wavelengths must be different")
        object.__setattr__(
            self,
            "wavelength_1_il_db",
            require_loss(self.wavelength_1_il_db, "First insertion loss"),
        )
        object.__setattr__(
            self,
            "wavelength_2_il_db",
            require_loss(self.wavelength_2_il_db, "Second insertion loss"),
        )
        if self.physical_port is not None:
            require_positive(self.physical_port, "Physical port")
        object.__setattr__(
            self, "written_at_utc", require_utc(self.written_at_utc, "Write time")
        )
        object.__setattr__(self, "written_by", require_text(self.written_by, "Write operator"))
        object.__setattr__(
            self,
            "reference_snapshot",
            require_snapshot(self.reference_snapshot, "Reference snapshot"),
        )


@dataclass(frozen=True)
class MeasurementWriteSpec:
    """A complete pending Write IL sample before attempt allocation."""

    measurement_uuid: UUID
    run_id: int
    logical_channel: int
    wavelength_1_nm: int
    wavelength_1_il_db: Decimal
    wavelength_2_nm: int
    wavelength_2_il_db: Decimal
    reference_snapshot: Mapping
    written_at_utc: datetime
    written_by: str
    physical_port: int | None = None

    def __post_init__(self) -> None:
        validated = self.with_attempt_number(1)
        for name in (
            "wavelength_1_il_db",
            "wavelength_2_il_db",
            "reference_snapshot",
            "written_at_utc",
            "written_by",
        ):
            object.__setattr__(self, name, getattr(validated, name))

    def with_attempt_number(self, attempt_number: int) -> MeasurementSpec:
        return MeasurementSpec(
            measurement_uuid=self.measurement_uuid,
            run_id=self.run_id,
            logical_channel=self.logical_channel,
            attempt_number=attempt_number,
            wavelength_1_nm=self.wavelength_1_nm,
            wavelength_1_il_db=self.wavelength_1_il_db,
            wavelength_2_nm=self.wavelength_2_nm,
            wavelength_2_il_db=self.wavelength_2_il_db,
            reference_snapshot=self.reference_snapshot,
            written_at_utc=self.written_at_utc,
            written_by=self.written_by,
            physical_port=self.physical_port,
        )


@dataclass(frozen=True)
class ReplacementSpec:
    assignment_id: int
    logical_channel: int
    previous_physical_port: int
    replacement_physical_port: int
    reason: str
    replaced_by: str
    replaced_at_utc: datetime
    related_run_id: int | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        require_positive(self.assignment_id, "Assignment ID")
        require_positive(self.logical_channel, "Logical channel")
        require_positive(self.previous_physical_port, "Previous physical port")
        require_positive(self.replacement_physical_port, "Replacement physical port")
        if self.previous_physical_port == self.replacement_physical_port:
            raise ValueError("Replacement physical port must differ from previous port")
        require_text(self.reason, "Replacement reason")
        require_text(self.replaced_by, "Replacement operator")
        object.__setattr__(
            self, "replaced_at_utc", require_utc(self.replaced_at_utc, "Replacement time")
        )


@dataclass(frozen=True)
class SpareEventSpec:
    assignment_id: int
    physical_port: int
    action: str
    recorded_by: str
    recorded_at_utc: datetime
    notes: str | None = None

    def __post_init__(self) -> None:
        require_positive(self.assignment_id, "Assignment ID")
        require_positive(self.physical_port, "Spare physical port")
        if self.action not in {"designated", "undesignated"}:
            raise ValueError("Invalid spare action")
        require_text(self.recorded_by, "Spare operator")
        object.__setattr__(
            self, "recorded_at_utc", require_utc(self.recorded_at_utc, "Spare event time")
        )


__all__ = [name for name in globals() if name.endswith(("Record", "Spec"))]
