#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "🚀 Initializing Agent Station Stack"
echo "=========================================================="

INSTALL_DEPS=0
for arg in "$@"; do
    case "$arg" in
        --install-deps)
            INSTALL_DEPS=1
            ;;
    esac
done

DATA_DIR=${DATA_DIR:-/srv/dev-data}

# ------------------------------------------------------------------------------
# Docker + Compose plugin presence check.
# This stack runs on any Debian-based Linux (Debian, Ubuntu, Raspberry Pi OS) --
# not just OpenMediaVault, where these packages already come as .deb dependencies.
# ------------------------------------------------------------------------------
check_docker() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

if ! check_docker; then
    if [ "$INSTALL_DEPS" -eq 1 ]; then
        echo "📦 Docker/Compose plugin not found -- installing (--install-deps)..."
        if command -v apt-get >/dev/null 2>&1; then
            sudo apt-get update -qq
            sudo apt-get install -y docker.io docker-compose-plugin
            echo "ℹ️  You may need to log out and back in (or run 'newgrp docker') for group membership to take effect."
        else
            echo "❌ --install-deps only supports apt-based systems (Debian/Ubuntu/Raspberry Pi OS). Please install Docker manually: https://docs.docker.com/engine/install/"
            exit 1
        fi
    else
        echo "❌ Docker and/or the 'docker compose' plugin were not found."
        echo "   Install them first, e.g. on Debian/Ubuntu/Raspberry Pi OS:"
        echo "     sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin"
        echo "   ...or re-run this script with --install-deps to do that automatically."
        exit 1
    fi
fi

if [ "$(uname -m)" = "aarch64" ] || [ "$(uname -m)" = "arm64" ]; then
    echo "ℹ️  Detected ARM64 (e.g. Raspberry Pi) -- all images support this natively, but the first 'docker compose build' may take a while. 4GB+ RAM is recommended."
fi

echo "📂 Creating storage directories at $DATA_DIR..."
mkdir -p "$DATA_DIR/obsidian"
mkdir -p "$DATA_DIR/workspace"
mkdir -p ./syncthing/config
mkdir -p ./credentials

if [ ! -f .env ]; then
    echo "⚠️ .env file not found. Copying from env.example..."
    cp env.example .env
    echo "❗ PLEASE EDIT .env AND FILL IN YOUR API KEYS & TELEGRAM TOKEN BEFORE STARTING!"
    exit 1
fi

echo "🐳 Building and starting Docker containers..."
docker compose build
docker compose up -d

echo ""
echo "✅ All services successfully launched!"
echo "----------------------------------------------------------"
echo "• LiteLLM AI Proxy:    http://<this-server-IP>:4000 (Health: /health)"
echo "• Syncthing GUI:       http://<this-server-IP>:8384"
echo "• Web Terminal (ttyd): http://<this-server-IP>:7681"
echo "• Telegram Bot:        Listening for commands..."
echo "----------------------------------------------------------"
