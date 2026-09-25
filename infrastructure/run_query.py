"""Read-only queries over the current file-backed run repository."""

from collections.abc import Iterator
from pathlib import Path

from domain.reporting import RunSummary, summarize_run
from domain.run_data import RunData

from .run_repository import FileRunRepository
from .unit_repository import FileUnitRepository


class FileRunQueryService:
    """Load and summarize saved runs without modifying operator data."""

    def __init__(
        self,
        run_repository: FileRunRepository | None = None,
        unit_repository: FileUnitRepository | None = None,
    ):
        self.run_repository = run_repository or FileRunRepository()
        self.unit_repository = unit_repository or FileUnitRepository()

    def summarize_unit_runs(
        self,
        unit_directory: str | Path,
        warning_limit: float,
    ) -> list[RunSummary]:
        """Return summaries for all readable CSV runs indexed for a unit."""
        summaries = [
            summarize_run(run_data.measurements, run_data.metadata, warning_limit)
            for _, run_data in self.iter_unit_runs(unit_directory)
        ]
        return sorted(
            summaries,
            key=lambda summary: (
                summary.run_number is None,
                summary.run_number or 0,
            ),
        )

    def iter_unit_runs(
        self,
        unit_directory: str | Path,
    ) -> Iterator[tuple[Path, RunData]]:
        """Yield readable indexed CSV runs without changing source files."""
        unit_directory = Path(unit_directory)
        record = self.unit_repository.load_record(unit_directory)
        for run_entry in record.get("runs", []):
            if not isinstance(run_entry, dict):
                continue
            directory_name = str(run_entry.get("directory") or "").strip()
            csv_name = str(run_entry.get("csv_file") or "").strip()
            if not directory_name or not csv_name:
                continue
            csv_path = unit_directory / directory_name / csv_name
            if not csv_path.is_file():
                continue
            try:
                run_data = self.run_repository.load_csv(csv_path)
            except (OSError, ValueError):
                continue
            yield csv_path, run_data

    def summarize_root_runs(
        self,
        run_root: str | Path,
        warning_limit: float,
    ) -> list[RunSummary]:
        """Return summaries from every indexed unit below a run root."""
        run_root = Path(run_root)
        summaries = []
        for unit_directory in sorted(run_root.glob("Unit-*")):
            if not unit_directory.is_dir():
                continue
            summaries.extend(
                self.summarize_unit_runs(unit_directory, warning_limit)
            )
        return sorted(
            summaries,
            key=lambda summary: (
                summary.run_number is None,
                summary.run_number or 0,
                summary.switch_serial.casefold(),
            ),
        )


__all__ = ["FileRunQueryService"]
