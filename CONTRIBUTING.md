# Contributing to OpenMediaVault Agent Station

Thank you for your interest in contributing to **OMV Agent Station**! We welcome contributions from developers, DevOps engineers, and self-hosting enthusiasts.

---

## 🌿 GitFlow Branching Model & PR Rules

We adhere strictly to the **GitFlow** branching strategy to maintain stability in production releases:

```
feature/* / fix/* ──(PR)──> develop ──(PR)──> main (Official Release Tag vX.Y.Z)
```

### 📌 Branch Roles:
1. **`main` (Production & Stable Releases)**:
   - Contains only tested, production-ready releases.
   - Direct commits and direct PRs from `feature/*` or `fix/*` are **blocked**.
   - Receives PRs **strictly from `develop`** (for stable release promotions) or `hotfix/*`.
   - Every merge into `main` is tagged with a SemVer tag (e.g. `v0.0.2-alpha.36` or `v1.0.0`) and triggers the automated GitHub Release & `.deb` package builder.

2. **`develop` (Integration & Active Development)**:
   - The primary default target for all active development.
   - All `feature/*` and `fix/*` branches must branch off `develop` and open Pull Requests targeting `develop`.

3. **`feature/<name>` & `fix/<name>` (Topic Branches)**:
   - Created from `develop`.
   - Once implementation and tests pass, open a PR targeting `develop`.

---

## 🛠️ Local Development & Quality Gates

### 1. Prerequisites
* Python 3.11+
* Docker & Docker Compose
* Node.js 20+ (for Astro documentation website)

### 2. Setting Up Your Development Environment
```bash
git clone https://github.com/el-j/omv-agent-station.git
cd omv-agent-station

# Checkout develop
git checkout develop
git checkout -b feature/my-feature-name

# Install test, linter, and runtime dependencies
pip install -r telegram-agent-bot/requirements.txt
pip install -r signal-agent-bot/requirements.txt
pip install -r discord-agent-bot/requirements.txt
pip install pytest pytest-cov "flake8>=7.3.0" mypy bandit pyyaml httpx openai websockets
```

> `flake8>=7.3.0` matters: older pycodestyle releases misattribute `E401` on
> Python 3.13 (a PEP 701 f-string tokenizer interaction), which fails the lint
> job on the version Debian trixie actually ships.

### 3. Validation Suite Commands
Before opening a Pull Request, run the local quality checks:

```bash
# Run complete verification suite (Lint + Yaml + Unit + Blackbox + Mutation + Deb Build)
make all

# Run specific check suites
make test        # Unit, Blackbox & Mutation tests + the coverage gate
make lint        # Flake8, mypy type checks, and YAML schema validation
make security    # Bandit security audit and secret leak scanning
make deb         # Native Debian package builder
```

### 4. Coverage gate

`scripts/test.sh` runs pytest under `pytest-cov` and **fails the build** if
total line coverage drops below the threshold. CI enforces the same number on
every Python version in the matrix (3.11, 3.12, 3.13).

* **Current threshold: 75%.** It lives in one place — `COVERAGE_MIN` at the top
  of `scripts/test.sh`.
* **Measured coverage as of the last change: 77%.** The gate deliberately sits a
  couple of points under the real number so an unrelated PR isn't blocked by
  normal churn.
* **What is measured** is configured under `[tool.coverage.run]` in
  `pyproject.toml`: `agent_station_core/`, the three bot directories, and
  `scripts/`. The byte-identical `agent_station_core` copies vendored inside
  each bot directory (they exist so each Docker build context is
  self-contained) are omitted — counting them would triple the denominator with
  files the tests never import.

**To raise the threshold** (please do, whenever you add meaningful tests):

```bash
bash scripts/test.sh                    # read the reported TOTAL
# then edit COVERAGE_MIN in scripts/test.sh to a couple of points below it
```

Raise it in the same PR that earns the coverage. Never lower it to make a build
pass — add the missing tests instead. To run the suite without the gate while
iterating locally: `COVERAGE_MIN=0 bash scripts/test.sh`.

### 5. Type checking

`scripts/lint.sh` runs `mypy` alongside flake8. The configuration
(`[tool.mypy]` in `pyproject.toml`) is intentionally permissive —
`ignore_missing_imports = true`, no `disallow_untyped_defs` — so it passes today
and can be tightened one module at a time. mypy is invoked **once per bot
directory** because all three ship same-named `core`/`handlers` packages (each
runs as its own container) and mypy refuses to run when two files map to one
module name.

---

## 🔀 Pull Request Process

1. **Create your branch from `develop`:**
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/my-awesome-feature
   ```
2. **Commit changes** using Conventional Commits (`feat: ...`, `fix: ...`, `docs: ...`, `refactor: ...`).
3. **Verify all checks pass locally** (`make all`).
4. **Open a Pull Request targeting `develop`**.
5. Once reviewed and merged into `develop`, your changes will be included in the next integration cycle and promoted to `main`.

---

## 📜 Code Style & Standards

* **Shared Core Engine:** Common logic must live in `agent_station_core/` so it is shared identically across Telegram, Discord, and Signal.
* **Python:** Follow PEP 8 guidelines. Include type annotations and docstrings.
* **YAML:** Maintain clean 2-space indentation for Docker Compose and OpenMediaVault Workbench schemas.
* **Security First:** Never hardcode credentials, tokens, or private keys. Always sanitize filesystem paths using `sanitize_project_path()`.

Thank you for building the open-source self-hosted AI development ecosystem with us!
