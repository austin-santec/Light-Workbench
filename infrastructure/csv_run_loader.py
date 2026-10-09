"""CSV parsing for the established insertion-loss run format."""

import csv
import re
from pathlib import Path

from domain.models import MeasurementRecord
from domain.run_data import RunData
from domain.reference_catalog import ReferenceCatalog


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


def _normalised_header_indexes(header: list[str]) -> dict[str, int]:
    """Return the first index for each descriptive CSV header."""
    indexes = {}
    for index, value in enumerate(header):
        normalized = _normalise_header(value)
        if normalized and normalized not in indexes:
            indexes[normalized] = index
    return indexes


def _cell(row: list[str], index: int | None) -> str:
    """Read one optional CSV cell without exposing index errors."""
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _reference_catalog_from_csv(
    rows: list[list[str]],
    catalog_start: int,
    catalog_headers: list[str],
) -> ReferenceCatalog:
    """Load and validate the compact reference catalog section."""
    indexes = _normalised_header_indexes(catalog_headers)
    required = (
        "reference",
        "wavelength mode",
        "first wavelength nm",
        "first reference dbm",
        "second wavelength nm",
        "second reference dbm",
    )
    missing = [name for name in required if name not in indexes]
    if missing:
        raise ValueError(
            "The CSV reference catalog is missing: %s."
            % ", ".join(missing)
        )

    entries = []
    for row in rows[1:]:
        key = _cell(row, catalog_start + indexes["reference"])
        if not key:
            continue
        try:
            first_wavelength = int(
                _cell(row, catalog_start + indexes["first wavelength nm"])
            )
            second_wavelength = int(
                _cell(row, catalog_start + indexes["second wavelength nm"])
            )
            first_reference = float(
                _cell(row, catalog_start + indexes["first reference dbm"])
            )
            second_reference = float(
                _cell(row, catalog_start + indexes["second reference dbm"])
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Reference catalog entry %s has invalid wavelength or reference values."
                % key
            ) from error

        mode = _cell(row, catalog_start + indexes["wavelength mode"]).upper()
        if not mode:
            mode = "MM" if (first_wavelength, second_wavelength) == (850, 1300) else "SM"
        snapshot = {
            "reference_key": key,
            "wavelength_mode": mode,
            "opm_wavelengths_nm": [first_wavelength, second_wavelength],
            "references_by_wavelength": {
                str(first_wavelength): first_reference,
                str(second_wavelength): second_reference,
            },
        }
        if mode == "SM":
            snapshot.update(
                {
                    "reference_1310_dbm": first_reference,
                    "reference_1550_dbm": second_reference,
                }
            )
        for field, header in (
            ("method", "method"),
            ("established_at", "established utc"),
            ("snapshot_id", "snapshot id"),
            ("operator_initials", "operator initials"),
            ("meter_model", "meter model"),
            ("meter_serial", "meter serial"),
            ("laser_model", "laser model"),
            ("laser_serial", "laser serial"),
            ("measurement_classification", "measurement classification"),
            ("source_profile_id", "source profile id"),
            ("source_profile_origin", "source profile origin"),
        ):
            if header in indexes:
                value = _cell(row, catalog_start + indexes[header])
                if value:
                    snapshot[field] = value
        entries.append({"reference_key": key, "snapshot": snapshot})
    return ReferenceCatalog(entries)


def load_run_csv(path: str | Path) -> RunData:
    """Load current and older measurement CSV layouts."""
    source_path = Path(path)
    measurement_rows = []
    metadata = {}
    wavelengths = (1310, 1550)

    with source_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        rows = list(csv.reader(csv_file))

    main_header = None
    main_header_index = None
    for index, row in enumerate(rows):
        header = [_normalise_header(cell) for cell in row[:3]]
        wavelength_headers = [
            re.fullmatch(r"(\d+)\s*(?:nm\s*)?il(?:\s*\(db\))?", value)
            for value in header[1:3]
        ]
        if header and header[0] == "channel" and all(wavelength_headers):
            main_header = row
            main_header_index = index
            wavelengths = tuple(
                int(match.group(1)) for match in wavelength_headers
            )
            break

    if main_header is None:
        raise ValueError("No measurement header was found in %s." % source_path.name)

    header_indexes = _normalised_header_indexes(main_header)
    reference_used_index = header_indexes.get("reference used")
    catalog_start = None
    catalog = None
    if reference_used_index is not None:
        catalog_start = next(
            (
                index
                for index in range(reference_used_index + 1, len(main_header))
                if _normalise_header(main_header[index]) == "reference"
            ),
            None,
        )
        if catalog_start is None:
            raise ValueError("The CSV reference catalog header is missing.")
        catalog = _reference_catalog_from_csv(
            rows[main_header_index:],
            catalog_start,
            main_header[catalog_start:],
        )

    for row in rows:
        if not row or not any(cell.strip() for cell in row):
            continue

        header = [_normalise_header(cell) for cell in row[:3]]
        wavelength_headers = [
            re.fullmatch(r"(\d+)\s*(?:nm\s*)?il(?:\s*\(db\))?", value)
            for value in header[1:3]
        ]
        if header and header[0] == "channel" and all(wavelength_headers):
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
        if catalog is not None:
            reference_key = _cell(row, reference_used_index)
            if reference_key:
                reference = catalog.snapshot_for(reference_key)
                if reference is None:
                    raise ValueError(
                        "Measurement row references missing catalog entry %s."
                        % reference_key
                    )
        elif len(row) >= 12 and row[7].strip() and row[8].strip():
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
