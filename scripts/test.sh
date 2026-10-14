#!/usr/bin/env bash
# Run full unit, black-box, and mutation test suite
set -e

# Minimum total line coverage, enforced in CI. Raise it (never lower it) when
# real coverage moves up -- see "Coverage gate" in CONTRIBUTING.md.
COVERAGE_MIN="${COVERAGE_MIN:-75}"

echo "🧪 Running unit, black-box, and mutation tests..."
if python3 -c "import pytest" 2>/dev/null; then
    if python3 -c "import pytest_cov" 2>/dev/null; then
        python3 -m pytest tests/ -v --cov --cov-report=term-missing --cov-fail-under="$COVERAGE_MIN"
    else
        echo "⚠️  pytest-cov is not installed -- running without the coverage gate."
        echo "   Install it with: pip install pytest-cov"
        python3 -m pytest tests/ -v
    fi
else
    python3 -m unittest discover -s tests -p "test_*.py" -v
fi

echo "✅ All tests (unit + black-box + mutation) passed!"
