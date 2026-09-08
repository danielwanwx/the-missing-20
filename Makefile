.PHONY: bootstrap format lint typecheck test test-js check demo case-console case-console-judge case-console-live golden golden-v2 agent-preflight agent-smoke authority-b-preflight authority-b-proof aws-smoke workspace workspace-smoke m6-proof m7-audit capture-current-release judge-demo legacy-judge-demo

PYTHON ?= .venv/bin/python
UV ?= uv
AWS_CONFIRM ?= 0
CASE_CONSOLE_RUNTIME ?= .missing20-runtime
CASE_CONSOLE_HOST ?= 127.0.0.1
CASE_CONSOLE_PORT ?= 8765

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
	# Keep the strict static gate on the typed decision and safety core. Dynamic
	# SaaS/provider boundaries are contract-tested through pytest and browser smoke.
	$(PYTHON) -m mypy src/the_missing_20/domain src/the_missing_20/application src/the_missing_20/ports src/the_missing_20/authority_b src/the_missing_20/config.py src/the_missing_20/experiment src/the_missing_20/evaluation

test:
	$(PYTHON) -m pytest

test-js:
	npm test

check: lint typecheck test test-js

demo:
	PYTHONPATH=src $(PYTHON) scripts/run_demo.py

case-console:
	PYTHONPATH=src $(PYTHON) scripts/decision_workspace_server.py --runtime-directory $(CASE_CONSOLE_RUNTIME) --host $(CASE_CONSOLE_HOST) --port $(CASE_CONSOLE_PORT)

case-console-judge: aws-smoke
	MISSING20_CASE_CONSOLE_SOURCE=live MISSING20_AGENT_PROVIDER=bedrock PYTHONPATH=src $(PYTHON) scripts/decision_workspace_server.py --runtime-directory $(CASE_CONSOLE_RUNTIME) --host $(CASE_CONSOLE_HOST) --port $(CASE_CONSOLE_PORT)

case-console-live:
	MISSING20_CASE_CONSOLE_SOURCE=live PYTHONPATH=src $(PYTHON) scripts/decision_workspace_server.py --runtime-directory $(CASE_CONSOLE_RUNTIME) --host $(CASE_CONSOLE_HOST) --port $(CASE_CONSOLE_PORT)

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

capture-current-release:
	PYTHONPATH=src $(PYTHON) scripts/capture_current_release.py

judge-demo:
	PYTHONPATH=src $(PYTHON) scripts/verify_current_release.py

legacy-judge-demo:
	PYTHONPATH=src $(PYTHON) scripts/run_judge_demo.py --check
