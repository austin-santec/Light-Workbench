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
COC_TEMPLATE_45_FILENAME = "OSX-150 Single Mode COC Template 2 (45max).xlsx"
COC_TEMPLATE_48_FILENAME = "OSX-150 Single Mode COC Template 1 (48max).xlsx"
# The bundled COC catalog is keyed by switch model, wavelength mode, and
# report capacity.  The legacy constants above remain OSX-150 SM aliases.
COC_TEMPLATE_PROFILE_FILENAMES = {
    ("OSX-100", "SM", 45): "OSX-100 Single Mode COC Template 2 (45max).xlsx",
    ("OSX-100", "SM", 48): "OSX-100 Single Mode COC Template 1 (48max).xlsx",
    ("OSX-100", "MM", 45): "OSX-100 Multi Mode COC Template 2 (45max).xlsx",
    ("OSX-100", "MM", 48): "OSX-100 Multi Mode COC Template 1 (48max).xlsx",
    ("OSX-150", "SM", 45): COC_TEMPLATE_45_FILENAME,
    ("OSX-150", "SM", 48): COC_TEMPLATE_48_FILENAME,
}
# Compatibility name for older imports. New code selects by channel capacity.
COC_TEMPLATE_FILENAME = COC_TEMPLATE_45_FILENAME
# Support logs are retained indefinitely. The 500 MB value is a warning
# threshold for operator-managed archiving/deletion, not an automatic cleanup
# limit.
SUPPORT_LOG_RETENTION_DAYS = None
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


def default_limit_profile_path() -> Path:
    """Return the per-user administrator profile location."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "LightWorkbench" / "config" / "limit_profiles.ini"


def default_timing_profile_path() -> Path:
    """Return the per-user administrator timing-profile location."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "LightWorkbench" / "config" / "timing_profiles.ini"


def default_database_config_path() -> Path:
    """Return the per-user, non-secret SQL Server settings location."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "LightWorkbench" / "config" / "database.ini"


@dataclass(frozen=True)
class AppPaths:
    """Paths shared by the desktop app and deployment tools."""

    project_root: Path = PROJECT_ROOT
    run_root: Path = DEFAULT_RUN_ROOT
    part_lookup_root: Path = DEFAULT_PART_LOOKUP_ROOT
    coc_template_filename: str = COC_TEMPLATE_FILENAME
    support_log_root: Path = default_support_log_root()
    support_log_fallback_root: Path = fallback_support_log_root()
    limit_profile_path: Path = default_limit_profile_path()
    timing_profile_path: Path = default_timing_profile_path()
    database_config_path: Path = default_database_config_path()

    @property
    def coc_template_path(self) -> Path:
        return self.project_root / "Templates" / self.coc_template_filename

    def coc_template_path_for_capacity(self, capacity: int) -> Path:
        """Return the legacy OSX-150 SM template for a report capacity."""
        return self.coc_template_path_for_profile("OSX-150", "SM", capacity)

    def coc_template_path_for_profile(
        self, model: str, wavelength_mode: str, capacity: int
    ) -> Path:
        """Return the bundled template for a model, mode, and capacity."""
        normalized_model = str(model or "").strip().upper().replace("_", "-")
        normalized_mode = str(wavelength_mode or "SM").strip().upper()
        report_capacity = 45 if int(capacity) <= 45 else 48
        filename = COC_TEMPLATE_PROFILE_FILENAMES.get(
            (normalized_model, normalized_mode, report_capacity)
        )
        if filename is None:
            raise ValueError(
                "No bundled COC template is approved for %s %s (%d channels)."
                % (normalized_model or "unknown model", normalized_mode, report_capacity)
            )
        return self.project_root / "Templates" / filename

    @property
    def assets_root(self) -> Path:
        return self.project_root / "assets"

    @property
    def instructions_path(self) -> Path:
        return self.project_root / "ILM_READING_GUIDE.html"


DEFAULT_PATHS = AppPaths()
