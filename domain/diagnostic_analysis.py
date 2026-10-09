"""In-memory models and statistics for power-diagnostic readings."""

from dataclasses import dataclass
from statistics import fmean, stdev
from typing import Sequence


MANUAL_METHOD = "Manual"
MONITORING_METHOD = "Monitoring"
SUPPORTED_METHODS = (MANUAL_METHOD, MONITORING_METHOD)


@dataclass(frozen=True)
class DiagnosticReading:
    """One complete two-wavelength diagnostic sample.

    The values are intentionally kept separate from persistence models because
    diagnostic history exists only for the lifetime of the tool window.
    """

    reading_number: int
    timestamp: str
    method: str
    channel: int | None
    physical_port: int | None
    measured_1310: float
    reference_1310: float
    insertion_loss_1310: float
    measured_1550: float
    reference_1550: float
    insertion_loss_1550: float
    wavelength_mode: str = "SM"
    opm_wavelengths_nm: tuple[int, int] = (1310, 1550)
    source_wavelengths_nm: tuple[int, int] = (1310, 1550)
    source_ids: tuple[int, int] = (0, 1)
    measurement_classification: str = "native"

    def insertion_loss_for(self, wavelength_nm: int) -> float:
        slot = self.opm_wavelengths_nm.index(int(wavelength_nm))
        return (
            self.insertion_loss_1310
            if slot == 0
            else self.insertion_loss_1550
        )


@dataclass(frozen=True)
class VariationStatistics:
    """Descriptive statistics for one wavelength's ordered samples."""

    wavelength_nm: int
    count: int
    average: float
    minimum: float
    maximum: float
    value_range: float
    standard_deviation: float
    first_to_last: float


@dataclass(frozen=True)
class DiagnosticAnalysis:
    """Statistics calculated for one acquisition method."""

    method: str
    count: int
    by_wavelength: dict[int, VariationStatistics]


def _values_for_wavelength(
    readings: Sequence[DiagnosticReading], wavelength_nm: int
) -> list[float]:
    try:
        return [reading.insertion_loss_for(wavelength_nm) for reading in readings]
    except ValueError:
        raise ValueError("Unsupported diagnostic wavelength: %s" % wavelength_nm)


def calculate_variation_statistics(
    readings: Sequence[DiagnosticReading], wavelength_nm: int
) -> VariationStatistics:
    """Calculate statistics for at least two ordered diagnostic readings.

    Standard deviation uses the sample definition (``n - 1``), which is the
    useful estimate when these readings represent a sample of future cable or
    instrument behavior rather than every possible observation.
    """
    if len(readings) < 2:
        raise ValueError("At least two readings are required for analysis.")

    values = _values_for_wavelength(readings, wavelength_nm)
    return VariationStatistics(
        wavelength_nm=wavelength_nm,
        count=len(values),
        average=fmean(values),
        minimum=min(values),
        maximum=max(values),
        value_range=max(values) - min(values),
        standard_deviation=stdev(values),
        first_to_last=values[-1] - values[0],
    )


def analyze_diagnostic_readings(
    readings: Sequence[DiagnosticReading], method: str
) -> DiagnosticAnalysis:
    """Analyze only readings collected by the requested acquisition method."""
    if method not in SUPPORTED_METHODS:
        raise ValueError("Unsupported diagnostic acquisition method: %s" % method)

    selected = tuple(reading for reading in readings if reading.method == method)
    if len(selected) < 2:
        raise ValueError(
            "%s analysis requires at least two %s readings."
            % (method, method.lower())
        )

    wavelengths = selected[0].opm_wavelengths_nm
    if any(reading.opm_wavelengths_nm != wavelengths for reading in selected):
        raise ValueError("Diagnostic analysis cannot mix wavelength modes.")
    return DiagnosticAnalysis(
        method=method,
        count=len(selected),
        by_wavelength={
            wavelength: calculate_variation_statistics(selected, wavelength)
            for wavelength in wavelengths
        },
    )


__all__ = [
    "DiagnosticAnalysis",
    "DiagnosticReading",
    "MANUAL_METHOD",
    "MONITORING_METHOD",
    "SUPPORTED_METHODS",
    "VariationStatistics",
    "analyze_diagnostic_readings",
    "calculate_variation_statistics",
]
