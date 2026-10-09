from pathlib import Path

import pytest

from fraud.config import load_config

VALID = """
data:
  raw_csv: data/raw/Base.csv
  parquet: data/processed/base.parquet
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return path


def test_repo_config_loads():
    cfg = load_config(Path("configs/config.yaml"))
    assert cfg.data.parquet.suffix == ".parquet"


def test_valid_config(tmp_path):
    cfg = load_config(write(tmp_path, VALID))
    assert cfg.data.raw_csv == Path("data/raw/Base.csv")
    assert cfg.data.parquet == Path("data/processed/base.parquet")


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_config(tmp_path / "nope.yaml")


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("", "'<root>' must be a mapping"),
        ("- a\n- b\n", "'<root>' must be a mapping"),
        ("other: 1\n", "missing keys: \\['data'\\]"),
        (VALID + "extra: 1\n", "unknown keys: \\['extra'\\]"),
        ("data: [1, 2]\n", "'data' must be a mapping"),
        ("data:\n  raw_csv: a.csv\n", "missing keys: \\['parquet'\\]"),
        ("data:\n  raw_csv: a.csv\n  parquet: b.parquet\n  parqet: c\n", "unknown keys"),
        ("data:\n  raw_csv: 3\n  parquet: b.parquet\n", "'data.raw_csv' must be a non-empty"),
        ("data:\n  raw_csv: ''\n  parquet: b.parquet\n", "'data.raw_csv' must be a non-empty"),
    ],
)
def test_invalid_config(tmp_path, text, error):
    with pytest.raises(ValueError, match=error):
        load_config(write(tmp_path, text))
