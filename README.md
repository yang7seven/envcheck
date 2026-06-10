# 🏥 envcheck

**Dev environment doctor** — one command to check your entire dev setup. Like `brew doctor` but for project onboarding.

✅ Semver-aware version matching | 🐳 Docker Compose aware | 🗄️ DB connectivity tests | 🔧 Auto-fix mode

## Install

```bash
pip install envcheck
```

For memory/CPU checks:
```bash
pip install envcheck[full]   # adds psutil
```

## Quick Start

```bash
# Check current directory
envcheck check

# See only issues
envcheck check -m summary

# Full verbose output
envcheck check -m verbose

# JSON for CI
envcheck check --json

# What do I need to install to contribute?
envcheck onboard ~/new-project

# Auto-fix common problems
envcheck fix

# Generate project config
envcheck init
```

## What it checks

| Category | Checks |
|----------|--------|
| **Languages** | Python (`.python-version`, `pyproject.toml`, `Pipfile`, `.tool-versions`), Node.js (`.nvmrc`, `package.json` engines), Rust (`rust-toolchain.toml`, `Cargo.toml`), Go (`go.mod`), Java (`build.gradle`, `pom.xml`), Ruby (`Gemfile`, `.ruby-version`) |
| **Dependencies** | Virtual env (`.venv`/`venv`), `node_modules/`, lock files |
| **Docker** | `docker-compose.yml` detection, service status (`docker compose ps`) |
| **Databases** | PostgreSQL (real `psql` test), Redis (real `PING`), MySQL, MongoDB |
| **Dev Tools** | git, make, docker, curl, ssh, wget, jq, tmux + project-specific recommendations |
| **Network** | Port availability (3000, 5173, 8080, 8000, 4200, 5000, 11434) |
| **Env Vars** | `.env.example` vs `.env` key completeness |
| **System** | OS, disk space, memory, CPU, package manager |
| **Project** | Project type detection, CI/CD config, pre-commit hooks, linter config |
| **Custom** | `.envcheck.toml` — project-specific required tools/ports |

## Configuration

Create a `.envcheck.toml` in your project root:

```toml
# Skip noisy checks
ignore = "MongoDB,Redis"

# Tools required for this project
required_tools = "docker,just,pre-commit"

# Ports that must be open
required_ports = "5432,6379"
```

## Commands

| Command | What it does |
|---------|-------------|
| `envcheck check` | Full environment audit |
| `envcheck onboard` | Quick setup guide for new contributors |
| `envcheck fix` | Auto-fix common issues (venv, node_modules, .env) |
| `envcheck init` | Generate `.envcheck.toml` template |

## Example

```
🏥 envcheck — ~/my-project
Health 95/100  ✅14 ⚠️1 ❌0 ℹ️21

  ── Dependencies ──
    ⚠️ Python venv: virtual env missing → python -m venv .venv

  ── Docker ──
    ✅ Compose services: 3 running: db, redis, web

  ── Databases ──
    ✅ PostgreSQL: connection successful (psql)
    ✅ Redis: PONG — connection successful
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All critical checks passed |
| 2 | Errors found (missing required tools, disk full, etc.) |

## License

MIT