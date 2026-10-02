PYTHON ?= .venv/bin/python
PIP ?= uv pip
RUFF ?= uv run ruff
PYTEST ?= $(PYTHON) -m pytest

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Create the virtualenv and install dev dependencies
	uv venv --python 3.12 .venv
	$(PIP) install -e ".[dev]"

.PHONY: format
format: ## Format code
	$(RUFF) format src tests
	$(RUFF) check --fix src tests

.PHONY: format-check
format-check: ## Verify formatting (CI)
	$(RUFF) format --check src tests
	$(RUFF) check src tests

.PHONY: lint
lint: ## Lint code (alias for format-check)
	@$(MAKE) --no-print-directory format-check

.PHONY: test
test: ## Run the test suite
	$(PYTEST)

.PHONY: schema
schema: ## Validate the bundled JSON Schemas and the example Codex
	$(PYTEST) tests/test_schemas.py -q

.PHONY: demo
demo: ## Run the full end-to-end workflow in a temporary Codex
	$(PYTHON) scripts/demo.py

.PHONY: ci
ci: format-check test schema ## Everything CI runs

.PHONY: clean
clean: ## Remove build and cache artifacts
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info src/*.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
