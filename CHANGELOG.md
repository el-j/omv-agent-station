# Changelog

All notable changes to the OpenMediaVault Agent Station plugin will be documented in this file.

## [0.0.3-alpha] - 2026-08-23

### Added
- GitHub repository integration in Git Providers with guided token generator link.
- Granular per-provider enable/disable switches for GitHub, GitLab, and Bitbucket.
- Direct external token creation links for Google AI Studio, Anthropic, Telegram, and Discord.
- Pure top-level root sidebar navigation entry for Agent Station.

### Fixed
- Resolved exit code 127 during 'omv-agent-station apply' by implementing multi-binary compose fallback.
- Aligned route and component namespaces for seamless OpenMediaVault Workbench routing.


### Added
- GitHub repository integration in Git Providers with guided token generator link.
- Granular per-provider enable/disable switches for GitHub, GitLab, and Bitbucket.
- Direct external token creation links for Google AI Studio, Anthropic, Telegram, and Discord.
- Pure top-level root sidebar navigation entry for Agent Station.

### Fixed
- Resolved exit code 127 during 'omv-agent-station apply' by implementing multi-binary compose fallback.
- Aligned route and component namespaces for seamless OpenMediaVault Workbench routing.

and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.1] - 2026-08-22

### Added
- **Top-Level Root Navigation**: Dedicated "Agent Station" left sidebar menu container (position 60) with 5 dedicated submenus:
  - `Overview`: General status, Master Engine enable toggle, and direct web endpoints
  - `AI Models`: Provider API keys (Gemini 3.7 Pro, Claude 3.7 Sonnet, Copilot Pro / GitHub Models)
  - `Git Providers`: Author identity, GitLab PAT, and Bitbucket App Password
  - `Chat & Messenger`: Multi-relay configuration for Telegram, Signal, and Discord bots
  - `Security & Web Access`: LiteLLM Proxy auth and Web Terminal credentials
- **Granular Enable/Disable Toggles**: Each configuration section can be enabled or disabled independently via form checkboxes.
- **Home Dashboard Grid Widget**: Dedicated `type: grid` widget monitoring engine state, AI model routing, git sync, messenger relay, and security.
- **dpkg Triggers Architecture**: Integrated `debian/triggers` (`activate update-workbench` and `activate restart-engined`) for clean, async daemon reloading without breaking active RPC sessions.

### Fixed
- **RPC 500 Connection Reset Error**: Resolved socket drops during plugin installation by removing synchronous daemon restarts from `postinst` and leveraging dpkg trigger queues.
- **Workbench UI Discovery**: Corrected YAML schemas across `navigation.d/`, `route.d/`, `dashboard.d/`, and `component.d/` conforming to OpenMediaVault 6, 7 & 8 specs.
- **Partial Form Save Corruption**: Updated `AgentStation::setSettings` to merge section parameters, preserving existing configuration across multiple tabs.
