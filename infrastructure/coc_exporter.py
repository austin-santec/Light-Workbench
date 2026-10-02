"""Application-facing boundary for COC template lookup and XLSX export."""

from pathlib import Path
from typing import Any

from config.app_config import COC_TEMPLATE_FILENAME, DEFAULT_PART_LOOKUP_ROOT
from infrastructure.coc_export import (
    export_coc as _export_coc,
    find_part_number as _find_part_number,
    normalise_serial as _normalise_serial,
)


class FileCocExporter:
    """Provide the current file-backed COC and part lookup operations."""

    def __init__(self, support_logger=None):
        self.support_logger = support_logger

    def find_part_number(
        self,
        main_board_serial: str,
        lookup_root: str | Path = DEFAULT_PART_LOOKUP_ROOT,
    ) -> str:
        """Find a part number in the configured OSX-150 folder tree."""
        return _find_part_number(main_board_serial, lookup_root)

    def normalise_serial(self, value: str) -> str:
        """Normalize the serial format used in COC fields and filenames."""
        return _normalise_serial(value)

    def export(
        self,
        template_path: str | Path,
        output_directory: str | Path,
        measurements: list[Any],
        part_number: str,
        main_board_serial: str,
        export_date=None,
        tested_by: str = "",
    ) -> Path:
        """Create a COC workbook from the template without altering it."""
        try:
            result = _export_coc(
                template_path,
                output_directory,
                measurements,
                part_number,
                main_board_serial,
                export_date=export_date,
                tested_by=tested_by,
            )
        except Exception as error:
            self._record(
                "export.coc_failed",
                level="error",
                destination=output_directory,
                measurement_count=len(measurements),
                unit_serial=main_board_serial,
                error_type=type(error).__name__,
                error_message=str(error),
                status="error",
            )
            raise
        self._record(
            "export.coc_completed",
            destination=result,
            file_type="xlsx",
            measurement_count=len(measurements),
            unit_serial=main_board_serial,
            operator_initials=tested_by,
            status="success",
        )
        return result

    def _record(self, event, **fields):
        if self.support_logger is None:
            return
        try:
            self.support_logger.record("export", event, **fields)
        except Exception:
            pass


__all__ = [
    "COC_TEMPLATE_FILENAME",
    "DEFAULT_PART_LOOKUP_ROOT",
    "FileCocExporter",
]
