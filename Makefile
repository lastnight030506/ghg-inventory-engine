# Makefile — the commands CI runs, runnable locally.
#
# `make check` is the single gate: lint, tests with the coverage floor, and a
# regeneration of the committed report so the docs cannot drift.
.PHONY: help install lint types test test-fast coverage run scenario check wheel clean

PY ?= python3

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install with dev dependencies
	$(PY) -m pip install -e ".[dev]"

lint:  ## Ruff
	ruff check src/ tests/

types:  ## mypy
	mypy src/ghg

test:  ## Full suite with the coverage floor
	pytest tests/ --cov=ghg --cov-report=term-missing --cov-fail-under=90

test-fast:  ## Suite without coverage, for the inner loop
	pytest tests/ -q

coverage:  ## Open the HTML coverage report
	pytest tests/ --cov=ghg --cov-report=html
	@echo "open htmlcov/index.html"

# `python -m` rather than the console script: it works from a checkout without an
# install, and still respects whatever interpreter PY points at.
run:  ## Full pipeline into out/
	$(PY) -m ghg inventory --out out

scenario:  ## Year-over-year comparison into out/
	$(PY) -m ghg scenario --out out

check: lint types test run scenario  ## What CI runs

wheel:  ## Build the distributable wheel
	$(PY) -m build --wheel

clean:  ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov dist build *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
