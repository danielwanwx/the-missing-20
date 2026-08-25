.PHONY: bootstrap format lint typecheck test test-js check aws-smoke

PYTHON ?= .venv/bin/python
UV ?= uv
AWS_CONFIRM ?= 0

bootstrap:
	$(UV) sync --frozen --extra dev
	npm ci --ignore-scripts

format:
	$(PYTHON) -m ruff format src tests scripts
	$(PYTHON) -m ruff check --fix src tests scripts

lint:
	$(PYTHON) -m ruff format --check src tests scripts
	$(PYTHON) -m ruff check src tests scripts

typecheck:
	$(PYTHON) -m mypy src tests scripts

test:
	$(PYTHON) -m pytest

test-js:
	npm test

check: lint typecheck test test-js

aws-smoke:
	PYTHONPATH=src $(PYTHON) scripts/aws_preflight.py --confirm $(AWS_CONFIRM)
