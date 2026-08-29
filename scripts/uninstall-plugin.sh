#!/usr/bin/env bash
# ==============================================================================
# OpenMediaVault Agent Station Plugin & Stack Clean Uninstaller
# Repository: https://github.com/el-j/omv-agent-station
# ==============================================================================
set -e

echo "=========================================================="
echo "🧹 OpenMediaVault Agent Station Plugin Uninstaller"
echo "=========================================================="

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Error: Please run this uninstaller as root (e.g. sudo bash uninstall-plugin.sh)"
    exit 1
fi

# 1. Stop active containers
echo "🛑 Stopping running Agent Station containers..."
if [ -x /usr/sbin/omv-agent-station ]; then
    /usr/sbin/omv-agent-station down 2>/dev/null || true
fi
if [ -x /usr/sbin/omv-agent-station ]; then
    /usr/sbin/omv-agent-station down 2>/dev/null || true
fi
if [ -d "/usr/share/openmediavault/agent-station" ] && command -v docker >/dev/null 2>&1; then
    docker compose -f /usr/share/openmediavault/agent-station/docker-compose.yml down 2>/dev/null || true
fi
if [ -d "/usr/share/openmediavault/ai-orchestrator" ] && command -v docker >/dev/null 2>&1; then
    docker compose -f /usr/share/openmediavault/ai-orchestrator/docker-compose.yml down 2>/dev/null || true
fi

# 2. Purge Debian packages
echo "📦 Purging openmediavault-agent-station and openmediavault-ai-orchestrator packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get purge -y -qq openmediavault-agent-station openmediavault-ai-orchestrator 2>/dev/null || dpkg -P openmediavault-agent-station openmediavault-ai-orchestrator 2>/dev/null || true

# 3. Clean up stale datamodels and RPC handlers
echo "🧹 Removing plugin assets and cached configurations..."
rm -f /usr/share/openmediavault/datamodels/*agentstation*.json* 2>/dev/null || true
rm -f /usr/share/openmediavault/datamodels/*aiorchestrator*.json* 2>/dev/null || true
rm -f /usr/share/openmediavault/datamodels/*ai_orchestrator*.json* 2>/dev/null || true
rm -f /usr/share/openmediavault/engined/rpc/agentstation.inc 2>/dev/null || true
rm -f /usr/share/openmediavault/engined/rpc/aiorchestrator.inc 2>/dev/null || true
rm -f /usr/share/openmediavault/workbench/component.d/*agentstation* 2>/dev/null || true
rm -f /usr/share/openmediavault/workbench/component.d/*aiorchestrator* 2>/dev/null || true
rm -f /usr/share/openmediavault/workbench/navigation.d/*agentstation* 2>/dev/null || true
rm -f /usr/share/openmediavault/workbench/navigation.d/*aiorchestrator* 2>/dev/null || true
rm -f /usr/share/openmediavault/workbench/route.d/*agentstation* 2>/dev/null || true
rm -f /usr/share/openmediavault/workbench/route.d/*aiorchestrator* 2>/dev/null || true
rm -f /usr/share/openmediavault/workbench/dashboard.d/*agentstation* 2>/dev/null || true
rm -f /usr/share/openmediavault/workbench/dashboard.d/*aiorchestrator* 2>/dev/null || true
rm -f /usr/sbin/omv-agent-station /usr/sbin/omv-ai-orchestrator 2>/dev/null || true
rm -rf /usr/share/openmediavault/agent-station /usr/share/openmediavault/ai-orchestrator 2>/dev/null || true

# 4. Ensure archives directory exists and clear compiled cache
mkdir -p /var/cache/openmediavault/archives 2>/dev/null || true
find /var/cache/openmediavault/ -maxdepth 1 -name "cache.*" -delete 2>/dev/null || true

if command -v omv-mkworkbench >/dev/null 2>&1; then
    omv-mkworkbench all || true
fi

# 5. Refresh OpenMediaVault daemons
echo "🔄 Refreshing OpenMediaVault daemons..."
if command -v systemctl >/dev/null 2>&1; then
    systemctl restart openmediavault-engined 2>/dev/null || systemctl restart omv-engined 2>/dev/null || true
    systemctl restart 'php*-fpm' 2>/dev/null || true
    systemctl reload nginx 2>/dev/null || true
fi

echo "=========================================================="
echo "✅ Agent Station Plugin has been completely removed."
echo "👉 Your project data in /srv/dev-data was preserved."
echo "=========================================================="
