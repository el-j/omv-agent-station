# 🚀 24/7 Headless AI Agent Orchestrator for OpenMediaVault (OMV)

An always-on, self-hosted AI engineering stack that **turns your OpenMediaVault (OMV) box into a 24/7 autonomous AI development agent**.

Control autonomous coding agents from **Signal (E2EE)**, **Telegram**, or **Discord**, sync your **Obsidian** Second Brain in real-time with **Syncthing**, multiplex sessions with **tmux / cmux**, and shield yourself from rate limits and high costs using **LiteLLM Proxy** configured for your existing subscriptions (**Google AI Studio / Gemini 3.7**, **Google Cloud Vertex AI Claude**, **Direct Anthropic Claude 3.7 Sonnet**, and **GitHub Copilot**).

---

## ⚡ 1-Liner Quick-Start on OMV Server (SSH Terminal)

Run this single command on your OpenMediaVault SSH console to clone, configure, and launch the entire stack:

```bash
git clone https://github.com/el-j/omv-agent-station.git /srv/dev-data/omv-agent-station && cd /srv/dev-data/omv-agent-station && cp env.example .env && nano .env && ./setup.sh
```

> Not on OpenMediaVault? The exact same command works on any Debian-based Linux — Debian, Ubuntu, or a 64-bit Raspberry Pi OS — just clone it wherever you like instead of `/srv/dev-data`. See [Installation: OpenMediaVault or Any Debian-Based Linux](#-installation-openmediavault-or-any-debian-based-linux) below.

---

## 📑 Table of Contents

1. [Why This Architecture?](#-why-this-architecture)
2. [Official Documentation & Sources](#-official-documentation--sources)
3. [Tested Hardware & Verified Benchmarks](#-tested-hardware--verified-benchmarks)
4. [Stack Components & Synergy](#-stack-components--synergy)
5. [Multi-Tier AI Redundancy & Smart Failover](#-multi-tier-ai-redundancy--smart-failover)
6. [Installation: OpenMediaVault or Any Debian-Based Linux](#-installation-openmediavault-or-any-debian-based-linux)
7. [Messenger Bot Commands & Workflow](#-messenger-bot-commands--workflow)
8. [Obsidian & Syncthing Integration](#-obsidian--syncthing-integration)
9. [Live Terminal & Session Multiplexing](#-live-terminal--session-multiplexing)
10. [Troubleshooting & Maintenance](#-troubleshooting--maintenance)

---

## 💡 Why This Architecture?

### The Shift to Autonomous Agentic Loops

Traditional AI tools operated on a rigid **"Single Prompt → Single LLM Response → Write to File"** pattern. Modern software engineering with AI requires **autonomous ReAct loops**:

- Reading project context, ASTs, and searching with `grep`
- Applying atomic diffs
- Running tests (`go test`, `npm test`, `pytest`) and linters in real time
- Self-correcting on compiler errors and stack traces
- Committing to git branches and opening pull requests

### The Always-On Advantage

Instead of keeping your primary laptop powered on 24/7 or being tied to your desk, your **OpenMediaVault home server runs the orchestrator stack 24/7**. You can send prompts and review code directly from your **phone via Signal, Telegram, or Discord** while on the go.

```
+-----------------------------------------------------------------------------------+
|                           YOUR MOBILE & WORKSTATION                               |
|   [ Signal / Telegram ]     [ Obsidian App (Mobile/Mac) ]    [ Browser / Terminal]|
+----------+--------------------------------+----------------------------+----------+
           |                                |                            |
           | Encrypted HTTPS/WSS            | Syncthing Sync             | SSH / HTTP
           v                                v                            v
+-----------------------------------------------------------------------------------+
|              v                                                                    |
|  +-----------------------------------------------------------------------------+  |
|  |                    LiteLLM Multi-Provider Proxy Router                      |  |
|  |  - Prompt Caching (90% savings)    - Rate Limit Shield & 429 Cooldown       |  |
|  |  - Dual Claude Failover Router     - Gemini 3.7 Workhorse & Reasoning       |  |
|  +-----------------------------------+-----------------------------------------+  |
+--------------------------------------|--------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------------+
|                           YOUR ACTIVE PRO SUBSCRIPTIONS                           |
|                                                                                   |
|  1. Google AI Pro (5 TB):   Gemini 3.7 Flash & Pro (1M-2M Context, Rapid Workhorse)|
|  2. Claude Pro:             Claude 3.7 Sonnet Thinking (Primary Coding Brain)     |
|  3. GitHub Copilot Pro:     GPT-4o & o3-mini via GitHub Models (Free Cloud Fallback)|
+-----------------------------------------------------------------------------------+
```

---

## 🎯 How Your 3 Pro Subscriptions Complement Each Other

| Your Subscription | Integration in this Stack | Role & Superpower |
| :--- | :--- | :--- |
| 👑 **Google AI Pro (5 TB)** | [Google AI Studio API Key](https://aistudio.google.com/app/apikey) | **The High-Speed Workhorse:** Powers `gemini-3.7-flash` and `gemini-3.7-pro`. Massive 1M+ token context window for reading whole repos, running lint triage, and test generation with high speed and generous tier limits. |
| 🧠 **Claude Pro** | [Anthropic Console API / Claude Code](https://console.anthropic.com/) | **The Coding Maestro:** Powers `claude-3-7-sonnet-20250219`. Unmatched code synthesis, complex bug fixing, architectural refactoring, and Hybrid Thinking mode. Prompt caching enabled by default (90% savings). |
| 🛡️ **GitHub Copilot Pro** | [GitHub Personal Access Token](https://github.com/settings/tokens) | **The Zero-Added-Cost Safety Net:** Direct access to `gpt-4o` and `o3-mini` via GitHub Models inference endpoint (`https://models.inference.ai.azure.com`). Automatically kicks in if other providers hit cooldowns. |

---

## 📚 Official Documentation & Sources

All models, routing parameters, and API integration paths strictly adhere to the official vendor documentation:

| Provider / Tool | Documentation Source | Key Models & Capabilities |
| :--- | :--- | :--- |
| **Google AI Studio (Google AI Pro)** | [Google AI Studio Documentation](https://ai.google.dev/gemini-api/docs) | `gemini-3.7-flash`, `gemini-3.7-pro`, dynamic reasoning tokens, 1M+ context window |
| **Anthropic API (Claude Pro)** | [Anthropic Developer Documentation](https://docs.anthropic.com/en/docs/about-claude/models) | `anthropic/claude-3-7-sonnet-20250219`, Prompt Caching, Extended Thinking |
| **GitHub Models (Copilot Pro)** | [GitHub Models Documentation](https://docs.github.com/en/github-models) | `openai/gpt-4o`, `openai/o3-mini` (Azure inference endpoint) |
| **LiteLLM Gateway** | [LiteLLM Official Documentation](https://docs.litellm.ai/docs/providers) | Unified proxy, usage-based routing, cooldown periods, multi-provider fallbacks |
| **OMV-Extras Compose** | [OMV-Extras Compose Repository](https://github.com/OpenMediaVault-Plugin-Developers/packages-openmediavault-compose) | Native OpenMediaVault container compose plugin & template catalog |

---

## 🖥️ Hardware & Server Feasibility: HP ProLiant Gen8

- **Hardware Profile:** Intel Celeron G1610T or Xeon E3-1265L v2 (Ivy Bridge), DDR3 ECC RAM, SATA storage bays, Gigabit Ethernet.
- **Local LLM Inference Reality:** The Gen8 CPU cannot run large local models (70B or heavy 14B) at acceptable speeds (no modern AVX2/AVX-512 or dedicated GPU).
- **Headless Orchestrator & Relay:** **10/10 Perfect.**
  - Idle power is extremely low (~25W–45W).
  - Effortlessly runs Docker containers for LiteLLM, Syncthing, Telegram bot, and multiple parallel CLI agent processes with <5% CPU usage.

---

## 🧩 Stack Components & Synergy

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **AI Gateway** | [LiteLLM Proxy](https://github.com/BerriAI/litellm) | Unifies all AI providers into a single OpenAI-compatible endpoint with automatic failover, prompt caching, and rate-limit shields. |
| **Second Brain** | [Obsidian](https://obsidian.md) + [Syncthing](https://syncthing.net) | Stores project specs, architecture guides (`AGENTS.md`), memory notes, and task lists, synced bi-directionally across devices. |
| **Agent Multiplexer** | `cmux` / `tmux` | Runs long-running CLI coding agents in detached persistent terminal sessions that survive network drops. |
| **Remote Control** | Telegram Bot (Python 3.11) | Receive commands on Telegram, run agents in git branches, run tests, and message back diffs & logs. |
| **Web Console** | `ttyd` | Browser-based terminal (`http://<OMV-IP>:7681`) to inspect running agent sessions from anywhere. |

---

## 🎯 Multi-Tier AI Redundancy & Smart Failover

### Double Claude Redundancy (Direct Anthropic + Google Vertex AI)
If your primary direct Anthropic subscription hits a rate limit (HTTP 429) or token ceiling, LiteLLM **automatically fails over to Claude 3.7 Sonnet via your Google Cloud / Vertex AI subscription** without interrupting the agent's work.

```
[ Coding Agent Request (coder-smart) ]
│
▼
1️⃣ Anthropic API (Claude 3.7 Sonnet) ──[429 / Quota exhausted]──►
│
▼
2️⃣ Google Vertex AI (Claude 3.7 Sonnet / Opus via Google Sub) ──[Fallback]──►
│
▼
3️⃣ Google AI Studio (Gemini 3.7 Pro / Gemini 3.7 Flash) ──[Fallback]──►
│
▼
4️⃣ GitHub Copilot (GitHub Models: GPT-4o / o3-mini)
```

### Virtual Router Aliases in `litellm/config.yaml`:
- **`coder-fast`**: Ultra-fast triage, search, and repository mapping using **Gemini 3.7 Flash** (fallback: Gemini 2.5 Flash, Claude 3.5 Haiku).
- **`coder-smart`**: Primary agentic loop model using **Claude 3.7 Sonnet** (fallback: Vertex AI Claude 3.7 Sonnet, Gemini 3.7 Pro, GitHub GPT-4o).
- **`reasoning-heavy`**: Deep architecture design & mathematical reasoning using **Claude 3.7 Sonnet Thinking** & **Gemini 3.7 Pro** (fallback: GitHub o3-mini).

---

## 🌐 Installation: OpenMediaVault or Any Debian-Based Linux

The stack itself (Docker Compose, LiteLLM, the bots) has **no OpenMediaVault dependency at all** — it runs the same way on plain Debian, Ubuntu Server, or a 64-bit Raspberry Pi OS install. OpenMediaVault users get an extra, optional WebGUI management layer on top of that same stack. Pick the path that matches your box:

### 🏆 OpenMediaVault (WebGUI-managed)

**Option A: Native Plugin (`openmediavault-agent-station`)** — adds **Services → Agent Station** to the OMV Workbench:
1. Build or download the `.deb` package: `./build-deb.sh`
2. Install it: `sudo dpkg -i openmediavault-agent-station_*_all.deb`
3. Refresh the WebGUI → **Services → Agent Station** → toggle **Enable**, enter your API keys in the form, click **Save** & **Apply**. The plugin manages the Docker containers and logs for you.

**Option B: OMV-Extras Compose Plugin (WebGUI Templates)** — no `.deb` install needed:
1. In the OMV WebGUI, navigate to **Services → Compose → Files**.
2. Click **+** (Add) and load [`omv-compose-template.yaml`](omv-compose-template.yaml) or `docker-compose.yml`.
3. In **Environment**, paste your keys from `env.example`.
4. Click **Apply** and **Up**.

### 🐧 Any Debian-Based Linux — Debian, Ubuntu, Raspberry Pi OS (CLI-managed)

No OMV required. This is the same stack, managed directly with `docker compose`. Confirmed to build and run on `arm64` (Raspberry Pi 4/5, 64-bit OS, 4GB+ RAM recommended) as well as `amd64`.

**1. Install Docker**, if you don't already have it:
```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin
```

**2. Clone and configure:**
```bash
git clone https://github.com/el-j/omv-agent-station.git ~/agent-station
cd ~/agent-station
cp env.example .env
nano .env   # fill in your API keys and bot token(s) — see Key Variables below
```

**3. Start the stack:**
```bash
./setup.sh
# or, on a completely fresh box with no Docker installed yet:
./setup.sh --install-deps
```
`setup.sh` detects Docker/Compose, notes when it's running on ARM64, creates the data directories, and brings the stack up with `docker compose`. Manage it afterwards with plain `docker compose {ps,logs,restart,down}` from the same directory — there's no extra CLI to learn.

#### Key Variables in `.env`:
```ini
DATA_DIR=/srv/dev-data   # any writable path — doesn't need to be an OMV mount
TZ=Europe/Berlin
LITELLM_MASTER_KEY=sk-omv-secret-master-key-change-me

# 1. Google AI Studio (https://aistudio.google.com/app/apikey)
GEMINI_API_KEY=your_gemini_api_key_here

# 2. Anthropic API (https://console.anthropic.com/)
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# 3. Google Cloud Vertex AI (Optional Claude Redundancy)
VERTEX_PROJECT_ID=your-gcp-project-id
VERTEX_LOCATION=europe-west1
VERTEX_CREDENTIALS_PATH=/app/credentials/gcp-service-account.json

# 4. GitHub Copilot Token (https://github.com/settings/tokens)
GITHUB_TOKEN=your_github_token_here

# 5. Telegram Bot Token (@BotFather) & User ID (@userinfobot)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_ALLOWED_USER_ID=your_numeric_user_id
```

---

## 📱 Telegram Bot Commands & Workflow

Once the bot is running, message it in your Telegram app:

### Everyday Commands:
- `/task <project-folder> <instruction>`: Launches an autonomous agent session on `/data/workspace/<project-folder>`, generates a new git branch, runs tests, and replies with a summary and diff.
  - _Example:_ `/task backend-api "Add rate-limiting middleware to auth routes and write integration tests"`
- `/chat <question>`: Ask general coding/architecture questions using Gemini 3.7 / Claude 3.7 with fallback routing.
- `/projects`: List all repositories available in your server's workspace.
- `/vault`: Check total notes and recently modified files in your Obsidian vault.
- `/note <Title> | <Content>`: Save a quick note directly into your Obsidian `Inbox/` folder.
- `/models`: Check live model endpoints and connectivity in the LiteLLM proxy.
- `/status`: Check server uptime, disk space, and active background tmux sessions.

---

## 📓 Obsidian & Syncthing Integration

1. Open Syncthing Web UI at `http://<OMV-IP>:8384`.
2. Add your laptop/mobile device as a remote device.
3. Share your Obsidian Vault directory:
   - **Server Path:** `/data/obsidian` (or `${DATA_DIR}/obsidian`)
   - **Local Device:** `~/Documents/ObsidianVault`
4. **Best Practice:** Keep a `Projects/<ProjectName>/project-spec.md` note for each repository. The Telegram bot and agents can read these specs as source-of-truth context.

---

## 💻 Live Terminal & Session Multiplexing

If you ever want to watch an agent code in real time or take manual control:

1. Open your browser to `http://<OMV-IP>:7681` (Web Terminal).
2. Log in with the credentials set in `.env` (`TERMINAL_USER` / `TERMINAL_PASS`).
3. You will enter a persistent `tmux` session directly inside `/workspace`.
4. You can also SSH into OMV and attach anytime:
   ```bash
   tmux attach -t agent-main
   ```

---

## 🛠️ Troubleshooting & Maintenance

### Checking Service Logs:
```bash
# Check LiteLLM routing and request metrics
docker compose logs -f litellm

# Check Telegram bot agent runs and errors
docker compose logs -f telegram-bot

# Check Syncthing synchronization
docker compose logs -f syncthing
```

### Restarting the Stack:
```bash
docker compose restart
```

### Updating Models or Prompt Settings:
Edit `litellm/config.yaml` and restart LiteLLM:
```bash
nano litellm/config.yaml
docker compose restart litellm
```

### 🧹 Clean Uninstallation & Reset:
If you wish to remove the plugin, stop all containers, and purge all OMV workbench assets (while keeping your project files in `/srv/dev-data` intact):

**1-Liner Shell Uninstaller:**
```bash
wget -qO- https://raw.githubusercontent.com/el-j/omv-agent-station/main/scripts/uninstall-plugin.sh | sudo bash
```

**Or via CLI / APT:**
```bash
sudo omv-agent-station uninstall
# or:
sudo apt purge openmediavault-agent-station
```

---

## 🧪 Quality Assurance, Testing & Security

This repository is maintained with strict automated CI/CD quality checks, secret leak detection, and unit testing:

```bash
# Run unit tests
make test

# Run code linter
make lint

# Scan for vulnerabilities & secret leaks
make security

# Build OpenMediaVault .deb package
make deb

# Run full suite
make all
```

---

## 🌐 Astro Documentation Website & GitHub Pages

A static documentation site built with **Astro** is available in the [`website/`](website/) directory. It deploys automatically to GitHub Pages via GitHub Actions:

```bash
cd website
npm install
npm run dev   # Start local preview at http://localhost:4321
npm run build # Build production static bundle to website/dist/
```

---

## 🤝 Community & Contributing

* 📖 **[Contributing Guidelines](CONTRIBUTING.md)**: How to file issues, submit PRs, and develop locally.
* 🛡️ **[Security Policy](SECURITY.md)**: Secret management and confidential vulnerability reporting.
* 📜 **[Code of Conduct](CODE_OF_CONDUCT.md)**: Contributor Covenant standards.
* ⚖️ **[License](LICENSE)**: GNU General Public License v3.0 (GPL-3.0-or-later).


