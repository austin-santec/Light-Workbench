"""Database run lifecycle states and production-analysis policy."""

from __future__ import annotations

from enum import Enum

from domain.database_records import RunRecord


class StaleRunDecision(str, Enum):
    RESUME = "resume"
    CLOSE_STOPPED = "close_stopped"
    CLOSE_FAILED = "close_failed"


def is_normal_production_analysis_eligible(run: RunRecord) -> bool:
    """Return whether a run belongs in ordinary production analysis."""
    return (
        run.run_purpose == "production"
        and run.completion_status == "complete"
        and run.analysis_status == "included"
    )


__all__ = ["StaleRunDecision", "is_normal_production_analysis_eligible"]
