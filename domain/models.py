"""Typed, vendor-neutral models for optical test data.

The persistence layer still uses the existing CSV/JSON field names. These
models provide a safer representation for new application code while the
serialization migration happens incrementally.
"""

from dataclasses import dataclass, field, replace
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


class DeviceCategory(str, Enum):
    """Vendor-neutral hardware categories shown to the operator."""

    POWER_METER = "power_meter"
    OPTICAL_SWITCH = "optical_switch"
    LASER_SOURCE = "laser_source"


class ConnectionState(str, Enum):
    """Connection lifecycle states for one physical device."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    IN_USE = "in_use"
    ERROR = "error"


@dataclass(frozen=True)
class DeviceInfo:
    """Identity and connection state reported by a hardware adapter.

    This model is intentionally separate from run metadata.  It describes the
    transient device currently connected to the workstation and is therefore
    not written to CSV, JSON, or COC output.
    """

    category: DeviceCategory
    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""
    raw_identity: str = ""
    resource_address: str = ""
    state: ConnectionState = ConnectionState.DISCONNECTED
    error: str = ""
    transport_details: str = ""
    firmware_version: str = ""
    configured_channel_count: int | None = None
    discovery_method: str = ""
    failure_stage: str = ""
    failed_command: str = ""
    raw_response: str = ""
    connection_warning: str = ""
    model_detection_method: str = ""
    source_profile_id: str = ""
    source_profile_origin: str = ""
    source_mode: str = ""
    source_ids: tuple[int, int] = ()
    source_wavelengths_nm: tuple[int, int] = ()

    def with_state(self, state: ConnectionState, error: str = "") -> "DeviceInfo":
        """Return this identity with an updated transient connection state."""
        return replace(self, state=state, error=error)


@dataclass(frozen=True)
class MeasurementRecord:
    """One accepted insertion-loss result for a logical channel."""

    channel: int
    loss_1310: float | None
    loss_1550: float | None
    physical_port: int | None = None
    reference_snapshot: dict | None = None
    wavelength_mode: str = "SM"
    losses_by_wavelength: dict[int, float] = field(default_factory=dict)
    measurement_classification: str = "native"
    opm_wavelengths_nm: tuple[int, int] = (1310, 1550)
    source_wavelengths_nm: tuple[int, int] = (1310, 1550)
    source_ids: tuple[int, int] = (0, 1)

    def __post_init__(self):
        from domain.wavelengths import wavelength_profile

        profile = wavelength_profile(self.wavelength_mode)
        wavelengths = tuple(int(value) for value in self.opm_wavelengths_nm)
        if not self.losses_by_wavelength:
            if self.loss_1310 is None or self.loss_1550 is None:
                raise ValueError("Both configured wavelength losses are required.")
            losses = {
                profile.opm_wavelengths_nm[0]: float(self.loss_1310),
                profile.opm_wavelengths_nm[1]: float(self.loss_1550),
            }
            wavelengths = profile.opm_wavelengths_nm
        else:
            losses = {
                int(wavelength): float(value)
                for wavelength, value in self.losses_by_wavelength.items()
            }
            missing = set(wavelengths) - set(losses)
            if missing:
                raise ValueError(
                    "Measurement is missing wavelength(s): %s"
                    % ", ".join(str(value) for value in sorted(missing))
                )
        object.__setattr__(self, "wavelength_mode", profile.code)
        object.__setattr__(self, "opm_wavelengths_nm", wavelengths)
        object.__setattr__(self, "losses_by_wavelength", losses)
        if profile.code == "SM":
            object.__setattr__(self, "loss_1310", losses[1310])
            object.__setattr__(self, "loss_1550", losses[1550])

    @classmethod
    def from_wavelengths(
        cls,
        channel: int,
        losses: Mapping[int, float],
        *,
        physical_port: int | None = None,
        reference_snapshot: dict | None = None,
        wavelength_mode: str = "SM",
        measurement_classification: str = "native",
        source_wavelengths_nm=(1310, 1550),
        source_ids=(0, 1),
    ) -> "MeasurementRecord":
        from domain.wavelengths import wavelength_profile

        profile = wavelength_profile(wavelength_mode)
        normalized = {int(key): float(value) for key, value in losses.items()}
        legacy = (
            (normalized.get(1310), normalized.get(1550))
            if profile.code == "SM"
            else (None, None)
        )
        return cls(
            channel,
            legacy[0],
            legacy[1],
            physical_port=physical_port,
            reference_snapshot=reference_snapshot,
            wavelength_mode=profile.code,
            losses_by_wavelength=normalized,
            measurement_classification=measurement_classification,
            opm_wavelengths_nm=profile.opm_wavelengths_nm,
            source_wavelengths_nm=tuple(source_wavelengths_nm),
            source_ids=tuple(source_ids),
        )

    def loss_for(self, wavelength_nm: int) -> float:
        return float(self.losses_by_wavelength[int(wavelength_nm)])

    @property
    def ordered_losses(self) -> tuple[float, float]:
        return tuple(self.loss_for(value) for value in self.opm_wavelengths_nm)


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
