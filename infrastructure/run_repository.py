"""File-backed repository boundary for run CSV and JSON data."""

from pathlib import Path
from typing import Any

from config.app_config import DEFAULT_RUN_ROOT
from domain.run_data import RunData
from infrastructure.csv_run_loader import load_run_csv as _load_run_csv
from infrastructure.run_persistence import (
    RunRecorder,
    find_run_json_path as _find_run_json_path,
    load_run_json as _load_run_json,
)
from infrastructure.unit_persistence import (
    available_run_numbers as _available_run_numbers,
    find_run_csv_for_number as _find_run_csv_for_number,
    run_csv_for_number as _run_csv_for_number,
)


class FileRunRepository:
    """Provide application-facing access to the current file-based run store."""

    def load_csv(self, path: str | Path) -> RunData:
        """Load a CSV run using the compatibility-aware CSV reader."""
        return _load_run_csv(path)

    def load_json(self, path: str | Path) -> dict:
        """Load a companion JSON audit record."""
        return _load_run_json(path)

    def find_json_path(self, csv_path: str | Path) -> Path:
        """Find the current or legacy JSON companion for a CSV path."""
        return _find_run_json_path(csv_path)

    def available_run_numbers(self, unit_directory: str | Path) -> list[int]:
        """Return numbered runs that have a saved CSV file."""
        return _available_run_numbers(unit_directory)

    def run_csv_for_number(
        self,
        unit_directory: str | Path,
        run_number: int,
        switch_serial: str | None = None,
    ) -> Path:
        """Return the preferred path for a numbered unit run."""
        return _run_csv_for_number(unit_directory, run_number, switch_serial)

    def find_run_csv_for_number(
        self,
        unit_directory: str | Path,
        run_number: int,
        switch_serial: str | None = None,
    ) -> Path | None:
        """Find a numbered run while preserving legacy naming support."""
        return _find_run_csv_for_number(unit_directory, run_number, switch_serial)

    def new_recorder(self, *args: Any, **kwargs: Any) -> RunRecorder:
        """Create a recorder for a new or explicitly selected run directory."""
        return RunRecorder(*args, **kwargs)

    def recorder_from_existing(self, *args: Any, **kwargs: Any) -> RunRecorder:
        """Create a recorder that updates an existing run."""
        return RunRecorder.from_existing(*args, **kwargs)


__all__ = ["DEFAULT_RUN_ROOT", "FileRunRepository"]
