"""Instrument-independent insertion-loss calculations."""

from collections.abc import Mapping


MEASUREMENT_WAVELENGTHS_NM = (1310, 1550)


def calculate_insertion_loss(
    reference_powers: Mapping[int, float],
    measured_powers: Mapping[int, float],
) -> dict[int, float]:
    """Calculate insertion loss for each supported wavelength.

    The calculation is intentionally independent of the instrument that
    produced the absolute power readings. A reference is the measured power
    without the device under test, so insertion loss is ``reference - measured``.
    """
    missing_reference = [
        wavelength
        for wavelength in MEASUREMENT_WAVELENGTHS_NM
        if wavelength not in reference_powers
    ]
    if missing_reference:
        raise ValueError(
            "Reference is missing wavelength(s): %s"
            % ", ".join(str(value) for value in missing_reference)
        )

    missing_measurements = [
        wavelength
        for wavelength in MEASUREMENT_WAVELENGTHS_NM
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
        for wavelength in MEASUREMENT_WAVELENGTHS_NM
    }
