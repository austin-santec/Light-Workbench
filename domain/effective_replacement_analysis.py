"""Pure assignment-wide measurement projection for iterative replacements."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Sequence

from domain.database_records import MeasurementRecord, ReplacementRecord, RunRecord
from domain.models import MeasurementRecord as DisplayMeasurement
from domain.replacements import ReplacementReading, analyze_replacements


RESULT_OPTIMIZED = "optimized"
RESULT_RECOMMENDATIONS_AVAILABLE = "recommendations_available"
RESULT_VERIFICATION_REQUIRED = "verification_required"
RESULT_PASS_NO_VIABLE_OPTIMIZATION = "pass_no_viable_optimization"
RESULT_FAIL_NO_VIABLE_RECOVERY = "fail_no_viable_recovery"
RESULT_INCOMPLETE_INPUT = "incomplete_input"
RESULT_REVIEW_REQUIRED = "review_required"


def _run_key(run: RunRecord):
    return run.run_started_at_utc, run.run_id


def _measurement_key(item: MeasurementRecord):
    return item.written_at_utc, item.attempt_number, item.measurement_id


def _wavelength_pair(item: MeasurementRecord) -> tuple[int, int]:
    return int(item.wavelength_1_nm), int(item.wavelength_2_nm)


def _criteria_signature(run: RunRecord) -> tuple:
    values = run.limit_snapshot
    return tuple(
        values.get(key)
        for key in (
            "model",
            "wavelength_mode",
            "too_good_below_db",
            "warning_enabled",
            "warning_above_db",
            "fail_above_db",
            "minimum_replacement_improvement_db",
        )
    )


@dataclass(frozen=True)
class EffectiveMeasurement:
    record: MeasurementRecord
    run: RunRecord

    def provenance(self) -> dict[str, object]:
        return {
            "run_id": self.run.run_id,
            "run_number": self.run.run_number,
            "measurement_id": self.record.measurement_id,
            "attempt_number": self.record.attempt_number,
            "logical_channel": self.record.logical_channel,
            "physical_port": self.record.physical_port,
            "written_at_utc": self.record.written_at_utc.isoformat(),
            "wavelength_1_nm": self.record.wavelength_1_nm,
            "wavelength_1_il_db": float(self.record.wavelength_1_il_db),
            "wavelength_2_nm": self.record.wavelength_2_nm,
            "wavelength_2_il_db": float(self.record.wavelength_2_il_db),
        }

    def display_record(self, mode: str) -> DisplayMeasurement:
        return DisplayMeasurement.from_wavelengths(
            self.record.logical_channel,
            {
                self.record.wavelength_1_nm: float(self.record.wavelength_1_il_db),
                self.record.wavelength_2_nm: float(self.record.wavelength_2_il_db),
            },
            physical_port=self.record.physical_port,
            reference_snapshot=dict(self.record.reference_snapshot),
            wavelength_mode=mode,
            written_at_utc=self.record.written_at_utc,
            attempt_number=self.record.attempt_number,
            measurement_id=self.record.measurement_id,
            run_id=self.record.run_id,
        )


@dataclass(frozen=True)
class ReplacementVerification:
    replacement: ReplacementRecord
    state: str
    measurement: EffectiveMeasurement | None = None

    def as_dict(self) -> dict[str, object]:
        values = {
            "replacement_id": self.replacement.replacement_id,
            "logical_channel": self.replacement.logical_channel,
            "previous_physical_port": self.replacement.previous_physical_port,
            "current_physical_port": self.replacement.replacement_physical_port,
            "replaced_at_utc": self.replacement.replaced_at_utc.isoformat(),
            "replaced_by": self.replacement.replaced_by,
            "verification_state": self.state,
        }
        if self.measurement is not None:
            values["retest"] = self.measurement.provenance()
            values["retest_run_number"] = self.measurement.run.run_number
        return values


@dataclass(frozen=True)
class EffectiveReplacementProjection:
    context_run: RunRecord
    included_runs: tuple[RunRecord, ...]
    excluded_runs: tuple[tuple[RunRecord, str], ...]
    front_measurements: tuple[EffectiveMeasurement, ...]
    extra_measurements: tuple[EffectiveMeasurement, ...]
    missing_channels: tuple[int, ...]
    review_issues: tuple[str, ...]
    verifications: tuple[ReplacementVerification, ...]
    analysis_result: Mapping[str, object]
    source_snapshot: Mapping[str, object]

    @property
    def fingerprint(self) -> str:
        return str(self.source_snapshot["state_fingerprint_sha256"])

    def to_result_dict(self) -> dict[str, object]:
        result = dict(self.analysis_result)
        result.update(
            {
                "analysis_result_status": result["result_status"],
                "source_snapshot": dict(self.source_snapshot),
                "source_runs": [run.run_number for run in self.included_runs],
                "included_run_ids": [run.run_id for run in self.included_runs],
                "excluded_runs": [
                    {
                        "run_id": run.run_id,
                        "run_number": run.run_number,
                        "reason": reason,
                    }
                    for run, reason in self.excluded_runs
                ],
                "effective_measurements": [
                    item.provenance() for item in self.front_measurements
                ],
                "extra_measurements": [
                    item.provenance() for item in self.extra_measurements
                ],
                "replacement_verification": [
                    item.as_dict() for item in self.verifications
                ],
                "review_issues": list(self.review_issues),
                "valid_effective_channel_count": len(self.front_measurements),
            }
        )
        return result


def _compatible_run(context: RunRecord, candidate: RunRecord) -> str | None:
    if candidate.assignment_id != context.assignment_id:
        return "different assignment"
    if _run_key(candidate) > _run_key(context):
        return "later than context run"
    if candidate.analysis_status == "excluded":
        return "voided"
    if candidate.analysis_status == "superseded" or candidate.superseded_by_run_id:
        return "superseded"
    if candidate.wavelength_mode != context.wavelength_mode:
        return "different wavelength mode"
    if candidate.front_panel_channel_count != context.front_panel_channel_count:
        return "different front-panel channel count"
    if _criteria_signature(candidate) != _criteria_signature(context):
        return "incompatible criteria"
    candidate_model = str(candidate.limit_snapshot.get("model") or "")
    context_model = str(context.limit_snapshot.get("model") or "")
    if candidate_model != context_model:
        return "different switch model"
    return None


def _latest_by(items, key):
    selected = {}
    for item in items:
        identity = key(item)
        prior = selected.get(identity)
        if prior is None or _measurement_key(item.record) > _measurement_key(prior.record):
            selected[identity] = item
    return selected


def build_effective_replacement_projection(
    *,
    context_run: RunRecord,
    runs: Sequence[RunRecord],
    measurements_by_run: Mapping[int, Sequence[MeasurementRecord]],
    effective_channel_map: Mapping[int, int],
    replacements: Sequence[ReplacementRecord],
    active_spares: Sequence[int],
    spare_event_ids: Sequence[int],
    profile,
    bottom_spare_count: int = 2,
) -> EffectiveReplacementProjection:
    """Build the deterministic assignment state visible from *context_run*."""
    if context_run.front_panel_channel_count is None:
        raise ValueError("Front-panel channel count is required")
    count = int(context_run.front_panel_channel_count)
    included, excluded = [], []
    for run in sorted(runs, key=_run_key):
        reason = _compatible_run(context_run, run)
        if reason is None:
            included.append(run)
        else:
            excluded.append((run, reason))

    expected_pair = (1310, 1550) if context_run.wavelength_mode == "SM" else (850, 1300)
    candidates = []
    review = []
    for run in included:
        for record in measurements_by_run.get(run.run_id, ()):
            if _wavelength_pair(record) != expected_pair:
                review.append(
                    "Measurement %d uses incompatible wavelengths" % record.measurement_id
                )
                continue
            candidates.append(EffectiveMeasurement(record, run))

    included_run_ids = {run.run_id for run in included}
    replacement_rows = [
        row
        for row in replacements
        if row.assignment_id == context_run.assignment_id
        and (row.related_run_id is None or row.related_run_id in included_run_ids)
    ]
    latest_replacement_by_channel = {}
    context_channel_map = {
        int(logical): int(physical)
        for logical, physical in effective_channel_map.items()
    }
    for row in sorted(
        replacement_rows,
        key=lambda value: (value.replaced_at_utc, value.replacement_id),
    ):
        latest_replacement_by_channel[row.logical_channel] = row
        context_channel_map[row.logical_channel] = row.replacement_physical_port

    latest_front = _latest_by(
        (item for item in candidates if 1 <= item.record.logical_channel <= count),
        lambda item: item.record.logical_channel,
    )
    front = []
    duplicate_ports = {}
    for channel in range(1, count + 1):
        item = latest_front.get(channel)
        if item is None:
            continue
        expected_port = int(context_channel_map.get(channel, channel))
        actual_port = int(item.record.physical_port or item.record.logical_channel)
        if actual_port != expected_port:
            replacement = latest_replacement_by_channel.get(channel)
            if not (
                replacement is not None
                and replacement.replacement_physical_port == expected_port
                and item.record.written_at_utc <= replacement.replaced_at_utc
            ):
                review.append(
                    "Logical channel %d newest measurement uses physical port %d; expected %d"
                    % (channel, actual_port, expected_port)
                )
            continue
        other = duplicate_ports.get(actual_port)
        if other is not None and other != channel:
            review.append(
                "Physical port %d is mapped to logical channels %d and %d"
                % (actual_port, other, channel)
            )
            continue
        duplicate_ports[actual_port] = channel
        front.append(item)

    missing = tuple(
        channel
        for channel in range(1, count + 1)
        if channel not in {item.record.logical_channel for item in front}
    )
    assigned_ports = {int(value) for value in context_channel_map.values()}
    extra_candidates = (
        item
        for item in candidates
        if int(item.record.physical_port or item.record.logical_channel) > count
        or item.record.logical_channel > count
    )
    latest_extras = _latest_by(
        extra_candidates,
        lambda item: int(item.record.physical_port or item.record.logical_channel),
    )
    extras = []
    too_good_extras = []
    for port, item in sorted(latest_extras.items()):
        if port in assigned_ports:
            continue
        assessment = profile.classify(
            float(item.record.wavelength_1_il_db),
            float(item.record.wavelength_2_il_db),
            expected_pair,
        )
        if assessment.is_too_good:
            too_good_extras.append(port)
            continue
        extras.append(item)
    if too_good_extras:
        review.append(
            "Too-good extra-port readings require review: %s"
            % ", ".join(str(value) for value in too_good_extras)
        )

    verifications = []
    for row in replacement_rows:
        if latest_replacement_by_channel.get(row.logical_channel) != row:
            verifications.append(ReplacementVerification(row, "superseded_by_later_replacement"))
            continue
        matching = [
            item
            for item in candidates
            if item.record.logical_channel == row.logical_channel
            and int(item.record.physical_port or item.record.logical_channel)
            == row.replacement_physical_port
            and item.record.written_at_utc > row.replaced_at_utc
        ]
        if not matching:
            verifications.append(ReplacementVerification(row, "awaiting_retest"))
            continue
        measured = max(matching, key=lambda item: _measurement_key(item.record))
        assessment = profile.classify(
            float(measured.record.wavelength_1_il_db),
            float(measured.record.wavelength_2_il_db),
            expected_pair,
        )
        if assessment.is_too_good:
            state = "invalid_retest"
        elif assessment.is_fail:
            state = "verified_failing"
        elif assessment.is_optimization:
            state = "verified_optimization_warning"
        else:
            state = "verified_passing"
        verifications.append(ReplacementVerification(row, state, measured))

    production = tuple(item.display_record(context_run.wavelength_mode) for item in front)
    extra_readings = tuple(
        ReplacementReading(
            int(item.record.physical_port or item.record.logical_channel),
            float(item.record.wavelength_1_il_db),
            float(item.record.wavelength_2_il_db),
        )
        for item in extras
    )
    optimization_limit = (
        profile.warning_above_db
        if profile.warning_enabled and profile.warning_above_db is not None
        else profile.fail_above_db
    )
    analysis = analyze_replacements(
        production,
        extra_readings,
        count,
        optimization_limit,
        minimum_improvement=profile.minimum_replacement_improvement_db,
        bottom_spare_count=bottom_spare_count,
        fail_limit=profile.fail_above_db,
        model=profile.model,
        too_good_limit=profile.too_good_below_db,
        wavelengths=expected_pair,
    )
    measured_extra_ports = {item.port for item in extra_readings}
    analysis["bottom_spares"] = [
        item
        for item in analysis.get("bottom_spares", ())
        if item["physical_port"] in measured_extra_ports
    ]
    analysis["remaining_extras"] = [
        port for port in analysis.get("remaining_extras", ()) if port in measured_extra_ports
    ]
    front_by_channel = {
        item.record.logical_channel: item for item in front
    }
    extras_by_port = {
        int(item.record.physical_port or item.record.logical_channel): item
        for item in extras
    }
    for recommendation in analysis.get("recommendations", ()):
        current_source = front_by_channel.get(recommendation["logical_channel"])
        candidate_source = extras_by_port.get(
            recommendation["candidate_physical_port"]
        )
        if current_source is not None:
            recommendation["current_source_run_number"] = current_source.run.run_number
            recommendation["current_measurement_id"] = current_source.record.measurement_id
        if candidate_source is not None:
            recommendation["candidate_source_run_number"] = candidate_source.run.run_number
            recommendation["candidate_measurement_id"] = candidate_source.record.measurement_id
    front_assessments = [
        profile.classify(*item.ordered_losses, item.opm_wavelengths_nm)
        for item in production
    ]
    too_good_front = [
        item.record.logical_channel
        for item, assessment in zip(front, front_assessments)
        if assessment.is_too_good
    ]
    if too_good_front:
        review.append(
            "Too-good front-panel readings require review: %s"
            % ", ".join(str(value) for value in too_good_front)
        )
    awaiting = any(item.state == "awaiting_retest" for item in verifications)
    failing = any(item.is_fail for item in front_assessments)
    warning = any(item.is_optimization and not item.is_fail for item in front_assessments)
    awaiting_channels = {
        item.replacement.logical_channel
        for item in verifications
        if item.state == "awaiting_retest"
    }
    missing = tuple(channel for channel in missing if channel not in awaiting_channels)
    if review:
        result_status = RESULT_REVIEW_REQUIRED
    elif missing:
        result_status = RESULT_INCOMPLETE_INPUT
    elif awaiting:
        result_status = RESULT_VERIFICATION_REQUIRED
    elif analysis.get("recommendations"):
        result_status = RESULT_RECOMMENDATIONS_AVAILABLE
    elif failing:
        result_status = RESULT_FAIL_NO_VIABLE_RECOVERY
    elif warning:
        result_status = RESULT_PASS_NO_VIABLE_OPTIMIZATION
    else:
        result_status = RESULT_OPTIMIZED
    analysis["result_status"] = result_status
    analysis["status"] = result_status.replace("_", " ").title()
    analysis["missing_channels"] = list(missing)
    analysis["designated_spares"] = sorted(int(value) for value in active_spares)

    source_material = {
        "assignment_id": context_run.assignment_id,
        "context_run_id": context_run.run_id,
        "context_run_number": context_run.run_number,
        "switch_serial": str(
            dict(context_run.measurement_hardware.get("switch") or {}).get("serial")
            or ""
        ),
        "runs": [(run.run_id, run.analysis_status) for run in included],
        "measurements": [item.record.measurement_id for item in front + extras],
        "replacements": [item.replacement_id for item in replacement_rows],
        "spare_events": sorted(int(value) for value in spare_event_ids),
        "criteria": dict(context_run.limit_snapshot),
        "wavelength_mode": context_run.wavelength_mode,
    }
    encoded = json.dumps(source_material, sort_keys=True, separators=(",", ":"), default=str)
    source_snapshot = {
        "assignment_id": context_run.assignment_id,
        "context_run_id": context_run.run_id,
        "context_run_number": context_run.run_number,
        "switch_serial": source_material["switch_serial"],
        "included_run_ids": [run.run_id for run in included],
        "included_run_numbers": [run.run_number for run in included],
        "selected_measurement_ids": [item.record.measurement_id for item in front],
        "extra_measurement_ids": [item.record.measurement_id for item in extras],
        "measurement_high_watermark_id": max(
            (item.record.measurement_id for item in front + extras), default=None
        ),
        "replacement_ids": [item.replacement_id for item in replacement_rows],
        "replacement_high_watermark_id": max(
            (item.replacement_id for item in replacement_rows), default=None
        ),
        "spare_event_ids": sorted(int(value) for value in spare_event_ids),
        "spare_event_high_watermark_id": max(spare_event_ids, default=None),
        "state_fingerprint_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "superseded_attempt_count": len(candidates)
        - len(_latest_by(candidates, lambda item: item.record.logical_channel)),
    }
    return EffectiveReplacementProjection(
        context_run,
        tuple(included),
        tuple(excluded),
        tuple(front),
        tuple(extras),
        missing,
        tuple(review),
        tuple(verifications),
        analysis,
        source_snapshot,
    )


__all__ = [
    "EffectiveMeasurement",
    "EffectiveReplacementProjection",
    "ReplacementVerification",
    "build_effective_replacement_projection",
    "RESULT_FAIL_NO_VIABLE_RECOVERY",
    "RESULT_INCOMPLETE_INPUT",
    "RESULT_OPTIMIZED",
    "RESULT_PASS_NO_VIABLE_OPTIMIZATION",
    "RESULT_RECOMMENDATIONS_AVAILABLE",
    "RESULT_REVIEW_REQUIRED",
    "RESULT_VERIFICATION_REQUIRED",
]
