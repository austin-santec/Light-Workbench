"""Persist live measurement runs as CSV plus a JSON audit record."""

import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path

from run_data import MeasurementRecord, RunData


DEFAULT_RUN_ROOT = Path.home() / "Documents" / "ILM-Reads"


def _safe_serial_component(value):
    """Make an entered serial safe to use as one Windows path component."""
    value = str(value or "").strip()
    safe_value = re.sub(r"[^A-Za-z0-9_-]+", "-", value)
    return safe_value.strip("-_")


def build_run_directory_name(metadata, now=None):
    """Build the timestamped run folder name from optional serial metadata."""
    if now is None:
        now = datetime.now()
    timestamp = now.strftime("%y%m%d_%H%M")
    serials = [
        _safe_serial_component(metadata.get("Main board serial")),
        _safe_serial_component(metadata.get("Switch serial")),
    ]
    serial_suffix = "-".join(serial for serial in serials if serial)
    return "ILM-Run_%s%s" % (
        timestamp,
        ("_" + serial_suffix) if serial_suffix else "",
    )


class RunRecorder:
    """Write the current results and every accepted attempt to disk."""

    def __init__(self, root: str | Path | None = None, metadata=None, limit=2.0):
        self.metadata = dict(metadata or {})
        self.limit = float(limit)
        self.root_path = Path(root) if root is not None else DEFAULT_RUN_ROOT
        base_name = build_run_directory_name(self.metadata)
        directory = self.root_path / base_name
        suffix = 2
        while directory.exists():
            directory = self.root_path / ("%s-%d" % (base_name, suffix))
            suffix += 1
        self.directory = directory
        self.csv_path = directory / "output.csv"
        self.json_path = directory / "run.json"
        self.attempts = []
        self.replacement_analysis = None
        self._directory_created = False

    @classmethod
    def from_existing(
        cls,
        csv_path: str | Path,
        metadata=None,
        limit=2.0,
        attempts=None,
        replacement_analysis=None,
    ):
        """Create a recorder that updates an already-loaded CSV run."""
        recorder = cls.__new__(cls)
        recorder.csv_path = Path(csv_path)
        recorder.directory = recorder.csv_path.parent
        recorder.directory.mkdir(parents=True, exist_ok=True)
        recorder.root_path = recorder.directory.parent
        recorder.json_path = recorder.directory / "run.json"
        recorder.metadata = dict(metadata or {})
        recorder.limit = float(limit)
        recorder.attempts = list(attempts or [])
        recorder.replacement_analysis = replacement_analysis
        recorder._directory_created = True
        return recorder

    def save(self, measurements: list[MeasurementRecord]):
        """Atomically save the current table and its audit history."""
        # A newly started run is allowed to exist only in memory until the
        # first accepted measurement is written. This prevents abandoned runs
        # from leaving empty folders, CSV files, or JSON files behind.
        if not measurements and not self._directory_created:
            return
        self._ensure_directory()
        self._write_csv(measurements)
        payload = {
            "created_at": self.metadata.get("Created at", datetime.now().isoformat(timespec="seconds")),
            "warning_limit_db": self.limit,
            "metadata": self.metadata,
            "measurements": [
                {
                    "channel": record.channel,
                    "physical_port": record.physical_port,
                    "loss_1310_db": record.loss_1310,
                    "loss_1550_db": record.loss_1550,
                }
                for record in measurements
            ],
            "attempts": self.attempts,
            "replacement_analysis": self.replacement_analysis,
        }
        temporary_path = self.json_path.with_suffix(".json.tmp")
        try:
            with temporary_path.open("w", encoding="utf-8") as json_file:
                json.dump(payload, json_file, indent=2)
                json_file.write("\n")
                json_file.flush()
                os.fsync(json_file.fileno())
            os.replace(temporary_path, self.json_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def _ensure_directory(self):
        """Create the deferred run folder on the first real save."""
        if self._directory_created:
            return
        self.root_path.mkdir(parents=True, exist_ok=True)
        if self.directory.exists():
            base_name = self.directory.name
            suffix = 2
            while (self.root_path / ("%s-%d" % (base_name, suffix))).exists():
                suffix += 1
            self.directory = self.root_path / ("%s-%d" % (base_name, suffix))
            self.csv_path = self.directory / "output.csv"
            self.json_path = self.directory / "run.json"
        self.directory.mkdir()
        self._directory_created = True

    def record_attempt(self, channel, loss_1310, loss_1550, physical_port, retest=False):
        self.attempts.append(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "channel": channel,
                "physical_port": physical_port,
                "loss_1310_db": loss_1310,
                "loss_1550_db": loss_1550,
                "retest": retest,
            }
        )

    def _write_csv(self, measurements):
        rows = [["channel", "1310 IL", "1550 IL"]]
        rows.extend(
            [record.channel, "%.4f" % record.loss_1310, "%.4f" % record.loss_1550]
            for record in measurements
        )
        metadata_rows = [["Metadata", "Value"]]
        metadata_rows.extend(list(item) for item in sorted(self.metadata.items()))
        row_count = max(len(rows), len(metadata_rows))
        temporary_path = self.csv_path.with_suffix(".csv.tmp")
        try:
            with temporary_path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file)
                for index in range(row_count):
                    measurement = rows[index] if index < len(rows) else ["", "", ""]
                    metadata = metadata_rows[index] if index < len(metadata_rows) else ["", ""]
                    writer.writerow(measurement + [""] + metadata)
                csv_file.flush()
                os.fsync(csv_file.fileno())
            os.replace(temporary_path, self.csv_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()


def load_run_json(path: str | Path) -> dict:
    """Load a structured run record for future detailed viewer support."""
    with Path(path).open("r", encoding="utf-8") as json_file:
        return json.load(json_file)
