"""File-backed repository boundary for unit records and numbered runs."""

from pathlib import Path

from infrastructure.unit_persistence import (
    UNIT_SCHEMA_VERSION,
    available_run_numbers as _available_run_numbers,
    find_run_csv_for_number as _find_run_csv_for_number,
    infer_unit_directory as _infer_unit_directory,
    load_unit_record as _load_unit_record,
    run_csv_for_number as _run_csv_for_number,
    run_directory_for_number as _run_directory_for_number,
    save_unit_record as _save_unit_record,
    unit_directory_for_metadata as _unit_directory_for_metadata,
)


class FileUnitRepository:
    """Provide application-facing access to unit JSON and unit run paths."""

    def __init__(self, support_logger=None):
        self.support_logger = support_logger

    def available_run_numbers(self, unit_directory: str | Path) -> list[int]:
        """Return saved numbered runs for a unit."""
        return _available_run_numbers(unit_directory)

    def find_run_csv_for_number(
        self,
        unit_directory: str | Path,
        run_number: int,
        switch_serial: str | None = None,
    ) -> Path | None:
        """Find a unit run CSV using current and legacy naming conventions."""
        return _find_run_csv_for_number(unit_directory, run_number, switch_serial)

    def infer_unit_directory(self, csv_path: str | Path) -> Path | None:
        """Infer a unit directory from a numbered-run CSV path."""
        return _infer_unit_directory(csv_path)

    def load_record(self, unit_directory: str | Path) -> dict:
        """Load a unit record or return the default empty record."""
        return _load_unit_record(unit_directory)

    def run_csv_for_number(
        self,
        unit_directory: str | Path,
        run_number: int,
        switch_serial: str | None = None,
    ) -> Path:
        """Return the preferred CSV path for a numbered run."""
        return _run_csv_for_number(unit_directory, run_number, switch_serial)

    def run_directory_for_number(
        self,
        unit_directory: str | Path,
        run_number: int,
        switch_serial: str | None = None,
    ) -> Path:
        """Return the preferred directory for a numbered run."""
        return _run_directory_for_number(unit_directory, run_number, switch_serial)

    def save_record(
        self,
        unit_directory: str | Path,
        unit_metadata: dict,
        completed_replacements: list[dict],
        designated_spares: list[int],
        run_number: int,
        run_directory: str | Path,
        switch_serial: str | None = None,
        replacement_history: list[dict] | None = None,
    ) -> None:
        """Atomically save unit metadata and its run index."""
        try:
            _save_unit_record(
                unit_directory,
                unit_metadata,
                completed_replacements,
                designated_spares,
                run_number,
                run_directory,
                switch_serial,
                replacement_history,
            )
        except Exception as error:
            self._record(
                "persistence.unit_save_failed",
                level="error",
                destination=unit_directory,
                run_number=run_number,
                error_type=type(error).__name__,
                error_message=str(error),
                status="error",
            )
            raise
        self._record(
            "persistence.unit_save_completed",
            destination=unit_directory,
            run_number=run_number,
            switch_serial=switch_serial,
            unit_serial=unit_metadata.get("Main board serial"),
            schema_version_written=UNIT_SCHEMA_VERSION,
            status="success",
        )

    def _record(self, event, **fields):
        if self.support_logger is None:
            return
        try:
            self.support_logger.record("persistence", event, **fields)
        except Exception:
            pass

    def unit_directory_for_metadata(
        self,
        root: str | Path,
        metadata: dict,
    ) -> Path:
        """Resolve a unit directory without creating it."""
        return _unit_directory_for_metadata(root, metadata)


__all__ = ["FileUnitRepository"]
