PY := python3.11

install:
	$(PY) -m venv .venv && .venv/bin/pip install -U pip
	.venv/bin/pip install -r requirements.lock && .venv/bin/pip install --no-deps -e .
# Re-resolve pyproject.toml ranges in a fresh venv and pin every package exactly.
lock:
	rm -rf .venv-lock && $(PY) -m venv .venv-lock && .venv-lock/bin/pip install -q -U pip
	.venv-lock/bin/pip install -q -e ".[dev]"
	.venv-lock/bin/pip freeze --exclude-editable > requirements.lock && rm -rf .venv-lock
lint:
	.venv/bin/ruff check src tests
test:
	.venv/bin/pytest -q
data:
	.venv/bin/python -m fraud.data --config configs/config.yaml

.PHONY: install lock lint test data
