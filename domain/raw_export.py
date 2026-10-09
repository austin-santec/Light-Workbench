"""Formatting helpers for copying accepted run readings to other tools."""

from collections.abc import Iterable

from .models import MeasurementRecord


def format_raw_measurements(
    measurements: Iterable[MeasurementRecord],
    decimal_places: int = 4,
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

    format_string = "%%.%df" % decimal_places
    rows = [
        "\t".join(
            (
                str(record.channel),
                *(format_string % value for value in record.ordered_losses),
            )
        )
        for record in sorted(records_by_channel.values(), key=lambda item: item.channel)
    ]
    return "\n".join(rows)


__all__ = ["format_raw_measurements"]
