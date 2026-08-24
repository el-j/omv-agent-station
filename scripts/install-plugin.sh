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

# Ensure required OMV system directories exist before running apt
mkdir -p /var/cache/openmediavault/archives 2>/dev/null || true

echo "📦 Ensuring essential prerequisites (git, python3, wget, tmux)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || true
apt-get install -y -qq git python3 python3-yaml wget curl tmux || true

# Try installing docker and compose if not present
if ! command -v docker >/dev/null 2>&1; then
    echo "📦 Installing Docker engine and CLI..."
    apt-get update -qq && apt-get install -y -qq docker.io docker-cli || apt-get install -y -qq docker.io || true
fi

if ! command -v docker-compose >/dev/null 2>&1 && ! docker compose version >/dev/null 2>&1; then
    echo "📦 Installing Docker Compose..."
    apt-get install -y -qq docker-compose-plugin || apt-get install -y -qq docker-compose || true
fi

BRANCH="${BRANCH:-develop}"
INSTALL_DIR="/srv/dev-data/omv-agent-station"
mkdir -p "$INSTALL_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
    echo "🔄 Resetting and fetching latest clean code ($BRANCH) in $INSTALL_DIR..."
    git -C "$INSTALL_DIR" fetch origin "$BRANCH" 2>/dev/null || git -C "$INSTALL_DIR" fetch origin main || true
    git -C "$INSTALL_DIR" checkout -B "$BRANCH" "origin/$BRANCH" 2>/dev/null || git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH" 2>/dev/null || git -C "$INSTALL_DIR" reset --hard origin/main || true
    git -C "$INSTALL_DIR" clean -fdx || true
else
    echo "📥 Cloning omv-agent-station repository ($BRANCH) to $INSTALL_DIR..."
    git clone -b "$BRANCH" https://github.com/el-j/omv-agent-station.git "$INSTALL_DIR" 2>/dev/null || git clone https://github.com/el-j/omv-agent-station.git "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

echo "🔨 Building native Debian package..."
bash build-deb.sh

# Full cleanup of any previous broken install artifacts from all workbench dirs
rm -f /usr/share/openmediavault/datamodels/*aiorchestrator*.json* \
      /usr/share/openmediavault/datamodels/*ai_orchestrator*.json* \
      /usr/share/openmediavault/datamodels/*agentstation*.json* 2>/dev/null || true
rm -f /usr/share/openmediavault/workbench/navigation.d/*agentstation* \
      /usr/share/openmediavault/workbench/navigation.d/*aiorchestrator* 2>/dev/null || true
rm -f /usr/share/openmediavault/workbench/route.d/*agentstation* \
      /usr/share/openmediavault/workbench/route.d/*aiorchestrator* 2>/dev/null || true
rm -f /usr/share/openmediavault/workbench/dashboard.d/*agentstation* \
      /usr/share/openmediavault/workbench/dashboard.d/*aiorchestrator* 2>/dev/null || true
rm -f /usr/share/openmediavault/workbench/component.d/*agentstation* \
      /usr/share/openmediavault/workbench/component.d/*aiorchestrator* 2>/dev/null || true
mkdir -p /var/cache/openmediavault/archives 2>/dev/null || true
find /var/cache/openmediavault/ -maxdepth 1 -name "cache.*" -delete 2>/dev/null || true

# Backup existing user configuration to persistent storage before upgrade
mkdir -p /srv/dev-data/config 2>/dev/null || true
if [ -s "/etc/openmediavault-agent-station.json" ]; then
    cp -f "/etc/openmediavault-agent-station.json" "/srv/dev-data/config/agent-station.json" 2>/dev/null || true
elif [ -s "/etc/openmediavault-ai-orchestrator.json" ]; then
    cp -f "/etc/openmediavault-ai-orchestrator.json" "/srv/dev-data/config/agent-station.json" 2>/dev/null || true
fi

echo "📦 Installing .deb package via apt / dpkg..."
DEB_PKG=$(ls -1 openmediavault-agent-station_*.deb openmediavault-ai-orchestrator_*.deb 2>/dev/null | head -n1)
if ! apt-get install -y --reinstall "./$DEB_PKG"; then
    echo "⚠️ Apt direct install encountered a dependency preference issue; applying with dpkg + fix-broken..."
    dpkg -i --force-depends "./$DEB_PKG" || true
    apt-get install -f -y || true
fi

# Restore configuration from persistent storage if needed
if [ ! -s "/etc/openmediavault-agent-station.json" ] && [ -s "/srv/dev-data/config/agent-station.json" ]; then
    cp -f "/srv/dev-data/config/agent-station.json" "/etc/openmediavault-agent-station.json" 2>/dev/null || true
    chmod 600 "/etc/openmediavault-agent-station.json" 2>/dev/null || true
fi

# Regenerate .env from restored config
if command -v omv-agent-station >/dev/null 2>&1; then
    omv-agent-station write-env 2>/dev/null || true
fi

# Process any pending dpkg triggers (compiles workbench and restarts engined cleanly)
dpkg --configure --pending 2>/dev/null || true

# If omv-mkworkbench is available, ensure all compiled assets are generated
if command -v omv-mkworkbench >/dev/null 2>&1; then
    echo "🔨 Compiling OpenMediaVault Workbench routes & widgets..."
    omv-mkworkbench all || true
fi

# Clear any cached schema files without disrupting active background processes
mkdir -p /var/cache/openmediavault/archives 2>/dev/null || true
find /var/cache/openmediavault/ -maxdepth 1 -name "cache.*" -delete 2>/dev/null || true

echo "=========================================================="
echo "✅ Agent Station Plugin successfully installed on your OMV Server!"
echo "👉 1. Refresh your OMV WebGUI browser tab (Cmd+R / F5)"
echo "👉 2. Open 'Agent Station' in the root sidebar menu"
echo "👉 3. Configure your AI models, git sync, and messenger bots"
echo "=========================================================="
