"""Compatibility facade for application configuration paths."""

from config.app_config import (
    AppPaths,
    COC_TEMPLATE_FILENAME,
    DEFAULT_PART_LOOKUP_ROOT,
    DEFAULT_PATHS,
    DEFAULT_RUN_ROOT,
    PROJECT_ROOT,
    SUPPORT_LOG_COMPRESSION_AFTER_DAYS,
    SUPPORT_LOG_MAX_FILE_BYTES,
    SUPPORT_LOG_MAX_TOTAL_BYTES,
    SUPPORT_LOG_MEMORY_CAPACITY,
    SUPPORT_LOG_QUEUE_CAPACITY,
    SUPPORT_LOG_RETENTION_DAYS,
    default_support_log_root,
    fallback_support_log_root,
)

__all__ = [
    "AppPaths",
    "COC_TEMPLATE_FILENAME",
    "DEFAULT_PART_LOOKUP_ROOT",
    "DEFAULT_PATHS",
    "DEFAULT_RUN_ROOT",
    "PROJECT_ROOT",
    "SUPPORT_LOG_COMPRESSION_AFTER_DAYS",
    "SUPPORT_LOG_MAX_FILE_BYTES",
    "SUPPORT_LOG_MAX_TOTAL_BYTES",
    "SUPPORT_LOG_MEMORY_CAPACITY",
    "SUPPORT_LOG_QUEUE_CAPACITY",
    "SUPPORT_LOG_RETENTION_DAYS",
    "default_support_log_root",
    "fallback_support_log_root",
]
