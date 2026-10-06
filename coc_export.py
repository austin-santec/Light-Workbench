"""Compatibility facade for the infrastructure COC exporter."""

from infrastructure.coc_export import (
    COC_TEMPLATE_45_FILENAME,
    COC_TEMPLATE_48_FILENAME,
    COC_TEMPLATE_FILENAME,
    DEFAULT_PART_LOOKUP_ROOT,
    export_coc,
    find_part_number,
    inspect_coc_template_capacity,
    measurement_rows,
    normalise_serial,
    template_filename_for_channel_count,
)

__all__ = [
    "COC_TEMPLATE_45_FILENAME",
    "COC_TEMPLATE_48_FILENAME",
    "COC_TEMPLATE_FILENAME",
    "DEFAULT_PART_LOOKUP_ROOT",
    "export_coc",
    "find_part_number",
    "inspect_coc_template_capacity",
    "measurement_rows",
    "normalise_serial",
    "template_filename_for_channel_count",
]
