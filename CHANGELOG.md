# Changelog

All notable changes to the OpenMediaVault Agent Station plugin will be documented in this file.

## [0.0.2-alpha.31] - 2026-08-24

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


### Added
- Masked passwordInput components across all 4 WebGUI form pages (AI models, Git credentials, messenger tokens, security keys).
- Anti-theft 3-tier secret persistence and permission lockdown (0600 root-only).
- Dedicated virtual model fallback priority chains for `coder-smart`, `coder-fast`, and `reasoning-heavy`.
- GitHub repository integration in Git Providers with guided token generator link.
- Granular per-provider enable/disable switches for GitHub, GitLab, and Bitbucket.
- Dedicated enable/disable switches for Telegram, Signal, and Discord messenger bots.
- Diagnostics & Logs real-time monitoring view under Agent Station sidebar.
- Guided 'Get token here' direct generation URLs for all AI, Git, and Messenger providers.

### Fixed
- Fixed 504 Gateway Timeout on Engine startup by switching to asynchronous stack lifecycle management (`apply-bg`).
- Fixed exit code 127 during 'omv-agent-station apply' with multi-binary compose fallback detection.
- Fixed LiteLLM config loading by passing explicit `--config /app/config.yaml` command flag.
- Clean root-level sidebar navigation for OpenMediaVault Workbench.

## [0.0.1] - 2026-08-22

### Added
- Initial OpenMediaVault Agent Station plugin structure with Debian packaging.
- LiteLLM multi-provider gateway, obsidian sync, and chat bot relays.
