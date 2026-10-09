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
class SplitConfig:
    train_months: tuple[int, ...]
    valid_months: tuple[int, ...]
    test_months: tuple[int, ...]

    def __post_init__(self) -> None:
        # Strict order (train < valid < test) also rules out overlapping months.
        parts = [self.train_months, self.valid_months, self.test_months]
        if not all(parts):
            raise ValueError("Split month lists must all be non-empty")
        if not (max(parts[0]) < min(parts[1]) and max(parts[1]) < min(parts[2])):
            raise ValueError(
                f"Split months must be in time order train < valid < test, got {parts}"
            )


@dataclass(frozen=True)
class EvaluationConfig:
    target_fpr: float
    cost_false_negative: float
    cost_false_positive: float

    def __post_init__(self) -> None:
        if not 0 < self.target_fpr < 1:
            raise ValueError(f"target_fpr must be in (0, 1), got {self.target_fpr}")
        if self.cost_false_negative <= 0 or self.cost_false_positive <= 0:
            raise ValueError("Costs must be > 0")


@dataclass(frozen=True)
class Config:
    data: DataConfig
    split: SplitConfig
    evaluation: EvaluationConfig


def _mapping(value: Any, name: str, keys: set[str]) -> dict[str, Any]:
    """Check that `value` is a mapping with exactly `keys`, so typos fail at load time."""
    if not isinstance(value, dict):
        raise ValueError(f"Config '{name}' must be a mapping, got {type(value).__name__}")
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


def _int_list(value: Any, name: str) -> tuple[int, ...]:
    # bool is a subclass of int in Python; reject it explicitly.
    if not isinstance(value, list) or not all(
        isinstance(v, int) and not isinstance(v, bool) for v in value
    ):
        raise ValueError(f"Config '{name}' must be a list of integers, got {value!r}")
    return tuple(value)


def _number(value: Any, name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"Config '{name}' must be a number, got {value!r}")
    return float(value)


def load_config(path: Path) -> Config:
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    raw = _mapping(yaml.safe_load(path.read_text()), "<root>", {"data", "split", "evaluation"})
    data = _mapping(raw["data"], "data", {"raw_csv", "parquet"})
    split = _mapping(raw["split"], "split", {"train_months", "valid_months", "test_months"})
    evaluation = _mapping(
        raw["evaluation"],
        "evaluation",
        {"target_fpr", "cost_false_negative", "cost_false_positive"},
    )
    return Config(
        data=DataConfig(
            raw_csv=_path(data["raw_csv"], "data.raw_csv"),
            parquet=_path(data["parquet"], "data.parquet"),
        ),
        split=SplitConfig(**{k: _int_list(v, f"split.{k}") for k, v in split.items()}),
        evaluation=EvaluationConfig(
            **{k: _number(v, f"evaluation.{k}") for k, v in evaluation.items()}
        ),
    )
