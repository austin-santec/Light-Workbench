"""Read-only queries over the current file-backed run repository."""

from pathlib import Path

from domain.reporting import RunSummary, summarize_run

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
        unit_directory = Path(unit_directory)
        record = self.unit_repository.load_record(unit_directory)
        summaries = []
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
            summaries.append(
                summarize_run(
                    run_data.measurements,
                    run_data.metadata,
                    warning_limit,
                )
            )
        return sorted(
            summaries,
            key=lambda summary: (
                summary.run_number is None,
                summary.run_number or 0,
            ),
        )


__all__ = ["FileRunQueryService"]
