"""CSV parsing for the established insertion-loss run format."""

import csv
import re
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
    measurement_rows = []
    metadata = {}
    wavelengths = (1310, 1550)

    with source_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        for row in csv.reader(csv_file):
            if not row or not any(cell.strip() for cell in row):
                continue

            header = [_normalise_header(cell) for cell in row[:3]]
            wavelength_headers = [
                re.fullmatch(r"(\d+)\s*(?:nm\s*)?il(?:\s*\(db\))?", value)
                for value in header[1:3]
            ]
            if header and header[0] == "channel" and all(wavelength_headers):
                wavelengths = tuple(
                    int(match.group(1)) for match in wavelength_headers
                )
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
                        "wavelength_mode": (
                            "MM" if wavelengths == (850, 1300) else "SM"
                        ),
                        "opm_wavelengths_nm": list(wavelengths),
                        "references_by_wavelength": {
                            str(wavelengths[0]): float(row[7].strip()),
                            str(wavelengths[1]): float(row[8].strip()),
                        },
                        "method": row[9].strip(),
                        "established_at": row[10].strip(),
                        "snapshot_id": row[11].strip(),
                    }
                    if wavelengths == (1310, 1550):
                        reference.update(
                            {
                                "reference_1310_dbm": float(row[7].strip()),
                                "reference_1550_dbm": float(row[8].strip()),
                            }
                        )
                except ValueError:
                    reference = None
            measurement_rows.append((channel, loss_1310, loss_1550, reference))

    if not measurement_rows:
        raise ValueError("No measurement rows were found in %s." % source_path.name)

    mode = str(metadata.get("Wavelength mode") or "").upper()
    if not mode:
        mode = "MM" if wavelengths == (850, 1300) else "SM"
    source_wavelengths = tuple(
        int(value.strip())
        for value in str(
            metadata.get(
                "Source wavelengths nm",
                "1310,1550" if mode == "SM" else "850,1300",
            )
        ).split(",")
        if value.strip()
    )
    if len(source_wavelengths) != 2:
        source_wavelengths = (1310, 1550)
    source_ids = tuple(
        int(value.strip())
        for value in str(metadata.get("Source IDs", "0,1")).split(",")
        if value.strip()
    )
    if len(source_ids) != 2:
        source_ids = (0, 1)
    classification = str(
        metadata.get("Measurement classification") or "native"
    )
    measurements = [
        MeasurementRecord.from_wavelengths(
            channel,
            {wavelengths[0]: first_loss, wavelengths[1]: second_loss},
            reference_snapshot=reference,
            wavelength_mode=mode,
            measurement_classification=classification,
            source_wavelengths_nm=source_wavelengths,
            source_ids=source_ids,
        )
        for channel, first_loss, second_loss, reference in measurement_rows
    ]

    return RunData(source_path, measurements, metadata)


__all__ = ["load_run_csv"]
