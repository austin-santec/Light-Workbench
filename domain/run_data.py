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
