"""Centralized application paths and stable configuration defaults."""

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUN_ROOT = Path.home() / "Documents" / "ILM-Reads"
DEFAULT_PART_LOOKUP_ROOT = Path(
    r"U:\Product Log\Units-COCs-Param Files\OSX-150"
)
COC_TEMPLATE_FILENAME = "OSX-100 Single Mode COC Template 1.xlsx"


@dataclass(frozen=True)
class AppPaths:
    """Paths shared by the desktop app and deployment tools."""

    project_root: Path = PROJECT_ROOT
    run_root: Path = DEFAULT_RUN_ROOT
    part_lookup_root: Path = DEFAULT_PART_LOOKUP_ROOT
    coc_template_filename: str = COC_TEMPLATE_FILENAME

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
