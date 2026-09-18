"""Reusable reference-offset calculations for optical power measurements."""


def calculate_reference_offsets(absolute_readings):
    """Return two-decimal reference offsets from absolute power readings.

    The application calculates insertion loss as ``reference - measured``.
    Therefore, when the zero-reference measurement is used as the baseline,
    the reference value to store is the measured absolute power itself.  For
    example, a zero-reference IL display of ``-0.72`` means the meter's
    absolute reading is ``+0.72`` and the stored reference must be ``+0.72``.
    The calculation is intentionally independent of the instrument
    implementation so a future OPM/laser measurement provider can use it too.
    """
    try:
        reading_1310 = float(absolute_readings[1310])
        reading_1550 = float(absolute_readings[1550])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "Both 1310 nm and 1550 nm absolute readings are required."
        ) from error

    return round(reading_1310, 2), round(reading_1550, 2)
