"""Read and check settings.toml (the file in the repository root)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "settings.toml"
_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class SettingsError(Exception):
    """settings.toml is missing or not correct. The message tells the user what to fix."""


@dataclass(frozen=True)
class Settings:
    activity_types: tuple[str, ...]
    detail_activity_types: tuple[str, ...]


def _read_key_list(data: dict, name: str) -> tuple[str, ...]:
    value = data.get(name)
    if value is None:
        raise SettingsError(f"settings.toml: '{name}' is missing")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SettingsError(f"settings.toml: '{name}' must be a list of text values")
    for item in value:
        if not _KEY_PATTERN.match(item):
            raise SettingsError(
                f"settings.toml: '{name}' has a key that is not correct. "
                "Use only lowercase letters, digits and '_'"
            )
    if len(set(value)) != len(value):
        raise SettingsError(f"settings.toml: '{name}' has the same key two times")
    return tuple(value)


def load(path: Path | None = None) -> Settings:
    path = SETTINGS_FILE if path is None else path
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        raise SettingsError("settings.toml is missing from the repository root") from None
    except tomllib.TOMLDecodeError:
        raise SettingsError("settings.toml has a syntax error. Compare it with the example in the README") from None

    activity_types = _read_key_list(data, "activity_types")
    detail_activity_types = _read_key_list(data, "detail_activity_types")
    not_in_activity_types = [t for t in detail_activity_types if t not in activity_types]
    if not_in_activity_types:
        raise SettingsError(
            "settings.toml: each key in 'detail_activity_types' must also be in 'activity_types'"
        )
    return Settings(activity_types=activity_types, detail_activity_types=detail_activity_types)
