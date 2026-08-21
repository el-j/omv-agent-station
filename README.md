# 🚀 24/7 Headless AI Agent Orchestrator for OpenMediaVault (OMV) & HP ProLiant Gen8

An always-on, self-hosted AI engineering stack running on your home server (Debian / OpenMediaVault on HP ProLiant MicroServer Gen8).

Control autonomous coding agents from **Telegram**, sync your **Obsidian** Second Brain in real-time with **Syncthing**, multiplex sessions with **cmux / tmux**, and shield yourself from rate limits and high costs using **LiteLLM Proxy** configured for your existing subscriptions (**Google AI / Gemini**, **Claude Code**, and **GitHub Copilot**).

---

## 📑 Table of Contents

1. [Why This Architecture?](#-why-this-architecture)
2. [Hardware & Server Feasibility (HP ProLiant Gen8)](#-hardware--server-feasibility-hp-proliant-gen8)
3. [Stack Components & Synergy](#-stack-components--synergy)
4. [How Your AI Subscriptions Are Maximized](#-how-your-ai-subscriptions-are-maximized)
5. [Quick Start & Setup Guide](#-quick-start--setup-guide)
6. [Telegram Bot Commands & Workflow](#-telegram-bot-commands--workflow)
7. [Obsidian & Syncthing Integration](#-obsidian--syncthing-integration)
8. [Live Terminal & Session Multiplexing](#-live-terminal--session-multiplexing)
9. [Troubleshooting & Maintenance](#-troubleshooting--maintenance)

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

Instead of keeping your primary laptop powered on 24/7 or being tied to your desk, your **HP ProLiant Gen8 server runs the orchestrator stack 24/7**. You can send prompts and review code directly from your **phone via Telegram** while on the go.

```
+-----------------------------------------------------------------------------------+
|                           YOUR MOBILE & WORKSTATION                               |
|   [ Telegram App ]          [ Obsidian App (Mobile/Mac) ]    [ Browser / Terminal]|
+----------+--------------------------------+----------------------------+----------+
           |                                |                            |
           | Encrypted HTTPS/WSS            | Syncthing Sync             | SSH / HTTP
           v                                v                            v
+-----------------------------------------------------------------------------------+
|                HP PROLIANT GEN8 SERVER (OpenMediaVault / Docker)                  |
|                                                                                   |
|  +-----------------------+   +-----------------------+  +----------------------+  |
|  |  Telegram Agent Bot   |   |   Syncthing Daemon    |  |  Web Terminal (ttyd) |  |
|  |  (Python + Aider/CLI) |<->|  (/data/obsidian)     |  |  (:7681 / tmux)      |  |
|  +-----------+-----------+   +-----------------------+  +----------------------+  |
|              |                                                                    |
|              | OpenAI-Compatible API (:4000)                                      |
|              v                                                                    |
|  +-----------------------------------------------------------------------------+  |
|  |                    LiteLLM Multi-Provider Proxy Router                      |  |
|  |  - Prompt Caching (90% savings)    - Rate Limit Shield & 429 Cooldown       |  |
|  |  - Usage & Budget Telemetry        - Multi-Tier Virtual Aliases             |  |
|  +-----------------------------------+-----------------------------------------+  |
+--------------------------------------|--------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------------+
|                           YOUR AI SUBSCRIPTIONS                                   |
|                                                                                   |
|  1. Google AI:          Gemini 2.5 Flash & Pro (1M-2M Context, Rapid Workhorse)   |
|  2. GitHub Copilot:     GitHub Models API (GPT-4o & o3-mini via GitHub Token)     |
|  3. Claude Code:        Anthropic API (Claude 3.7 Sonnet Thinking, 3.5 Haiku)     |
+-----------------------------------------------------------------------------------+
```

---

## 🖥️ Hardware & Server Feasibility: HP ProLiant Gen8

- **Hardware Profile:** Intel Celeron G1610T or Xeon E3-1265L v2 (Ivy Bridge), DDR3 ECC RAM, SATA storage bays, Gigabit Ethernet.
- **Local LLM Inference Reality:** The Gen8 CPU cannot run large local models (70B or heavy 14B) at acceptable speeds (no modern AVX2/AVX-512 or dedicated GPU).
- **Headless Orchestrator & Relay:** **10/10 Perfect.**
  - Idle power is extremely low (~25W–45W).
  - Effortlessly runs Docker containers for LiteLLM, Syncthing, Telegram bot, and multiple parallel CLI agent processes with <5% CPU usage.

---

## 🧩 Stack Components & Synergy

| Component             | Technology                                                           | Purpose                                                                                                                            |
| --------------------- | -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **AI Gateway**        | [LiteLLM Proxy](https://github.com/BerriAI/litellm)                  | Unifies all AI providers into a single OpenAI-compatible endpoint with automatic failover, prompt caching, and rate-limit shields. |
| **Second Brain**      | [Obsidian](https://obsidian.md) + [Syncthing](https://syncthing.net) | Stores project specs, architecture guides (`AGENTS.md`), memory notes, and task lists, synced bi-directionally across devices.     |
| **Agent Multiplexer** | `cmux` / `tmux`                                                      | Runs long-running CLI coding agents in detached persistent terminal sessions that survive network drops.                           |
| **Remote Control**    | Telegram Bot (Python 3.11)                                           | Receive commands on Telegram, run agents in git branches, run tests, and message back diffs & logs.                                |
| **Web Console**       | `ttyd`                                                               | Optional browser-based terminal (`http://<OMV-IP>:7681`) to inspect running agent sessions from anywhere.                          |

---

## 🎯 How Your AI Subscriptions Are Maximized

### 1. Google AI (Gemini 2.5 Flash & Pro)

- **Role in Stack:** Fast workhorse and entire-repo analyzer.
- **Why it shines:** 1,000,000 to 2,000,000 token context window, ultra-fast generation, extremely low cost per token.
- **Assigned Model Group:** `coder-fast` (file discovery, repo mapping, triage, unit test generation).

### 2. Claude Code / Anthropic (Claude 3.7 Sonnet)

- **Role in Stack:** Premier reasoning & autonomous coding engine.
- **Why it shines:** Gold standard for complex refactoring, multi-file edits, and architectural thinking.
- **Prompt Caching:** LiteLLM is pre-configured with `enable_prompt_caching: true`, saving up to 90% on repeated system prompts and project context.
- **Assigned Model Group:** `coder-smart` & `reasoning-heavy`.

### 3. Microsoft Copilot from GitHub (GitHub Models)

- **Role in Stack:** Zero-added-cost cloud fallback.
- **Why it shines:** Access Azure-hosted `gpt-4o` and `o3-mini` endpoints using your existing `GITHUB_TOKEN`.
- **Assigned Model Group:** Automated failover tier when other providers hit temporary cooldowns.

---

## 🚀 Quick Start & Setup Guide

### 1. Prerequisites on Your OpenMediaVault Server

Ensure Docker and Docker Compose are installed on OMV (via OMV-Extras or standard Debian apt):

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin
```

### 2. Copy the Stack to Your Server

From your local machine:

```bash
scp -r /Users/rex-fab-alt/Documents/code/playground/omv-stack root@<OMV-SERVER-IP>:/srv/dev-data/ai-stack
```

### 3. SSH into OMV and Configure Environment

```bash
ssh root@<OMV-SERVER-IP>
cd /srv/dev-data/ai-stack

# Copy example environment file
cp env.example .env

# Edit configuration with your keys
nano .env
```

#### Required Keys in `.env`:

```ini
DATA_DIR=/srv/dev-data
TZ=Europe/Berlin
LITELLM_MASTER_KEY=sk-omv-secret-master-key-change-me

# 1. Google AI Studio API Key (https://aistudio.google.com/app/apikey)
GEMINI_API_KEY=AIzaSy...

# 2. Anthropic API Key (https://console.anthropic.com/)
ANTHROPIC_API_KEY=sk-ant-api03-...

# 3. GitHub Personal Access Token (https://github.com/settings/tokens)
GITHUB_TOKEN=ghp_...

# 4. Telegram Bot Token (@BotFather) & Your Numeric User ID (@userinfobot)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_ALLOWED_USER_ID=123456789
```

### 4. Launch the Stack

```bash
./setup.sh
```

---

## 📱 Telegram Bot Commands & Workflow

Once the bot is running, message it in your Telegram app:

### Everyday Commands:

- `/task <project-folder> <instruction>`: Launches an autonomous agent session on `/data/workspace/<project-folder>`, generates a new git branch, runs tests, and replies with a summary and diff.
  - _Example:_ `/task backend-api "Add rate-limiting middleware to auth routes and write integration tests"`
- `/chat <question>`: Ask general coding/architecture questions using the smart multi-model router.
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
4. **Best Practice:** Keep a `Projects/<ProjectName>/spec.md` note for each repository. The Telegram bot and agents can read these specs as source-of-truth context.

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

---

## 📜 License

MIT License. Built for seamless self-hosted AI engineering.
