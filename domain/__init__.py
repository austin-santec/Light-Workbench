"""Vendor-neutral domain models and calculations used by Light Workbench."""

from .measurement import calculate_insertion_loss
from .reference import calculate_reference_offsets
from .reporting import RunSummary, summarize_run
from .comparison import comparison_values, index_measurements
from .timing import SwitchTestTimer, format_duration, format_timestamp, parse_duration
from .replacements import (
    ReplacementReading,
    analyze_replacements,
    completed_replacement_metadata,
    normalise_completed_replacements,
    parse_extra_readings,
    recommendation_category,
    replacement_metadata,
)
from .models import (
    ChannelMode,
    MeasurementRecord,
    MeasurementStatus,
    OperatingBand,
    ReferenceValues,
    RunIdentity,
    RunState,
    UnitIdentity,
)

__all__ = [
    "ChannelMode",
    "calculate_insertion_loss",
    "calculate_reference_offsets",
    "RunSummary",
    "summarize_run",
    "comparison_values",
    "index_measurements",
    "SwitchTestTimer",
    "format_duration",
    "format_timestamp",
    "parse_duration",
    "ReplacementReading",
    "analyze_replacements",
    "completed_replacement_metadata",
    "normalise_completed_replacements",
    "parse_extra_readings",
    "recommendation_category",
    "replacement_metadata",
    "MeasurementRecord",
    "MeasurementStatus",
    "OperatingBand",
    "ReferenceValues",
    "RunIdentity",
    "RunState",
    "UnitIdentity",
]
