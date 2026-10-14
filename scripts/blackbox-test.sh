#!/usr/bin/env bash
# Execute Black-Box Testing Suite
set -e

echo "📦 Running Black-Box Security, CLI & Packaging Verification..."
# test_security_unit.py holds the security/sanitization checks this target used
# to cover before issue #60 split them out of test_blackbox.py by what they
# really are; both are run here so the target's coverage is unchanged.
if python3 -c "import pytest" 2>/dev/null; then
    python3 -m pytest tests/test_blackbox.py tests/test_security_unit.py -v
else
    python3 -m unittest discover -s tests -p "test_blackbox.py" -v
    python3 -m unittest discover -s tests -p "test_security_unit.py" -v
fi

echo "✅ All Black-Box integrity checks passed!"
