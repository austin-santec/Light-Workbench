"""Application workflow for database-backed run identity and lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from application.database_repositories import RunRepository
from domain.database_records import RunRecord, RunStartSpec, utc_now
from domain.database_run_lifecycle import StaleRunDecision


class DatabaseReadinessResult(Protocol):
    ready: bool
    operator_message: str


class DatabaseRunUnavailableError(RuntimeError):
    """Raised when database readiness prevents a new run from starting."""

    def __init__(self, preflight_result) -> None:
        super().__init__(preflight_result.operator_message)
        self.preflight_result = preflight_result


class RunLifecycleWorkflow:
    """Coordinate retry-safe run creation, closure, and stale-run decisions."""

    def __init__(
        self,
        repository: RunRepository,
        readiness_check: Callable[[], DatabaseReadinessResult],
    ) -> None:
        self._repository = repository
        self._readiness_check = readiness_check

    def start_run(
        self,
        *,
        assignment_id: int,
        tested_by: str,
        wavelength_mode: str,
        operating_band: str,
        application_version: str,
        measurement_hardware: Mapping,
        limit_snapshot: Mapping,
        part_number_snapshot: str | None,
        front_panel_channel_count: int | None,
        run_purpose: str = "production",
        analysis_status: str | None = None,
        analysis_exclusion_reason: str | None = None,
        notes: str | None = None,
        client_run_uuid: UUID | None = None,
        started_at_utc: datetime | None = None,
    ) -> RunRecord:
        preflight = self._readiness_check()
        if not getattr(preflight, "ready", False):
            raise DatabaseRunUnavailableError(preflight)

        purpose = str(run_purpose).strip().lower()
        if analysis_status is None:
            if purpose == "production":
                analysis_status = "pending"
            else:
                analysis_status = "excluded"
                analysis_exclusion_reason = (
                    analysis_exclusion_reason or f"Run purpose: {purpose}"
                )
        if purpose != "production" and analysis_status == "included":
            raise ValueError("Only production runs may enter normal production analysis")
        spec = RunStartSpec(
            assignment_id=assignment_id,
            client_run_uuid=client_run_uuid or uuid4(),
            run_started_at_utc=started_at_utc or utc_now(),
            tested_by=tested_by,
            wavelength_mode=wavelength_mode,
            operating_band=operating_band,
            application_version=application_version,
            measurement_hardware=measurement_hardware,
            limit_snapshot=limit_snapshot,
            run_purpose=purpose,
            analysis_status=analysis_status,
            analysis_exclusion_reason=analysis_exclusion_reason,
            part_number_snapshot=part_number_snapshot,
            front_panel_channel_count=front_panel_channel_count,
            notes=notes,
        )
        return self._repository.create_next(spec)

    def finish_run(
        self,
        run_id: int,
        completion_status: str,
        ended_at_utc: datetime | None = None,
    ) -> RunRecord:
        return self._repository.finish(
            run_id,
            completion_status,
            ended_at_utc or utc_now(),
        )

    def resume_run(self, run_id: int) -> RunRecord:
        """Explicitly reopen a retained run for continuation or a retest."""
        return self._repository.resume(run_id)

    def set_analysis_status(
        self,
        run_id: int,
        analysis_status: str,
        *,
        exclusion_reason: str | None = None,
        superseded_by_run_id: int | None = None,
    ) -> RunRecord:
        current = self._repository.get(run_id)
        if current is None:
            raise ValueError("Run was not found")
        if analysis_status == "included" and current.run_purpose != "production":
            raise ValueError("Only production runs may enter normal production analysis")
        return self._repository.set_analysis_status(
            run_id,
            analysis_status,
            exclusion_reason,
            superseded_by_run_id,
        )

    def find_stale_runs(self, before_utc: datetime) -> tuple[RunRecord, ...]:
        return self._repository.find_stale_in_progress(before_utc)

    def resolve_stale_run(
        self,
        run_id: int,
        decision: StaleRunDecision | str,
        decided_at_utc: datetime | None = None,
    ) -> RunRecord:
        current = self._repository.get(run_id)
        if current is None:
            raise ValueError("Run was not found")
        if current.completion_status != "in_progress":
            raise ValueError("Only an in-progress run can be resolved as stale")
        choice = StaleRunDecision(decision)
        if choice is StaleRunDecision.RESUME:
            return current
        status = "stopped" if choice is StaleRunDecision.CLOSE_STOPPED else "failed"
        return self.finish_run(run_id, status, decided_at_utc)


__all__ = ["DatabaseRunUnavailableError", "RunLifecycleWorkflow"]
