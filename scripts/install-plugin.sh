#!/usr/bin/env bash
# ==============================================================================
# OpenMediaVault Agent Station Plugin & Stack Automated Installer
# Repository: https://github.com/el-j/omv-agent-station
# ==============================================================================
set -e

echo "=========================================================="
echo "🚀 OpenMediaVault Agent Station Plugin Installer"
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

if [ -d "$INSTALL_DIR/.git" ]; then
    echo "🔄 Resetting and fetching latest clean code in $INSTALL_DIR..."
    git -C "$INSTALL_DIR" fetch origin main || true
    git -C "$INSTALL_DIR" reset --hard origin/main || true
    git -C "$INSTALL_DIR" clean -fdx || true
else
    echo "📥 Cloning omv-agent-station repository to $INSTALL_DIR..."
    git clone https://github.com/el-j/omv-agent-station.git "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

echo "🔨 Building native Debian package..."
bash build-deb.sh

# Remove legacy/duplicate datamodel files and clear OMV compiled cache
rm -f /usr/share/openmediavault/datamodels/*aiorchestrator*.json* \
      /usr/share/openmediavault/datamodels/*ai_orchestrator*.json* \
      /usr/share/openmediavault/datamodels/*agentstation*.json* 2>/dev/null || true
rm -rf /var/cache/openmediavault/* 2>/dev/null || true

echo "📦 Installing .deb package via apt / dpkg..."
DEB_PKG=$(ls -1 openmediavault-agent-station_*.deb openmediavault-ai-orchestrator_*.deb 2>/dev/null | head -n1)
if ! apt-get install -y --reinstall "./$DEB_PKG"; then
    echo "⚠️ Apt direct install encountered a dependency preference issue; applying with dpkg + fix-broken..."
    dpkg -i --force-depends "./$DEB_PKG" || true
    apt-get install -f -y || true
fi

# Clear cache again post-installation and reload all OMV daemons
rm -rf /var/cache/openmediavault/* 2>/dev/null || true

if command -v systemctl >/dev/null 2>&1; then
    echo "🔄 Reloading OpenMediaVault daemons (Engined, PHP-FPM, Nginx)..."
    systemctl restart omv-engined 2>/dev/null || true
    systemctl restart 'php*-fpm' 2>/dev/null || true
    systemctl restart nginx 2>/dev/null || true
fi

if command -v omv-salt >/dev/null 2>&1; then
    echo "🔄 Refreshing OpenMediaVault Workbench cache & Salt state..."
    omv-salt deploy run workbench 2>/dev/null || true
fi

echo "=========================================================="
echo "✅ Agent Station Plugin successfully installed on your OMV Server!"
echo "👉 1. Open your OMV WebGUI in your browser"
echo "👉 2. Navigate to: Services ➔ Agent Station"
echo "👉 3. Enter your subscription tokens and click Apply"
echo "=========================================================="
