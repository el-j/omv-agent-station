#!/usr/bin/env bash
# Resolve a stable or prerelease SemVer for the OMV plugin from git metadata.
# Priority:
#   1) explicit AGENT_STATION_VERSION / VERSION_TAG env
#   2) git exact tag match on HEAD
#   3) branch-derived SemVer for develop/feature/fix/main
#   4) repository default fallback

set -euo pipefail

if [ -n "${AGENT_STATION_VERSION:-}" ]; then
    echo "${AGENT_STATION_VERSION#v}"
    exit 0
fi

if [ -n "${VERSION_TAG:-}" ]; then
    echo "${VERSION_TAG#v}"
    exit 0
fi

if git rev-parse --git-dir >/dev/null 2>&1; then
    if git describe --tags --exact-match >/dev/null 2>&1; then
        tag="$(git describe --tags --exact-match)"
        echo "${tag#v}"
        exit 0
    fi

    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "${GITHUB_REF_NAME:-develop}")"
    if [ -n "${GITHUB_HEAD_REF:-}" ]; then
        branch="$GITHUB_HEAD_REF"
    fi

    latest_tag="$(git tag -l 'v*' --sort=-version:refname | head -n 1 || true)"
    base="${latest_tag#v}"
    if [[ "$base" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)(-(alpha|beta)\.([0-9]+))?$ ]]; then
        major="${BASH_REMATCH[1]}"
        minor="${BASH_REMATCH[2]}"
        patch="${BASH_REMATCH[3]}"
        case "$branch" in
            main)
                echo "${major}.${minor}.${patch}"
                exit 0
                ;;
            develop)
                run_number="${GITHUB_RUN_NUMBER:-$(git rev-list --count HEAD 2>/dev/null || echo 1)}"
                echo "${major}.${minor}.${patch}-beta.${run_number}"
                exit 0
                ;;
            feature/*|fix/*)
                run_number="${GITHUB_RUN_NUMBER:-$(git rev-list --count HEAD 2>/dev/null || echo 1)}"
                echo "${major}.${minor}.${patch}-alpha.${run_number}"
                exit 0
                ;;
            *)
                run_number="${GITHUB_RUN_NUMBER:-$(git rev-list --count HEAD 2>/dev/null || echo 1)}"
                echo "${major}.${minor}.${patch}-beta.${run_number}"
                exit 0
                ;;
        esac
    fi
fi

echo "0.0.2-beta.2"
