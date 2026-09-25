"""Compatibility facade for domain switch-test timing services."""

from domain.timing import (
    SwitchTestTimer,
    format_duration,
    format_timestamp,
    parse_duration,
)

__all__ = [
    "SwitchTestTimer",
    "format_duration",
    "format_timestamp",
    "parse_duration",
]
