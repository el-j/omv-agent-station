## 📌 Pull Request Description

### 🎯 Objective & Summary
<!-- Describe what this change accomplishes and the rationale behind it -->

---

### 🌿 GitFlow Branching Checklist
- [ ] **Target Branch:** This PR targets `develop` (for `feature/*` and `fix/*` branches) OR targets `main` (for release promotions from `develop`).
- [ ] **Commit Messages:** Follow Conventional Commits format (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`).

---

### 🧪 Validation & Testing Performed
- [ ] Ran `make test` — all unit, blackbox, and mutation tests passed.
- [ ] Ran `make lint` — flake8 and YAML schema validation passed.
- [ ] Ran `make security` — bandit and secret scan passed with 0 vulnerabilities.
- [ ] Ran `make deb` — Debian `.deb` package built cleanly.
- [ ] Ran `npm run build` in `website/` — all static documentation pages built without errors.

---

### 📋 Areas Impacted
- [ ] `agent_station_core/` (Shared business logic & AI gateway)
- [ ] `telegram-agent-bot/` (Telegram interface & topics)
- [ ] `discord-agent-bot/` (Discord interface & threads)
- [ ] `signal-agent-bot/` (Signal interface & E2EE relay)
- [ ] `openmediavault-agent-station/` (OMV PHP RPC, Workbench UI & CLI helper)
- [ ] `website/` (Astro Documentation site)
- [ ] CI/CD & Deployment scripts
