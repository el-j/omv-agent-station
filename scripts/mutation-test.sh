#!/usr/bin/env bash
# Execute Mutation Fault Injection Suite
set -e

echo "🧬 Running Mutation Testing & Fault Injection Suite..."
if python3 -c "import pytest" 2>/dev/null; then
    python3 -m pytest tests/test_mutation.py -v
else
    python3 -m unittest discover -s tests -p "test_mutation.py" -v
fi

echo "✅ 100% of injected mutants were detected and killed!"
