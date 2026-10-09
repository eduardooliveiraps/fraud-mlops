from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.fixture
def config_dict() -> dict[str, Any]:
    """A fresh, editable copy of the shipped config."""
    return yaml.safe_load(Path("configs/config.yaml").read_text())


@pytest.fixture
def write_config(tmp_path: Path) -> Callable[[dict[str, Any] | str], Path]:
    def write(cfg: dict[str, Any] | str) -> Path:
        path = tmp_path / "config.yaml"
        path.write_text(cfg if isinstance(cfg, str) else yaml.safe_dump(cfg))
        return path

    return write
