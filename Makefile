.PHONY: all test lint security deb clean help

all: lint test security deb

help:
	@echo "OpenMediaVault AI Orchestrator Development Commands:"
	@echo "  make test      - Run unit test suite with pytest"
	@echo "  make lint      - Lint Python and YAML configurations"
	@echo "  make security  - Scan codebase for security issues & secret leaks"
	@echo "  make deb       - Build openmediavault-ai-orchestrator .deb package"
	@echo "  make clean     - Clean temporary build artifacts and caches"

test:
	@bash scripts/test.sh

lint:
	@bash scripts/lint.sh

security:
	@bash scripts/security-check.sh

deb:
	@bash build-deb.sh

clean:
	@rm -rf build-pkg *.deb .pytest_cache __pycache__ */__pycache__
	@echo "🧹 Cleaned build artifacts."
