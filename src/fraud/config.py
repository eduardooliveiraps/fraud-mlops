"""Load the project config (YAML) into typed, immutable objects. Fails fast on bad config."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class DataConfig:
    raw_csv: Path
    parquet: Path


@dataclass(frozen=True)
class Config:
    data: DataConfig


def _mapping(value: Any, name: str, keys: set[str]) -> dict[str, Any]:
    """Check that `value` is a mapping with exactly `keys`, so typos fail at load time."""
    if not isinstance(value, dict):  # bad file content, not a caller bug: ValueError, not TypeError
        raise ValueError(f"Config '{name}' must be a mapping, got {type(value).__name__}")  # noqa: TRY004
    missing, unknown = keys - value.keys(), value.keys() - keys
    if missing:
        raise ValueError(f"Config '{name}' is missing keys: {sorted(missing)}")
    if unknown:
        raise ValueError(f"Config '{name}' has unknown keys: {sorted(unknown)}")
    return value


def _path(value: Any, name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Config '{name}' must be a non-empty path string, got {value!r}")
    return Path(value)


def load_config(path: Path) -> Config:
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    raw = _mapping(yaml.safe_load(path.read_text()), "<root>", {"data"})
    data = _mapping(raw["data"], "data", {"raw_csv", "parquet"})
    return Config(
        data=DataConfig(
            raw_csv=_path(data["raw_csv"], "data.raw_csv"),
            parquet=_path(data["parquet"], "data.parquet"),
        )
    )
