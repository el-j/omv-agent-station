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
    echo "📦 Installing Docker engine..."
    apt-get install -y -qq docker.io || true
fi

if ! command -v docker-compose >/dev/null 2>&1 && ! docker compose version >/dev/null 2>&1; then
    echo "📦 Installing Docker Compose..."
    apt-get install -y -qq docker-compose-plugin || apt-get install -y -qq docker-compose-v2 || apt-get install -y -qq docker-compose || true
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

echo "📦 Installing .deb package via apt / dpkg..."
DEB_PKG=$(ls -1 openmediavault-agent-station_*.deb openmediavault-ai-orchestrator_*.deb 2>/dev/null | head -n1)
if ! apt-get install -y --reinstall "./$DEB_PKG"; then
    echo "⚠️ Apt direct install encountered a dependency preference issue; applying with dpkg + fix-broken..."
    dpkg -i --force-depends "./$DEB_PKG" || true
    apt-get install -f -y || true
fi

# Process any pending dpkg triggers (compiles workbench and restarts engined cleanly)
dpkg --configure --pending 2>/dev/null || true

# If omv-mkworkbench is available, ensure all compiled assets are generated
if command -v omv-mkworkbench >/dev/null 2>&1; then
    echo "🔨 Compiling OpenMediaVault Workbench routes & widgets..."
    omv-mkworkbench all || true
fi

echo "=========================================================="
echo "✅ Agent Station Plugin successfully installed on your OMV Server!"
echo "👉 1. Refresh your OMV WebGUI browser tab"
echo "👉 2. Open Agent Station in the sidebar menu"
echo "👉 3. Configure your AI models, git sync, and messenger bots"
echo "=========================================================="

# Smooth daemon reload in background so active RPC session stream completes 100% cleanly
if command -v systemctl >/dev/null 2>&1; then
    (
        sleep 2
        systemctl restart openmediavault-engined 2>/dev/null || true
        systemctl restart 'php*-fpm' 2>/dev/null || true
        systemctl reload nginx 2>/dev/null || true
    ) >/dev/null 2>&1 &
fi
