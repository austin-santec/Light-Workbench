"""Reference-offset calculations and immutable reference audit snapshots."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4
from collections.abc import Mapping


class ReferenceMethod(str, Enum):
    """How a production reference was established."""

    CALCULATED = "calculated"
    MANUAL_ADMIN = "manual_admin"


@dataclass(frozen=True)
class ReferenceSnapshot:
    """Immutable references authorized for one acquisition session."""

    snapshot_id: str
    reference_1310_dbm: float
    reference_1550_dbm: float
    method: str
    established_at: str
    meter_model: str = ""
    meter_serial: str = ""
    meter_resource_address: str = ""
    laser_model: str = ""
    laser_serial: str = ""
    operator_initials: str = ""

    def __post_init__(self):
        if self.method not in {item.value for item in ReferenceMethod}:
            raise ValueError("Unsupported reference method: %s" % self.method)
        if not self.snapshot_id.strip():
            raise ValueError("A reference snapshot ID is required.")
        float(self.reference_1310_dbm)
        float(self.reference_1550_dbm)

    @property
    def is_valid(self) -> bool:
        return bool(
            self.snapshot_id
            and self.established_at
            and self.method in {item.value for item in ReferenceMethod}
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "reference_1310_dbm": float(self.reference_1310_dbm),
            "reference_1550_dbm": float(self.reference_1550_dbm),
            "method": self.method,
            "established_at": self.established_at,
            "meter_model": self.meter_model,
            "meter_serial": self.meter_serial,
            "meter_resource_address": self.meter_resource_address,
            "laser_model": self.laser_model,
            "laser_serial": self.laser_serial,
            "operator_initials": self.operator_initials,
        }

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "ReferenceSnapshot":
        if not isinstance(values, Mapping):
            raise ValueError("Reference snapshot must be an object.")
        return cls(
            snapshot_id=str(values.get("snapshot_id") or ""),
            reference_1310_dbm=float(values["reference_1310_dbm"]),
            reference_1550_dbm=float(values["reference_1550_dbm"]),
            method=str(values.get("method") or ""),
            established_at=str(values.get("established_at") or ""),
            meter_model=str(values.get("meter_model") or ""),
            meter_serial=str(values.get("meter_serial") or ""),
            meter_resource_address=str(values.get("meter_resource_address") or ""),
            laser_model=str(values.get("laser_model") or ""),
            laser_serial=str(values.get("laser_serial") or ""),
            operator_initials=str(values.get("operator_initials") or ""),
        )


def new_reference_snapshot(
    reference_1310_dbm: float,
    reference_1550_dbm: float,
    *,
    method: ReferenceMethod,
    meter_model: str = "",
    meter_serial: str = "",
    meter_resource_address: str = "",
    laser_model: str = "",
    laser_serial: str = "",
    operator_initials: str = "",
) -> ReferenceSnapshot:
    """Create a uniquely identified reference snapshot for an active session."""
    return ReferenceSnapshot(
        snapshot_id=uuid4().hex,
        reference_1310_dbm=float(reference_1310_dbm),
        reference_1550_dbm=float(reference_1550_dbm),
        method=method.value,
        established_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        meter_model=str(meter_model or ""),
        meter_serial=str(meter_serial or ""),
        meter_resource_address=str(meter_resource_address or ""),
        laser_model=str(laser_model or ""),
        laser_serial=str(laser_serial or ""),
        operator_initials=str(operator_initials or ""),
    )


def calculate_reference_offsets(
    absolute_readings: Mapping[int, float],
) -> tuple[float, float]:
    """Return two-decimal reference offsets from absolute power readings.

    With the software reference at zero, the absolute reading is the power
    baseline. The stored reference is therefore that measured power. For
    example, a zero-reference reading of ``-0.72`` represents a ``0.72 dBm``
    reference offset used by the insertion-loss calculation.
    """
    try:
        reading_1310 = float(absolute_readings[1310])
        reading_1550 = float(absolute_readings[1550])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "Both 1310 nm and 1550 nm absolute readings are required."
        ) from error

    return round(reading_1310, 2), round(reading_1550, 2)
