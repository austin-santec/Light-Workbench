"""Instrument-independent reference-offset calculations."""

from collections.abc import Mapping


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
