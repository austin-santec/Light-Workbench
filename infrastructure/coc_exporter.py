"""Application-facing boundary for COC template lookup and XLSX export."""

from pathlib import Path
from typing import Any

from config.app_config import (
    COC_TEMPLATE_45_FILENAME,
    COC_TEMPLATE_48_FILENAME,
    COC_TEMPLATE_FILENAME,
    COC_TEMPLATE_PROFILE_FILENAMES,
    DEFAULT_PART_LOOKUP_ROOT,
)
from infrastructure.coc_export import (
    CocTemplateProfile,
    export_coc as _export_coc,
    find_part_number as _find_part_number,
    inspect_coc_template_capacity as _inspect_coc_template_capacity,
    inspect_coc_template_profile as _inspect_coc_template_profile,
    normalise_serial as _normalise_serial,
    template_filename_for_channel_count as _template_filename_for_channel_count,
    template_filename_for_profile as _template_filename_for_profile,
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

    def inspect_template_capacity(self, template_path: str | Path) -> int:
        """Validate a COC template and return its supported channel capacity."""
        return _inspect_coc_template_capacity(template_path)

    def inspect_template_profile(self, template_path: str | Path) -> CocTemplateProfile:
        """Validate and identify a COC template's complete report profile."""
        return _inspect_coc_template_profile(template_path)

    def template_filename_for_channel_count(self, channel_count: int) -> str:
        """Return the approved default template filename for a channel count."""
        return _template_filename_for_channel_count(channel_count)

    def template_filename_for_profile(
        self, model: str, wavelength_mode: str, channel_count: int
    ) -> str:
        """Return the approved filename for a model, mode, and capacity."""
        return _template_filename_for_profile(model, wavelength_mode, channel_count)

    def export(
        self,
        template_path: str | Path,
        output_directory: str | Path,
        measurements: list[Any],
        part_number: str,
        main_board_serial: str,
        export_date=None,
        tested_by: str = "",
        front_panel_channel_count: int = 48,
        export_timestamp=None,
        coc_attempt_id: str | None = None,
        switch_model: str = "OSX-150",
        wavelength_mode: str = "SM",
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
                front_panel_channel_count=front_panel_channel_count,
                export_timestamp=export_timestamp,
                switch_model=switch_model,
                wavelength_mode=wavelength_mode,
            )
        except Exception as error:
            self._record(
                "export.coc_failed",
                operation_id=coc_attempt_id,
                level="error",
                destination=output_directory,
                measurement_count=len(measurements),
                unit_serial=main_board_serial,
                **(
                    {"coc_attempt_id": coc_attempt_id}
                    if coc_attempt_id is not None
                    else {}
                ),
                error_type=type(error).__name__,
                error_message=str(error),
                status="error",
            )
            raise
        self._record(
            "export.coc_completed",
            operation_id=coc_attempt_id,
            destination=result,
            file_type="xlsx",
            measurement_count=len(measurements),
            unit_serial=main_board_serial,
            operator_initials=tested_by,
            switch_model=switch_model,
            wavelength_mode=wavelength_mode,
            **(
                {"coc_attempt_id": coc_attempt_id}
                if coc_attempt_id is not None
                else {}
            ),
            status="success",
        )
        return result

    def _record(self, event, operation_id=None, **fields):
        if self.support_logger is None:
            return
        try:
            if operation_id is None:
                self.support_logger.record("export", event, **fields)
            else:
                self.support_logger.record(
                    "export", event, operation_id=operation_id, **fields
                )
        except Exception:
            pass


__all__ = [
    "COC_TEMPLATE_PROFILE_FILENAMES",
    "COC_TEMPLATE_FILENAME",
    "COC_TEMPLATE_45_FILENAME",
    "COC_TEMPLATE_48_FILENAME",
    "DEFAULT_PART_LOOKUP_ROOT",
    "CocTemplateProfile",
    "FileCocExporter",
]
