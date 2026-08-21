#!/usr/bin/env bash
# Lint Python and YAML files across the repository
set -e

echo "🔍 Linting Python files..."
if command -v flake8 >/dev/null 2>&1; then
    flake8 telegram-agent-bot/ signal-agent-bot/ discord-agent-bot/ tests/ --max-line-length=160 --ignore=E501,W503
else
    python3 -m py_compile telegram-agent-bot/bot.py signal-agent-bot/signal_bot.py discord-agent-bot/discord_bot.py tests/*.py
fi

echo "🔍 Validating YAML configurations..."
python3 -c "import yaml; yaml.safe_load(open('litellm/config.yaml')); yaml.safe_load(open('docker-compose.yml')); yaml.safe_load(open('omv-compose-template.yaml'))"

echo "✅ Lint checks completed successfully!"
