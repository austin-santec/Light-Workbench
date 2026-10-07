"""Typed structured events used by the engineering support log."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Mapping


SUPPORT_LOG_SCHEMA_VERSION = 1


class SupportLogLevel(str, Enum):
    """Severity values written to support JSONL files."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class SupportEventCategory(str, Enum):
    """Stable, searchable groups for support events."""

    APPLICATION = "application"
    WORKFLOW = "workflow"
    MEASUREMENT = "measurement"
    HARDWARE = "hardware"
    CONNECTION = "connection"
    PERSISTENCE = "persistence"
    EXPORT = "export"
    OPERATOR = "operator"
    LOGGING = "logging"


# Event extras are deliberately allowlisted. This prevents accidental dumping
# of arbitrary objects, settings, credentials, notes, or environment data.
ALLOWED_EVENT_FIELDS = frozenset(
    {
        "workflow_type",
        "run_number",
        "run_identifier",
        "operator_initials",
        "unit_serial",
        "switch_serial",
        "device_category",
        "manufacturer",
        "model",
        "device_serial",
        "firmware",
        "resource_address",
        "network_address",
        "raw_identity",
        "discovery_method",
        "connection_state",
        "lease_owner",
        "capability",
        "logical_channel",
        "physical_port",
        "requested_wavelength_nm",
        "actual_wavelength_nm",
        "wavelength_index",
        "wavelength_count",
        "source_id",
        "source_enabled",
        "measured_power_dbm",
        "raw_power_dbm",
        "reference_power_dbm",
        "reference_1310_dbm",
        "reference_1550_dbm",
        "threshold_dbm",
        "threshold_db",
        "loss_1310_db",
        "loss_1550_db",
        "rounded_loss_1310_db",
        "rounded_loss_1550_db",
        "insertion_loss_db",
        "elapsed_ms",
        "status",
        "status_code",
        "visa_status",
        "error_category",
        "disconnection_certainty",
        "error_type",
        "error_message",
        "stack_trace",
        "details",
        "operation",
        "command",
        "raw_response",
        "response_length",
        "measurement_id",
        "acquisition_method",
        "reading_state",
        "both_wavelengths_complete",
        "measurement_count",
        "recommendation_count",
        "file_type",
        "destination",
        "schema_version_written",
        "temporary_destination",
        "selected_start_date",
        "selected_end_date",
        "file_count",
        "bytes_written",
        "queue_depth",
        "dropped_event_count",
        "fallback_active",
        "retention_days",
        "max_file_bytes",
        "max_total_bytes",
        "reason",
        "choice",
        "retest",
        "repeated_reading",
        "live_write_mode",
        "configured_channel_count",
        "write_termination",
        "model_detection_method",
        "connection_warning",
        "partial_success",
        "admin_mode",
        "criteria_profile",
        "criteria_revision",
        "switch_model",
        "previous_too_good_db",
        "previous_warning_db",
        "previous_fail_db",
        "new_too_good_db",
        "new_warning_db",
        "new_fail_db",
        "criteria_snapshot",
        "warning_enabled",
        "too_good_limit_db",
        "fail_limit_db",
        "reference_snapshot_id",
        "reference_method",
        "reference_state",
        "reference_invalidation_reason",
        "reference_established_at",
        "meter_model",
        "meter_serial",
        "validation_reason",
        "invalid_wavelength",
        "invalid_sample_count",
        "part_number",
        "lookup_mode",
        "lookup_request_id",
        "coc_attempt_id",
        "outcome",
        "failure_stage",
        "reason_code",
        "supplemental_run_number",
        "front_panel_channel_count",
        "template_capacity",
        "missing_channels",
        "failure_details",
        "validation_issue_codes",
        "validation_issue_details",
        "template_path",
        "source_runs",
        "operator_choice",
    }
)


def utc_timestamp(value: datetime | None = None) -> str:
    """Return a UTC ISO-8601 timestamp with millisecond precision."""
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


@dataclass(frozen=True)
class SupportEvent:
    """One validated support event before infrastructure sanitization."""

    timestamp_utc: str
    local_date: str
    level: SupportLogLevel
    category: SupportEventCategory
    event: str
    application_name: str
    application_version: str
    app_instance_id: str
    workflow_id: str = ""
    operation_id: str = ""
    fields: Mapping[str, object] = field(default_factory=dict)
    schema_version: int = SUPPORT_LOG_SCHEMA_VERSION

    def __post_init__(self):
        if not self.event or not self.event.strip():
            raise ValueError("Support event name cannot be empty.")
        unknown = set(self.fields) - ALLOWED_EVENT_FIELDS
        if unknown:
            raise ValueError(
                "Unsupported support-event field(s): %s"
                % ", ".join(sorted(unknown))
            )
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    def to_dict(self) -> dict[str, object]:
        """Return the stable JSON-compatible event envelope."""
        result = {
            "schema_version": self.schema_version,
            "timestamp_utc": self.timestamp_utc,
            "local_date": self.local_date,
            "level": self.level.value,
            "category": self.category.value,
            "event": self.event,
            "application_name": self.application_name,
            "application_version": self.application_version,
            "app_instance_id": self.app_instance_id,
        }
        if self.workflow_id:
            result["workflow_id"] = self.workflow_id
        if self.operation_id:
            result["operation_id"] = self.operation_id
        result.update(
            (key, value)
            for key, value in self.fields.items()
            if value is not None and value != ""
        )
        return result


__all__ = [
    "ALLOWED_EVENT_FIELDS",
    "SUPPORT_LOG_SCHEMA_VERSION",
    "SupportEvent",
    "SupportEventCategory",
    "SupportLogLevel",
    "utc_timestamp",
]
