"""Vendor-neutral domain models and calculations used by Light Workbench."""

from .measurement import calculate_insertion_loss
from .raw_export import format_raw_measurements
from .coc_preparation import (
    CocPreparationResult,
    CocPreparedChannel,
    CocSourceRun,
    infer_front_panel_channel_count,
    prepare_coc,
)
from .run_data import RunData
from .measurement_attempts import (
    MeasurementAttempt,
    latest_attempt_for_channel,
    legacy_attempts_for_measurements,
    new_measurement_attempt,
    normalise_attempts,
)
from .reference import calculate_reference_offsets
from .reporting import (
    MultiRunSummary,
    OperatorRunSummary,
    RunSummary,
    aggregate_run_summaries,
    summarize_run,
)
from .comparison import comparison_values, index_measurements
from .timing import SwitchTestTimer, format_duration, format_timestamp, parse_duration
from .replacements import (
    REPLACEMENT_RECORDED,
    REPLACEMENT_VOIDED,
    ReplacementReading,
    analyze_replacements,
    completed_replacement_metadata,
    effective_replacements,
    legacy_replacement_history,
    new_replacement_event,
    new_replacement_void_event,
    normalise_completed_replacements,
    normalise_replacement_history,
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
    "format_raw_measurements",
    "CocPreparationResult",
    "CocPreparedChannel",
    "CocSourceRun",
    "infer_front_panel_channel_count",
    "prepare_coc",
    "RunData",
    "MeasurementAttempt",
    "latest_attempt_for_channel",
    "legacy_attempts_for_measurements",
    "new_measurement_attempt",
    "normalise_attempts",
    "calculate_reference_offsets",
    "RunSummary",
    "OperatorRunSummary",
    "MultiRunSummary",
    "aggregate_run_summaries",
    "summarize_run",
    "comparison_values",
    "index_measurements",
    "SwitchTestTimer",
    "format_duration",
    "format_timestamp",
    "parse_duration",
    "ReplacementReading",
    "REPLACEMENT_RECORDED",
    "REPLACEMENT_VOIDED",
    "analyze_replacements",
    "completed_replacement_metadata",
    "effective_replacements",
    "legacy_replacement_history",
    "new_replacement_event",
    "new_replacement_void_event",
    "normalise_completed_replacements",
    "normalise_replacement_history",
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
