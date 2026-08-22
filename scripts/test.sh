#!/usr/bin/env bash
# Run full unit, black-box, and mutation test suite
set -e

echo "🧪 Running unit, black-box, and mutation tests..."
if python3 -c "import pytest" 2>/dev/null; then
    python3 -m pytest tests/ -v
else
    python3 -m unittest discover -s tests -p "test_*.py" -v
fi

echo "✅ All tests (unit + black-box + mutation) passed!"
