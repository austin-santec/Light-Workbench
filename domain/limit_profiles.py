"""Model-specific insertion-loss quality criteria.

The optical-switch model determines which criteria apply.  Keeping this
separate from the hardware driver prevents SCPI/VISA code from becoming the
owner of production-quality rules.
"""

from dataclasses import dataclass
import math
from typing import Mapping


SUPPORTED_SWITCH_MODELS = ("OSX-100", "OSX-150")


def normalize_switch_model(value: str | None) -> str:
    """Return the canonical supported model name for an identity string."""
    text = str(value or "").strip().upper().replace("_", "-")
    compact = text.replace(" ", "")
    if compact in {"OSX100", "OSX-100"} or "OSX-100" in text or "OSX100" in compact:
        return "OSX-100"
    if compact in {"OSX150", "OSX-150"} or "OSX-150" in text or "OSX150" in compact:
        return "OSX-150"
    return text


@dataclass(frozen=True)
class LimitAssessment:
    """Classification of one completed two-wavelength reading."""

    too_good_wavelengths: tuple[int, ...] = ()
    optimization_wavelengths: tuple[int, ...] = ()
    fail_wavelengths: tuple[int, ...] = ()

    @property
    def is_too_good(self) -> bool:
        return bool(self.too_good_wavelengths)

    @property
    def is_optimization(self) -> bool:
        return bool(self.optimization_wavelengths)

    @property
    def is_fail(self) -> bool:
        return bool(self.fail_wavelengths)


@dataclass(frozen=True)
class LimitProfile:
    """Validated criteria used for one switch model and run."""

    model: str
    profile_name: str
    revision: str
    too_good_below_db: float
    warning_enabled: bool
    warning_above_db: float | None
    fail_above_db: float

    def validate(self) -> "LimitProfile":
        model = normalize_switch_model(self.model)
        if model not in SUPPORTED_SWITCH_MODELS and model != "LEGACY":
            raise ValueError("Unsupported switch model: %s" % self.model)
        if not str(self.profile_name).strip() or not str(self.revision).strip():
            raise ValueError("Profile name and revision are required.")
        values = (self.too_good_below_db, self.fail_above_db)
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError("Limit values must be finite numbers.")
        if not -100 <= float(self.too_good_below_db) <= 100:
            raise ValueError("Too-good limit must be between -100 and 100 dB.")
        if not -100 <= float(self.fail_above_db) <= 100:
            raise ValueError("Fail limit must be between -100 and 100 dB.")
        if model != "LEGACY" and self.too_good_below_db >= self.fail_above_db:
            raise ValueError("Too-good limit must be below the fail limit.")
        if self.warning_enabled:
            if model == "OSX-100":
                raise ValueError("OSX-100 does not have an optimization warning limit.")
            if self.warning_above_db is None:
                raise ValueError("An enabled warning limit must have a value.")
            if not math.isfinite(float(self.warning_above_db)):
                raise ValueError("Warning limit must be a finite number.")
            if not -100 <= float(self.warning_above_db) <= 100:
                raise ValueError("Warning limit must be between -100 and 100 dB.")
            if model != "LEGACY" and self.warning_above_db >= self.fail_above_db:
                raise ValueError("Warning limit must be below the fail limit.")
        elif model == "OSX-150":
            raise ValueError("OSX-150 requires an optimization warning limit.")
        return self

    def classify(self, loss_1310: float, loss_1550: float) -> LimitAssessment:
        """Classify both wavelengths using strict boundary comparisons."""
        losses = ((1310, float(loss_1310)), (1550, float(loss_1550)))
        too_good = tuple(
            wavelength
            for wavelength, loss in losses
            if loss < self.too_good_below_db
        )
        fail = tuple(
            wavelength
            for wavelength, loss in losses
            if loss > self.fail_above_db
        )
        optimization = ()
        if self.warning_enabled and self.warning_above_db is not None:
            optimization = tuple(
                wavelength
                for wavelength, loss in losses
                if loss > self.warning_above_db and loss <= self.fail_above_db
            )
        return LimitAssessment(too_good, optimization, fail)

    def as_dict(self) -> dict[str, object]:
        """Return the stable JSON-compatible run snapshot."""
        return {
            "model": normalize_switch_model(self.model),
            "profile_name": str(self.profile_name),
            "revision": str(self.revision),
            "too_good_below_db": float(self.too_good_below_db),
            "warning_enabled": bool(self.warning_enabled),
            "warning_above_db": (
                None if self.warning_above_db is None else float(self.warning_above_db)
            ),
            "fail_above_db": float(self.fail_above_db),
        }

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "LimitProfile":
        """Build and validate a profile from INI/JSON-like values."""
        warning_enabled = values.get("warning_enabled", True)
        if isinstance(warning_enabled, str):
            warning_enabled = warning_enabled.strip().lower() in {"1", "true", "yes", "on"}
        warning = values.get("warning_above_db")
        return cls(
            model=str(values.get("model", "")),
            profile_name=str(values.get("profile_name", "")),
            revision=str(values.get("revision", "")),
            too_good_below_db=float(values["too_good_below_db"]),
            warning_enabled=bool(warning_enabled),
            warning_above_db=None if warning in (None, "", "none") else float(warning),
            fail_above_db=float(values["fail_above_db"]),
        ).validate()


def default_limit_profiles() -> dict[str, LimitProfile]:
    """Return the shipped production defaults."""
    return {
        "OSX-100": LimitProfile(
            "OSX-100", "OSX-100 standard", "1", 0.2, False, None, 0.8
        ),
        "OSX-150": LimitProfile(
            "OSX-150", "OSX-150 standard", "1", 0.5, True, 2.25, 2.5
        ),
    }


def legacy_limit_profile(warning_limit: float) -> LimitProfile:
    """Represent an older run's single editable warning limit safely."""
    limit = float(warning_limit)
    return LimitProfile(
        "LEGACY",
        "Legacy warning limit",
        "legacy",
        -100.0,
        True,
        limit,
        limit,
    )


__all__ = [
    "SUPPORTED_SWITCH_MODELS",
    "LimitAssessment",
    "LimitProfile",
    "default_limit_profiles",
    "legacy_limit_profile",
    "normalize_switch_model",
]
