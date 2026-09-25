"""Compatibility facade for the domain replacement-analysis services.

New code should import replacement analysis from :mod:`domain.replacements`.
This module remains available so existing integrations and saved-project tests
that import the historical top-level module continue to work.
"""

from domain.replacements import (
    ReplacementReading,
    analyze_replacements,
    completed_replacement_metadata,
    normalise_completed_replacements,
    parse_extra_readings,
    recommendation_category,
    replacement_metadata,
)

__all__ = [
    "ReplacementReading",
    "analyze_replacements",
    "completed_replacement_metadata",
    "normalise_completed_replacements",
    "parse_extra_readings",
    "recommendation_category",
    "replacement_metadata",
]
