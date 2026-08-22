# Contributing to OpenMediaVault AI Orchestrator

Thank you for your interest in contributing to **OMV AI Orchestrator**! We welcome contributions from developers, DevOps engineers, and self-hosting enthusiasts.

---

## 🧭 How You Can Contribute

* 🐛 **Report Bugs:** Open an issue describing the unexpected behavior, server hardware/OMV version, and steps to reproduce.
* 💡 **Feature Requests:** Suggest new LLM provider integrations, chat relays (e.g. Matrix, Zulip), or OMV WebGUI improvements.
* 💻 **Code Contributions:** Submit PRs for bug fixes, performance optimizations, or tests.
* 📖 **Documentation:** Improve installation guides, tutorials, or architecture diagrams.

---

## 🛠️ Local Development & Standards

### 1. Prerequisites
* Python 3.11+
* Docker & Docker Compose
* Node.js 20+ (for Astro documentation website)

### 2. Setting Up Your Development Environment
```bash
git clone https://github.com/el-j/hs-ai-worker.git
cd hs-ai-worker

# Install test and lint dependencies
pip install -r telegram-agent-bot/requirements.txt
pip install -r signal-agent-bot/requirements.txt
pip install -r discord-agent-bot/requirements.txt
pip install pytest flake8 bandit pyyaml
```

### 3. Housekeeping & Validation Commands
Before opening a Pull Request, always run the local quality checks:

```bash
# Run test suite
make test

# Run code linter
make lint

# Run security vulnerability scan
make security

# Build Debian package
make deb
```

---

## 🔀 Pull Request Process

1. **Fork the repo** and create your branch from `main`:
   ```bash
   git checkout -b feature/my-new-feature
   ```
2. **Commit your changes** with clear, semantic commit messages (`feat: ...`, `fix: ...`, `docs: ...`).
3. **Ensure all tests and security checks pass** (`make test && make security`).
4. **Open a Pull Request** with a detailed description of what changed and why.

---

## 📜 Code Style & Standards

* **Python:** Follow PEP 8 guidelines. Type hints are encouraged where applicable.
* **YAML:** Maintain clean indentation (2 spaces) for Docker Compose and LiteLLM configurations.
* **Security First:** Never commit hardcoded API keys, tokens, or private certificates.

Thank you for building the open-source self-hosted AI ecosystem with us!
