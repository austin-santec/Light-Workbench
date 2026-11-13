"""Formatting helpers for copying accepted run readings to other tools."""

from collections.abc import Iterable
from decimal import Decimal, ROUND_HALF_UP

from .models import MeasurementRecord


MAX_COPY_DECIMAL_PLACES = 4


def format_raw_measurements(
    measurements: Iterable[MeasurementRecord],
    decimal_places: int = MAX_COPY_DECIMAL_PLACES,
) -> str:
    """Format accepted readings as Excel-compatible tab-separated text.

    ``RunData.measurements`` contains only readings that were accepted with
    Write IL. The last record for a duplicate logical channel is retained so
    legacy inputs with repeated rows follow the same replacement semantics as
    the current run workflow.
    """
    records_by_channel = {record.channel: record for record in measurements}
    if not records_by_channel:
        raise ValueError("At least one completed measurement is required.")
    if (
        isinstance(decimal_places, bool)
        or not isinstance(decimal_places, int)
        or not 0 <= decimal_places <= MAX_COPY_DECIMAL_PLACES
    ):
        raise ValueError(
            "Decimal places must be an integer from 0 through %d."
            % MAX_COPY_DECIMAL_PLACES
        )

    quantum = Decimal(1).scaleb(-decimal_places)

    def format_loss(value: float) -> str:
        rounded = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
        return f"{rounded:.{decimal_places}f}"

    rows = [
        "\t".join(
            (
                str(record.channel),
                *(format_loss(value) for value in record.ordered_losses),
            )
        )
        for record in sorted(records_by_channel.values(), key=lambda item: item.channel)
    ]
    return "\n".join(rows)


__all__ = ["MAX_COPY_DECIMAL_PLACES", "format_raw_measurements"]
