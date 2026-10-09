"""Reference-offset calculations and immutable reference audit snapshots."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4
from collections.abc import Mapping

from domain.wavelengths import SM_WAVELENGTH_PROFILE, WavelengthProfile


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
    wavelength_mode: str = "SM"
    opm_wavelengths_nm: tuple[int, int] = (1310, 1550)
    source_wavelengths_nm: tuple[int, int] = (1310, 1550)
    source_ids: tuple[int, int] = (0, 1)
    source_profile_id: str = "op815-sm"
    source_profile_origin: str = "legacy_default"
    measurement_classification: str = "native"

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
        values = {
            "snapshot_id": self.snapshot_id,
            "method": self.method,
            "established_at": self.established_at,
            "meter_model": self.meter_model,
            "meter_serial": self.meter_serial,
            "meter_resource_address": self.meter_resource_address,
            "laser_model": self.laser_model,
            "laser_serial": self.laser_serial,
            "operator_initials": self.operator_initials,
            "wavelength_mode": self.wavelength_mode,
            "opm_wavelengths_nm": list(self.opm_wavelengths_nm),
            "source_wavelengths_nm": list(self.source_wavelengths_nm),
            "source_ids": list(self.source_ids),
            "source_profile_id": self.source_profile_id,
            "source_profile_origin": self.source_profile_origin,
            "measurement_classification": self.measurement_classification,
            "references_by_wavelength": {
                str(wavelength): float(reference)
                for wavelength, reference in zip(
                    self.opm_wavelengths_nm,
                    (self.reference_1310_dbm, self.reference_1550_dbm),
                )
            },
        }
        if self.wavelength_mode == "SM":
            values.update(
                {
                    "reference_1310_dbm": float(self.reference_1310_dbm),
                    "reference_1550_dbm": float(self.reference_1550_dbm),
                }
            )
        return values

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "ReferenceSnapshot":
        if not isinstance(values, Mapping):
            raise ValueError("Reference snapshot must be an object.")
        opm_wavelengths = tuple(
            int(value)
            for value in values.get("opm_wavelengths_nm", (1310, 1550))
        )
        generic_references = values.get("references_by_wavelength", {})
        if isinstance(generic_references, Mapping) and generic_references:
            first_reference = float(
                generic_references.get(
                    str(opm_wavelengths[0]), generic_references.get(opm_wavelengths[0])
                )
            )
            second_reference = float(
                generic_references.get(
                    str(opm_wavelengths[1]), generic_references.get(opm_wavelengths[1])
                )
            )
        else:
            first_reference = float(values["reference_1310_dbm"])
            second_reference = float(values["reference_1550_dbm"])
        return cls(
            snapshot_id=str(values.get("snapshot_id") or ""),
            reference_1310_dbm=first_reference,
            reference_1550_dbm=second_reference,
            method=str(values.get("method") or ""),
            established_at=str(values.get("established_at") or ""),
            meter_model=str(values.get("meter_model") or ""),
            meter_serial=str(values.get("meter_serial") or ""),
            meter_resource_address=str(values.get("meter_resource_address") or ""),
            laser_model=str(values.get("laser_model") or ""),
            laser_serial=str(values.get("laser_serial") or ""),
            operator_initials=str(values.get("operator_initials") or ""),
            wavelength_mode=str(values.get("wavelength_mode") or "SM"),
            opm_wavelengths_nm=opm_wavelengths,
            source_wavelengths_nm=tuple(
                int(value)
                for value in values.get("source_wavelengths_nm", (1310, 1550))
            ),
            source_ids=tuple(
                int(value) for value in values.get("source_ids", (0, 1))
            ),
            source_profile_id=str(values.get("source_profile_id") or "op815-sm"),
            source_profile_origin=str(
                values.get("source_profile_origin") or "legacy_default"
            ),
            measurement_classification=str(
                values.get("measurement_classification") or "native"
            ),
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
    measurement_configuration=None,
) -> ReferenceSnapshot:
    """Create a uniquely identified reference snapshot for an active session."""
    configuration = measurement_configuration
    configuration_values = (
        configuration.as_dict()
        if configuration is not None
        else {
            "wavelength_mode": "SM",
            "opm_wavelengths_nm": list(SM_WAVELENGTH_PROFILE.opm_wavelengths_nm),
            "source_wavelengths_nm": [1310, 1550],
            "source_ids": [0, 1],
            "source_profile_id": "op815-sm",
            "source_profile_origin": "legacy_default",
            "measurement_classification": "native",
        }
    )
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
        wavelength_mode=str(configuration_values["wavelength_mode"]),
        opm_wavelengths_nm=tuple(configuration_values["opm_wavelengths_nm"]),
        source_wavelengths_nm=tuple(configuration_values["source_wavelengths_nm"]),
        source_ids=tuple(configuration_values["source_ids"]),
        source_profile_id=str(configuration_values["source_profile_id"]),
        source_profile_origin=str(configuration_values["source_profile_origin"]),
        measurement_classification=str(
            configuration_values["measurement_classification"]
        ),
    )


def calculate_reference_offsets(
    absolute_readings: Mapping[int, float],
    wavelengths=(1310, 1550),
) -> tuple[float, float]:
    """Return two-decimal reference offsets from absolute power readings.

    With the software reference at zero, the absolute reading is the power
    baseline. The stored reference is therefore that measured power. For
    example, a zero-reference reading of ``-0.72`` represents a ``0.72 dBm``
    reference offset used by the insertion-loss calculation.
    """
    try:
        first_wavelength, second_wavelength = tuple(wavelengths)
        first_reading = float(absolute_readings[first_wavelength])
        second_reading = float(absolute_readings[second_wavelength])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "Both configured wavelength readings are required."
        ) from error

    return round(first_reading, 2), round(second_reading, 2)
