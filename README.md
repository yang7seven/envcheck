# 🏥 envcheck

**Dev environment doctor** — one command to check your entire dev setup. Like `brew doctor` but for project onboarding.

Checks Python/Node/Rust versions against project config, verifies services are running, scans for missing env vars, and confirms essential tools are installed.

## Install

```bash
pip install envcheck
```

## Usage

```bash
# Check current directory
envcheck check

# Check a specific project
envcheck check ~/my-project

# See fix suggestions inline
envcheck check . -v

# JSON output for scripting
envcheck check . --json

# Quick onboarding — "what do I need to start?"
envcheck onboard ~/new-project
```

## What it checks

| Category | Checks |
|----------|--------|
| **Language Runtimes** | Python (vs `.python-version`, `pyproject.toml`), Node.js (vs `.nvmrc`, `package.json` engines), Rust (vs `rust-toolchain.toml`) |
| **Dev Tools** | git, make, docker, curl, ssh |
| **Services** | PostgreSQL (5432), Redis (6379), MySQL (3306), MongoDB (27017), Docker daemon |
| **Ports** | 3000, 5173, 8080, 8000, 4200, 9000 availability |
| **Env Vars** | `.env.example` vs `.env` completeness |
| **System** | OS, disk space, package manager |

## Example output

```
🏥 envcheck — ~/my-project
Health 95/100  ✅10 ⚠️1 ❌0 ℹ️9

  ── Language Runtimes ──
  ✅  Python           Python 3.12.1
  ✅  Node.js          v20.11.0
  ℹ️  Rust             Not installed (ignore if not needed)

  ── Dev Tools ──
  ✅  Git              /usr/bin/git
  ✅  Docker           /usr/bin/docker
  ⚠️  Docker           Docker daemon not running

  ── Services ──
  ✅  PostgreSQL       PostgreSQL running (port 5432)
  ℹ️  Redis            Redis not running

  ⚠️  Suggestions:
     • Docker: Docker daemon not running → Start Docker Desktop
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | All critical checks passed |
| 2 | Errors found (missing required tools, disk full, etc.) |

## FAQ

**Q: How is this different from `doctor` tools in individual tools?**
A: `envcheck` is project-scoped — it reads your project's config files and tells you if your environment matches what the project expects. One command instead of `python --version && node --version && docker info && ...`

**Q: Can I add custom checks?**
A: Not yet, but `.envcheck.toml` config support is on the roadmap.

## License

MIT