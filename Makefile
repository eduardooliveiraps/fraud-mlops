PY := python3.11

install:
	$(PY) -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -e ".[dev]"
lint:
	.venv/bin/ruff check src tests
test:
	.venv/bin/pytest -q
