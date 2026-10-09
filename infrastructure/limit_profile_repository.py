"""INI persistence for administrator-controlled limit profiles."""

import configparser
import os
import tempfile
from pathlib import Path

from config.app_config import default_limit_profile_path
from domain.limit_profiles import (
    LimitProfile,
    LimitProfileCollection,
    SUPPORTED_SWITCH_MODELS,
    SUPPORTED_WAVELENGTH_MODES,
    default_limit_profiles,
    profile_key,
)


class LimitProfileRepository:
    """Load and atomically save independent model/mode profiles.

    Older installations used one section per switch model.  Those sections
    are treated as SM settings and copied to MM only when an MM section is
    absent; the migration is therefore safe to repeat.
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_limit_profile_path()

    def load_profiles(self) -> LimitProfileCollection:
        defaults = default_limit_profiles()
        if not self.path.is_file():
            return defaults
        parser = configparser.ConfigParser()
        parser.read(self.path, encoding="utf-8")
        profiles = LimitProfileCollection()
        for model in SUPPORTED_SWITCH_MODELS:
            legacy_values = dict(parser[model]) if parser.has_section(model) else None
            sm_key = profile_key(model, "SM")
            for mode in SUPPORTED_WAVELENGTH_MODES:
                key = profile_key(model, mode)
                section_names = (key, key.replace("/", "."))
                section = next(
                    (name for name in section_names if parser.has_section(name)),
                    None,
                )
                if section is not None:
                    values = dict(parser[section])
                elif mode == "SM" and legacy_values is not None:
                    values = dict(legacy_values)
                elif mode == "MM" and sm_key in profiles:
                    # Copy the migrated SM values once; this is not a live
                    # alias, so later administrator edits remain independent.
                    profiles[key] = LimitProfile(
                        **{
                            **profiles[sm_key].as_dict(),
                            "wavelength_mode": "MM",
                        }
                    ).validate()
                    continue
                else:
                    values = defaults[key].as_dict()
                values["model"] = model
                values["wavelength_mode"] = mode
                profiles[key] = LimitProfile.from_mapping(values)
        return profiles

    def save_profiles(self, profiles: dict[str, LimitProfile]):
        validated = LimitProfileCollection()
        for model, profile in profiles.items():
            if model in SUPPORTED_SWITCH_MODELS:
                model = profile_key(model, getattr(profile, "wavelength_mode", "SM"))
            validated[model] = profile.validate()
        defaults = default_limit_profiles()
        for model in SUPPORTED_SWITCH_MODELS:
            sm_key = profile_key(model, "SM")
            if sm_key not in validated:
                # Accept old callers that only provide model-keyed profiles.
                legacy = profiles.get(model)
                if legacy is not None:
                    validated[sm_key] = legacy.validate()
            if sm_key not in validated:
                validated[sm_key] = defaults[sm_key]
            mm_key = profile_key(model, "MM")
            if mm_key not in validated:
                validated[mm_key] = LimitProfile(
                    **{**validated[sm_key].as_dict(), "wavelength_mode": "MM"}
                ).validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        parser = configparser.ConfigParser()
        for model in SUPPORTED_SWITCH_MODELS:
            for mode in SUPPORTED_WAVELENGTH_MODES:
                key = profile_key(model, mode)
                profile = validated[key]
                parser[key] = {
                    "model": profile.model,
                    "wavelength_mode": profile.wavelength_mode,
                    "profile_name": profile.profile_name,
                    "revision": profile.revision,
                    "too_good_below_db": str(profile.too_good_below_db),
                    "warning_enabled": str(profile.warning_enabled),
                    "warning_above_db": (
                        "" if profile.warning_above_db is None
                        else str(profile.warning_above_db)
                    ),
                    "fail_above_db": str(profile.fail_above_db),
                }
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.path.parent,
                prefix=self.path.name + ".", suffix=".tmp", delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                parser.write(stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()


__all__ = ["LimitProfileRepository"]
