"""CSV parsing for the established insertion-loss run format."""

import csv
from pathlib import Path

from domain.models import MeasurementRecord
from domain.run_data import RunData


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

            reference = None
            if len(row) >= 12 and row[7].strip() and row[8].strip():
                try:
                    reference = {
                        "reference_1310_dbm": float(row[7].strip()),
                        "reference_1550_dbm": float(row[8].strip()),
                        "method": row[9].strip(),
                        "established_at": row[10].strip(),
                        "snapshot_id": row[11].strip(),
                    }
                except ValueError:
                    reference = None
            measurements.append(
                MeasurementRecord(
                    channel,
                    loss_1310,
                    loss_1550,
                    reference_snapshot=reference,
                )
            )

    if not measurements:
        raise ValueError("No measurement rows were found in %s." % source_path.name)

    return RunData(source_path, measurements, metadata)


__all__ = ["load_run_csv"]
