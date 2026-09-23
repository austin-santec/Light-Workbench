"""Persistence helpers for device-level data shared by multiple test runs."""

import json
import os
import re
from datetime import datetime
from pathlib import Path


UNIT_SCHEMA_VERSION = 2
UNIT_FILENAME = "unit.json"


def _safe_component(value):
    """Return a value that is safe to use as one Windows path component."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "").strip())
    return cleaned.strip("-_")


def build_unit_directory_name(metadata):
    """Build a stable unit folder name from the strongest available identity."""
    # A switch can be replaced while the physical unit remains the same, so
    # switch serial is deliberately not part of the unit directory identity.
    for key in ("Main board serial", "Part number"):
        value = _safe_component(metadata.get(key))
        if value:
            return "Unit-%s" % value
    return "Unit-Unknown"


def unit_directory_for_metadata(root, metadata):
    """Return the unit directory for an identity without creating it."""
    return Path(root) / build_unit_directory_name(metadata)


def unit_json_path(unit_directory):
    return Path(unit_directory) / UNIT_FILENAME


def run_directory_for_number(unit_directory, run_number, switch_serial=None):
    """Return a numbered run directory, including its switch serial when set."""
    name = "Run-%d" % int(run_number)
    switch_component = _safe_component(switch_serial)
    if switch_component:
        name += "-" + switch_component
    return Path(unit_directory) / name


def run_csv_for_number(unit_directory, run_number, switch_serial=None):
    directory = run_directory_for_number(unit_directory, run_number, switch_serial)
    return directory / ("%s.csv" % directory.name)


def run_directory_candidates(unit_directory, run_number):
    """Return existing legacy and serial-suffixed directories for a run number."""
    unit_directory = Path(unit_directory)
    candidates = []
    requested_number = int(run_number)
    for candidate in unit_directory.glob("Run-*"):
        if not candidate.is_dir():
            continue
        match = re.fullmatch(r"Run-(\d+)(?:-.+)?", candidate.name)
        if match and int(match.group(1)) == requested_number:
            candidates.append(candidate)
    prefix = "Run-%d" % requested_number
    return sorted(candidates, key=lambda path: (path.name != prefix, path.name))


def run_csv_candidates(unit_directory, run_number):
    """Return existing CSV files for a numbered run, including legacy paths."""
    return [
        candidate / (candidate.name + ".csv")
        for candidate in run_directory_candidates(unit_directory, run_number)
        if (candidate / (candidate.name + ".csv")).is_file()
    ]


def find_run_csv_for_number(unit_directory, run_number, switch_serial=None):
    """Find a numbered run CSV, preferring the entered switch serial.

    A single legacy or serial-suffixed run is accepted when no exact serial
    match exists. This keeps older numbered runs loadable after the naming
    convention changes.
    """
    preferred = run_csv_for_number(unit_directory, run_number, switch_serial)
    if preferred.is_file():
        return preferred
    candidates = run_csv_candidates(unit_directory, run_number)
    if len(candidates) == 1:
        return candidates[0]
    legacy = run_csv_for_number(unit_directory, run_number)
    if legacy.is_file():
        return legacy
    return None


def infer_unit_directory(csv_path):
    """Return a unit directory when a CSV is inside the new unit layout."""
    csv_path = Path(csv_path)
    run_directory = csv_path.parent
    if not re.fullmatch(r"Run-\d+(?:-.+)?", run_directory.name):
        return None
    unit_directory = run_directory.parent
    if unit_json_path(unit_directory).is_file():
        return unit_directory
    return None


def _normalise_spares(values):
    result = []
    for value in values or []:
        try:
            port = int(value)
        except (TypeError, ValueError):
            continue
        if port > 0 and port not in result:
            result.append(port)
    return sorted(result)


def _normalise_replacements(values):
    result = []
    for value in values or []:
        try:
            current_port = int(value.get("current_port"))
            replacement_port = int(value.get("replacement_port"))
        except (AttributeError, TypeError, ValueError):
            continue
        if current_port < 1 or replacement_port < 1:
            continue
        result.append(
            {
                "current_port": current_port,
                "replacement_port": replacement_port,
            }
        )
    return result


def load_unit_record(unit_directory):
    """Load a unit record, returning an empty compatible record if absent."""
    path = unit_json_path(unit_directory)
    if not path.is_file():
        return {
            "schema_version": UNIT_SCHEMA_VERSION,
            "unit_metadata": {},
            "completed_replacements": [],
            "designated_spares": [],
            "runs": [],
        }
    with path.open("r", encoding="utf-8") as json_file:
        payload = json.load(json_file)
    return {
        "schema_version": payload.get("schema_version", UNIT_SCHEMA_VERSION),
        "unit_metadata": {
            key: value
            for key, value in dict(payload.get("unit_metadata") or {}).items()
            if key != "Switch serial"
        },
        "completed_replacements": _normalise_replacements(
            payload.get("completed_replacements")
        ),
        "designated_spares": _normalise_spares(
            payload.get("designated_spares")
        ),
        "runs": list(payload.get("runs") or []),
    }


def save_unit_record(
    unit_directory,
    unit_metadata,
    completed_replacements,
    designated_spares,
    run_number,
    run_directory,
    switch_serial=None,
):
    """Atomically save shared unit data and the known run index."""
    unit_directory = Path(unit_directory)
    unit_directory.mkdir(parents=True, exist_ok=True)
    existing = load_unit_record(unit_directory)
    runs = [
        item
        for item in existing["runs"]
        if str(item.get("run_number")) != str(run_number)
    ]
    run_directory = Path(run_directory)
    runs.append(
        {
            "run_number": int(run_number),
            "directory": run_directory.name,
            "csv_file": "%s.csv" % run_directory.name,
            "switch_serial": str(switch_serial or "").strip(),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    payload = {
        "schema_version": UNIT_SCHEMA_VERSION,
        "unit_metadata": {
            key: str(unit_metadata.get(key) or "").strip()
            for key in ("Main board serial", "Part number")
            if str(unit_metadata.get(key) or "").strip()
        },
        "completed_replacements": _normalise_replacements(
            completed_replacements
        ),
        "designated_spares": _normalise_spares(designated_spares),
        "runs": sorted(runs, key=lambda item: int(item.get("run_number", 0))),
    }
    temporary_path = unit_json_path(unit_directory).with_suffix(".json.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8") as json_file:
            json.dump(payload, json_file, indent=2)
            json_file.write("\n")
            json_file.flush()
            os.fsync(json_file.fileno())
        os.replace(temporary_path, unit_json_path(unit_directory))
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def available_run_numbers(unit_directory):
    """Return numbered runs whose CSV files are present."""
    unit_directory = Path(unit_directory)
    numbers = []
    for candidate in unit_directory.glob("Run-*/Run-*.csv"):
        match = re.fullmatch(r"Run-(\d+)(?:-.+)?", candidate.parent.name)
        if match and candidate.is_file():
            numbers.append(int(match.group(1)))
    return sorted(set(numbers))
