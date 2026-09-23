"""Persist live measurement runs as CSV plus a JSON audit record."""

import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path

from run_data import MeasurementRecord, RunData


DEFAULT_RUN_ROOT = Path.home() / "Documents" / "ILM-Reads"


def _run_metadata(metadata):
    """Keep CSV/JSON metadata focused on settings for this test run."""
    excluded_exact = {
        "1310 reference dBm",
        "1550 reference dBm",
        "Retest attempts",
        "Completed replacements",
        "Designated spare ports",
    }
    excluded_prefixes = (
        "Replacement ",
        "Required replacement recommendation ",
        "Optional replacement recommendation ",
        "Recommended designated spare",
        "Completed replacement ",
    )
    return {
        key: value
        for key, value in metadata.items()
        if key not in excluded_exact
        and not key.startswith(excluded_prefixes)
    }


def _safe_serial_component(value):
    """Make an entered serial safe to use as one Windows path component."""
    value = str(value or "").strip()
    safe_value = re.sub(r"[^A-Za-z0-9_-]+", "-", value)
    return safe_value.strip("-_")


def build_run_directory_name(metadata, now=None):
    """Build the timestamped run folder name from optional serial metadata."""
    if now is None:
        now = datetime.now()
    timestamp = now.strftime("%y%m%d_%H%M%S")
    serials = [
        _safe_serial_component(metadata.get("Main board serial")),
        _safe_serial_component(metadata.get("Switch serial")),
    ]
    serial_suffix = "-".join(serial for serial in serials if serial)
    return "ILM-Run_%s%s" % (
        timestamp,
        ("_" + serial_suffix) if serial_suffix else "",
    )


def extract_run_timestamp(directory):
    """Return the timestamp portion of a run folder name.

    Current runs use ``YYMMDD_HHMMSS``.  The shorter ``HHMM`` format and
    older hyphenated folders are also accepted so an older run can be
    continued without changing its original test time.
    """
    name = Path(directory).name
    for pattern in (
        r"^ILM-Run_(\d{6}_\d{6})",
        r"^ILM-Run_(\d{6}_\d{4})",
        r"^ILM-Run-(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})",
    ):
        match = re.match(pattern, name)
        if match:
            return match.group(1)
    try:
        return datetime.fromtimestamp(Path(directory).stat().st_mtime).strftime(
            "%y%m%d_%H%M%S"
        )
    except OSError:
        return datetime.now().strftime("%y%m%d_%H%M%S")


def build_run_directory_name_for_timestamp(metadata, timestamp):
    """Build a run folder name while preserving an existing timestamp."""
    serials = [
        _safe_serial_component(metadata.get("Main board serial")),
        _safe_serial_component(metadata.get("Switch serial")),
    ]
    serial_suffix = "-".join(serial for serial in serials if serial)
    return "ILM-Run_%s%s" % (
        timestamp,
        ("_" + serial_suffix) if serial_suffix else "",
    )


def build_run_csv_path(directory):
    """Return the run CSV path using the run folder's final name."""
    directory = Path(directory)
    return directory / ("%s.csv" % directory.name)


def build_run_json_path(directory):
    """Return the run JSON path using the run folder's final name."""
    directory = Path(directory)
    return directory / ("%s.json" % directory.name)


def find_run_json_path(csv_path):
    """Find a same-named JSON file, falling back to the legacy run.json."""
    csv_path = Path(csv_path)
    same_named_path = csv_path.with_suffix(".json")
    legacy_path = csv_path.parent / "run.json"
    if same_named_path.is_file():
        return same_named_path
    if legacy_path.is_file():
        return legacy_path
    return same_named_path


class RunRecorder:
    """Write the current table and run-level timing metadata to disk."""

    def __init__(
        self,
        root: str | Path | None = None,
        metadata=None,
        limit=2.0,
        directory: str | Path | None = None,
    ):
        self.metadata = dict(metadata or {})
        self.limit = float(limit)
        self._fixed_directory = directory is not None
        if directory is not None:
            self.directory = Path(directory)
            self.root_path = self.directory.parent
        else:
            self.root_path = Path(root) if root is not None else DEFAULT_RUN_ROOT
            base_name = build_run_directory_name(self.metadata)
            directory = self.root_path / base_name
            suffix = 2
            while directory.exists():
                directory = self.root_path / ("%s-%d" % (base_name, suffix))
                suffix += 1
            self.directory = directory
        self.csv_path = build_run_csv_path(directory)
        self.json_path = build_run_json_path(directory)
        self.attempts = []
        self.replacement_analysis = None
        self.switch_test_sessions = []
        self.completed_replacements = []
        self._directory_created = False

    @classmethod
    def from_existing(
        cls,
        csv_path: str | Path,
        metadata=None,
        limit=2.0,
        attempts=None,
        replacement_analysis=None,
        switch_test_sessions=None,
        completed_replacements=None,
    ):
        """Create a recorder that updates an already-loaded CSV run."""
        recorder = cls.__new__(cls)
        recorder.csv_path = Path(csv_path)
        recorder.directory = recorder.csv_path.parent
        recorder.directory.mkdir(parents=True, exist_ok=True)
        recorder.root_path = recorder.directory.parent
        recorder.json_path = find_run_json_path(recorder.csv_path)
        recorder.metadata = dict(metadata or {})
        recorder.limit = float(limit)
        recorder.attempts = list(attempts or [])
        recorder.replacement_analysis = replacement_analysis
        recorder.switch_test_sessions = list(switch_test_sessions or [])
        recorder.completed_replacements = list(completed_replacements or [])
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
        stored_metadata = _run_metadata(self.metadata)
        payload = {
            "created_at": self.metadata.get("Created at", datetime.now().isoformat(timespec="seconds")),
            "run_number": stored_metadata.get("Run number"),
            "warning_limit_db": self.limit,
            "metadata": stored_metadata,
            "measurements": [
                {
                    "channel": record.channel,
                    "physical_port": record.physical_port,
                    "loss_1310_db": record.loss_1310,
                    "loss_1550_db": record.loss_1550,
                }
                for record in measurements
            ],
            "switch_test_sessions": self.switch_test_sessions,
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
        if self._fixed_directory:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.csv_path = build_run_csv_path(self.directory)
            self.json_path = build_run_json_path(self.directory)
            self._directory_created = True
            return
        self.root_path.mkdir(parents=True, exist_ok=True)
        if self.directory.exists():
            base_name = self.directory.name
            suffix = 2
            while (self.root_path / ("%s-%d" % (base_name, suffix))).exists():
                suffix += 1
            self.directory = self.root_path / ("%s-%d" % (base_name, suffix))
            self.csv_path = build_run_csv_path(self.directory)
            self.json_path = build_run_json_path(self.directory)
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

    def rename_for_metadata(self, metadata):
        """Rename a loaded run and its related files to match new serials.

        The original timestamp is retained.  A numbered suffix is used when
        another run already occupies the requested name.  Existing COC
        workbooks belonging to this run are renamed with the new main-board
        serial as well, without overwriting another workbook.
        """
        metadata = dict(metadata or {})
        if not self.directory.exists():
            self.metadata = metadata
            return self.metadata

        old_directory = self.directory
        numbered_match = re.fullmatch(r"Run-(\d+)(?:-.+)?", old_directory.name)
        if numbered_match:
            # Numbered runs belong to a unit directory. Their switch serial is
            # run-specific, so changing it only renames this run folder.
            switch_serial = _safe_serial_component(metadata.get("Switch serial"))
            base_name = "Run-%s" % numbered_match.group(1)
            if switch_serial:
                base_name += "-" + switch_serial
        else:
            timestamp = extract_run_timestamp(old_directory)
            base_name = build_run_directory_name_for_timestamp(metadata, timestamp)
        new_directory = old_directory.parent / base_name
        suffix = 2
        while new_directory.exists() and new_directory != old_directory:
            new_directory = old_directory.parent / ("%s-%d" % (base_name, suffix))
            suffix += 1

        old_csv_name = self.csv_path.name
        old_json_name = self.json_path.name
        old_csv_path = old_directory / old_csv_name
        old_json_path = old_directory / old_json_name
        new_csv_path = new_directory / ("%s.csv" % new_directory.name)
        new_json_path = new_directory / ("%s.json" % new_directory.name)

        if new_directory == old_directory:
            if new_csv_path.exists() and new_csv_path != old_csv_path:
                raise OSError("The target CSV filename already exists in the run folder.")
            if new_json_path.exists() and new_json_path != old_json_path:
                raise OSError("The target JSON filename already exists in the run folder.")
        else:
            if new_csv_path.exists() or new_json_path.exists():
                raise OSError("The target run folder already contains the target data files.")

        coc_files = []
        for candidate in sorted(old_directory.glob("COC OSX-150 *.xlsx")):
            if candidate.is_file():
                coc_files.append(candidate.name)

        if new_directory != old_directory:
            old_directory.rename(new_directory)

        moved_csv_path = new_directory / old_csv_name
        moved_json_path = new_directory / old_json_name
        if moved_csv_path.exists() and moved_csv_path != new_csv_path:
            moved_csv_path.rename(new_csv_path)
        if moved_json_path.exists() and moved_json_path != new_json_path:
            moved_json_path.rename(new_json_path)

        coc_renames = {}
        new_main_serial = _safe_serial_component(metadata.get("Main board serial"))
        if new_main_serial:
            used_coc_paths = set()
            for old_name in coc_files:
                source = new_directory / old_name
                if not source.exists():
                    continue
                match = re.match(
                    r"^(COC OSX-150 )(.*?)( \(\d+\))?\.xlsx$",
                    old_name,
                    re.IGNORECASE,
                )
                suffix_text = match.group(3) or "" if match else ""
                target = new_directory / (
                    "COC OSX-150 %s%s.xlsx" % (new_main_serial, suffix_text)
                )
                number = 2
                while target.exists() or target in used_coc_paths:
                    target = new_directory / (
                        "COC OSX-150 %s (%d).xlsx" % (new_main_serial, number)
                    )
                    number += 1
                source.rename(target)
                used_coc_paths.add(target)
                coc_renames[old_name] = target.name

        old_coc_file = self.metadata.get("COC output file")
        if old_coc_file in coc_renames:
            metadata["COC output file"] = coc_renames[old_coc_file]
            metadata["COC output path"] = str(new_directory / coc_renames[old_coc_file])
        elif old_coc_file:
            metadata["COC output file"] = Path(old_coc_file).name
            metadata["COC output path"] = str(new_directory / Path(old_coc_file).name)
        elif self.metadata.get("COC output path"):
            old_name = Path(self.metadata["COC output path"]).name
            metadata["COC output path"] = str(new_directory / coc_renames.get(old_name, old_name))

        self.directory = new_directory
        self.root_path = new_directory.parent
        self.csv_path = new_csv_path
        self.json_path = new_json_path
        self.metadata = metadata
        return self.metadata

    def _write_csv(self, measurements):
        rows = [["channel", "1310 IL", "1550 IL"]]
        rows.extend(
            [record.channel, "%.4f" % record.loss_1310, "%.4f" % record.loss_1550]
            for record in measurements
        )
        metadata_rows = [["Metadata", "Value"]]
        metadata_rows.extend(
            list(item) for item in sorted(_run_metadata(self.metadata).items())
        )
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
