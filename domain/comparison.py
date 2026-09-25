"""Read-only comparison calculations for measurements from multiple runs."""

from collections.abc import Iterable

from .models import MeasurementRecord


def index_measurements(
    measurements: Iterable[MeasurementRecord],
) -> dict[int, MeasurementRecord]:
    """Index one run's accepted measurements by logical channel."""
    return {record.channel: record for record in measurements}


def comparison_values(
    comparison_records: dict[int, MeasurementRecord],
    channel: int,
    decimal_places: int = 4,
) -> tuple[str, str]:
    """Return display-ready wavelength values for a comparison channel."""
    record = comparison_records.get(channel)
    if record is None:
        return ("-", "-")
    format_string = "%%.%df" % decimal_places
    return (
        format_string % record.loss_1310,
        format_string % record.loss_1550,
    )
