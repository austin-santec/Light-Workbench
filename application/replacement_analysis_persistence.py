"""Persistence and hydration for append-only replacement analyses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Mapping
from uuid import UUID, uuid4

from domain.database_records import (
    ReplacementAnalysisRecommendationSpec,
    ReplacementAnalysisRecord,
    ReplacementAnalysisRecommendationRecord,
    ReplacementAnalysisSpec,
    utc_now,
)


RESULT_RECOMMENDATIONS_AVAILABLE = "recommendations_available"
RESULT_NO_VIABLE_RECOMMENDATIONS = "no_viable_recommendations"
RESULT_NOT_APPLICABLE = "not_applicable_no_extra_ports"
RESULT_INCOMPLETE_INPUT = "incomplete_input"
RESULT_OPTIMIZED = "optimized"
RESULT_VERIFICATION_REQUIRED = "verification_required"
RESULT_PASS_NO_VIABLE_OPTIMIZATION = "pass_no_viable_optimization"
RESULT_FAIL_NO_VIABLE_RECOVERY = "fail_no_viable_recovery"
RESULT_REVIEW_REQUIRED = "review_required"


def _json_safe(value):
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    return value


def classify_result(result: Mapping) -> str:
    """Classify a completed calculation without introducing mutable state."""
    explicit = str(
        result.get("result_status") or result.get("analysis_result_status") or ""
    )
    if explicit in {
        RESULT_OPTIMIZED,
        RESULT_RECOMMENDATIONS_AVAILABLE,
        RESULT_VERIFICATION_REQUIRED,
        RESULT_PASS_NO_VIABLE_OPTIMIZATION,
        RESULT_FAIL_NO_VIABLE_RECOVERY,
        RESULT_INCOMPLETE_INPUT,
        RESULT_REVIEW_REQUIRED,
        RESULT_NO_VIABLE_RECOMMENDATIONS,
        RESULT_NOT_APPLICABLE,
    }:
        return explicit
    if result.get("missing_channels"):
        return RESULT_INCOMPLETE_INPUT
    if not result.get("extra_ports"):
        return RESULT_NOT_APPLICABLE
    if result.get("recommendations"):
        return RESULT_RECOMMENDATIONS_AVAILABLE
    return RESULT_NO_VIABLE_RECOMMENDATIONS


@dataclass(frozen=True)
class PersistedReplacementAnalysis:
    record: ReplacementAnalysisRecord
    recommendations: tuple[ReplacementAnalysisRecommendationRecord, ...]

    def is_current(self, current_source_state) -> bool:
        saved_snapshot = self.record.result_details.get("source_snapshot", {})
        saved_fingerprint = saved_snapshot.get("state_fingerprint_sha256")
        if isinstance(current_source_state, str) and saved_fingerprint:
            return saved_fingerprint == current_source_state
        current_measurement_high_watermark = current_source_state
        return (
            current_measurement_high_watermark is not None
            and self.record.source_measurement_high_watermark_id
            == int(current_measurement_high_watermark)
        )

    def to_result_dict(self) -> dict:
        result = dict(self.record.result_details)
        result["analysis_id"] = self.record.analysis_id
        result["analysis_uuid"] = str(self.record.analysis_uuid)
        result["analyzed_at_utc"] = self.record.analyzed_at_utc.isoformat()
        result["analyzed_by"] = self.record.analyzed_by
        result["application_version"] = self.record.application_version
        result["source_measurement_high_watermark_id"] = (
            self.record.source_measurement_high_watermark_id
        )
        result["front_panel_channel_count"] = self.record.front_panel_channel_count
        result["wavelengths_nm"] = tuple(
            int(value) for value in self.record.wavelengths.get("wavelengths_nm", ())
        )
        result["criteria_snapshot"] = dict(self.record.criteria)
        result["analysis_result_status"] = self.record.result_status
        result["recommendations"] = [
            {
                "recommendation_id": item.recommendation_id,
                "logical_channel": item.logical_channel,
                "category": item.category,
                "current_physical_port": item.current_physical_port,
                "candidate_physical_port": item.candidate_physical_port,
                "current_loss_1310_db": float(item.current_wavelength_1_il_db),
                "current_loss_1550_db": float(item.current_wavelength_2_il_db),
                "candidate_loss_1310_db": float(item.candidate_wavelength_1_il_db),
                "candidate_loss_1550_db": float(item.candidate_wavelength_2_il_db),
                "current_worst_loss_db": float(item.current_worst_loss_db),
                "candidate_worst_loss_db": float(item.candidate_worst_loss_db),
                "improvement_db": float(item.improvement_db),
            }
            for item in self.recommendations
        ]
        return result


class ReplacementAnalysisPersistenceWorkflow:
    """Save and reload analysis snapshots without changing measurements."""

    def __init__(self, repository) -> None:
        self._repository = repository

    def save_result(
        self,
        *,
        run_id: int,
        result: Mapping,
        analyzed_by: str,
        application_version: str,
        front_panel_channel_count: int,
        wavelengths: tuple[int, int],
        criteria: Mapping,
        measurement_count: int,
        analysis_uuid: UUID | None = None,
        analyzed_at_utc: datetime | None = None,
    ) -> PersistedReplacementAnalysis:
        """Persist one complete result and return its authoritative snapshot."""
        snapshot = result.get("source_snapshot", {})
        high_watermark = snapshot.get("measurement_high_watermark_id")
        if high_watermark is None:
            high_watermark = self._repository.current_measurement_high_watermark(run_id)
        if high_watermark is None:
            raise ValueError("Replacement analysis requires an accepted measurement")
        result_status = classify_result(result)
        details = _json_safe(dict(result))
        details.pop("recommendations", None)
        details.setdefault("effective_measurement_count", int(measurement_count))
        details["effective_measurement_count"] = int(measurement_count)
        spec = ReplacementAnalysisSpec(
            analysis_uuid=analysis_uuid or uuid4(),
            run_id=int(run_id),
            analyzed_at_utc=analyzed_at_utc or utc_now(),
            analyzed_by=analyzed_by,
            application_version=application_version,
            source_measurement_high_watermark_id=int(high_watermark),
            front_panel_channel_count=int(front_panel_channel_count),
            wavelengths={"wavelengths_nm": [int(value) for value in wavelengths]},
            criteria=_json_safe(criteria),
            result_status=result_status,
            result_details=details,
        )
        recommendation_specs = tuple(
            self._recommendation_spec(spec, rank, item)
            for rank, item in enumerate(result.get("recommendations", ()), start=1)
        )
        record, recommendations = self._repository.append_analysis(
            spec, recommendation_specs
        )
        return PersistedReplacementAnalysis(record, recommendations)

    def latest_for_run(self, run_id: int) -> PersistedReplacementAnalysis | None:
        loaded = self._repository.latest_analysis_for_run(int(run_id))
        return None if loaded is None else PersistedReplacementAnalysis(*loaded)

    def history_for_run(self, run_id: int) -> tuple[PersistedReplacementAnalysis, ...]:
        return tuple(
            PersistedReplacementAnalysis(*item)
            for item in self._repository.analysis_history_for_run(int(run_id))
        )

    def current_high_watermark(self, run_id: int) -> int | None:
        return self._repository.current_measurement_high_watermark(int(run_id))

    @staticmethod
    def _recommendation_spec(analysis, rank: int, item: Mapping):
        def decimal(name):
            return Decimal(str(item[name]))

        return ReplacementAnalysisRecommendationSpec(
            analysis_id=None,
            recommendation_rank=rank,
            category=str(item.get("category") or "optional").strip().lower(),
            logical_channel=int(item["logical_channel"]),
            current_physical_port=int(item["current_physical_port"]),
            candidate_physical_port=int(item["candidate_physical_port"]),
            current_wavelength_1_il_db=decimal("current_loss_1310_db"),
            current_wavelength_2_il_db=decimal("current_loss_1550_db"),
            candidate_wavelength_1_il_db=decimal("candidate_loss_1310_db"),
            candidate_wavelength_2_il_db=decimal("candidate_loss_1550_db"),
            current_worst_loss_db=decimal("current_worst_loss_db"),
            candidate_worst_loss_db=decimal("candidate_worst_loss_db"),
            improvement_db=decimal("improvement_db"),
        )


__all__ = [
    "PersistedReplacementAnalysis",
    "ReplacementAnalysisPersistenceWorkflow",
    "RESULT_INCOMPLETE_INPUT",
    "RESULT_FAIL_NO_VIABLE_RECOVERY",
    "RESULT_OPTIMIZED",
    "RESULT_NO_VIABLE_RECOMMENDATIONS",
    "RESULT_NOT_APPLICABLE",
    "RESULT_RECOMMENDATIONS_AVAILABLE",
    "RESULT_PASS_NO_VIABLE_OPTIMIZATION",
    "RESULT_REVIEW_REQUIRED",
    "RESULT_VERIFICATION_REQUIRED",
    "classify_result",
]
