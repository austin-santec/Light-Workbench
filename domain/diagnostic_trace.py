"""Typed in-memory events collected while diagnosing optical hardware."""

from dataclasses import asdict, dataclass
from typing import Mapping


@dataclass(frozen=True)
class DiagnosticTraceEvent:
    """One chronological hardware event from a diagnostic acquisition."""

    timestamp: str
    session_id: str
    event: str
    meter_description: str | None = None
    meter_serial: str | None = None
    measurement_id: int | None = None
    method: str | None = None
    channel: int | None = None
    physical_port: int | None = None
    requested_wavelength_nm: int | None = None
    requested_opm_wavelength_nm: int | None = None
    nominal_source_wavelength_nm: int | None = None
    actual_wavelength_nm: int | None = None
    wavelength_index: int | None = None
    wavelength_count: int | None = None
    source_id: int | None = None
    source_enabled: bool | None = None
    operation: str | None = None
    status: str | None = None
    status_code: int | None = None
    raw_power_dbm: float | None = None
    reference_power_dbm: float | None = None
    insertion_loss_db: float | None = None
    elapsed_ms: float | None = None
    error: str | None = None
    details: str | None = None

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, object],
        default_session_id: str,
    ) -> "DiagnosticTraceEvent":
        """Normalize an optional hardware callback payload into a typed event."""
        allowed = {
            field.name
            for field in cls.__dataclass_fields__.values()
        }
        payload = {key: value for key, value in values.items() if key in allowed}
        payload.setdefault("session_id", default_session_id)
        payload.setdefault("event", "unknown")
        payload.setdefault("timestamp", "")
        return cls(**payload)

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation of the event."""
        return asdict(self)


__all__ = ["DiagnosticTraceEvent"]
