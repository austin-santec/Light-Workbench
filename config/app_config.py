"""Centralized application paths and stable configuration defaults."""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUN_ROOT = Path.home() / "Documents" / "ILM-Reads"
DEFAULT_PART_LOOKUP_ROOT = Path(
    r"U:\Product Log\Units-COCs-Param Files\OSX-150"
)
COC_TEMPLATE_FILENAME = "OSX-100 Single Mode COC Template 1.xlsx"
SUPPORT_LOG_RETENTION_DAYS = 30
SUPPORT_LOG_COMPRESSION_AFTER_DAYS = 7
SUPPORT_LOG_MAX_FILE_BYTES = 25 * 1024 * 1024
SUPPORT_LOG_MAX_TOTAL_BYTES = 500 * 1024 * 1024
SUPPORT_LOG_QUEUE_CAPACITY = 10000
SUPPORT_LOG_MEMORY_CAPACITY = 1000


def default_support_log_root() -> Path:
    """Return the per-user support-log directory without using install paths."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "LightWorkbench" / "logs"


def fallback_support_log_root() -> Path:
    """Return a safe temporary fallback for degraded file logging."""
    return Path(tempfile.gettempdir()) / "LightWorkbench" / "logs"


@dataclass(frozen=True)
class AppPaths:
    """Paths shared by the desktop app and deployment tools."""

    project_root: Path = PROJECT_ROOT
    run_root: Path = DEFAULT_RUN_ROOT
    part_lookup_root: Path = DEFAULT_PART_LOOKUP_ROOT
    coc_template_filename: str = COC_TEMPLATE_FILENAME
    support_log_root: Path = default_support_log_root()
    support_log_fallback_root: Path = fallback_support_log_root()

    @property
    def coc_template_path(self) -> Path:
        return self.project_root / "Templates" / self.coc_template_filename

    @property
    def assets_root(self) -> Path:
        return self.project_root / "assets"

    @property
    def instructions_path(self) -> Path:
        return self.project_root / "ILM_READING_GUIDE.html"


DEFAULT_PATHS = AppPaths()
