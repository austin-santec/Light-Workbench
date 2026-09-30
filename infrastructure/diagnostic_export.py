"""Explicit CSV and JSON export for in-memory diagnostic history."""

import csv
import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Sequence

from domain.diagnostic_analysis import DiagnosticReading
from domain.diagnostic_trace import DiagnosticTraceEvent


DIAGNOSTIC_CSV_COLUMNS = (
    "Reading",
    "Time",
    "Method",
    "Channel",
    "Physical port",
    "1310 measured (dBm)",
    "1310 reference (dBm)",
    "1310 IL (dB)",
    "1550 measured (dBm)",
    "1550 reference (dBm)",
    "1550 IL (dB)",
)

DIAGNOSTIC_TRACE_CSV_COLUMNS = (
    "Timestamp",
    "Session ID",
    "Application version",
    "Meter description",
    "Meter serial",
    "Measurement ID",
    "Event",
    "Method",
    "Channel",
    "Physical port",
    "Requested wavelength (nm)",
    "Actual wavelength (nm)",
    "Wavelength index",
    "Wavelength count",
    "Source ID",
    "Source enabled",
    "Operation",
    "Status",
    "Status code",
    "Raw power (dBm)",
    "Reference power (dBm)",
    "Insertion loss (dB)",
    "Elapsed (ms)",
    "Error",
    "Details",
)


def _csv_row(reading: DiagnosticReading) -> dict[str, object]:
    """Return stable, human-readable export fields for one reading."""
    return {
        "Reading": reading.reading_number,
        "Time": reading.timestamp,
        "Method": reading.method,
        "Channel": reading.channel if reading.channel is not None else "-",
        "Physical port": (
            reading.physical_port if reading.physical_port is not None else "-"
        ),
        "1310 measured (dBm)": "%.4f" % reading.measured_1310,
        "1310 reference (dBm)": "%.2f" % reading.reference_1310,
        "1310 IL (dB)": "%.4f" % reading.insertion_loss_1310,
        "1550 measured (dBm)": "%.4f" % reading.measured_1550,
        "1550 reference (dBm)": "%.2f" % reading.reference_1550,
        "1550 IL (dB)": "%.4f" % reading.insertion_loss_1550,
    }


def _trace_csv_row(
    event: DiagnosticTraceEvent,
    metadata: dict[str, object],
) -> dict[str, object]:
    """Return stable, readable fields for one hardware trace event."""
    return {
        "Timestamp": event.timestamp,
        "Session ID": event.session_id,
        "Application version": metadata.get("application_version", ""),
        "Meter description": metadata.get("meter_description", ""),
        "Meter serial": metadata.get("meter_serial", ""),
        "Measurement ID": (
            event.measurement_id if event.measurement_id is not None else ""
        ),
        "Event": event.event,
        "Method": event.method or "",
        "Channel": event.channel if event.channel is not None else "",
        "Physical port": (
            event.physical_port if event.physical_port is not None else ""
        ),
        "Requested wavelength (nm)": (
            event.requested_wavelength_nm
            if event.requested_wavelength_nm is not None
            else ""
        ),
        "Actual wavelength (nm)": (
            event.actual_wavelength_nm
            if event.actual_wavelength_nm is not None
            else ""
        ),
        "Wavelength index": (
            event.wavelength_index if event.wavelength_index is not None else ""
        ),
        "Wavelength count": (
            event.wavelength_count if event.wavelength_count is not None else ""
        ),
        "Source ID": event.source_id if event.source_id is not None else "",
        "Source enabled": (
            event.source_enabled if event.source_enabled is not None else ""
        ),
        "Operation": event.operation or "",
        "Status": event.status or "",
        "Status code": event.status_code if event.status_code is not None else "",
        "Raw power (dBm)": (
            "%.4f" % event.raw_power_dbm
            if event.raw_power_dbm is not None
            else ""
        ),
        "Reference power (dBm)": (
            "%.2f" % event.reference_power_dbm
            if event.reference_power_dbm is not None
            else ""
        ),
        "Insertion loss (dB)": (
            "%.4f" % event.insertion_loss_db
            if event.insertion_loss_db is not None
            else ""
        ),
        "Elapsed (ms)": (
            "%.3f" % event.elapsed_ms if event.elapsed_ms is not None else ""
        ),
        "Error": event.error or "",
        "Details": event.details or "",
    }


def _atomic_write(path: Path, writer) -> None:
    """Write one selected export without leaving a partial destination file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".%s-" % path.stem,
            suffix=path.suffix,
            dir=path.parent,
            text=True,
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        writer(temporary_path)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def export_diagnostic_history(
    path: str | Path,
    readings: Sequence[DiagnosticReading],
    include_hardware_trace: bool = False,
    trace_events: Sequence[DiagnosticTraceEvent] = (),
    trace_metadata: dict[str, object] | None = None,
) -> Path:
    """Export diagnostic history, optionally including hardware trace data."""
    if not readings:
        raise ValueError("There are no diagnostic readings to export.")

    destination = Path(path)
    extension = destination.suffix.lower()
    rows = [_csv_row(reading) for reading in readings]
    trace_metadata = dict(trace_metadata or {})
    trace_events = tuple(trace_events)

    if extension == ".csv":
        def write_csv(temporary_path: Path) -> None:
            with temporary_path.open(
                "w", encoding="utf-8-sig", newline=""
            ) as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=DIAGNOSTIC_CSV_COLUMNS,
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerows(rows)

        _atomic_write(destination, write_csv)

        if include_hardware_trace:
            trace_destination = destination.with_name(
                "%s-hardware-trace.csv" % destination.stem
            )
            trace_rows = [
                _trace_csv_row(event, trace_metadata) for event in trace_events
            ]

            def write_trace_csv(temporary_path: Path) -> None:
                with temporary_path.open(
                    "w", encoding="utf-8-sig", newline=""
                ) as stream:
                    writer = csv.DictWriter(
                        stream,
                        fieldnames=DIAGNOSTIC_TRACE_CSV_COLUMNS,
                        lineterminator="\n",
                    )
                    writer.writeheader()
                    writer.writerows(trace_rows)

            _atomic_write(trace_destination, write_trace_csv)
        return destination

    if extension == ".json":
        payload = {
            "format": "Light Workbench Power Measurement Diagnostics",
            "schema_version": 1,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "readings": [asdict(reading) for reading in readings],
        }
        if include_hardware_trace:
            payload["hardware_trace"] = {
                "session": trace_metadata,
                "events": [event.as_dict() for event in trace_events],
            }

        def write_json(temporary_path: Path) -> None:
            with temporary_path.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
                stream.write("\n")

        _atomic_write(destination, write_json)
        return destination

    raise ValueError("Choose a .csv or .json diagnostic export filename.")


__all__ = [
    "DIAGNOSTIC_CSV_COLUMNS",
    "DIAGNOSTIC_TRACE_CSV_COLUMNS",
    "export_diagnostic_history",
]
