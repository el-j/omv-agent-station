#!/usr/bin/env bash
# Lint Python and YAML files across the repository
set -e

echo "🔍 Linting Python files..."
if command -v flake8 >/dev/null 2>&1; then
    flake8 telegram-agent-bot/ signal-agent-bot/ discord-agent-bot/ agent_station_core/ scripts/ tests/ --config=.flake8
else
    python3 -m py_compile telegram-agent-bot/bot.py signal-agent-bot/signal_bot.py discord-agent-bot/discord_bot.py tests/*.py
fi

echo "🔍 Type-checking Python files..."
if command -v mypy >/dev/null 2>&1; then
    # One invocation per bot: all three ship same-named `core`/`handlers`
    # packages (by design -- each runs as its own container), and mypy aborts
    # outright when two files map to one module name.
    mypy agent_station_core/ scripts/
    mypy telegram-agent-bot/
    mypy discord-agent-bot/
    mypy signal-agent-bot/
else
    echo "⚠️  mypy is not installed -- skipping type checks."
    echo "   Install it with: pip install mypy"
fi

echo "🔍 Validating YAML configurations..."
python3 -c "import yaml; yaml.safe_load(open('litellm/config.yaml')); yaml.safe_load(open('docker-compose.yml')); yaml.safe_load(open('omv-compose-template.yaml'))"

echo "✅ Lint checks completed successfully!"
