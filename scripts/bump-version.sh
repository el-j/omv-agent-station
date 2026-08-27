#!/usr/bin/env bash
# ==============================================================================
# Automated Semantic Versioning (SemVer) Manager for OMV Agent Station
#
# Release Scheme:
#   feature/* branches ➔ 0.0.2-alpha.X  (e.g., ./scripts/bump-version.sh alpha)
#   develop branch     ➔ 0.0.2-beta.X   (e.g., ./scripts/bump-version.sh beta)
#   main branch        ➔ 0.0.2          (e.g., ./scripts/bump-version.sh stable)
#
# Usage:
#   ./scripts/bump-version.sh 0.0.2-beta.1
#   ./scripts/bump-version.sh alpha
#   ./scripts/bump-version.sh beta
#   ./scripts/bump-version.sh stable
# ==============================================================================

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTROL_FILE="$ROOT_DIR/openmediavault-agent-station/debian/control"
BUILD_SCRIPT="$ROOT_DIR/build-deb.sh"
CHANGELOG_FILE="$ROOT_DIR/CHANGELOG.md"

CURRENT_VERSION=$(grep -E '^Version:' "$CONTROL_FILE" | awk '{print $2}')

if [ -z "$1" ]; then
    echo "Current version: $CURRENT_VERSION"
    echo "Usage: $0 <version|alpha|beta|stable|patch|minor|major>"
    exit 0
fi

NEW_VERSION="$1"

# Base semver (e.g., 0.0.2 from 0.0.2-beta.1 or 0.0.3-alpha)
BASE_VER=$(echo "$CURRENT_VERSION" | sed -E 's/-.*//')
IFS='.' read -r MAJOR MINOR PATCH <<< "$BASE_VER"

case "$NEW_VERSION" in
    alpha)
        # Check current alpha count
        if [[ "$CURRENT_VERSION" =~ -alpha\.([0-9]+) ]]; then
            COUNT="${BASH_REMATCH[1]}"
            COUNT=$((COUNT + 1))
        else
            COUNT=1
        fi
        NEW_VERSION="${BASE_VER}-alpha.${COUNT}"
        ;;
    beta)
        # Check current beta count
        if [[ "$CURRENT_VERSION" =~ -beta\.([0-9]+) ]]; then
            COUNT="${BASH_REMATCH[1]}"
            COUNT=$((COUNT + 1))
        else
            COUNT=1
        fi
        NEW_VERSION="${BASE_VER}-beta.${COUNT}"
        ;;
    stable)
        NEW_VERSION="${BASE_VER}"
        ;;
    patch)
        PATCH=$((PATCH + 1))
        NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
        ;;
    minor)
        MINOR=$((MINOR + 1))
        PATCH=0
        NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
        ;;
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
        ;;
esac

echo "🚀 Bumping version: $CURRENT_VERSION ➔ $NEW_VERSION"

# 1. Update debian/control
sed -i '' "s/^Version:.*/Version: $NEW_VERSION/" "$CONTROL_FILE" 2>/dev/null || sed -i "s/^Version:.*/Version: $NEW_VERSION/" "$CONTROL_FILE"

# 2. Update build-deb.sh
sed -i '' "s/^VERSION=\".*\"/VERSION=\"$NEW_VERSION\"/" "$BUILD_SCRIPT" 2>/dev/null || sed -i "s/^VERSION=\".*\"/VERSION=\"$NEW_VERSION\"/" "$BUILD_SCRIPT"

# 3. Update or prepend in CHANGELOG.md
TODAY=$(date +%Y-%m-%d)
if ! grep -q "## \[$NEW_VERSION\]" "$CHANGELOG_FILE"; then
    TEMP_FILE=$(mktemp)
    cat <<EOF > "$TEMP_FILE"
# Changelog

All notable changes to the OpenMediaVault Agent Station plugin will be documented in this file.

## [$NEW_VERSION] - $TODAY

### Added
- GitHub repository integration in Git Providers with guided token generator link.
- Granular per-provider enable/disable switches for GitHub, GitLab, and Bitbucket.
- Dedicated enable/disable switches for Telegram, Signal, and Discord messenger bots.
- Diagnostics & Logs real-time monitoring view under Agent Station sidebar.
- Guided 'Get token here' direct generation URLs for all AI, Git, and Messenger providers.

### Fixed
- Fixed 504 Gateway Timeout on Engine startup by switching to asynchronous stack lifecycle management.
- Fixed exit code 127 during 'omv-agent-station apply' with multi-binary compose fallback detection.
- Clean root-level sidebar navigation for OpenMediaVault Workbench.

EOF
    tail -n +6 "$CHANGELOG_FILE" >> "$TEMP_FILE"
    mv "$TEMP_FILE" "$CHANGELOG_FILE"
fi

echo "✅ Successfully updated version to $NEW_VERSION across all project manifests!"
