.PHONY: bootstrap format lint typecheck test test-js check

PYTHON ?= python3

bootstrap:
	$(PYTHON) -m pip install -e ".[dev]"
	npm install --ignore-scripts

format:
	$(PYTHON) -m ruff format src tests
	$(PYTHON) -m ruff check --fix src tests

lint:
	$(PYTHON) -m ruff format --check src tests
	$(PYTHON) -m ruff check src tests

typecheck:
	$(PYTHON) -m mypy src tests

test:
	$(PYTHON) -m pytest

test-js:
	npm test

check: lint typecheck test test-js
