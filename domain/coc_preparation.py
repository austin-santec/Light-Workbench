"""Pure preparation and validation rules for production COC exports."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from pathlib import Path
from typing import Mapping, Sequence

from .limit_profiles import normalize_switch_model
from .models import MeasurementRecord
from .replacements import ReplacementReading, analyze_replacements


COC_MAX_CHANNELS = 48
COC_FORMAL_LIMIT_DB = 2.5
COC_OPTIMIZATION_LIMIT_DB = 2.25


@dataclass(frozen=True)
class CocSourceRun:
    """One persisted run that may contribute accepted readings to a COC."""

    run_number: int
    source_path: Path
    measurements: tuple[MeasurementRecord, ...]
    metadata: Mapping[str, str] = field(default_factory=dict)
    criteria: Mapping[str, object] | None = None


@dataclass(frozen=True)
class CocPreparedChannel:
    """One final logical-channel result with its report provenance."""

    record: MeasurementRecord
    source_run_number: int
    source_path: Path
    physical_port: int
    physical_port_inferred: bool = False
    supplemental_override: bool = False


@dataclass(frozen=True)
class CocFailure:
    """A wavelength value that prevents production COC publication."""

    channel: int
    wavelength_nm: int
    value_db: float
    source_run_number: int
    physical_port: int


@dataclass(frozen=True)
class CocValidationIssue:
    """A non-measurement consistency problem that blocks COC export."""

    code: str
    message: str


@dataclass(frozen=True)
class CocPreparationResult:
    """Final report data, validation evidence, and advisory optimizations."""

    front_panel_channel_count: int
    channels: tuple[CocPreparedChannel, ...]
    missing_channels: tuple[int, ...]
    failures: tuple[CocFailure, ...]
    invalid_readings: tuple[CocValidationIssue, ...]
    validation_issues: tuple[CocValidationIssue, ...]
    optimization_channels: tuple[int, ...]
    optimization_recommendations: tuple[Mapping[str, object], ...]
    effective_criteria: Mapping[str, object]
    base_run_number: int
    supplemental_run_number: int | None
    template_capacity: int

    @property
    def eligible(self) -> bool:
        return not (
            self.missing_channels
            or self.failures
            or self.invalid_readings
            or self.validation_issues
        )

    @property
    def measurements(self) -> tuple[MeasurementRecord, ...]:
        return tuple(channel.record for channel in self.channels)

    @property
    def overridden_channels(self) -> tuple[CocPreparedChannel, ...]:
        return tuple(
            channel for channel in self.channels if channel.supplemental_override
        )


def infer_front_panel_channel_count(part_number: str) -> int | None:
    """Extract the known three-digit channel field from an OSX part number."""
    match = re.match(
        r"^OSX-(?:100|150)-[^-]+-(\d{3})(?:-|$)",
        str(part_number or "").strip(),
        re.IGNORECASE,
    )
    if match is None:
        return None
    count = int(match.group(1))
    return count if 1 <= count <= COC_MAX_CHANNELS else None


def prepare_coc(
    base_run: CocSourceRun,
    front_panel_channel_count: int,
    *,
    supplemental_run: CocSourceRun | None = None,
    completed_replacements: Sequence[Mapping[str, object]] = (),
    designated_spares: Sequence[int] = (),
) -> CocPreparationResult:
    """Merge explicitly selected runs and validate a production COC dataset."""
    count = int(front_panel_channel_count)
    if not 1 <= count <= COC_MAX_CHANNELS:
        raise ValueError("Front-panel channel count must be between 1 and 48.")
    if supplemental_run is not None and supplemental_run.run_number == base_run.run_number:
        raise ValueError("Base and replacement/retest runs must be different.")

    validation_issues = list(_compatibility_issues(base_run, supplemental_run))
    replacements = _replacement_map(completed_replacements)
    base_records = _index_last(base_run.measurements)
    supplemental_records = (
        _index_last(supplemental_run.measurements)
        if supplemental_run is not None
        else {}
    )

    prepared = []
    missing = []
    invalid = []
    failures = []
    assigned_ports: dict[int, int] = {}

    for logical_channel in range(1, count + 1):
        base_record = base_records.get(logical_channel)
        supplemental_record = supplemental_records.get(logical_channel)
        selected = supplemental_record or base_record
        if selected is None:
            missing.append(logical_channel)
            continue

        source = supplemental_run if supplemental_record is not None else base_run
        assert source is not None
        inferred = selected.physical_port is None
        physical_port = (
            logical_channel if selected.physical_port is None else int(selected.physical_port)
        )
        is_override = supplemental_record is not None

        if is_override and base_record is not None:
            base_inferred = base_record.physical_port is None
            base_port = (
                logical_channel
                if base_record.physical_port is None
                else int(base_record.physical_port)
            )
            expected_replacement = replacements.get(base_port)
            if inferred and expected_replacement is not None:
                validation_issues.append(
                    CocValidationIssue(
                        "unverifiable_replacement_port",
                        "Channel %d in Run %d has no persisted physical port; "
                        "the recorded replacement from port %d to port %d cannot be verified."
                        % (
                            logical_channel,
                            supplemental_run.run_number,
                            base_port,
                            expected_replacement,
                        ),
                    )
                )
            elif physical_port != base_port and physical_port != expected_replacement:
                validation_issues.append(
                    CocValidationIssue(
                        "unrecorded_physical_port_change",
                        "Channel %d changes from physical port %d in Run %d to "
                        "physical port %d in Run %d without a matching completed replacement."
                        % (
                            logical_channel,
                            base_port,
                            base_run.run_number,
                            physical_port,
                            supplemental_run.run_number,
                        ),
                    )
                )
            elif base_inferred and physical_port != base_port:
                # A legacy base may safely infer its original logical port only
                # when the explicit supplemental route matches a recorded swap.
                if expected_replacement != physical_port:
                    validation_issues.append(
                        CocValidationIssue(
                            "unverifiable_base_physical_port",
                            "Channel %d has no persisted base physical port, so its "
                            "replacement route cannot be verified." % logical_channel,
                        )
                    )

        if physical_port < 1:
            validation_issues.append(
                CocValidationIssue(
                    "invalid_physical_port",
                    "Channel %d has invalid physical port %d."
                    % (logical_channel, physical_port),
                )
            )
        previous_channel = assigned_ports.get(physical_port)
        if previous_channel is not None and previous_channel != logical_channel:
            validation_issues.append(
                CocValidationIssue(
                    "duplicate_active_physical_port",
                    "Physical port %d is assigned to both logical channels %d and %d."
                    % (physical_port, previous_channel, logical_channel),
                )
            )
        assigned_ports[physical_port] = logical_channel

        prepared_channel = CocPreparedChannel(
            record=selected,
            source_run_number=source.run_number,
            source_path=source.source_path,
            physical_port=physical_port,
            physical_port_inferred=inferred,
            supplemental_override=is_override,
        )
        prepared.append(prepared_channel)
        invalid.extend(_invalid_reading_issues(prepared_channel))
        failures.extend(_formal_failures(prepared_channel))

    optimization_channels = tuple(
        channel.record.channel
        for channel in prepared
        if _is_optimization_reading(channel.record)
    )
    recommendations = ()
    if not missing and not invalid and not failures and not validation_issues:
        recommendations = _optimization_recommendations(
            prepared,
            base_run,
            supplemental_run,
            count,
            designated_spares,
        )

    return CocPreparationResult(
        front_panel_channel_count=count,
        channels=tuple(prepared),
        missing_channels=tuple(missing),
        failures=tuple(failures),
        invalid_readings=tuple(invalid),
        validation_issues=tuple(validation_issues),
        optimization_channels=optimization_channels,
        optimization_recommendations=tuple(recommendations),
        effective_criteria=dict(base_run.criteria or {}),
        base_run_number=base_run.run_number,
        supplemental_run_number=(
            supplemental_run.run_number if supplemental_run is not None else None
        ),
        template_capacity=45 if count <= 45 else 48,
    )


def _index_last(
    measurements: Sequence[MeasurementRecord],
) -> dict[int, MeasurementRecord]:
    return {int(record.channel): record for record in measurements}


def _normalized_metadata(run: CocSourceRun, key: str) -> str:
    return str(run.metadata.get(key) or "").strip()


def _compatibility_issues(
    base_run: CocSourceRun,
    supplemental_run: CocSourceRun | None,
) -> tuple[CocValidationIssue, ...]:
    issues = []
    base_model = normalize_switch_model(
        str((base_run.criteria or {}).get("model") or "")
    )
    if base_model != "OSX-150":
        issues.append(
            CocValidationIssue(
                "unsupported_coc_model",
                "The approved bundled COC templates support OSX-150 runs only; "
                "the base run reports %s." % (base_model or "an unknown model"),
            )
        )
    if supplemental_run is None:
        return tuple(issues)
    for key, label, required in (
        ("Main board serial", "Main Board serial", True),
        ("Part number", "Part Number", False),
        ("Switch serial", "Switch serial", True),
        ("Operating band", "Operating band", True),
    ):
        base_value = _normalized_metadata(base_run, key)
        supplemental_value = _normalized_metadata(supplemental_run, key)
        if required and (not base_value or not supplemental_value):
            issues.append(
                CocValidationIssue(
                    "missing_compatibility_metadata",
                    "%s must be recorded in both selected runs." % label,
                )
            )
        elif base_value and supplemental_value and base_value.casefold() != supplemental_value.casefold():
            issues.append(
                CocValidationIssue(
                    "incompatible_%s" % key.lower().replace(" ", "_"),
                    "%s does not match between Run %d (%s) and Run %d (%s)."
                    % (
                        label,
                        base_run.run_number,
                        base_value,
                        supplemental_run.run_number,
                        supplemental_value,
                    ),
                )
            )

    base_criteria = dict(base_run.criteria or {})
    supplemental_criteria = dict(supplemental_run.criteria or {})
    if bool(base_criteria) != bool(supplemental_criteria):
        issues.append(
            CocValidationIssue(
                "incompatible_criteria",
                "Both selected runs must contain compatible saved criteria.",
            )
        )
    elif base_criteria and supplemental_criteria:
        base_signature = _criteria_signature(base_criteria)
        supplemental_signature = _criteria_signature(supplemental_criteria)
        if base_signature != supplemental_signature:
            issues.append(
                CocValidationIssue(
                    "incompatible_criteria",
                    "The saved switch model or quality criteria differ between Run %d and Run %d."
                    % (base_run.run_number, supplemental_run.run_number),
                )
            )
    return tuple(issues)


def _criteria_signature(criteria: Mapping[str, object]) -> tuple[object, ...]:
    warning = criteria.get("warning_above_db")
    return (
        normalize_switch_model(str(criteria.get("model") or "LEGACY")),
        bool(criteria.get("warning_enabled", True)),
        None if warning in (None, "") else float(warning),
        float(criteria.get("fail_above_db", COC_FORMAL_LIMIT_DB)),
    )


def _replacement_map(
    completed_replacements: Sequence[Mapping[str, object]],
) -> dict[int, int]:
    result = {}
    for item in completed_replacements:
        try:
            current = int(item["current_port"])
            replacement = int(item["replacement_port"])
        except (KeyError, TypeError, ValueError):
            continue
        if current > 0 and replacement > 0:
            result[current] = replacement
    return result


def _rounded_loss(value: float) -> float:
    return float("%.4f" % float(value))


def _invalid_reading_issues(
    channel: CocPreparedChannel,
) -> tuple[CocValidationIssue, ...]:
    issues = []
    for wavelength, value in (
        (1310, channel.record.loss_1310),
        (1550, channel.record.loss_1550),
    ):
        if not math.isfinite(float(value)):
            issues.append(
                CocValidationIssue(
                    "non_finite_reading",
                    "Channel %d from Run %d has a non-finite %d nm reading."
                    % (channel.record.channel, channel.source_run_number, wavelength),
                )
            )
        elif _rounded_loss(value) < 0:
            issues.append(
                CocValidationIssue(
                    "negative_reading",
                    "Channel %d from Run %d has negative %d nm loss %.4f dB."
                    % (
                        channel.record.channel,
                        channel.source_run_number,
                        wavelength,
                        float(value),
                    ),
                )
            )
    return tuple(issues)


def _formal_failures(channel: CocPreparedChannel) -> tuple[CocFailure, ...]:
    failures = []
    for wavelength, value in (
        (1310, channel.record.loss_1310),
        (1550, channel.record.loss_1550),
    ):
        if math.isfinite(float(value)) and _rounded_loss(value) >= COC_FORMAL_LIMIT_DB:
            failures.append(
                CocFailure(
                    channel.record.channel,
                    wavelength,
                    float(value),
                    channel.source_run_number,
                    channel.physical_port,
                )
            )
    return tuple(failures)


def _is_optimization_reading(record: MeasurementRecord) -> bool:
    values = (_rounded_loss(record.loss_1310), _rounded_loss(record.loss_1550))
    return any(
        COC_OPTIMIZATION_LIMIT_DB < value < COC_FORMAL_LIMIT_DB
        for value in values
    )


def _optimization_recommendations(
    prepared: Sequence[CocPreparedChannel],
    base_run: CocSourceRun,
    supplemental_run: CocSourceRun | None,
    channel_count: int,
    designated_spares: Sequence[int],
) -> tuple[Mapping[str, object], ...]:
    assigned_ports = {channel.physical_port for channel in prepared}
    readings_by_port: dict[int, ReplacementReading] = {}
    for source in (base_run, supplemental_run):
        if source is None:
            continue
        for record in source.measurements:
            port = record.physical_port
            if port is None:
                port = record.channel
            port = int(port)
            if port in assigned_ports:
                continue
            if not (
                math.isfinite(float(record.loss_1310))
                and math.isfinite(float(record.loss_1550))
            ):
                continue
            readings_by_port[port] = ReplacementReading(
                port,
                float(record.loss_1310),
                float(record.loss_1550),
            )

    # Designated-spare membership is useful only when that port has a measured
    # reading; unmeasured spares cannot support an optimization recommendation.
    spare_ports = set()
    for value in designated_spares:
        try:
            port = int(value)
        except (TypeError, ValueError):
            continue
        if port > 0:
            spare_ports.add(port)
    extras = sorted(
        readings_by_port.values(),
        key=lambda reading: (reading.port not in spare_ports, reading.port),
    )
    production = [
        MeasurementRecord(
            channel.record.channel,
            channel.record.loss_1310,
            channel.record.loss_1550,
            channel.physical_port,
            channel.record.reference_snapshot,
        )
        for channel in prepared
    ]
    result = analyze_replacements(
        production,
        extras,
        channel_count,
        COC_OPTIMIZATION_LIMIT_DB,
        fail_limit=COC_FORMAL_LIMIT_DB,
        model="OSX-150",
    )
    return tuple(result.get("recommendations", ()))


__all__ = [
    "COC_FORMAL_LIMIT_DB",
    "COC_MAX_CHANNELS",
    "COC_OPTIMIZATION_LIMIT_DB",
    "CocFailure",
    "CocPreparationResult",
    "CocPreparedChannel",
    "CocSourceRun",
    "CocValidationIssue",
    "infer_front_panel_channel_count",
    "prepare_coc",
]
