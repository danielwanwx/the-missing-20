.PHONY: bootstrap format lint typecheck test test-js check demo golden aws-smoke

PYTHON ?= .venv/bin/python
UV ?= uv
AWS_CONFIRM ?= 0

-include .env
export MISSING20_ENVIRONMENT
export MISSING20_AWS_REGION
export MISSING20_AWS_PROFILE
export MISSING20_EXPECTED_AWS_ACCOUNT_ID
export MISSING20_RESOURCE_PREFIX
export MISSING20_CLEANUP_MANIFEST
export MISSING20_MAX_AWS_SPEND_USD
export MISSING20_ALLOW_AWS_MUTATIONS

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

demo:
	PYTHONPATH=src $(PYTHON) scripts/run_demo.py

golden:
	PYTHONPATH=src $(PYTHON) scripts/run_golden.py

aws-smoke:
	PYTHONPATH=src $(PYTHON) scripts/aws_preflight.py --confirm $(AWS_CONFIRM)
