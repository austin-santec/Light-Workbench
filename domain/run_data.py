"""Domain model for a loaded insertion-loss run."""

from dataclasses import dataclass, field
from pathlib import Path

from .models import MeasurementRecord


@dataclass
class RunData:
    """Loaded run data and derived analysis state.

    The model contains no CSV or Qt behavior. File loading remains in the
    infrastructure layer, and the compatibility facade re-exports this class
    for older callers.
    """

    source_path: Path
    measurements: list[MeasurementRecord] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    attempts: list[dict] = field(default_factory=list)
    warning_limit: float | None = None
    replacement_analysis: dict | None = None
    switch_test_sessions: list[dict] = field(default_factory=list)
    completed_replacements: list[dict] = field(default_factory=list)
    criteria_snapshot: dict | None = None

    def analysis_with_profile(self, profile) -> dict:
        """Return model-specific quality counts for the active criteria."""
        assessments = [
            (record, profile.classify(record.loss_1310, record.loss_1550))
            for record in self.measurements
        ]
        failed = [record for record, assessment in assessments if assessment.is_fail]
        fail_1310 = [record.channel for record, assessment in assessments if 1310 in assessment.fail_wavelengths]
        fail_1550 = [record.channel for record, assessment in assessments if 1550 in assessment.fail_wavelengths]
        fail_both = [
            record.channel for record, assessment in assessments
            if 1310 in assessment.fail_wavelengths and 1550 in assessment.fail_wavelengths
        ]
        return {
            "limit": profile.fail_above_db,
            "total": len(self.measurements),
            "over_limit": len(failed),
            "over_1310": len(fail_1310),
            "over_1310_channels": fail_1310,
            "over_1550": len(fail_1550),
            "over_1550_channels": fail_1550,
            "over_both": len(fail_both),
            "over_both_channels": fail_both,
            "too_good": sum(1 for _, assessment in assessments if assessment.is_too_good),
            "too_good_channels": [record.channel for record, assessment in assessments if assessment.is_too_good],
            "optimization": sum(1 for _, assessment in assessments if assessment.is_optimization and not assessment.is_fail),
            "optimization_channels": [record.channel for record, assessment in assessments if assessment.is_optimization and not assessment.is_fail],
            "failed": len(failed),
            "fail_1310": len(fail_1310),
            "fail_1550": len(fail_1550),
            "fail_both": len(fail_both),
        }

    def over_limit(self, limit: float) -> list[MeasurementRecord]:
        """Return channels exceeding the limit at either wavelength."""
        return [
            record
            for record in self.measurements
            if record.loss_1310 > limit or record.loss_1550 > limit
        ]

    def analysis(self, limit: float) -> dict[str, int | float | list[int]]:
        """Return summary counts and channel values for a selected limit."""
        over_limit = self.over_limit(limit)
        over_1310_channels = [
            record.channel
            for record in self.measurements
            if record.loss_1310 > limit
        ]
        over_1550_channels = [
            record.channel
            for record in self.measurements
            if record.loss_1550 > limit
        ]
        over_both_channels = [
            record.channel
            for record in self.measurements
            if record.loss_1310 > limit and record.loss_1550 > limit
        ]
        return {
            "limit": limit,
            "total": len(self.measurements),
            "over_limit": len(over_limit),
            "over_1310": len(over_1310_channels),
            "over_1310_channels": over_1310_channels,
            "over_1550": len(over_1550_channels),
            "over_1550_channels": over_1550_channels,
            "over_both": len(over_both_channels),
            "over_both_channels": over_both_channels,
        }


__all__ = ["RunData"]
