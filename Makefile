.PHONY: all test lint security deb blackbox mutation clean help

all: lint test blackbox mutation security deb

help:
	@echo "OpenMediaVault Agent Station Development Commands:"
	@echo "  make test      - Run all unit, black-box, and mutation tests"
	@echo "  make blackbox  - Run isolated black-box security & packaging tests"
	@echo "  make mutation  - Run AST semantic mutation & fault injection tests"
	@echo "  make lint      - Lint Python and YAML configurations"
	@echo "  make security  - Scan codebase for security issues & secret leaks"
	@echo "  make deb       - Build openmediavault-agent-station .deb package"
	@echo "  make clean     - Clean temporary build artifacts and caches"

test:
	@bash scripts/test.sh

blackbox:
	@bash scripts/blackbox-test.sh

mutation:
	@bash scripts/mutation-test.sh

lint:
	@bash scripts/lint.sh

security:
	@bash scripts/security-check.sh

deb:
	@bash build-deb.sh

clean:
	@rm -rf build-pkg *.deb .pytest_cache __pycache__ */__pycache__
	@echo "🧹 Cleaned build artifacts."
