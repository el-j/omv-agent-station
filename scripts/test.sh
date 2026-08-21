#!/usr/bin/env bash
# Run full unit and integration test suite (works with pytest or built-in unittest)
set -e

echo "🧪 Running unit tests..."
if python3 -c "import pytest" 2>/dev/null; then
    python3 -m pytest tests/ -v
else
    python3 -m unittest discover -s tests -p "test_*.py" -v
fi

echo "✅ All tests passed!"
