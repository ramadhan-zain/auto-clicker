.DEFAULT_GOAL := help
.PHONY: help install run test lint format check build spike-check spike-basic spike-timing spike-soak clean

SPIKE := uv run python scripts/spike_input.py

help: ## List available commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'

install: ## Install Python and dependencies
	uv sync

run: ## Open the app window
	uv run python -m autoclick

test: ## Run tests (no real input is sent)
	uv run pytest

lint: ## Check lint and formatting
	uv run ruff check .
	uv run ruff format --check .

format: ## Fix lint issues and reformat
	uv run ruff check --fix .
	uv run ruff format .

check: lint test ## Lint, then test

build: ## Build dist/AutoClick.app (ad-hoc signed) and dist/AutoClick-macos-arm64.zip
	rm -rf build dist
	uv run pyinstaller --noconfirm AutoClick.spec
	codesign --verify --deep --strict dist/AutoClick.app
	ditto -c -k --keepParent dist/AutoClick.app dist/AutoClick-macos-arm64.zip

spike-check: ## Show Accessibility permission and focus state
	$(SPIKE) check

spike-basic: ## Send one click and one Space tap to Roblox
	$(SPIKE) basic

spike-timing: ## Send click bursts at 100/50/20/10 ms to Roblox
	$(SPIKE) timing

spike-soak: ## 25 minute anti-AFK run, keeps the display awake
	caffeinate -d $(SPIKE) soak

clean: ## Remove caches and build output
	rm -rf .pytest_cache .ruff_cache build dist
	find . -name __pycache__ -type d -not -path './.venv/*' -prune -exec rm -rf {} +
