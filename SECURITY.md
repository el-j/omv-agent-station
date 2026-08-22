# Security Policy

We take the security of **OMV Agent Station** seriously. Because this project manages sensitive API keys (Google AI, Anthropic, GitHub) and remote command execution on home servers, security is our top priority.

---

## 🛡️ Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

---

## 🔒 Security Best Practices for Users

1. **Telegram / Signal / Discord User ID Whitelisting:**
   * Always configure `TELEGRAM_ALLOWED_USER_ID`, `SIGNAL_ALLOWED_PHONE_NUMBER`, or `DISCORD_ALLOWED_USER_ID`.
   * Unset allowed user IDs will block all incoming messages by default for security.

2. **Master Key Security:**
   * Never leave `LITELLM_MASTER_KEY` at default values when exposing port `4000` to local networks.

3. **Never Commit Secrets:**
   * Keep `.env` and `credentials/` in your `.gitignore`.
   * Use environment variables instead of hardcoding tokens in config files.

---

## 🚨 Reporting a Vulnerability

If you discover a security vulnerability, please **DO NOT** open a public issue.

Instead, please report it confidentially:
* **Email:** `security@omv-agent-station.local` (or via private GitHub Vulnerability Reporting on this repository).
* **Include:** Description of vulnerability, proof-of-concept steps, and potential impact.

We will acknowledge your report within 48 hours and provide a remediation timeline.
