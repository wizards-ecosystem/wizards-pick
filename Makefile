.DEFAULT_GOAL := help
PYTHON ?= python3

.PHONY: help install dev run check lint format typecheck test build release-check clean model-serve model-build tools

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install the app into the active environment
	$(PYTHON) -m pip install -e .

dev: ## Install the app plus dev tooling (pytest, ruff, mypy)
	$(PYTHON) -m pip install -e ".[dev]"

run: ## Launch the terminal assistant
	wizards-pick

check: lint format-check typecheck test ## Run every quality gate

lint: ## Lint with ruff
	ruff check .

format: ## Auto-format with ruff
	ruff format .

format-check: ## Verify formatting without writing changes
	ruff format --check .

typecheck: ## Type-check with mypy
	mypy

test: ## Run the test suite
	pytest

build: ## Build the source and wheel distributions
	rm -rf build dist
	$(PYTHON) -m build

release-check: check build ## Run quality gates and validate distributions
	$(PYTHON) -m twine check dist/*

model-serve: ## Start the project-local Ollama server (loopback)
	scripts/ollama-local.sh serve

model-build: ## Fetch the GGUF and build the local `deephat` model
	scripts/ollama-local.sh build

clean: ## Remove caches and build artifacts (keeps .wizards-pick data)
	rm -rf build dist ./*.egg-info src/*.egg-info \
		.pytest_cache .ruff_cache .mypy_cache
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +
