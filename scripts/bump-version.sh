#!/usr/bin/env bash
# ==============================================================================
# Automated Semantic Versioning (SemVer) Manager for OMV Agent Station
# Usage:
#   ./scripts/bump-version.sh 0.0.2-alpha
#   ./scripts/bump-version.sh patch
#   ./scripts/bump-version.sh minor
#   ./scripts/bump-version.sh major
# ==============================================================================

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTROL_FILE="$ROOT_DIR/openmediavault-agent-station/debian/control"
BUILD_SCRIPT="$ROOT_DIR/build-deb.sh"
CHANGELOG_FILE="$ROOT_DIR/CHANGELOG.md"

CURRENT_VERSION=$(grep -E '^Version:' "$CONTROL_FILE" | awk '{print $2}')

if [ -z "$1" ]; then
    echo "Current version: $CURRENT_VERSION"
    echo "Usage: $0 <new_version|patch|minor|major|alpha>"
    exit 0
fi

NEW_VERSION="$1"

# Handle semantic increment aliases
if [ "$NEW_VERSION" = "patch" ] || [ "$NEW_VERSION" = "minor" ] || [ "$NEW_VERSION" = "major" ] || [ "$NEW_VERSION" = "alpha" ]; then
    BASE_VER=$(echo "$CURRENT_VERSION" | sed -E 's/-.*//')
    IFS='.' read -r MAJOR MINOR PATCH <<< "$BASE_VER"
    case "$NEW_VERSION" in
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
        alpha)
            PATCH=$((PATCH + 1))
            NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}-alpha"
            ;;
    esac
fi

echo "🚀 Bumping version: $CURRENT_VERSION ➔ $NEW_VERSION"

# 1. Update debian/control
sed -i '' "s/^Version:.*/Version: $NEW_VERSION/" "$CONTROL_FILE" 2>/dev/null || sed -i "s/^Version:.*/Version: $NEW_VERSION/" "$CONTROL_FILE"

# 2. Update build-deb.sh
sed -i '' "s/^VERSION=\".*\"/VERSION=\"$NEW_VERSION\"/" "$BUILD_SCRIPT" 2>/dev/null || sed -i "s/^VERSION=\".*\"/VERSION=\"$NEW_VERSION\"/" "$BUILD_SCRIPT"

# 3. Add section to CHANGELOG.md if not present
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
- Direct external token creation links for Google AI Studio, Anthropic, Telegram, and Discord.
- Pure top-level root sidebar navigation entry for Agent Station.

### Fixed
- Resolved exit code 127 during 'omv-agent-station apply' by implementing multi-binary compose fallback.
- Aligned route and component namespaces for seamless OpenMediaVault Workbench routing.

EOF
    tail -n +6 "$CHANGELOG_FILE" >> "$TEMP_FILE"
    mv "$TEMP_FILE" "$CHANGELOG_FILE"
fi

echo "✅ Successfully updated version to $NEW_VERSION across all project manifests!"
