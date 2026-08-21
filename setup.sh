#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "🚀 Initializing OMV AI Orchestrator Stack on ProLiant Gen8"
echo "=========================================================="

DATA_DIR=${DATA_DIR:-/srv/dev-data}

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
echo "• LiteLLM AI Proxy:    http://<OMV-IP>:4000 (Health: /health)"
echo "• Syncthing GUI:       http://<OMV-IP>:8384"
echo "• Web Terminal (ttyd): http://<OMV-IP>:7681"
echo "• Telegram Bot:        Listening for commands..."
echo "----------------------------------------------------------"
