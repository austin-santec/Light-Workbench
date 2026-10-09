"""Instrument-independent insertion-loss calculations and validation."""

from dataclasses import dataclass
from collections.abc import Mapping


MEASUREMENT_WAVELENGTHS_NM = (1310, 1550)
DARK_REFERENCE_THRESHOLD_DBM = -40.0
NON_NEGATIVE_LOSS_THRESHOLD_DB = 0.0


@dataclass(frozen=True)
class MeasurementValidation:
    """Validation result for a complete two-wavelength sample."""

    valid: bool
    reason: str = ""
    invalid_wavelengths: tuple[int, ...] = ()
    rounded_losses: Mapping[int, float] | None = None


def validate_reference_measurements(
    measured_powers: Mapping[int, float],
    threshold_dbm: float = DARK_REFERENCE_THRESHOLD_DBM,
    wavelengths=MEASUREMENT_WAVELENGTHS_NM,
) -> MeasurementValidation:
    """Reject a calculated reference when a wavelength appears dark."""
    invalid = tuple(
        wavelength
        for wavelength in tuple(wavelengths)
        if float(measured_powers[wavelength]) < float(threshold_dbm)
    )
    return MeasurementValidation(
        valid=not invalid,
        reason="dark_reference" if invalid else "",
        invalid_wavelengths=invalid,
    )


def format_dark_reference_error(
    measured_powers: Mapping[int, float],
    threshold_dbm: float = DARK_REFERENCE_THRESHOLD_DBM,
    wavelengths=MEASUREMENT_WAVELENGTHS_NM,
) -> str:
    """Return a concise operator-facing explanation for a dark reference."""
    validation = validate_reference_measurements(
        measured_powers, threshold_dbm, wavelengths
    )
    details = "; ".join(
        "%d nm measured %.4f dBm (limit %.4f dBm)"
        % (wavelength, float(measured_powers[wavelength]), float(threshold_dbm))
        for wavelength in validation.invalid_wavelengths
    )
    return (
        "Reference calculation failed because the measured power is below "
        "the expected signal level. %s\n\n"
        "The cable may be disconnected, the source may be off, or the optical "
        "connection may be incorrect. Check the setup and calculate the "
        "reference again." % details
    )


def validate_insertion_loss(
    losses: Mapping[int, float],
    wavelengths=MEASUREMENT_WAVELENGTHS_NM,
) -> MeasurementValidation:
    """Reject complete samples whose displayed IL is negative."""
    rounded = {
        wavelength: round(float(losses[wavelength]), 4)
        for wavelength in tuple(wavelengths)
    }
    invalid = tuple(
        wavelength
        for wavelength, value in rounded.items()
        if value < NON_NEGATIVE_LOSS_THRESHOLD_DB
    )
    return MeasurementValidation(
        valid=not invalid,
        reason="negative_insertion_loss" if invalid else "",
        invalid_wavelengths=invalid,
        rounded_losses=rounded,
    )


def calculate_insertion_loss(
    reference_powers: Mapping[int, float],
    measured_powers: Mapping[int, float],
    wavelengths=MEASUREMENT_WAVELENGTHS_NM,
) -> dict[int, float]:
    """Calculate insertion loss for each supported wavelength.

    The calculation is intentionally independent of the instrument that
    produced the absolute power readings. A reference is the measured power
    without the device under test, so insertion loss is ``reference - measured``.
    """
    wavelengths = tuple(wavelengths)
    missing_reference = [
        wavelength
        for wavelength in wavelengths
        if wavelength not in reference_powers
    ]
    if missing_reference:
        raise ValueError(
            "Reference is missing wavelength(s): %s"
            % ", ".join(str(value) for value in missing_reference)
        )

    missing_measurements = [
        wavelength
        for wavelength in wavelengths
        if wavelength not in measured_powers
    ]
    if missing_measurements:
        raise ValueError(
            "Measurement is missing wavelength(s): %s"
            % ", ".join(str(value) for value in missing_measurements)
        )

    return {
        wavelength: float(reference_powers[wavelength])
        - float(measured_powers[wavelength])
        for wavelength in wavelengths
    }
