"""File-backed reporting services for future analysis presentations."""

from pathlib import Path

from domain.reporting import MultiRunSummary, aggregate_run_summaries

from .run_query import FileRunQueryService


class FileRunReportService:
    """Build in-memory reports from the existing unit/run file layout."""

    def __init__(self, query_service: FileRunQueryService | None = None):
        self.query_service = query_service or FileRunQueryService()

    def summarize_unit(
        self,
        unit_directory: str | Path,
        warning_limit: float,
    ) -> MultiRunSummary:
        """Aggregate the readable runs belonging to one unit."""
        summaries = self.query_service.summarize_unit_runs(
            unit_directory,
            warning_limit,
        )
        return aggregate_run_summaries(summaries)

    def summarize_root(
        self,
        run_root: str | Path,
        warning_limit: float,
    ) -> MultiRunSummary:
        """Aggregate readable runs across all indexed unit folders."""
        summaries = self.query_service.summarize_root_runs(
            run_root,
            warning_limit,
        )
        return aggregate_run_summaries(summaries)


__all__ = ["FileRunReportService"]
