#!/usr/bin/env bash
# Execute Black-Box Testing Suite
set -e

echo "📦 Running Black-Box Security, CLI & Packaging Verification..."
if python3 -c "import pytest" 2>/dev/null; then
    python3 -m pytest tests/test_blackbox.py -v
else
    python3 -m unittest discover -s tests -p "test_blackbox.py" -v
fi

echo "✅ All Black-Box integrity checks passed!"
