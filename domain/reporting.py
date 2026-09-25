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


__all__ = ["RunSummary", "summarize_run"]
