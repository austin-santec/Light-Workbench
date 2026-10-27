"""Derived completion and result status for persisted hardware runs.

The status model deliberately separates whether a run collected its planned
readings from whether those readings are suitable for a standalone or
combined COC result.  It contains no Qt, filesystem, or hardware behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from collections.abc import Mapping, Sequence


COMPLETION_NOT_STARTED = "not_started"
COMPLETION_IN_PROGRESS = "in_progress"
COMPLETION_COMPLETE = "complete"
COMPLETION_INCOMPLETE = "incomplete"
COMPLETION_INTERRUPTED = "interrupted"
COMPLETION_UNKNOWN = "unknown"

RESULT_NOT_EVALUATED = "not_evaluated"
RESULT_PASS = "pass"
RESULT_PASS_OPTIMIZATION = "pass_optimization_available"
RESULT_PASS_REVIEW = "pass_review_recommended"
RESULT_FAIL_RECOVERABLE = "fail_recoverable"
RESULT_FAIL_UNRECOVERABLE = "fail_unrecoverable"
RESULT_COMPOSITE = "composite_pass_available"
RESULT_SUPPLEMENTAL = "supplemental_run"
RESULT_REVIEW = "review_required"


COMPLETION_LABELS = {
    COMPLETION_NOT_STARTED: "Not started",
    COMPLETION_IN_PROGRESS: "In progress",
    COMPLETION_COMPLETE: "Complete",
    COMPLETION_INCOMPLETE: "Incomplete",
    COMPLETION_INTERRUPTED: "Interrupted",
    COMPLETION_UNKNOWN: "Unknown",
}

RESULT_LABELS = {
    RESULT_NOT_EVALUATED: "Not evaluated",
    RESULT_PASS: "Pass",
    RESULT_PASS_OPTIMIZATION: "Pass · optimization available",
    RESULT_PASS_REVIEW: "Pass · review recommended",
    RESULT_FAIL_RECOVERABLE: "Fail · recovery available",
    RESULT_FAIL_UNRECOVERABLE: "Fail · no measured recovery",
    RESULT_COMPOSITE: "Composite pass available",
    RESULT_SUPPLEMENTAL: "Supplemental run",
    RESULT_REVIEW: "Review required",
}


@dataclass(frozen=True)
class RunStatusAssessment:
    """Structured status information used by the UI and future repositories."""

    completion_status: str = COMPLETION_UNKNOWN
    result_status: str = RESULT_NOT_EVALUATED
    planned_channel_count: int | None = None
    completed_channel_count: int = 0
    completion_reason: str = ""
    completed_at_utc: str = ""
    active: bool = False
    missing_channels: tuple[int, ...] = ()
    failing_channels: tuple[int, ...] = ()
    optimization_channels: tuple[int, ...] = ()
    compatible_run_numbers: tuple[int, ...] = ()
    detail: str = ""
    _metadata: Mapping[str, object] = field(default_factory=dict, repr=False)

    @property
    def completion_label(self) -> str:
        return COMPLETION_LABELS.get(self.completion_status, "Unknown")

    @property
    def result_label(self) -> str:
        return RESULT_LABELS.get(self.result_status, "Not evaluated")

    @property
    def completion_display(self) -> str:
        if self.planned_channel_count is not None:
            return "%s · %d/%d" % (
                self.completion_label,
                self.completed_channel_count,
                self.planned_channel_count,
            )
        return self.completion_label

    def as_dict(self) -> dict[str, object]:
        """Return the additive, database-ready completion payload."""
        return {
            "completion_status": self.completion_status,
            "completion_reason": self.completion_reason,
            "planned_channel_count": self.planned_channel_count,
            "completed_channel_count": self.completed_channel_count,
            "completed_at_utc": self.completed_at_utc,
        }

    def tooltip(self) -> str:
        lines = [
            "Completion: %s" % self.completion_display,
            "Result: %s" % self.result_label,
        ]
        if self.result_status == RESULT_COMPOSITE:
            lines.append("COC creation is available.")
        if self.completion_reason:
            lines.append("Reason: %s" % self.completion_reason)
        if self.missing_channels:
            lines.append(
                "Missing planned channels: %s"
                % _format_channels(self.missing_channels)
            )
        if self.failing_channels:
            lines.append(
                "Failing channels: %s" % _format_channels(self.failing_channels)
            )
        if self.optimization_channels:
            lines.append(
                "Optimization channels: %s"
                % _format_channels(self.optimization_channels)
            )
        if self.compatible_run_numbers:
            lines.append(
                "Compatible run(s): %s"
                % ", ".join(str(value) for value in self.compatible_run_numbers)
            )
        if self.detail:
            lines.append(self.detail)
        return "\n".join(lines)


def utc_now() -> str:
    """Return an ISO UTC timestamp suitable for persisted status metadata."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _format_channels(channels: Sequence[int]) -> str:
    values = [str(int(channel)) for channel in channels[:48]]
    if len(channels) > 48:
        values.append("…")
    return ", ".join(values)


def _format_run_numbers(run_numbers: Sequence[int]) -> str:
    return ", ".join(str(int(value)) for value in run_numbers)


def planned_channels_from_metadata(metadata: Mapping[str, object]) -> tuple[int, ...] | None:
    """Load a persisted plan without guessing from a filtered table."""
    raw_channels = metadata.get("Planned channels")
    if raw_channels not in (None, ""):
        try:
            values = tuple(dict.fromkeys(int(value.strip()) for value in str(raw_channels).split(",") if value.strip()))
        except (TypeError, ValueError):
            values = ()
        if values and all(value > 0 for value in values):
            return values
    raw_count = metadata.get("Planned channel count")
    try:
        count = int(raw_count)
    except (TypeError, ValueError):
        return None
    return tuple(range(1, count + 1)) if count > 0 else None


def _finite_nonnegative_records(records) -> bool:
    for record in records:
        for value in record.ordered_losses:
            if not math.isfinite(float(value)) or float(value) < 0:
                return False
    return True


def assess_run_status(
    records,
    *,
    planned_channels: Sequence[int] | None = None,
    active: bool = False,
    terminal_status: str | None = None,
    profile=None,
    front_panel_channel_count: int | None = None,
    replacement_analysis: Mapping[str, object] | None = None,
    composite_result=None,
    effective_result=None,
    effective_run_numbers: Sequence[int] = (),
    compatible_run_numbers: Sequence[int] = (),
    completion_reason: str = "",
    completed_at_utc: str = "",
    extra_only: bool = False,
    legacy=False,
) -> RunStatusAssessment:
    """Assess a run using accepted records and explicit workflow state.

    ``planned_channels`` is intentionally optional: old files without a saved
    plan receive ``unknown`` completion rather than an unsafe inferred state.
    ``composite_result`` is the legacy pairwise compatibility input. New
    callers should provide ``effective_result`` from the shared multi-run
    projection so a newer failure cannot be hidden by an older passing run.
    """
    records = tuple(records or ())
    completed_channels = {int(record.channel) for record in records}
    planned = tuple(dict.fromkeys(int(channel) for channel in (planned_channels or ())))
    planned_count = len(planned) if planned else None
    missing = tuple(channel for channel in planned if channel not in completed_channels)

    if active:
        completion = COMPLETION_IN_PROGRESS
    elif terminal_status in {COMPLETION_INCOMPLETE, COMPLETION_INTERRUPTED}:
        completion = terminal_status
    elif extra_only and terminal_status == COMPLETION_COMPLETE:
        completion = COMPLETION_COMPLETE
    elif planned and not missing:
        completion = COMPLETION_COMPLETE
    elif planned:
        completion = COMPLETION_INCOMPLETE
    elif not records:
        completion = COMPLETION_NOT_STARTED if not legacy else COMPLETION_UNKNOWN
    else:
        completion = COMPLETION_UNKNOWN

    if not completion_reason:
        if completion == COMPLETION_IN_PROGRESS:
            completion_reason = "The run is still active."
        elif completion == COMPLETION_INCOMPLETE:
            completion_reason = "The run ended before all planned channels were accepted."
        elif completion == COMPLETION_INTERRUPTED:
            completion_reason = "The run ended because of a hardware or software error."
        elif completion == COMPLETION_COMPLETE and extra_only:
            completion_reason = "The extra-channel run reached its configured endpoint."
        elif completion == COMPLETION_COMPLETE:
            completion_reason = "Every planned channel has an accepted reading."

    failing = []
    optimization = []
    review_required = not _finite_nonnegative_records(records)
    if profile is not None and not review_required:
        for record in records:
            assessment = profile.classify(
                *record.ordered_losses,
                record.opm_wavelengths_nm,
            )
            if assessment.is_fail:
                failing.append(int(record.channel))
            if assessment.is_optimization:
                optimization.append(int(record.channel))

    standalone_complete = bool(
        front_panel_channel_count
        and all(channel in completed_channels for channel in range(1, int(front_panel_channel_count) + 1))
    )
    projection = effective_result
    projection_runs = tuple(dict.fromkeys(int(value) for value in effective_run_numbers))
    if projection is not None:
        projection_invalid = bool(
            getattr(projection, "invalid_readings", ())
            or getattr(projection, "validation_issues", ())
        )
        projection_missing = tuple(getattr(projection, "missing_channels", ()))
        projection_failures = tuple(getattr(projection, "failures", ()))
        projection_optimizations = tuple(
            getattr(projection, "optimization_channels", ())
        )
        if projection_invalid or review_required:
            result = RESULT_REVIEW
            detail = "The current effective measurement projection requires review."
        elif projection_missing:
            result = RESULT_NOT_EVALUATED
            detail = "The current effective run history is missing required channels."
        elif projection_failures:
            recommendations = tuple(
                getattr(projection, "optimization_recommendations", ())
            )
            result = (
                RESULT_FAIL_RECOVERABLE
                if recommendations
                else RESULT_FAIL_UNRECOVERABLE
            )
            detail = (
                "The newest effective measurement for one or more channels fails; "
                "measured extra ports provide a possible recovery path."
                if recommendations
                else "The newest effective measurement for one or more channels fails."
            )
        elif projection_optimizations:
            recommendations = tuple(
                getattr(projection, "optimization_recommendations", ())
            )
            result = (
                RESULT_PASS_OPTIMIZATION
                if recommendations
                else RESULT_PASS_REVIEW
            )
            detail = "The effective measurement history passes but has optimization-level readings."
        elif len(projection_runs) > 1:
            result = RESULT_COMPOSITE
            if standalone_complete:
                detail = (
                    "The current result uses the newest measurements from "
                    "combined compatible run history."
                )
            else:
                detail = (
                    "This partial run contributes to a composite pass using "
                    "Runs %s." % _format_run_numbers(projection_runs)
                )
        else:
            result = RESULT_PASS
            detail = "All required front-panel readings are within the applicable fail limit."
    elif review_required:
        result = RESULT_REVIEW
        detail = "One or more accepted readings is invalid or non-finite."
    elif not standalone_complete:
        if composite_result is not None and getattr(composite_result, "eligible", False):
            result = RESULT_COMPOSITE
            run_numbers = tuple(
                dict.fromkeys(int(value) for value in (compatible_run_numbers or ()))
            )
            if run_numbers:
                detail = (
                    "This partial run contributes to a validated composite pass "
                    "with Run%s %s."
                    % (
                        "s" if len(run_numbers) != 1 else "",
                        _format_run_numbers(run_numbers),
                    )
                )
            else:
                detail = "This partial run contributes to a validated composite pass."
        else:
            result = RESULT_NOT_EVALUATED
            detail = "The run does not contain the complete front-panel channel set."
    elif failing:
        if composite_result is not None and getattr(composite_result, "eligible", False):
            result = RESULT_COMPOSITE
            detail = "A validated combination with another persisted run is available."
        else:
            recommendations = (replacement_analysis or {}).get("recommendations", ())
            result = RESULT_FAIL_RECOVERABLE if recommendations else RESULT_FAIL_UNRECOVERABLE
            detail = (
                "Replacement analysis identified a possible recovery path."
                if recommendations
                else "No measured replacement recovery is currently available."
            )
    elif optimization:
        recommendations = (replacement_analysis or {}).get("recommendations", ())
        if recommendations:
            result = RESULT_PASS_OPTIMIZATION
            detail = "The run passes the fail limit and replacement recommendations are available."
        else:
            result = RESULT_PASS_REVIEW
            detail = "The run passes the fail limit but has optimization-level readings to review."
    else:
        result = RESULT_PASS
        detail = "All required front-panel readings are within the applicable fail limit."

    if extra_only:
        if review_required:
            result = RESULT_REVIEW
            detail = "One or more accepted extra-channel readings requires review."
        elif not records:
            result = RESULT_NOT_EVALUATED
            detail = "No extra-channel readings have been accepted."
        else:
            result = RESULT_SUPPLEMENTAL
            detail = (
                "This independent extra-channel run provides supplemental "
                "measurements for replacement analysis; it is not a standalone COC."
            )
    elif (
        completion
        in {COMPLETION_IN_PROGRESS, COMPLETION_INCOMPLETE, COMPLETION_INTERRUPTED}
        and result == RESULT_PASS
    ):
        result = RESULT_NOT_EVALUATED
        detail = "The run has not completed its planned channel set."

    return RunStatusAssessment(
        completion_status=completion,
        result_status=result,
        planned_channel_count=planned_count,
        completed_channel_count=len(completed_channels.intersection(planned)) if planned else len(completed_channels),
        completion_reason=completion_reason,
        completed_at_utc=completed_at_utc,
        active=bool(active),
        missing_channels=missing,
        failing_channels=tuple(sorted(set(failing))),
        optimization_channels=tuple(sorted(set(optimization))),
        compatible_run_numbers=tuple(dict.fromkeys(int(value) for value in compatible_run_numbers)),
        detail=detail,
    )


__all__ = [
    "COMPLETION_NOT_STARTED",
    "COMPLETION_IN_PROGRESS",
    "COMPLETION_COMPLETE",
    "COMPLETION_INCOMPLETE",
    "COMPLETION_INTERRUPTED",
    "COMPLETION_UNKNOWN",
    "RESULT_NOT_EVALUATED",
    "RESULT_PASS",
    "RESULT_PASS_OPTIMIZATION",
    "RESULT_PASS_REVIEW",
    "RESULT_FAIL_RECOVERABLE",
    "RESULT_FAIL_UNRECOVERABLE",
    "RESULT_COMPOSITE",
    "RESULT_SUPPLEMENTAL",
    "RESULT_REVIEW",
    "COMPLETION_LABELS",
    "RESULT_LABELS",
    "RunStatusAssessment",
    "assess_run_status",
    "planned_channels_from_metadata",
    "utc_now",
]
