# Complete Handbook: 24/7 Autonomous AI Agent Stack on HP ProLiant Gen8 (OMV)

---

## 1. System Architecture Overview

This production stack turns your **HP ProLiant MicroServer Gen8 (running OpenMediaVault / Debian)** into an always-on, low-power AI development powerhouse. Your laptop no longer needs to be powered on to write, test, and commit code.

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

## 2. Leveraging Your Subscriptions to Maximum Advantage

### A. Google AI (Gemini Studio API)

- **Strengths:** Huge context window (1,000,000 to 2,000,000 tokens), extremely low latency, generous rate limits.
- **Role in Stack:**
  - **Gemini 2.5 Flash:** Used as the primary **triage & context reader** model (`coder-fast`). It reads whole repositories, summarizes logs, and handles quick edits at almost zero cost.
  - **Gemini 2.5 Pro:** Secondary heavyweight reasoning model when reviewing large codebases.

### B. Microsoft Copilot from GitHub

- **Strengths:** Included with your GitHub Copilot subscription; gives access to Azure/GitHub AI inference endpoints.
- **Role in Stack:**
  - Uses your `GITHUB_TOKEN` with the GitHub Models inference endpoint (`https://models.inference.ai.azure.com`).
  - Provides access to **GPT-4o** and **o3-mini** without requiring separate OpenAI credit cards.
  - Configured as an automatic fallback tier in `coder-smart` and `reasoning-heavy`.

### C. Claude Code / Anthropic

- **Strengths:** Unrivaled state-of-the-art coding, refactoring, and reasoning.
- **Role in Stack:**
  - **Claude 3.7 Sonnet (Hybrid Thinking):** The primary brain for autonomous coding agents (`coder-smart`).
  - **Prompt Caching Enabled:** LiteLLM passes prompt caching headers so repeated system prompts and project context are billed at a 90% discount.
  - **Claude Code CLI:** Pre-installed inside the container so you can trigger Claude Code directly or via terminal.

---

## 3. Quick-Start Deployment on OpenMediaVault

### Step 1: Copy the Stack to Your Server

From your computer, copy the `omv-stack` folder to your ProLiant Gen8:

```bash
scp -r ./omv-stack root@<YOUR-OMV-IP>:/srv/dev-data/ai-stack
```

### Step 2: SSH into Your OMV Server

```bash
ssh root@<YOUR-OMV-IP>
cd /srv/dev-data/ai-stack
```

### Step 3: Configure Your Credentials

Copy `env.example` to `.env` and fill in your API keys and tokens:

```bash
cp env.example .env
nano .env
```

Ensure you set:

- `GEMINI_API_KEY`: From Google AI Studio.
- `ANTHROPIC_API_KEY`: From Anthropic Console.
- `GITHUB_TOKEN`: GitHub Personal Access Token (classic or fine-grained with model access).
- `TELEGRAM_BOT_TOKEN`: From Telegram `@BotFather`.
- `TELEGRAM_ALLOWED_USER_ID`: Your numeric Telegram ID (from `@userinfobot`).

### Step 4: Run the Setup Script

```bash
./setup.sh
```

This script creates storage volumes, builds the containers, and launches the entire stack.

---

## 4. Telegram Bot Commands & Workflow

Once launched, open your Telegram chat with your bot and try:

| Command                    | Action                                                                   |
| -------------------------- | ------------------------------------------------------------------------ |
| `/start`                   | Display status and available options                                     |
| `/task <project> <prompt>` | Start an autonomous agent coding session in `/data/workspace/<project>`  |
| `/chat <question>`         | Ask technical questions using the smart router (Claude 3.7 / Gemini 2.5) |
| `/projects`                | List all repositories in your workspace directory                        |
| `/vault`                   | View status and recently modified files in your Obsidian second brain    |
| `/note <Title> \| <Body>`  | Instantly save a new note to `Inbox/` in your Obsidian vault             |
| `/models`                  | Query the LiteLLM proxy for active provider endpoints and health         |
| `/status`                  | View server uptime, RAM, disk space, and active tmux sessions            |

---

## 5. Integrating Obsidian (Second Brain) & Syncthing

1. Open the Syncthing Web UI on `http://<YOUR-OMV-IP>:8384`.
2. Add your laptop and phone as connected devices.
3. Share your Obsidian Vault folder:
   - On Server: `/data/obsidian`
   - On Mac/PC: `~/Documents/ObsidianVault`
4. **How the Agent uses Obsidian:**
   - Place project specs in `ObsidianVault/Projects/<ProjectName>/spec.md`.
   - Your Telegram bot and coding agent read specs from this path and write execution summaries back to `agent-log.md`.

---

## 6. Accessing the Live Terminal (cmux / tmux)

If you want to view a running agent live from a browser:

- Navigate to: `http://<YOUR-OMV-IP>:7681`
- Log in with credentials from `.env` (`TERMINAL_USER` / `TERMINAL_PASS`).
- Attach to any running tmux session:
  ```bash
  tmux attach -t agent-main
  ```

---

## 7. Service Maintenance & Logs

To check live logs from your server:

```bash
# View LiteLLM gateway traffic & rate-limit fallbacks
docker compose logs -f litellm

# View Telegram bot activities
docker compose logs -f telegram-bot

# Restart the stack
docker compose restart
```
