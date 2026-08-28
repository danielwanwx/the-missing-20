.PHONY: bootstrap format lint typecheck test test-js check demo golden golden-v2 agent-preflight agent-smoke authority-b-preflight authority-b-proof aws-smoke workspace workspace-smoke m6-proof m7-audit judge-demo

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

agent-preflight:
	PYTHONPATH=src BEDROCK_CONFIRM=$(BEDROCK_CONFIRM) MISSING20_AGENT_PROVIDER=$(MISSING20_AGENT_PROVIDER) $(PYTHON) scripts/run_agent_preflight.py

agent-smoke:
	PYTHONPATH=src BEDROCK_CONFIRM=$(BEDROCK_CONFIRM) MISSING20_AGENT_PROVIDER=$(MISSING20_AGENT_PROVIDER) $(PYTHON) scripts/run_agent_smoke.py

authority-b-preflight:
	PYTHONPATH=src BEDROCK_CONFIRM=$(BEDROCK_CONFIRM) MISSING20_AGENT_PROVIDER=$(MISSING20_AGENT_PROVIDER) $(PYTHON) scripts/run_authority_b_preflight.py

authority-b-proof:
	PYTHONPATH=src BEDROCK_CONFIRM=$(BEDROCK_CONFIRM) MISSING20_AGENT_PROVIDER=$(MISSING20_AGENT_PROVIDER) $(PYTHON) scripts/run_authority_b_proof.py

golden-v2:
	PYTHONPATH=src $(PYTHON) scripts/run_golden_v2.py

workspace:
	PYTHONPATH=src $(PYTHON) scripts/build_decision_workspace.py

workspace-smoke: workspace
	PYTHONPATH=src $(PYTHON) scripts/run_decision_workspace_smoke.py

m6-proof:
	PYTHONPATH=src $(PYTHON) scripts/build_m6_aws_proof.py

m7-audit:
	PYTHONPATH=src $(PYTHON) scripts/audit_competition_package.py --check

judge-demo:
	PYTHONPATH=src $(PYTHON) scripts/run_judge_demo.py --check
