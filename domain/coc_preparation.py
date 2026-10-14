"""Pure preparation and validation rules for production COC exports."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Mapping, Sequence

from .limit_profiles import normalize_switch_model
from .models import MeasurementRecord
from .part_numbers import infer_front_panel_channel_count
from .replacements import ReplacementReading, analyze_replacements


COC_MAX_CHANNELS = 48
COC_FORMAL_LIMIT_DB = 2.5
COC_OPTIMIZATION_LIMIT_DB = 2.25


@dataclass(frozen=True)
class CocSourceRun:
    """One persisted run that may contribute accepted readings to a COC."""

    run_number: int
    source_path: Path | None
    measurements: tuple[MeasurementRecord, ...]
    metadata: Mapping[str, str] = field(default_factory=dict)
    criteria: Mapping[str, object] | None = None
    source_identifier: str = ""


@dataclass(frozen=True)
class CocPreparedChannel:
    """One final logical-channel result with its report provenance."""

    record: MeasurementRecord
    source_run_number: int
    source_path: Path | None
    physical_port: int
    physical_port_inferred: bool = False
    supplemental_override: bool = False
    source_identifier: str = ""


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
    if any(
        issue.code in {
            "unsupported_wavelength_mode",
            "unsupported_supplemental_wavelength_mode",
            "unsupported_coc_model",
            "unsupported_coc_measurement_profile",
        }
        for issue in validation_issues
    ):
        return CocPreparationResult(
            front_panel_channel_count=count,
            channels=(),
            missing_channels=tuple(range(1, count + 1)),
            failures=(),
            invalid_readings=(),
            validation_issues=tuple(validation_issues),
            optimization_channels=(),
            optimization_recommendations=(),
            effective_criteria=dict(base_run.criteria or {}),
            base_run_number=base_run.run_number,
            supplemental_run_number=(
                supplemental_run.run_number if supplemental_run is not None else None
            ),
            template_capacity=45 if count <= 45 else 48,
        )
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
            source_identifier=source.source_identifier,
        )
        prepared.append(prepared_channel)
        invalid.extend(_invalid_reading_issues(prepared_channel))
        failures.extend(
            _formal_failures(
                prepared_channel,
                _effective_fail_limit(base_run),
            )
        )

    warning_limit = _effective_warning_limit(base_run)
    fail_limit = _effective_fail_limit(base_run)
    optimization_channels = tuple(
        channel.record.channel
        for channel in prepared
        if _is_optimization_reading(channel.record, warning_limit, fail_limit)
    )
    recommendations = ()
    if (
        warning_limit is not None
        and not missing
        and not invalid
        and not failures
        and not validation_issues
    ):
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


def _run_model(source_run: CocSourceRun) -> str:
    return normalize_switch_model(str((source_run.criteria or {}).get("model") or ""))


def _run_mode(source_run: CocSourceRun) -> str:
    return str(source_run.metadata.get("Wavelength mode") or "SM").strip().upper()


def _expected_wavelengths(wavelength_mode: str) -> tuple[int, int]:
    return (850, 1300) if str(wavelength_mode).upper() == "MM" else (1310, 1550)


def _effective_fail_limit(source_run: CocSourceRun) -> float:
    criteria = dict(source_run.criteria or {})
    value = criteria.get("fail_above_db")
    if value not in (None, ""):
        return float(value)
    return 0.8 if _run_model(source_run) == "OSX-100" else COC_FORMAL_LIMIT_DB


def _effective_warning_limit(source_run: CocSourceRun) -> float | None:
    criteria = dict(source_run.criteria or {})
    if not bool(criteria.get("warning_enabled", False)):
        return None
    value = criteria.get("warning_above_db")
    return None if value in (None, "") else float(value)


def _compatibility_issues(
    base_run: CocSourceRun,
    supplemental_run: CocSourceRun | None,
) -> tuple[CocValidationIssue, ...]:
    issues = []
    base_signatures = _measurement_signatures(base_run)
    base_mode = _run_mode(base_run)
    base_model = _run_model(base_run)
    if (base_model, base_mode) not in {
        ("OSX-100", "SM"),
        ("OSX-100", "MM"),
        ("OSX-150", "SM"),
    }:
        issues.append(
            CocValidationIssue(
                "unsupported_wavelength_mode",
                "COC generation supports OSX-100 SM/MM and OSX-150 SM runs only; "
                "OSX-150 MM is not supported.",
            )
        )
    if len(base_signatures) > 1:
        issues.append(
            CocValidationIssue(
                "mixed_base_measurement_profiles",
                "The base run contains mixed wavelength or source profiles.",
            )
        )
    elif base_signatures and next(iter(base_signatures)) != (
        base_mode,
        _expected_wavelengths(base_mode),
        "native",
    ):
        issues.append(
            CocValidationIssue(
                "unsupported_coc_measurement_profile",
                "COC generation requires native %s readings made with %s/%s nm sources."
                % (
                    base_mode,
                    _expected_wavelengths(base_mode)[0],
                    _expected_wavelengths(base_mode)[1],
                ),
            )
        )
    if base_model not in ("OSX-100", "OSX-150"):
        issues.append(
            CocValidationIssue(
                "unsupported_coc_model",
                "The approved bundled COC templates support OSX-100 and OSX-150 runs; "
                "the base run reports %s." % (base_model or "an unknown model"),
            )
        )
    if supplemental_run is None:
        return tuple(issues)
    supplemental_mode = _run_mode(supplemental_run)
    supplemental_model = _run_model(supplemental_run)
    if (supplemental_model, supplemental_mode) not in {
        ("OSX-100", "SM"),
        ("OSX-100", "MM"),
        ("OSX-150", "SM"),
    }:
        issues.append(
            CocValidationIssue(
                "unsupported_supplemental_wavelength_mode",
                "The supplemental run must use an approved OSX-100 SM/MM or OSX-150 SM profile.",
            )
        )
    supplemental_signatures = _measurement_signatures(supplemental_run)
    if len(supplemental_signatures) > 1:
        issues.append(
            CocValidationIssue(
                "mixed_supplemental_measurement_profiles",
                "The supplemental run contains mixed wavelength or source profiles.",
            )
        )
    elif supplemental_signatures and next(iter(supplemental_signatures)) != (
        supplemental_mode,
        _expected_wavelengths(supplemental_mode),
        "native",
    ):
        issues.append(
            CocValidationIssue(
                "unsupported_coc_measurement_profile",
                "The supplemental run contains a non-native or mismatched wavelength profile.",
            )
        )
    elif (
        base_signatures
        and supplemental_signatures
        and base_signatures != supplemental_signatures
    ):
        issues.append(
            CocValidationIssue(
                "incompatible_measurement_profiles",
                "The selected runs use different wavelength, source, or "
                "measurement-classification profiles.",
            )
        )
    if supplemental_model != base_model or supplemental_mode != base_mode:
        issues.append(
            CocValidationIssue(
                "incompatible_measurement_profiles",
                "The selected runs must use the same switch model and wavelength mode.",
            )
        )
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


def _measurement_signatures(
    source_run: CocSourceRun,
) -> set[tuple[str, tuple[int, int], str]]:
    """Return the wavelength/source validity signatures present in one run."""
    return {
        (
            record.wavelength_mode,
            tuple(record.source_wavelengths_nm),
            record.measurement_classification,
        )
        for record in source_run.measurements
    }


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
    for wavelength in channel.record.opm_wavelengths_nm:
        value = channel.record.loss_for(wavelength)
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


def _formal_failures(
    channel: CocPreparedChannel,
    fail_limit: float = COC_FORMAL_LIMIT_DB,
) -> tuple[CocFailure, ...]:
    failures = []
    for wavelength in channel.record.opm_wavelengths_nm:
        value = channel.record.loss_for(wavelength)
        if math.isfinite(float(value)) and _rounded_loss(value) >= fail_limit:
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


def _is_optimization_reading(
    record: MeasurementRecord,
    warning_limit: float | None = COC_OPTIMIZATION_LIMIT_DB,
    fail_limit: float = COC_FORMAL_LIMIT_DB,
) -> bool:
    if warning_limit is None:
        return False
    values = tuple(_rounded_loss(value) for value in record.ordered_losses)
    return any(
        warning_limit < value < fail_limit
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
            if not all(
                math.isfinite(float(value)) for value in record.ordered_losses
            ):
                continue
            losses = record.ordered_losses
            readings_by_port[port] = ReplacementReading(
                port,
                float(losses[0]),
                float(losses[1]),
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
        MeasurementRecord.from_wavelengths(
            channel.record.channel,
            dict(zip(channel.record.opm_wavelengths_nm, channel.record.ordered_losses)),
            physical_port=channel.physical_port,
            reference_snapshot=channel.record.reference_snapshot,
            wavelength_mode=channel.record.wavelength_mode,
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
