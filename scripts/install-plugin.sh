#!/usr/bin/env bash
# ==============================================================================
# OpenMediaVault Agent Station Plugin & Stack Automated Installer
# Repository: https://github.com/el-j/omv-agent-station
# ==============================================================================
set -euo pipefail

echo "=========================================================="
echo "🚀 OpenMediaVault Agent Station Plugin Installer"
echo "=========================================================="

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Error: Please run this installer as root (e.g. sudo bash install-plugin.sh)"
    exit 1
fi

# Explicit version or ref selection: accepts branch names (develop/main/feature/*),
# exact tags (v0.0.2-beta.2), or a raw version (0.0.2-beta.2).
REQUESTED_REF="${VERSION_TAG:-${AGENT_STATION_VERSION:-${VERSION:-${BRANCH:-develop}}}}"
BRANCH="${BRANCH:-${REQUESTED_REF:-develop}}"
REQUESTED_VERSION="${REQUESTED_REF#v}"
INSTALL_DIR="/srv/dev-data/omv-agent-station"

if [ -d "$INSTALL_DIR" ] && [ ! -d "$INSTALL_DIR/.git" ]; then
    echo "🧹 Removing stale non-git checkout at $INSTALL_DIR before installing requested ref: $REQUESTED_REF"
    rm -rf "$INSTALL_DIR"
fi

# If the request is a branch name rather than a version, resolve to the
# correct package SemVer before building the .deb artifact.
if [[ "${REQUESTED_VERSION}" =~ ^[A-Za-z0-9._/-]+$ ]] && ! [[ "${REQUESTED_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+ ]]; then
    RESOLVED_VERSION="$(GITHUB_REF_NAME="$BRANCH" BRANCH="$BRANCH" bash "$INSTALL_DIR/scripts/resolve-version.sh" 2>/dev/null || true)"
    if [ -n "${RESOLVED_VERSION:-}" ] && [[ "${RESOLVED_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+ ]]; then
        REQUESTED_VERSION="$RESOLVED_VERSION"
    fi
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

mkdir -p "$INSTALL_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
    echo "🔄 Updating repository checkout to requested ref: $REQUESTED_REF"
    git -C "$INSTALL_DIR" fetch --tags --force --prune origin || true
    if git -C "$INSTALL_DIR" rev-parse --verify --quiet "refs/tags/${REQUESTED_REF#v}" >/dev/null; then
        git -C "$INSTALL_DIR" checkout -f "${REQUESTED_REF#v}" 2>/dev/null || git -C "$INSTALL_DIR" checkout -f "tags/${REQUESTED_REF#v}" 2>/dev/null || true
    elif git -C "$INSTALL_DIR" rev-parse --verify --quiet "origin/${REQUESTED_REF}" >/dev/null; then
        git -C "$INSTALL_DIR" checkout -B "$REQUESTED_REF" "origin/$REQUESTED_REF" 2>/dev/null || git -C "$INSTALL_DIR" checkout -B "$REQUESTED_REF" "$REQUESTED_REF" 2>/dev/null || true
    else
        git -C "$INSTALL_DIR" fetch origin "$REQUESTED_REF" 2>/dev/null || true
        git -C "$INSTALL_DIR" checkout -B "$REQUESTED_REF" "origin/$REQUESTED_REF" 2>/dev/null || git -C "$INSTALL_DIR" reset --hard "origin/$REQUESTED_REF" 2>/dev/null || git -C "$INSTALL_DIR" checkout -B "$REQUESTED_REF" "$REQUESTED_REF" 2>/dev/null || true
    fi
    git -C "$INSTALL_DIR" clean -fdx || true
else
    echo "📥 Cloning omv-agent-station repository and selecting ref: $REQUESTED_REF"
    git clone https://github.com/el-j/omv-agent-station.git "$INSTALL_DIR"
    git -C "$INSTALL_DIR" fetch --tags --force --prune origin || true
    if git -C "$INSTALL_DIR" rev-parse --verify --quiet "refs/tags/${REQUESTED_REF#v}" >/dev/null; then
        git -C "$INSTALL_DIR" checkout -f "${REQUESTED_REF#v}" 2>/dev/null || git -C "$INSTALL_DIR" checkout -f "tags/${REQUESTED_REF#v}" 2>/dev/null || true
    elif git -C "$INSTALL_DIR" rev-parse --verify --quiet "origin/${REQUESTED_REF}" >/dev/null; then
        git -C "$INSTALL_DIR" checkout -B "$REQUESTED_REF" "origin/$REQUESTED_REF" || true
    else
        git -C "$INSTALL_DIR" checkout -B "$REQUESTED_REF" "origin/${REQUESTED_REF:-develop}" 2>/dev/null || git -C "$INSTALL_DIR" checkout -B "develop" "origin/develop" 2>/dev/null || true
    fi
fi

cd "$INSTALL_DIR"

echo "🔨 Building Debian package for explicit version/ref $REQUESTED_REF -> $REQUESTED_VERSION..."
AGENT_STATION_VERSION="$REQUESTED_VERSION" bash build-deb.sh

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
TARGET_DEB="openmediavault-agent-station_${REQUESTED_VERSION}_all.deb"
if [ ! -f "$TARGET_DEB" ]; then
    TARGET_DEB=$(ls -1 openmediavault-agent-station_*.deb openmediavault-ai-orchestrator_*.deb 2>/dev/null | head -n1)
fi

if [ -z "${TARGET_DEB:-}" ] || [ ! -f "$TARGET_DEB" ]; then
    echo "❌ No matching .deb package was built for version ${REQUESTED_VERSION}."
    exit 1
fi

if ! apt-get install -y --reinstall "./$TARGET_DEB"; then
    echo "⚠️ Apt direct install encountered a dependency preference issue; applying with dpkg + fix-broken..."
    dpkg -i --force-depends "./$TARGET_DEB" || true
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
echo "👉 2. Open Services -> Agent Station in the sidebar"
echo "👉 3. Configure your AI models, git sync, and messenger bots"
echo "=========================================================="
