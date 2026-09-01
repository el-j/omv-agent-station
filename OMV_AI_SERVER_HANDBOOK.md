# Complete Handbook: 24/7 Autonomous AI Agent Stack on HP ProLiant Gen8 (OMV)

> This handbook documents the reference setup: an HP ProLiant Gen8 running OpenMediaVault. The underlying stack has no OMV dependency, though, and runs the same way on any Debian-based Linux — including a Raspberry Pi 4/5 (64-bit OS). See the README's [Installation: OpenMediaVault or Any Debian-Based Linux](README.md#-installation-openmediavault-or-any-debian-based-linux) section for that path.

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

## 2. Leveraging Your 3 Pro Subscriptions to Maximum Advantage

### A. Google AI Pro (5 TB Subscription)
- **Official Docs:** [Google AI Studio Documentation](https://ai.google.dev/gemini-api/docs)
- **API Key Source:** [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
- **Strengths:** Huge context window (1M+ tokens), dynamic reasoning token support, ultra-low latency, generous quota tied to your Google AI Pro account.
- **Role in Stack:**
  - **Gemini 3.7 Flash:** Primary **triage & context reader** model (`coder-fast`). It reads entire repositories and summarizes logs.
  - **Gemini 3.7 Pro:** Secondary heavyweight reasoning model for deep codebase analysis.

### B. Claude Pro (Anthropic)
- **Official Docs:** [Anthropic Developer Documentation](https://docs.anthropic.com/en/docs/about-claude/models)
- **API Key Source:** [https://console.anthropic.com/](https://console.anthropic.com/) (and Claude Code CLI authentication)
- **Strengths:** Unrivaled code synthesis, Hybrid Thinking mode, and Prompt Caching (90% discount on cached tokens).
- **Role in Stack:** Primary reasoning engine for autonomous multi-file coding loops (`coder-smart`).

### C. GitHub Copilot Pro (GitHub / Microsoft)
- **Official Docs:** [GitHub Models Documentation](https://docs.github.com/en/github-models)
- **PAT Token Source:** [https://github.com/settings/tokens](https://github.com/settings/tokens)
- **Strengths:** Zero extra cost using your existing Copilot subscription via the GitHub Models inference endpoint (`https://models.inference.ai.azure.com`).
- **Role in Stack:** Automated cloud fallback for `gpt-4o` and `o3-mini` when other providers are in cooldown.

---

## 3. Quick-Start Deployment Options on OpenMediaVault

### Option 1: Native OpenMediaVault WebGUI Plugin
1. Build package: `./build-deb.sh`
2. Install on OMV: `sudo dpkg -i openmediavault-agent-station_1.0.0_all.deb`
3. Go to **OMV WebGUI $\to$ Services $\to$ Agent Station**: Enter your tokens and click **Save & Apply**!

### Option 2: 1-Liner Shell Quick-Start (SSH Terminal)
```bash
git clone https://github.com/el-j/omv-agent-station.git /srv/dev-data/omv-agent-station && cd /srv/dev-data/omv-agent-station && cp env.example .env && nano .env && ./setup.sh
```

### Option 3: OMV-Extras WebGUI Compose Plugin
1. In OMV WebGUI, go to **Services → Compose → Files**.
2. Click **+** (Add) and load [omv-compose-template.yaml](file:///Users/rex-fab-alt/Documents/code/playground/omv-stack/omv-compose-template.yaml) or `docker-compose.yml`.
3. Add your environment variables from `env.example`.
4. Click **Apply** and **Up**.

---

## 4. Telegram Bot Commands & Workflow

Once launched, open your Telegram chat with your bot and try:

| Command | Action |
| :--- | :--- |
| `/start` | Display status and available options |
| `/task <project> <prompt>` | Start an autonomous agent coding session in `/data/workspace/<project>` |
| `/chat <question>` | Ask technical questions using the smart router (Claude 3.7 / Gemini 3.7) |
| `/projects` | List all repositories in your workspace directory |
| `/vault` | View status and recently modified files in your Obsidian second brain |
| `/note <Title> \| <Body>` | Instantly save a new note to `Inbox/` in your Obsidian vault |
| `/models` | Query the LiteLLM proxy for active provider endpoints and health |
| `/status` | View server uptime, RAM usage, disk space, and active tmux sessions |

### Uploading Files to a Repository by Sending Them to the Bot

This isn't a slash command -- send a file, photo, or document directly to a chat (Telegram, Discord, or Signal all support it) and it gets committed into a repository:

1. **Bind a project first.** Use `/bind <project-name>` (Telegram forum topic, Discord channel, or your Signal chat) so the bot knows which repo to target.
2. **Send the file.** The caption controls where it lands:
   - No caption -> written to `uploads/<original-filename>`
   - `docs/notes.md` -> written to that exact path in the repo
   - `myapi: docs/notes.md` -> overrides the bound project and targets `myapi` instead, without needing to `/bind` first
3. **It never touches your current branch.** The bot always creates a fresh `upload/<timestamp>` branch, commits the file there, and pushes it -- then replies with a ready-to-open GitHub compare/PR link. Review and merge on your own terms.
4. **Size limit:** Telegram's Bot API caps file downloads at 20 MB regardless of your own bandwidth; larger files are rejected with an explicit error rather than failing silently.

---

## 5. Integrating Obsidian (Second Brain) & Syncthing

1. Open the Syncthing Web UI on `http://<YOUR-OMV-IP>:8384`.
2. Add your laptop and phone as connected devices.
3. Share your Obsidian Vault folder:
   - On Server: `/data/obsidian`
   - On Mac/PC: `~/Documents/ObsidianVault`
4. **How the Agent uses Obsidian:**
   - Place project specs in `ObsidianVault/Projects/<ProjectName>/project-spec.md`.
   - The Telegram bot automatically creates this note (with a Git remote, clone date, and an "Agent Execution History" section) whenever you run `/clone` or `/newrepo`.

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
