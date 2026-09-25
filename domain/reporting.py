"""Typed, read-only summaries for persisted switch-test runs."""

from dataclasses import dataclass
from collections.abc import Iterable, Mapping

from .models import MeasurementRecord
from .timing import parse_duration


@dataclass(frozen=True)
class RunSummary:
    """Summary fields suitable for future multi-run reporting."""

    run_number: int | None
    switch_serial: str
    tested_by: str
    accepted_channel_count: int
    over_limit_channel_count: int
    warning_limit_db: float
    total_duration_seconds: float
    start_time: str
    stop_time: str


@dataclass(frozen=True)
class OperatorRunSummary:
    """Timing and limit results grouped by tester initials."""

    tested_by: str
    run_count: int
    timed_run_count: int
    average_duration_seconds: float | None
    fastest_duration_seconds: float | None
    slowest_duration_seconds: float | None
    average_over_limit_channel_count: float


@dataclass(frozen=True)
class MultiRunSummary:
    """In-memory aggregate for a selected collection of saved runs."""

    run_count: int
    timed_run_count: int
    average_duration_seconds: float | None
    average_over_limit_channel_count: float
    operator_summaries: tuple[OperatorRunSummary, ...]


def summarize_run(
    measurements: Iterable[MeasurementRecord],
    metadata: Mapping[str, object],
    warning_limit: float,
) -> RunSummary:
    """Create a summary using only accepted/written measurements."""
    try:
        run_number = int(metadata.get("Run number"))
    except (TypeError, ValueError):
        run_number = None

    accepted_measurements = list(measurements)
    over_limit_count = sum(
        record.loss_1310 > warning_limit or record.loss_1550 > warning_limit
        for record in accepted_measurements
    )
    try:
        configured_limit = float(warning_limit)
    except (TypeError, ValueError):
        configured_limit = 0.0

    return RunSummary(
        run_number=run_number,
        switch_serial=str(metadata.get("Switch serial") or "").strip(),
        tested_by=str(metadata.get("Tested by") or "").strip(),
        accepted_channel_count=len(accepted_measurements),
        over_limit_channel_count=over_limit_count,
        warning_limit_db=configured_limit,
        total_duration_seconds=parse_duration(
            metadata.get("Switch test total duration")
        ),
        start_time=str(metadata.get("Switch test start time") or "").strip(),
        stop_time=str(metadata.get("Switch test stop time") or "").strip(),
    )


def aggregate_run_summaries(
    summaries: Iterable[RunSummary],
) -> MultiRunSummary:
    """Aggregate saved-run summaries without reading or modifying files.

    A zero duration means timing metadata was unavailable, so it is excluded
    from timing averages. Limit counts are still included because they are
    valid for runs that have no timing metadata.
    """
    selected_summaries = list(summaries)
    timed_durations = [
        summary.total_duration_seconds
        for summary in selected_summaries
        if summary.total_duration_seconds > 0
    ]
    grouped: dict[str, list[RunSummary]] = {}
    for summary in selected_summaries:
        operator = summary.tested_by or "Unknown"
        grouped.setdefault(operator, []).append(summary)

    operator_summaries = []
    for operator in sorted(grouped, key=str.casefold):
        operator_runs = grouped[operator]
        operator_durations = [
            summary.total_duration_seconds
            for summary in operator_runs
            if summary.total_duration_seconds > 0
        ]
        operator_summaries.append(
            OperatorRunSummary(
                tested_by=operator,
                run_count=len(operator_runs),
                timed_run_count=len(operator_durations),
                average_duration_seconds=(
                    sum(operator_durations) / len(operator_durations)
                    if operator_durations
                    else None
                ),
                fastest_duration_seconds=(
                    min(operator_durations) if operator_durations else None
                ),
                slowest_duration_seconds=(
                    max(operator_durations) if operator_durations else None
                ),
                average_over_limit_channel_count=(
                    sum(
                        summary.over_limit_channel_count
                        for summary in operator_runs
                    )
                    / len(operator_runs)
                ),
            )
        )

    return MultiRunSummary(
        run_count=len(selected_summaries),
        timed_run_count=len(timed_durations),
        average_duration_seconds=(
            sum(timed_durations) / len(timed_durations)
            if timed_durations
            else None
        ),
        average_over_limit_channel_count=(
            sum(summary.over_limit_channel_count for summary in selected_summaries)
            / len(selected_summaries)
            if selected_summaries
            else 0.0
        ),
        operator_summaries=tuple(operator_summaries),
    )


__all__ = [
    "MultiRunSummary",
    "OperatorRunSummary",
    "RunSummary",
    "aggregate_run_summaries",
    "summarize_run",
]
