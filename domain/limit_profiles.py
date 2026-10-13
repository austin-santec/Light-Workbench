"""Model- and wavelength-mode-specific insertion-loss quality criteria.

The optical-switch model determines which criteria apply.  Keeping this
separate from the hardware driver prevents SCPI/VISA code from becoming the
owner of production-quality rules.
"""

from dataclasses import dataclass
import math
from typing import Mapping


SUPPORTED_SWITCH_MODELS = ("OSX-100", "OSX-150")
SUPPORTED_WAVELENGTH_MODES = ("SM", "MM")


def normalize_wavelength_mode(value: str | None) -> str:
    text = str(value or "SM").strip().upper().replace("-", " ")
    if text in {"MM", "MULTIMODE", "MULTI MODE"}:
        return "MM"
    return "SM"


def profile_key(model: str, wavelength_mode: str = "SM") -> str:
    """Return the stable persisted key for one model/mode profile."""
    return "%s/%s" % (
        normalize_switch_model(model),
        normalize_wavelength_mode(wavelength_mode),
    )


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
    wavelength_mode: str = "SM"

    def validate(self) -> "LimitProfile":
        model = normalize_switch_model(self.model)
        wavelength_mode = normalize_wavelength_mode(self.wavelength_mode)
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
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "wavelength_mode", wavelength_mode)
        return self

    def classify(
        self,
        first_loss: float,
        second_loss: float,
        wavelengths: tuple[int, int] = (1310, 1550),
    ) -> LimitAssessment:
        """Classify both configured wavelengths using strict comparisons."""
        first_wavelength, second_wavelength = tuple(wavelengths)
        losses = ((first_wavelength, float(first_loss)), (second_wavelength, float(second_loss)))
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
            "wavelength_mode": normalize_wavelength_mode(self.wavelength_mode),
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
            wavelength_mode=normalize_wavelength_mode(
                values.get("wavelength_mode", values.get("mode", "SM"))
            ),
        ).validate()


@dataclass(frozen=True)
class LoadedLimitProfileResolution:
    """Result of resolving criteria for a persisted run."""

    profile: LimitProfile | None
    source: str
    reason: str = ""


def resolve_loaded_run_profile(
    criteria_snapshot: Mapping[str, object] | None,
    metadata: Mapping[str, object] | None,
    wavelength_mode: str,
    profiles: Mapping[str, LimitProfile],
    *,
    criteria_present: bool = False,
    legacy_warning_limit: float | None = None,
) -> LoadedLimitProfileResolution:
    """Resolve a saved run's model/mode criteria without hardware fallbacks.

    A valid persisted criteria snapshot is authoritative.  Older runs without
    a snapshot may infer a supported model from their saved part number, but a
    contradictory snapshot is never replaced with an unrelated device model.
    """
    mode = normalize_wavelength_mode(wavelength_mode)
    if criteria_present:
        if not isinstance(criteria_snapshot, Mapping):
            return LoadedLimitProfileResolution(
                None,
                "unavailable",
                "The saved criteria snapshot is missing or malformed.",
            )
        try:
            profile = LimitProfile.from_mapping(criteria_snapshot)
        except (KeyError, TypeError, ValueError):
            return LoadedLimitProfileResolution(
                None,
                "unavailable",
                "The saved criteria snapshot is invalid.",
            )
        if profile.wavelength_mode != mode:
            return LoadedLimitProfileResolution(
                None,
                "unavailable",
                "The saved criteria mode does not match the run wavelength mode.",
            )
        return LoadedLimitProfileResolution(profile, "saved_snapshot")

    saved_metadata = dict(metadata or {})
    model = ""
    for key in ("Switch model", "Part number"):
        candidate = normalize_switch_model(saved_metadata.get(key))
        if candidate in SUPPORTED_SWITCH_MODELS:
            model = candidate
            break
    if model:
        profile = profiles.get(profile_key(model, mode))
        if profile is not None:
            return LoadedLimitProfileResolution(profile, "persisted_identity")
        return LoadedLimitProfileResolution(
            None,
            "unavailable",
            "No configured limit profile exists for %s %s." % (model, mode),
        )

    if mode == "SM" and legacy_warning_limit is not None:
        try:
            return LoadedLimitProfileResolution(
                legacy_limit_profile(float(legacy_warning_limit)),
                "legacy_warning_limit",
            )
        except (TypeError, ValueError):
            return LoadedLimitProfileResolution(
                None,
                "unavailable",
                "The legacy warning limit is invalid.",
            )

    return LoadedLimitProfileResolution(
        None,
        "unavailable",
        "The saved switch model and limit criteria could not be determined.",
    )


class LimitProfileCollection(dict):
    """Mapping of all four profiles with legacy model-only lookup support."""

    def __getitem__(self, key):
        if isinstance(key, tuple):
            key = profile_key(*key)
        elif key in SUPPORTED_SWITCH_MODELS:
            key = profile_key(key, "SM")
        return super().__getitem__(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        if isinstance(key, tuple):
            key = profile_key(*key)
        elif key in SUPPORTED_SWITCH_MODELS:
            key = profile_key(key, "SM")
        return super().__contains__(key)

    def for_model_mode(self, model, wavelength_mode):
        return self[profile_key(model, wavelength_mode)]


def default_limit_profiles() -> LimitProfileCollection:
    """Return independent SM/MM profiles with the shipped criteria."""
    profiles = LimitProfileCollection()
    for model, too_good, warning_enabled, warning, fail in (
        ("OSX-100", 0.2, False, None, 0.8),
        ("OSX-150", 0.5, True, 2.25, 2.5),
    ):
        for mode in SUPPORTED_WAVELENGTH_MODES:
            profiles[profile_key(model, mode)] = LimitProfile(
                model,
                "%s %s standard" % (model, mode),
                "1",
                too_good,
                warning_enabled,
                warning,
                fail,
                mode,
            ).validate()
    return profiles


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
        "SM",
    )


__all__ = [
    "SUPPORTED_SWITCH_MODELS",
    "SUPPORTED_WAVELENGTH_MODES",
    "LimitProfileCollection",
    "LimitAssessment",
    "LimitProfile",
    "LoadedLimitProfileResolution",
    "default_limit_profiles",
    "legacy_limit_profile",
    "normalize_switch_model",
    "normalize_wavelength_mode",
    "profile_key",
    "resolve_loaded_run_profile",
]
