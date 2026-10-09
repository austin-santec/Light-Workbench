"""Operator-selected wavelength modes and source assumptions.

The application cannot reliably identify the installed ILM source set.  The
selected mode is therefore authoritative: it configures both the OPM pair and
the assumed source wavelengths.  The legacy compatibility classification is
retained only when loading historical records that already contain it.
"""

from dataclasses import dataclass
from enum import Enum
from collections.abc import Mapping


class WavelengthMode(str, Enum):
    """Operator-selectable optical test modes."""

    SM = "SM"
    MM = "MM"


class MeasurementClassification(str, Enum):
    """Relationship between requested OPM settings and physical sources."""

    NATIVE = "native"
    COMPATIBILITY = "compatibility"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class WavelengthProfile:
    """One ordered two-wavelength test definition."""

    mode: WavelengthMode
    display_name: str
    opm_wavelengths_nm: tuple[int, int]
    expected_source_wavelengths_nm: tuple[int, int]

    @property
    def code(self) -> str:
        return self.mode.value

    @property
    def short_label(self) -> str:
        first, second = self.opm_wavelengths_nm
        return "%s (%d/%d nm)" % (self.mode.value, first, second)

    @property
    def display_label(self) -> str:
        return "%s (%s)" % (self.display_name, self.short_label)

    def reference_label(self, slot: int) -> str:
        return "%d ref:" % self.opm_wavelengths_nm[int(slot)]

    def loss_header(self, slot: int) -> str:
        return "%d nm IL (dB)" % self.opm_wavelengths_nm[int(slot)]

    @property
    def has_approved_limits(self) -> bool:
        """Return whether production limits currently exist for this mode."""
        return True

    @property
    def coc_eligible(self) -> bool:
        """Return whether approved COC templates currently support this mode."""
        return self.mode is WavelengthMode.SM


SM_WAVELENGTH_PROFILE = WavelengthProfile(
    WavelengthMode.SM,
    "Single Mode",
    (1310, 1550),
    (1310, 1550),
)
MM_WAVELENGTH_PROFILE = WavelengthProfile(
    WavelengthMode.MM,
    "Multimode",
    (850, 1300),
    (850, 1300),
)

WAVELENGTH_PROFILES = {
    WavelengthMode.SM: SM_WAVELENGTH_PROFILE,
    WavelengthMode.MM: MM_WAVELENGTH_PROFILE,
}


def normalize_wavelength_mode(value: object) -> WavelengthMode:
    """Return a stable mode, treating missing legacy data as SM."""
    if isinstance(value, WavelengthMode):
        return value
    text = str(value or "SM").strip().upper().replace("-", " ")
    if text in {"MM", "MULTIMODE", "MULTI MODE"}:
        return WavelengthMode.MM
    if text in {"SM", "SINGLEMODE", "SINGLE MODE", ""}:
        return WavelengthMode.SM
    raise ValueError("Unsupported wavelength mode: %s" % value)


def wavelength_profile(value: object = WavelengthMode.SM) -> WavelengthProfile:
    """Resolve a profile from an enum, code, or persisted display value."""
    return WAVELENGTH_PROFILES[normalize_wavelength_mode(value)]


@dataclass(frozen=True)
class SourceCapabilityProfile:
    """Configured nominal wavelengths for two physical source IDs."""

    profile_id: str
    mode: WavelengthMode
    source_wavelengths_by_id: Mapping[int, int]
    origin: str = "adapter_default"

    def __post_init__(self):
        source_map = {
            int(source_id): int(wavelength)
            for source_id, wavelength in self.source_wavelengths_by_id.items()
        }
        if set(source_map) != {0, 1}:
            raise ValueError("A two-source profile must define source IDs 0 and 1.")
        object.__setattr__(self, "source_wavelengths_by_id", source_map)

    @property
    def ordered_source_ids(self) -> tuple[int, int]:
        return (0, 1)

    @property
    def ordered_wavelengths_nm(self) -> tuple[int, int]:
        return tuple(
            self.source_wavelengths_by_id[source_id]
            for source_id in self.ordered_source_ids
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "mode": self.mode.value,
            "source_ids": list(self.ordered_source_ids),
            "source_wavelengths_nm": list(self.ordered_wavelengths_nm),
            "origin": self.origin,
        }


SM_SOURCE_PROFILE = SourceCapabilityProfile(
    "op815-sm",
    WavelengthMode.SM,
    {0: 1310, 1: 1550},
)
MM_SOURCE_PROFILE = SourceCapabilityProfile(
    "op815-mm",
    WavelengthMode.MM,
    {0: 850, 1: 1300},
)


def source_profile_for_mode(
    value: object,
    *,
    origin: str = "configured",
) -> SourceCapabilityProfile:
    """Create the supported two-source profile for a configured ILM mode."""
    mode = normalize_wavelength_mode(value)
    base = SM_SOURCE_PROFILE if mode is WavelengthMode.SM else MM_SOURCE_PROFILE
    return SourceCapabilityProfile(
        base.profile_id,
        base.mode,
        base.source_wavelengths_by_id,
        origin,
    )


@dataclass(frozen=True)
class MeasurementConfiguration:
    """Resolved OPM/source pairing for one reference or run."""

    wavelength_profile: WavelengthProfile
    source_profile: SourceCapabilityProfile = SM_SOURCE_PROFILE
    classification_override: MeasurementClassification | None = None
    mode_selection_method: str = "operator_selected"

    @property
    def classification(self) -> MeasurementClassification:
        if self.classification_override is not None:
            return self.classification_override
        selected = self.wavelength_profile.mode
        source = self.source_profile.mode
        if selected is source:
            return MeasurementClassification.NATIVE
        if selected is WavelengthMode.MM and source is WavelengthMode.SM:
            return MeasurementClassification.COMPATIBILITY
        return MeasurementClassification.UNSUPPORTED

    @property
    def is_supported(self) -> bool:
        return self.classification is not MeasurementClassification.UNSUPPORTED

    @property
    def is_compatibility(self) -> bool:
        return self.classification is MeasurementClassification.COMPATIBILITY

    @property
    def opm_wavelengths_nm(self) -> tuple[int, int]:
        return self.wavelength_profile.opm_wavelengths_nm

    @property
    def source_ids(self) -> tuple[int, int]:
        return self.source_profile.ordered_source_ids

    @property
    def source_wavelengths_nm(self) -> tuple[int, int]:
        return self.source_profile.ordered_wavelengths_nm

    def as_dict(self) -> dict[str, object]:
        return {
            "wavelength_mode": self.wavelength_profile.code,
            "opm_wavelengths_nm": list(self.opm_wavelengths_nm),
            "source_ids": list(self.source_ids),
            "source_wavelengths_nm": list(self.source_wavelengths_nm),
            "source_profile_id": self.source_profile.profile_id,
            "source_profile_origin": self.source_profile.origin,
            "measurement_classification": self.classification.value,
            "mode_selection_method": self.mode_selection_method,
        }


def measurement_configuration(
    mode: object = WavelengthMode.SM,
    source_profile: SourceCapabilityProfile | None = None,
    *,
    mode_selection_method: str = "operator_selected",
) -> MeasurementConfiguration:
    profile = wavelength_profile(mode)
    # A caller may still pass the old default SM profile while selecting MM.
    # The selected mode must remain authoritative, so replace mismatched
    # source assumptions with the corresponding operator-selected profile.
    if source_profile is None or source_profile.mode is not profile.mode:
        source_profile = source_profile_for_mode(
            profile.mode,
            origin=mode_selection_method,
        )
    return MeasurementConfiguration(
        profile,
        source_profile,
        mode_selection_method=mode_selection_method,
    )


def profile_from_metadata(metadata: Mapping[str, object] | None) -> WavelengthProfile:
    """Resolve persisted run metadata, defaulting old runs to SM."""
    values = metadata or {}
    return wavelength_profile(
        values.get("Wavelength mode", values.get("wavelength_mode", "SM"))
    )


def configuration_from_metadata(
    metadata: Mapping[str, object] | None,
    *,
    fallback_source_profile: SourceCapabilityProfile = SM_SOURCE_PROFILE,
) -> MeasurementConfiguration:
    """Restore a run configuration without rewriting historical classification."""
    values = metadata or {}
    profile = profile_from_metadata(values)
    source_value = values.get(
        "Source wavelengths nm", values.get("source_wavelengths_nm")
    )
    if source_value:
        if isinstance(source_value, str):
            source_wavelengths = tuple(
                int(item.strip()) for item in source_value.split(",") if item.strip()
            )
        else:
            source_wavelengths = tuple(int(item) for item in source_value)
        if source_wavelengths == (850, 1300):
            source_mode = WavelengthMode.MM
        elif source_wavelengths == (1310, 1550):
            source_mode = WavelengthMode.SM
        else:
            raise ValueError("Unsupported persisted source wavelength profile.")
        raw_ids = values.get("Source IDs", values.get("source_ids", (0, 1)))
        if isinstance(raw_ids, str):
            source_ids = tuple(
                int(item.strip()) for item in raw_ids.split(",") if item.strip()
            )
        else:
            source_ids = tuple(int(item) for item in raw_ids)
        source_profile = SourceCapabilityProfile(
            str(
                values.get("Source profile", values.get("source_profile_id"))
                or ("op815-mm" if source_mode is WavelengthMode.MM else "op815-sm")
            ),
            source_mode,
            dict(zip(source_ids, source_wavelengths)),
            str(
                values.get(
                    "Source profile origin",
                    values.get("source_profile_origin", "run_metadata"),
                )
                or "run_metadata"
            ),
        )
    else:
        source_profile = fallback_source_profile
    classification_value = values.get(
        "Measurement classification",
        values.get("measurement_classification"),
    )
    classification_override = None
    if classification_value in {
        item.value for item in MeasurementClassification
    }:
        classification_override = MeasurementClassification(classification_value)
    return MeasurementConfiguration(
        profile,
        source_profile,
        classification_override=classification_override,
        mode_selection_method=str(
            values.get(
                "Mode selection method",
                values.get("mode_selection_method", "loaded_run_metadata"),
            )
            or "loaded_run_metadata"
        ),
    )


__all__ = [
    "MM_SOURCE_PROFILE",
    "MM_WAVELENGTH_PROFILE",
    "MeasurementClassification",
    "MeasurementConfiguration",
    "SM_SOURCE_PROFILE",
    "SM_WAVELENGTH_PROFILE",
    "SourceCapabilityProfile",
    "WAVELENGTH_PROFILES",
    "WavelengthMode",
    "WavelengthProfile",
    "measurement_configuration",
    "configuration_from_metadata",
    "normalize_wavelength_mode",
    "profile_from_metadata",
    "source_profile_for_mode",
    "wavelength_profile",
]
