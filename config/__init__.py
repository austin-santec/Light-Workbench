"""Application configuration and user-facing release metadata."""

from .app_config import (
    AppPaths,
    COC_TEMPLATE_FILENAME,
    DEFAULT_PART_LOOKUP_ROOT,
    DEFAULT_PATHS,
    DEFAULT_RUN_ROOT,
    PROJECT_ROOT,
)
from .app_info import APP_DESCRIPTION, APP_NAME, APP_TAGLINE, APP_VERSION, about_text

__all__ = [
    "APP_DESCRIPTION",
    "APP_NAME",
    "APP_TAGLINE",
    "APP_VERSION",
    "AppPaths",
    "COC_TEMPLATE_FILENAME",
    "DEFAULT_PART_LOOKUP_ROOT",
    "DEFAULT_PATHS",
    "DEFAULT_RUN_ROOT",
    "PROJECT_ROOT",
    "about_text",
]
