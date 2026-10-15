"""Run-purpose definitions and policy helpers shared by UI and persistence."""

from __future__ import annotations

from enum import Enum


class RunPurpose(str, Enum):
    PRODUCTION = "production"
    ENGINEERING = "engineering"
    TRAINING = "training"
    CALIBRATION = "calibration"


RUN_PURPOSE_OPTIONS = (
    ("Production", RunPurpose.PRODUCTION.value),
    ("Engineering", RunPurpose.ENGINEERING.value),
    ("Training", RunPurpose.TRAINING.value),
    ("Calibration", RunPurpose.CALIBRATION.value),
)
VALID_RUN_PURPOSES = frozenset(value for _label, value in RUN_PURPOSE_OPTIONS)


def normalize_run_purpose(value: str | RunPurpose | None) -> str:
    """Return a validated stable value for a persisted run purpose."""

    purpose = str(value.value if isinstance(value, RunPurpose) else value or "").strip().lower()
    if purpose not in VALID_RUN_PURPOSES:
        raise ValueError(
            "Run purpose must be one of: %s."
            % ", ".join(sorted(VALID_RUN_PURPOSES))
        )
    return purpose


def run_purpose_label(value: str | RunPurpose | None) -> str:
    """Return the operator-facing label for a validated purpose."""

    purpose = normalize_run_purpose(value)
    return dict((value, label) for label, value in RUN_PURPOSE_OPTIONS)[purpose]


def default_analysis_policy(value: str | RunPurpose | None) -> tuple[str, str | None]:
    """Return the initial analysis state and reason for a new run."""

    purpose = normalize_run_purpose(value)
    if purpose == RunPurpose.PRODUCTION.value:
        return "pending", None
    return "excluded", "Run purpose: %s" % purpose


__all__ = [
    "RUN_PURPOSE_OPTIONS",
    "RunPurpose",
    "VALID_RUN_PURPOSES",
    "default_analysis_policy",
    "normalize_run_purpose",
    "run_purpose_label",
]
