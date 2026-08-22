#!/usr/bin/env bash
# ==============================================================================
# OpenMediaVault AI Orchestrator Plugin & Stack Clean Uninstaller
# Repository: https://github.com/el-j/omv-agent-station
# ==============================================================================
set -e

echo "=========================================================="
echo "🧹 OpenMediaVault AI Orchestrator Plugin Uninstaller"
echo "=========================================================="

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Error: Please run this uninstaller as root (e.g. sudo bash uninstall-plugin.sh)"
    exit 1
fi

# 1. Stop active containers
echo "🛑 Stopping running AI stack containers..."
if [ -x /usr/sbin/omv-ai-orchestrator ]; then
    /usr/sbin/omv-ai-orchestrator down 2>/dev/null || true
fi
if [ -d "/usr/share/openmediavault/ai-orchestrator" ] && command -v docker >/dev/null 2>&1; then
    docker compose -f /usr/share/openmediavault/ai-orchestrator/docker-compose.yml down 2>/dev/null || true
fi

# 2. Purge Debian package
echo "📦 Purging openmediavault-ai-orchestrator package..."
export DEBIAN_FRONTEND=noninteractive
apt-get purge -y -qq openmediavault-ai-orchestrator 2>/dev/null || dpkg -P openmediavault-ai-orchestrator 2>/dev/null || true

# 3. Clean up stale datamodels and RPC handlers
echo "🧹 Removing plugin assets and cached configurations..."
rm -f /usr/share/openmediavault/datamodels/conf.service.aiorchestrator.json 2>/dev/null || true
rm -f /usr/share/openmediavault/datamodels/rpc.aiorchestrator.setsettings.json 2>/dev/null || true
rm -f /usr/share/openmediavault/datamodels/rpc.aiorchestrator.json 2>/dev/null || true
rm -f /usr/share/openmediavault/engined/rpc/aiorchestrator.inc 2>/dev/null || true
rm -f /usr/share/openmediavault/workbench/component.d/omv-services-ai-orchestrator-form-page.yaml 2>/dev/null || true
rm -f /usr/share/openmediavault/workbench/navigation.d/aiorchestrator.yaml 2>/dev/null || true
rm -f /usr/sbin/omv-ai-orchestrator 2>/dev/null || true
rm -rf /usr/share/openmediavault/ai-orchestrator 2>/dev/null || true

# 4. Refresh OMV Engined and Workbench Salt states
echo "🔄 Refreshing OpenMediaVault daemon & Workbench state..."
if command -v systemctl >/dev/null 2>&1; then
    systemctl restart omv-engined 2>/dev/null || true
fi

if command -v omv-salt >/dev/null 2>&1; then
    omv-salt deploy run workbench 2>/dev/null || true
fi

echo "=========================================================="
echo "✅ AI Orchestrator Plugin has been completely removed."
echo "👉 Your project data in /srv/dev-data was preserved."
echo "=========================================================="
