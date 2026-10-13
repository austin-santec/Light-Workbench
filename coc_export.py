"""Compatibility facade for the infrastructure COC exporter."""

from infrastructure.coc_export import (
    COC_TEMPLATE_45_FILENAME,
    COC_TEMPLATE_48_FILENAME,
    COC_TEMPLATE_FILENAME,
    COC_TEMPLATE_PROFILE_FILENAMES,
    CocTemplateProfile,
    DEFAULT_PART_LOOKUP_ROOT,
    export_coc,
    find_part_number,
    inspect_coc_template_capacity,
    inspect_coc_template_profile,
    measurement_rows,
    normalise_serial,
    template_filename_for_channel_count,
    template_filename_for_profile,
    template_profile_for,
)

__all__ = [
    "COC_TEMPLATE_45_FILENAME",
    "COC_TEMPLATE_48_FILENAME",
    "COC_TEMPLATE_FILENAME",
    "COC_TEMPLATE_PROFILE_FILENAMES",
    "CocTemplateProfile",
    "DEFAULT_PART_LOOKUP_ROOT",
    "export_coc",
    "find_part_number",
    "inspect_coc_template_capacity",
    "inspect_coc_template_profile",
    "measurement_rows",
    "normalise_serial",
    "template_filename_for_channel_count",
    "template_filename_for_profile",
    "template_profile_for",
]
