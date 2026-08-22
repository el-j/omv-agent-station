#!/usr/bin/env bash
# ==============================================================================
# OpenMediaVault AI Orchestrator Plugin & Stack Automated Installer
# Repository: https://github.com/el-j/omv-agent-station
# ==============================================================================
set -e

echo "=========================================================="
echo "🚀 OpenMediaVault AI Orchestrator Plugin Installer"
echo "=========================================================="

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Error: Please run this installer as root (e.g. sudo bash install-plugin.sh)"
    exit 1
fi

echo "📦 Ensuring essential prerequisites (git, python3, wget, tmux)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || true
apt-get install -y -qq git python3 python3-yaml wget curl tmux || true

# Try installing docker and compose if not present
if ! command -v docker >/dev/null 2>&1; then
    echo "📦 Installing Docker engine..."
    apt-get install -y -qq docker.io || true
fi

if ! command -v docker-compose >/dev/null 2>&1 && ! docker compose version >/dev/null 2>&1; then
    echo "📦 Installing Docker Compose..."
    apt-get install -y -qq docker-compose-plugin || apt-get install -y -qq docker-compose-v2 || apt-get install -y -qq docker-compose || true
fi

INSTALL_DIR="/srv/dev-data/omv-agent-station"
mkdir -p "$INSTALL_DIR"

if [ ! -d "$INSTALL_DIR/.git" ]; then
    echo "📥 Cloning omv-agent-station repository to $INSTALL_DIR..."
    git clone https://github.com/el-j/omv-agent-station.git "$INSTALL_DIR"
else
    echo "🔄 Updating existing installation in $INSTALL_DIR..."
    git -C "$INSTALL_DIR" pull --rebase || true
fi

cd "$INSTALL_DIR"

echo "🔨 Building native Debian package..."
bash build-deb.sh

# Remove legacy/duplicate datamodel files before package update
rm -f /usr/share/openmediavault/datamodels/rpc.aiorchestrator.json 2>/dev/null || true

echo "📦 Installing .deb package via apt / dpkg..."
if ! apt-get install -y --reinstall ./openmediavault-ai-orchestrator_1.0.0_all.deb; then
    echo "⚠️ Apt direct install encountered a dependency preference issue; applying with dpkg + fix-broken..."
    dpkg -i --force-depends ./openmediavault-ai-orchestrator_1.0.0_all.deb || true
    apt-get install -f -y || true
fi

if command -v systemctl >/dev/null 2>&1; then
    echo "🔄 Reloading OpenMediaVault Engined daemon..."
    systemctl restart omv-engined 2>/dev/null || true
fi

if command -v omv-salt >/dev/null 2>&1; then
    echo "🔄 Refreshing OpenMediaVault Workbench cache & Salt state..."
    omv-salt deploy run workbench 2>/dev/null || true
fi

echo "=========================================================="
echo "✅ AI Orchestrator Plugin successfully installed on your OMV Server!"
echo "👉 1. Open your OMV WebGUI in your browser"
echo "👉 2. Navigate to: Services ➔ AI Orchestrator"
echo "👉 3. Enter your subscription tokens and click Apply"
echo "=========================================================="
