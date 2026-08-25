# Changelog

All notable changes to the OpenMediaVault Agent Station plugin will be documented in this file.

## [0.0.2-beta.2] - 2026-08-25

### Added
- Multi-messenger single source of truth library `agent_station_core` powering Telegram, Discord, and Signal.
- Comprehensive 11-page static documentation website built with Astro under `/docs/*`.
- Automated GitFlow PR validation workflow (`pr-target-guard.yml`) enforcing `feature/*` / `fix/*` ➔ `develop` ➔ `main`.
- Automated GitHub Release publisher workflow (`release.yml`) attaching compiled Debian `.deb` packages and SHA256 checksums.
- Automatic Forum Topic / Sub-channel creation and project context binding (`/createtopic`, `/bind`, `/unbind`).
- User-defined dynamic custom command shortcuts (`/addcmd`, `/delcmd`, `/cmds`) with `{args}` interpolation.
- GitHub repository creation (`/newrepo`) and automated PAT-authenticated cloning (`/clone`).
- Obsidian second-brain note capture (`/note`, `/vault`) and automated project spec provisioning.

### Fixed
- Fixed Telegram Forum Topic creation permission feedback when bot lacks Manage Topics permission.
- Fixed multi-page Astro static documentation compilation and routing.
- Fixed 504 Gateway Timeout on Engine startup by switching to asynchronous stack lifecycle management.
- Fixed exit code 127 during 'omv-agent-station apply' with multi-binary compose fallback detection.
- Clean root-level sidebar navigation for OpenMediaVault Workbench.
