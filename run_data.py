"""Load and analyze insertion-loss CSV run files."""

import csv
from dataclasses import dataclass, field
from pathlib import Path

from domain.models import MeasurementRecord


@dataclass
class RunData:
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
        """Return summary counts and values for the selected limit."""
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


def _normalise_header(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _parse_metadata(row: list[str], metadata: dict[str, str]) -> None:
    for key_index, value_index in ((4, 5), (3, 4)):
        if len(row) > value_index and row[key_index].strip():
            key = row[key_index].strip()
            value = row[value_index].strip()
            if key.lower() not in {"metadata", "value"}:
                metadata[key] = value
            return


def load_run_csv(path: str | Path) -> RunData:
    """Load current and older measurement CSV layouts."""
    source_path = Path(path)
    measurements = []
    metadata = {}

    with source_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        for row in csv.reader(csv_file):
            if not row or not any(cell.strip() for cell in row):
                continue

            header = [_normalise_header(cell) for cell in row[:3]]
            if header[:3] == ["channel", "1310 il", "1550 il"]:
                _parse_metadata(row, metadata)
                continue

            _parse_metadata(row, metadata)
            if len(row) < 3:
                continue

            try:
                channel = int(row[0].strip())
                loss_1310 = float(row[1].strip())
                loss_1550 = float(row[2].strip())
            except ValueError:
                continue

            measurements.append(
                MeasurementRecord(channel, loss_1310, loss_1550)
            )

    if not measurements:
        raise ValueError("No measurement rows were found in %s." % source_path.name)

    return RunData(source_path, measurements, metadata)
