# Changelog

All notable changes to the OpenMediaVault Agent Station plugin will be documented in this file.

## [0.1.0] - 2026-08-29

### Added
- First official stable release for OpenMediaVault (OMV 6, 7 & 8).
- Dedicated `navigationPage` container component for `Services -> Agent Station` displaying all 6 sub-menu cards (*Overview*, *AI Models*, *Git Providers*, *Chat & Messenger*, *Security & Web Access*, *Diagnostics & Logs*).
- Dynamic SemVer packaging resolution (`resolve-version.sh`) with support for branch names, release tags (`v*`), and packaging fallbacks.
- Comprehensive RPC PHPUnit test suite for `AgentStation` RPC service and schema validations.
- Automated Debian package generation in GitHub Actions release publisher workflow.

### Fixed
- Fixed Workbench navigation lock where users were unable to switch out of Agent Station without a full page refresh.
- Fixed root-level menu collision by properly nesting Agent Station under `Services` (`services.agentstation.*`).
- Fixed dpkg parsing error `Version field value does not start with digit` during branch builds.
- Fixed git tag checkout logic in installer script to match both `refs/tags/${TAG}` and `refs/tags/v${TAG}`.
- Added `--allow-downgrades` flag during apt package installation to support switching between versions and branches.

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
