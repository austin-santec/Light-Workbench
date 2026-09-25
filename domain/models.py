"""Typed, vendor-neutral models for optical test data.

The persistence layer still uses the existing CSV/JSON field names. These
models provide a safer representation for new application code while the
serialization migration happens incrementally.
"""

from dataclasses import dataclass
from enum import Enum
from collections.abc import Mapping


class OperatingBand(str, Enum):
    """Supported optical operating bands."""

    O_BAND = "O band"
    C_BAND = "C band"


class ChannelMode(str, Enum):
    """Ways a hardware run can choose its logical channels."""

    FULL_CONFIGURED_PASS = "Full configured pass"
    SINGLE_CHANNEL = "Single channel"
    SPECIFIC_CHANNELS = "Specific channels/ranges"


class RunState(str, Enum):
    """Lifecycle states used by the future application run controller."""

    IDLE = "idle"
    STARTING = "starting"
    WAITING_FOR_CABLE = "waiting_for_cable"
    READING = "reading"
    READY_TO_WRITE = "ready_to_write"
    WRITING = "writing"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    CLOSING = "closing"


class MeasurementStatus(str, Enum):
    """Operator-visible lifecycle of a single channel measurement."""

    PENDING = "pending"
    READING = "reading"
    READY_TO_WRITE = "ready_to_write"
    WRITTEN = "written"
    FAILED = "failed"


@dataclass(frozen=True)
class MeasurementRecord:
    """One accepted insertion-loss result for a logical channel."""

    channel: int
    loss_1310: float
    loss_1550: float
    physical_port: int | None = None


@dataclass(frozen=True)
class ReferenceValues:
    """Reference powers used to convert absolute readings into IL values."""

    reference_1310_dbm: float
    reference_1550_dbm: float

    def as_mapping(self) -> dict[int, float]:
        """Return the wavelength-keyed shape used by current workers."""
        return {
            1310: self.reference_1310_dbm,
            1550: self.reference_1550_dbm,
        }

    @classmethod
    def from_mapping(cls, values: Mapping[int, float]) -> "ReferenceValues":
        """Build references from the worker-compatible mapping shape."""
        missing = {1310, 1550} - set(values)
        if missing:
            wavelengths = ", ".join(str(value) for value in sorted(missing))
            raise ValueError("Reference is missing wavelength(s): %s" % wavelengths)
        return cls(float(values[1310]), float(values[1550]))


@dataclass(frozen=True)
class UnitIdentity:
    """Identity fields shared by every run belonging to one physical unit."""

    main_board_serial: str = ""
    part_number: str = ""

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, object]) -> "UnitIdentity":
        return cls(
            main_board_serial=str(metadata.get("Main board serial") or "").strip(),
            part_number=str(metadata.get("Part number") or "").strip(),
        )

    def as_metadata(self) -> dict[str, str]:
        return {
            "Main board serial": self.main_board_serial,
            "Part number": self.part_number,
        }


@dataclass(frozen=True)
class RunIdentity:
    """Identity and operator fields that belong to one switch test run."""

    run_number: int = 1
    switch_serial: str = ""
    operating_band: OperatingBand = OperatingBand.O_BAND
    tested_by: str = ""

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, object]) -> "RunIdentity":
        try:
            run_number = max(1, int(metadata.get("Run number", 1)))
        except (TypeError, ValueError):
            run_number = 1

        operating_band_value = str(metadata.get("Operating band") or "").strip()
        try:
            operating_band = OperatingBand(operating_band_value)
        except ValueError:
            operating_band = OperatingBand.O_BAND

        return cls(
            run_number=run_number,
            switch_serial=str(metadata.get("Switch serial") or "").strip(),
            operating_band=operating_band,
            tested_by=str(metadata.get("Tested by") or "").strip(),
        )

    def as_metadata(self) -> dict[str, str]:
        return {
            "Run number": str(self.run_number),
            "Switch serial": self.switch_serial,
            "Operating band": self.operating_band.value,
            "Tested by": self.tested_by,
        }
