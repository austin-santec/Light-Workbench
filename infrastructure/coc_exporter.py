"""Application-facing boundary for COC template lookup and XLSX export."""

from pathlib import Path
from typing import Any

from app_config import COC_TEMPLATE_FILENAME, DEFAULT_PART_LOOKUP_ROOT
from infrastructure.coc_export import (
    export_coc as _export_coc,
    find_part_number as _find_part_number,
    normalise_serial as _normalise_serial,
)


class FileCocExporter:
    """Provide the current file-backed COC and part lookup operations."""

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
        return _export_coc(
            template_path,
            output_directory,
            measurements,
            part_number,
            main_board_serial,
            export_date=export_date,
            tested_by=tested_by,
        )


__all__ = [
    "COC_TEMPLATE_FILENAME",
    "DEFAULT_PART_LOOKUP_ROOT",
    "FileCocExporter",
]
