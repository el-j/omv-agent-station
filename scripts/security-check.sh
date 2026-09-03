#!/usr/bin/env bash
# Static Security Analysis & Secret Leak Check
set -e

echo "🛡️ Running security and secret leak scan..."

# 1. Check for accidental committed secrets in git tracked files
FORBIDDEN_PATTERNS=("AIzaSy[A-Za-z0-9_\\-]{33}" "sk-ant-api03-[A-Za-z0-9_\\-]{40,}" "ghp_[A-Za-z0-9]{36}")
LEAK_FOUND=0

for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
    if git grep -E "$pattern" -- ':(exclude)env.example' ':(exclude)README.md' ':(exclude)OMV_AI_SERVER_HANDBOOK.md' ':(exclude)scripts/security-check.sh' >/dev/null 2>&1; then
        echo "🚨 ERROR: Potential leaked secret detected matching pattern: $pattern"
        git grep -E "$pattern" -- ':(exclude)env.example' ':(exclude)README.md' ':(exclude)OMV_AI_SERVER_HANDBOOK.md'
        LEAK_FOUND=1
    fi
done

if [ "$LEAK_FOUND" -eq 1 ]; then
    echo "❌ Security check failed: Real API keys must not be committed!"
    exit 1
fi

# 2. Run Bandit AST security scan if available
if command -v bandit >/dev/null 2>&1; then
    echo "🛡️ Running Bandit Python vulnerability scanner..."
    bandit -c pyproject.toml -r telegram-agent-bot/ signal-agent-bot/ discord-agent-bot/ agent_station_core/ scripts/ -ll -q
fi

echo "✅ Security checks passed! No vulnerabilities or exposed secrets found."
