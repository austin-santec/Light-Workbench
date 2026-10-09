"""Parsing and validation for supported Santec OSX part numbers."""

from __future__ import annotations

from dataclasses import dataclass
import re


MAX_FRONT_PANEL_CHANNELS = 48
_OSX_PART_NUMBER_PATTERN = re.compile(
    r"^OSX-(?P<model>100|150)-[^-]+-(?P<channel_count>\d{3})(?:-|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class OsxPartNumber:
    """Validated product identity fields needed by the application."""

    value: str
    model: str
    front_panel_channel_count: int


def parse_osx_part_number(part_number: str) -> OsxPartNumber:
    """Parse a supported OSX part number and return its product count.

    The three-digit field immediately after the product configuration field
    defines the production/front-panel channel count. It is intentionally
    independent from the physical channel capacity reported by the switch.
    """
    value = str(part_number or "").strip()
    if not value:
        raise ValueError("A part number is required to determine front-panel channels.")

    match = _OSX_PART_NUMBER_PATTERN.match(value)
    if match is None:
        raise ValueError(
            "The part number does not contain a valid three-digit front-panel "
            "channel field. Expected a format such as "
            "OSX-150-1A-012-09-FA-00B-2HD."
        )

    count = int(match.group("channel_count"))
    if not 1 <= count <= MAX_FRONT_PANEL_CHANNELS:
        raise ValueError(
            "The part number specifies %d front-panel channels; supported "
            "values are 1 through %d."
            % (count, MAX_FRONT_PANEL_CHANNELS)
        )

    return OsxPartNumber(
        value=value,
        model="OSX-%s" % match.group("model"),
        front_panel_channel_count=count,
    )


def resolve_front_panel_channel_count(part_number: str) -> int:
    """Return the validated front-panel count or raise an actionable error."""
    return parse_osx_part_number(part_number).front_panel_channel_count


def infer_front_panel_channel_count(part_number: str) -> int | None:
    """Return a count when valid, preserving the legacy optional API."""
    try:
        return resolve_front_panel_channel_count(part_number)
    except ValueError:
        return None


__all__ = [
    "MAX_FRONT_PANEL_CHANNELS",
    "OsxPartNumber",
    "infer_front_panel_channel_count",
    "parse_osx_part_number",
    "resolve_front_panel_channel_count",
]
