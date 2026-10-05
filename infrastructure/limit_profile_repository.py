"""INI persistence for administrator-controlled limit profiles."""

import configparser
import os
import tempfile
from pathlib import Path

from config.app_config import default_limit_profile_path
from domain.limit_profiles import LimitProfile, default_limit_profiles


class LimitProfileRepository:
    """Load and atomically save the two supported model profiles."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_limit_profile_path()

    def load_profiles(self) -> dict[str, LimitProfile]:
        defaults = default_limit_profiles()
        if not self.path.is_file():
            return defaults
        parser = configparser.ConfigParser()
        parser.read(self.path, encoding="utf-8")
        profiles = {}
        for model, default in defaults.items():
            values = dict(parser[model]) if parser.has_section(model) else default.as_dict()
            values["model"] = model
            profiles[model] = LimitProfile.from_mapping(values)
        return profiles

    def save_profiles(self, profiles: dict[str, LimitProfile]):
        validated = {}
        for model, profile in profiles.items():
            validated[model] = profile.validate()
        for model in default_limit_profiles():
            if model not in validated:
                raise ValueError("Both OSX-100 and OSX-150 profiles are required.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        parser = configparser.ConfigParser()
        for model in ("OSX-100", "OSX-150"):
            profile = validated[model]
            parser[model] = {
                "model": profile.model,
                "profile_name": profile.profile_name,
                "revision": profile.revision,
                "too_good_below_db": str(profile.too_good_below_db),
                "warning_enabled": str(profile.warning_enabled),
                "warning_above_db": "" if profile.warning_above_db is None else str(profile.warning_above_db),
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
