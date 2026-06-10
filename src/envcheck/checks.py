"""envcheck v2 — comprehensive dev environment checks

Semver-aware version matching, Docker Compose, DB connectivity,
virtual env detection, resource monitoring, and .envcheck.toml config.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional, Literal, Callable

Status = Literal["ok", "warn", "error", "info"]


@dataclass
class CheckResult:
    name: str
    status: Status
    message: str
    detail: str = ""
    fix: str = ""


# ── helpers ────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 10, **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            errors="replace", **kwargs,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return subprocess.CompletedProcess(cmd, -1, "", "timeout/not found")


def _which(tool: str) -> Optional[str]:
    return shutil.which(tool)


def _check_port(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _read_file(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def _read_json(path: str) -> Optional[dict]:
    raw = _read_file(path)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return None


# ── semver parsing (no external deps) ───────────────────────────

_SEMVER_RE = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-.](.+))?$")


def _parse_semver(version_str: str) -> tuple[int, ...]:
    """Parse a version string into a comparable tuple."""
    v = version_str.strip().lstrip("v")
    m = _SEMVER_RE.match(v)
    if m:
        parts = [int(x) for x in m.groups()[:3] if x is not None]
        return tuple(parts)
    # Fallback: extract any numbers
    nums = re.findall(r"\d+", v)
    return tuple(int(n) for n in nums) if nums else (0,)


def _version_satisfies(current: str, requirement: str) -> tuple[bool, str]:
    """Check if `current` version satisfies a PEP 440-like `requirement`.

    Returns (satisfied, explanation).
    Handles: >=3.9, >3.9, <=3.12, <3.13, ==3.10, ~=3.9, ^18.0, 3.9, >=3.9,<3.13
    """
    cur = _parse_semver(current)
    req = requirement.strip()

    # Split on comma for multiple constraints
    constraints = [c.strip() for c in req.split(",") if c.strip()]
    if not constraints:
        return True, ""

    for c in constraints:
        # ^18.0 → >=18.0,<19.0 (npm-style caret)
        if c.startswith("^"):
            v = _parse_semver(c[1:])
            if v:
                lo, hi = v, (v[0] + 1,) + (0,) * (len(v) - 1)
                if not (lo <= cur < hi):
                    return False, f"npm caret {c} requires {lo} <= ver < {hi}"

        # ~=3.9 → >=3.9,<4.0
        elif c.startswith("~="):
            v = _parse_semver(c[2:])
            if v:
                hi = (v[0] + 1,) + (0,) * (len(v) - 1)
                if not (v <= cur < hi):
                    return False, f"compatible release {c} requires {v} <= ver < {hi}"

        # >=3.9
        elif c.startswith(">="):
            v = _parse_semver(c[2:])
            if v and cur < v:
                return False, f"requires ver >= {v}"

        # >3.9
        elif c.startswith(">"):
            v = _parse_semver(c[1:])
            if v and cur <= v:
                return False, f"requires ver > {v}"

        # <=3.12
        elif c.startswith("<="):
            v = _parse_semver(c[2:])
            if v and cur > v:
                return False, f"requires ver <= {v}"

        # <3.13
        elif c.startswith("<"):
            v = _parse_semver(c[1:])
            if v and cur >= v:
                return False, f"requires ver < {v}"

        # ==3.10
        elif c.startswith("=="):
            v = _parse_semver(c[2:])
            if v and cur != v:
                return False, f"requires ver == {v}"

        # plain "3.9" → prefix match (allow 3.9.x)
        else:
            v = _parse_semver(c)
            if v and cur[:len(v)] != v:
                return False, f"requires ver ~= {v}"

    return True, ""


# ═══════════════════════════════════════════════════════════════
# Language version checks (semver-aware, 6+ languages)
# ═══════════════════════════════════════════════════════════════

def _check_language(
    name: str,
    version_cmd: list[str],
    version_regex: str,
    config_files: list[tuple[str, str, Optional[str]]],
    # each: (filename, key/extractor, install_fix)
    install_fix: str,
    root: str,
) -> list[CheckResult]:
    """Generic language version checker.

    config_files: list of (filename, key_or_none, fix_hint)
      - If key is a string, looks for that key in json/toml.
      - If key is None, the file itself is the version source (e.g. .python-version).
    """
    results: list[CheckResult] = []
    found = _which(version_cmd[0])
    current = ""

    if not found:
        results.append(CheckResult(
            name, "info" if name not in ("Python", "Node.js") else "warn",
            f"{name} not installed",
            fix=install_fix,
        ))
        return results

    r = _run(version_cmd)
    if r.returncode == 0:
        raw = r.stdout.strip()
        m = re.search(version_regex, raw)
        current = m.group(1) if m else raw
    results.append(CheckResult(name, "ok", f"{name} {raw.split(chr(10))[0]}" if raw else "installed"))

    # Check against each config file
    for filename, key, fix_hint in config_files:
        fpath = os.path.join(root, filename)
        if not os.path.exists(fpath):
            continue

        if key is None:
            # File content IS the version
            content = _read_file(fpath)
            if content:
                req = content.strip()
                ok, reason = _version_satisfies(current, req)
                if not ok:
                    results.append(CheckResult(
                        f"{name} version",
                        "warn",
                        f"{filename} requires {req}, got {current} ({reason})",
                        fix=fix_hint or install_fix,
                    ))
                else:
                    results.append(CheckResult(
                        f"{name} version", "ok", f"matches {filename} ({req})",
                    ))
        elif filename.endswith(".json"):
            data = _read_json(fpath)
            if data:
                val = data
                for k in key.split("."):
                    val = val.get(k, {}) if isinstance(val, dict) else {}
                if val:
                    req = str(val)
                    ok, reason = _version_satisfies(current, req)
                    if not ok:
                        results.append(CheckResult(
                            f"{name} version",
                            "warn",
                            f"{filename} {key} requires {req}, got {current} ({reason})",
                            fix=fix_hint or install_fix,
                        ))
                    else:
                        results.append(CheckResult(
                            f"{name} version", "ok", f"matches {filename} {key} ({req})",
                        ))
        elif filename == "pyproject.toml":
            content = _read_file(fpath)
            if content:
                for line in content.splitlines():
                    if key and key in line:
                        req = line.split("=", 1)[-1].strip().strip('"').strip("'")
                        ok, reason = _version_satisfies(current, req)
                        if not ok:
                            results.append(CheckResult(
                                f"{name} version",
                                "warn",
                                f"pyproject.toml requires {req}, got {current} ({reason})",
                                fix=fix_hint or install_fix,
                            ))
                        else:
                            results.append(CheckResult(
                                f"{name} version", "ok", f"matches pyproject.toml ({req})",
                            ))
                        break

    return results


def check_python(root: str) -> list[CheckResult]:
    return _check_language(
        "Python",
        [sys.executable, "--version"],
        r"(\d+\.\d+(?:\.\d+)?)",
        [
            (".python-version", None, "pyenv install <version> && pyenv local <version>"),
            ("pyproject.toml", "requires-python", None),
            ("Pipfile", "python_version", "pipenv --python <version>"),
            (".tool-versions", "python", "asdf install python <version>"),
        ],
        "Install from https://python.org or pyenv",
        root,
    )


def check_node(root: str) -> list[CheckResult]:
    return _check_language(
        "Node.js",
        ["node", "--version"],
        r"v?(\d+\.\d+\.\d+)",
        [
            (".nvmrc", None, "nvm install && nvm use"),
            ("package.json", "engines.node", None),
            (".tool-versions", "nodejs", "asdf install nodejs <version>"),
        ],
        "Install from https://nodejs.org or nvm",
        root,
    )


def check_rust(root: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    if not _which("cargo"):
        results.append(CheckResult("Rust", "info", "not installed", fix="curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"))
        return results
    r = _run(["rustc", "--version"])
    ver = r.stdout.strip()
    results.append(CheckResult("Rust", "ok", ver))
    if os.path.exists(os.path.join(root, "rust-toolchain.toml")):
        results.append(CheckResult("Rust toolchain", "info", "rust-toolchain.toml present"))
    if os.path.exists(os.path.join(root, "Cargo.toml")):
        results.append(CheckResult("Cargo.toml", "ok", "Rust project detected"))
    return results


def check_go(root: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    if not _which("go"):
        results.append(CheckResult("Go", "info", "not installed", fix="Install from https://go.dev/dl"))
        return results
    r = _run(["go", "version"])
    ver = r.stdout.strip()
    m = re.search(r"go(\d+\.\d+(?:\.\d+)?)", ver)
    current = m.group(1) if m else ver
    results.append(CheckResult("Go", "ok", ver))

    # Check go.mod
    gomod = _read_file(os.path.join(root, "go.mod"))
    if gomod:
        for line in gomod.splitlines():
            if line.startswith("go "):
                req = line.split()[1]
                ok, reason = _version_satisfies(current, req)
                if not ok:
                    results.append(CheckResult(
                        "Go version", "warn",
                        f"go.mod requires go {req}, got {current} ({reason})",
                        fix=f"Install Go {req}",
                    ))
                else:
                    results.append(CheckResult("Go version", "ok", f"matches go.mod ({req})"))
                break
        results.append(CheckResult("go.mod", "ok", "Go module detected"))
    else:
        results.append(CheckResult("go.mod", "info", "no go.mod (not a Go project)"))
    return results


def check_java(root: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    if not _which("java"):
        results.append(CheckResult("Java", "info", "not installed", fix="Install from https://adoptium.net"))
        return results
    r = _run(["java", "-version"])
    # java -version writes to stderr
    output = r.stderr or r.stdout
    m = re.search(r'version\s+"?(\d+(?:\.\d+)?)', output)
    ver = m.group(1) if m else output.splitlines()[0]
    results.append(CheckResult("Java", "ok", ver))

    # Check for Gradle / Maven
    if os.path.exists(os.path.join(root, "build.gradle")) or \
       os.path.exists(os.path.join(root, "build.gradle.kts")):
        results.append(CheckResult("Gradle", "ok", "Gradle project detected"))
    if os.path.exists(os.path.join(root, "pom.xml")):
        results.append(CheckResult("Maven", "ok", "Maven project detected"))
    if not any(os.path.exists(os.path.join(root, f)) for f in
               ["build.gradle", "build.gradle.kts", "pom.xml"]):
        results.append(CheckResult("Java build", "info", "no build.gradle or pom.xml"))
    return results


def check_ruby(root: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    if not _which("ruby"):
        results.append(CheckResult("Ruby", "info", "not installed", fix="Install from https://ruby-lang.org or rbenv"))
        return results
    r = _run(["ruby", "--version"])
    ver = r.stdout.strip()
    results.append(CheckResult("Ruby", "ok", ver))

    # .ruby-version
    rv = _read_file(os.path.join(root, ".ruby-version"))
    if rv:
        results.append(CheckResult("Ruby version", "info", f".ruby-version: {rv.strip()}"))
    if os.path.exists(os.path.join(root, "Gemfile")):
        results.append(CheckResult("Gemfile", "ok", "Ruby project detected"))
    return results


# ═══════════════════════════════════════════════════════════════
# Docker Compose
# ═══════════════════════════════════════════════════════════════

COMPOSE_FILES = [
    "docker-compose.yml", "docker-compose.yaml",
    "compose.yml", "compose.yaml",
]


def check_docker_compose(root: str) -> list[CheckResult]:
    """Detect docker-compose files and check if services are running."""
    results: list[CheckResult] = []

    compose_file = None
    for fname in COMPOSE_FILES:
        fpath = os.path.join(root, fname)
        if os.path.exists(fpath):
            compose_file = fpath
            break

    if not compose_file:
        results.append(CheckResult("Docker Compose", "info", "no compose file found"))
        return results

    results.append(CheckResult("Docker Compose", "ok", f"found {os.path.basename(compose_file)}"))

    # Check if docker + compose are available
    docker = _which("docker")
    if not docker:
        results.append(CheckResult(
            "Docker Compose status", "warn",
            "docker not installed — can't check compose services",
            fix="Install Docker Desktop",
        ))
        return results

    # Try `docker compose ps` (new syntax)
    r = _run(["docker", "compose", "ps", "--format", "json"], cwd=root, timeout=10)
    if r.returncode == 0:
        try:
            services = json.loads(r.stdout) if r.stdout.strip() else []
        except json.JSONDecodeError:
            services = []
        running = [s for s in services if s.get("State") == "running"]
        exited = [s for s in services if s.get("State") and s["State"] != "running"]

        if running:
            names = ", ".join(s.get("Name", "?") for s in running)
            results.append(CheckResult(
                "Compose services", "ok",
                f"{len(running)} running: {names}",
            ))
        if exited:
            names = ", ".join(s.get("Name", "?") for s in exited[:5])
            results.append(CheckResult(
                "Compose services", "warn",
                f"{len(exited)} not running: {names}",
                fix="docker compose up -d",
            ))
        if not services:
            results.append(CheckResult(
                "Compose services", "warn",
                "compose file found but no services running",
                fix="docker compose up -d",
            ))
    else:
        results.append(CheckResult(
            "Compose services", "info",
            "run `docker compose up -d` to start services",
            fix="docker compose up -d",
        ))

    return results


# ═══════════════════════════════════════════════════════════════
# Virtual environment / dependency detection
# ═══════════════════════════════════════════════════════════════

VENV_DIRS = [".venv", "venv", ".virtualenv", "env"]


def check_virtual_envs(root: str) -> list[CheckResult]:
    """Check if Python/Node virtual environments exist and are synced."""
    results: list[CheckResult] = []

    # Python venv
    venv_found = None
    for d in VENV_DIRS:
        p = os.path.join(root, d)
        if os.path.isdir(p):
            venv_found = p
            break

    if venv_found:
        # Check if venv python matches project
        if os.path.exists(os.path.join(venv_found, "pyvenv.cfg")):
            results.append(CheckResult("Python venv", "ok", f"found {os.path.basename(venv_found)}/"))
        else:
            results.append(CheckResult("Python venv", "ok", f"found {os.path.basename(venv_found)}/"))
    elif os.path.exists(os.path.join(root, "pyproject.toml")) or \
         os.path.exists(os.path.join(root, "requirements.txt")) or \
         os.path.exists(os.path.join(root, "setup.py")):
        results.append(CheckResult(
            "Python venv", "warn",
            "Python project detected but no virtual env",
            fix="python -m venv .venv && source .venv/bin/activate && pip install -e .",
        ))
    else:
        results.append(CheckResult("Python venv", "info", "not a Python project"))

    # Node modules
    nm = os.path.join(root, "node_modules")
    pkg_json = os.path.join(root, "package.json")
    if os.path.isdir(nm):
        results.append(CheckResult("node_modules", "ok", "installed"))
    elif os.path.exists(pkg_json):
        results.append(CheckResult(
            "node_modules", "warn",
            "package.json found but node_modules/ missing",
            fix="npm install / yarn / pnpm install",
        ))

    # Lock file consistency
    has_lock = any(os.path.exists(os.path.join(root, f))
                   for f in ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock"])
    if has_lock:
        results.append(CheckResult("Lock file", "ok", "dependency lock file present"))

    return results


# ═══════════════════════════════════════════════════════════════
# Database connectivity tests
# ═══════════════════════════════════════════════════════════════

def _try_db_connect(name: str, port: int, probe_fn: Optional[Callable] = None) -> CheckResult:
    """Try to connect to a database. Falls back to TCP if no probe_fn."""
    if not _check_port(port):
        return CheckResult(name, "info", f"not running on port {port}")

    if probe_fn:
        try:
            if probe_fn(port):
                return CheckResult(name, "ok", f"accepting connections on port {port}")
        except Exception:
            pass

    return CheckResult(name, "ok", f"port {port} is open (TCP check only)")


def check_databases(root: str) -> list[CheckResult]:
    """Test actual database connectivity where possible."""
    results: list[CheckResult] = []

    # PostgreSQL
    psql = _which("psql")
    if psql:
        r = _run(["psql", "-c", "SELECT 1", "-w"], timeout=5)
        if r.returncode == 0:
            results.append(CheckResult("PostgreSQL", "ok", "connection successful (psql)"))
        else:
            port_ok = _check_port(5432)
            results.append(CheckResult(
                "PostgreSQL",
                "ok" if port_ok else "info",
                "port 5432 open" if port_ok else "not running",
                fix="" if port_ok else "Start PostgreSQL or docker compose up -d",
            ))
    else:
        results.append(_try_db_connect("PostgreSQL", 5432))

    # Redis
    redis_cli = _which("redis-cli")
    if redis_cli:
        r = _run(["redis-cli", "PING"], timeout=5)
        if r.returncode == 0 and "PONG" in r.stdout:
            results.append(CheckResult("Redis", "ok", "PONG — connection successful"))
        else:
            port_ok = _check_port(6379)
            results.append(CheckResult(
                "Redis",
                "ok" if port_ok else "info",
                "port 6379 open" if port_ok else "not running",
            ))
    else:
        results.append(_try_db_connect("Redis", 6379))

    # MySQL
    results.append(_try_db_connect("MySQL", 3306))

    # MongoDB
    results.append(_try_db_connect("MongoDB", 27017))

    # Check DATABASE_URL in .env
    env_file = _read_file(os.path.join(root, ".env"))
    if env_file:
        for line in env_file.splitlines():
            if line.startswith("DATABASE_URL") or line.startswith("REDIS_URL"):
                results.append(CheckResult(
                    "DB config", "info",
                    f"{line.split('=')[0]} found in .env",
                ))
                break

    return results


# ═══════════════════════════════════════════════════════════════
# Tools check
# ═══════════════════════════════════════════════════════════════

TOOL_LIST = {
    "git":      "https://git-scm.com",
    "make":     "brew install make / apt install build-essential",
    "docker":   "https://docker.com",
    "curl":     "usually pre-installed",
    "ssh":      "usually pre-installed",
    "wget":     "usually pre-installed",
    "htop":     "optional system monitor",
    "jq":       "brew install jq / apt install jq",
    "tmux":     "terminal multiplexer",
}

# Detect project type → suggest relevant tools
PROJECT_TOOLS: dict[str, list[str]] = {
    "pyproject.toml": ["python", "pip", "twine", "tox", "pre-commit"],
    "package.json":   ["node", "npm", "npx"],
    "Cargo.toml":     ["cargo", "rustc", "rustup"],
    "go.mod":         ["go", "gofmt"],
    "Gemfile":        ["ruby", "bundle"],
    "Makefile":       ["make"],
    "Dockerfile":     ["docker", "hadolint"],
    ".github/":       ["gh"],
}


def check_tools(root: str) -> list[CheckResult]:
    """Check essential + project-relevant dev tools."""
    results: list[CheckResult] = []

    # Core tools
    for tool, fix in TOOL_LIST.items():
        path = _which(tool)
        if path:
            results.append(CheckResult(tool.capitalize(), "ok", path))
        else:
            results.append(CheckResult(
                tool.capitalize(), "info",
                f"{tool} not installed",
                fix=fix,
            ))

    # Project-specific suggested tools
    suggested: set[str] = set()
    for indicator, tools in PROJECT_TOOLS.items():
        if os.path.exists(os.path.join(root, indicator)):
            suggested.update(tools)

    for tool in sorted(suggested):
        if tool not in TOOL_LIST and not _which(tool):
            results.append(CheckResult(
                tool.capitalize(),
                "info",
                f"recommended for this project (not installed)",
            ))

    return results


# ═══════════════════════════════════════════════════════════════
# Ports
# ═══════════════════════════════════════════════════════════════

COMMON_PORTS = {
    3000: "React / Next.js",
    5173: "Vite",
    8080: "HTTP dev server",
    8000: "Django / Flask",
    4200: "Angular",
    9000: "SonarQube / PHP",
    5000: "Flask / Express",
    4000: "Jekyll / Phoenix",
    11434: "Ollama",
}


def check_ports(root: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    busy, free = [], []
    for port in COMMON_PORTS:
        (busy if _check_port(port) else free).append(port)

    if busy:
        results.append(CheckResult(
            "Ports in use",
            "info",
            ", ".join(f"{p} ({COMMON_PORTS[p]})" for p in busy),
        ))
    if free:
        results.append(CheckResult(
            "Ports free",
            "ok",
            ", ".join(str(p) for p in free[:8]) + (f" +{len(free)-8} more" if len(free) > 8 else ""),
        ))
    return results


# ═══════════════════════════════════════════════════════════════
# Environment variables
# ═══════════════════════════════════════════════════════════════

def check_env_vars(root: str) -> list[CheckResult]:
    results: list[CheckResult] = []

    example = _read_file(os.path.join(root, ".env.example"))
    env_file = _read_file(os.path.join(root, ".env"))

    if not example:
        # Also try .env.template, .env.sample, env.example
        for alt in [".env.template", ".env.sample", "env.example"]:
            example = _read_file(os.path.join(root, alt))
            if example:
                break

    if not example:
        results.append(CheckResult(".env", "info", "no .env.example or template found"))
        return results

    example_keys: set[str] = set()
    for line in example.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key = line.split("=")[0].strip().split("#")[0].strip()
            if key:
                example_keys.add(key)

    if not env_file:
        results.append(CheckResult(
            ".env", "warn",
            f".env.example exists but .env missing ({len(example_keys)} vars needed)",
            fix="cp .env.example .env and fill in real values",
        ))
        return results

    env_keys: set[str] = set()
    for line in env_file.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key = line.split("=")[0].strip()
            if key:
                env_keys.add(key)

    missing = example_keys - env_keys
    extra = env_keys - example_keys

    if missing:
        results.append(CheckResult(
            "Missing env vars",
            "warn",
            f"{len(missing)} missing: {', '.join(sorted(missing)[:8])}"
            + ("…" if len(missing) > 8 else ""),
            fix="Add missing keys to .env",
        ))
    else:
        results.append(CheckResult("Env vars", "ok", f"all {len(env_keys)} vars configured"))

    if extra:
        results.append(CheckResult(
            "Extra env vars",
            "info",
            f"{len(extra)} keys in .env not in .env.example",
        ))

    return results


# ═══════════════════════════════════════════════════════════════
# System resources
# ═══════════════════════════════════════════════════════════════

def check_system(root: str) -> list[CheckResult]:
    results: list[CheckResult] = []

    # OS
    results.append(CheckResult(
        "OS", "ok",
        f"{platform.system()} {platform.release()} ({platform.machine()})",
    ))

    # Disk
    try:
        usage = shutil.disk_usage(root)
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        label, status = (
            ("error", "error") if free_gb < 5 else
            ("warn", "warn") if free_gb < 20 else
            ("ok", "ok")
        )
        results.append(CheckResult(
            "Disk space", status,
            f"{free_gb:.0f} GB free / {total_gb:.0f} GB",
            fix="Free up disk space" if free_gb < 20 else "",
        ))
    except Exception:
        pass

    # Memory / CPU (cross-platform)
    try:
        import psutil
        mem = psutil.virtual_memory()
        mem_gb = mem.total / (1024**3)
        mem_free = mem.available / (1024**3)
        cpu_pct = psutil.cpu_percent(interval=0.1)
        results.append(CheckResult(
            "Memory", "ok" if mem_free > 2 else "warn",
            f"{mem_free:.1f} GB available / {mem_gb:.0f} GB total",
        ))
        results.append(CheckResult(
            "CPU", "ok" if cpu_pct < 90 else "warn",
            f"{cpu_pct:.0f}% used",
        ))
    except ImportError:
        # Fallback: try platform-specific commands
        if platform.system() == "Windows":
            r = _run(["wmic", "OS", "get", "TotalVisibleMemorySize,FreePhysicalMemory", "/Value"], timeout=10)
            if r.returncode == 0:
                results.append(CheckResult("Memory", "info", "install `psutil` for detailed memory info"))
        else:
            r = _run(["free", "-h"], timeout=5)
            if r.returncode == 0:
                results.append(CheckResult("Memory", "info", r.stdout.splitlines()[1] if len(r.stdout.splitlines()) > 1 else "available"))
    except Exception:
        pass

    # Package manager
    for pm in ["brew", "apt", "choco", "winget", "yum", "dnf", "pacman", "scoop"]:
        if _which(pm):
            results.append(CheckResult("Package manager", "ok", pm))
            break
    else:
        results.append(CheckResult("Package manager", "info", "none detected"))

    return results


# ═══════════════════════════════════════════════════════════════
# Project config
# ═══════════════════════════════════════════════════════════════

def check_project_config(root: str) -> list[CheckResult]:
    """Detect project type and config quality."""
    results: list[CheckResult] = []

    # Detect project type
    indicators = {
        "pyproject.toml": "Python",
        "package.json": "Node.js",
        "Cargo.toml": "Rust",
        "go.mod": "Go",
        "Gemfile": "Ruby",
        "build.gradle": "Java/Gradle",
        "pom.xml": "Java/Maven",
        "CMakeLists.txt": "C++/CMake",
        "Makefile": "C/Make",
        "Dockerfile": "Docker",
    }

    detected: list[str] = []
    for fname, label in indicators.items():
        if os.path.exists(os.path.join(root, fname)):
            detected.append(label)

    if detected:
        results.append(CheckResult(
            "Project type", "ok",
            ", ".join(detected),
        ))
    else:
        results.append(CheckResult(
            "Project type", "info",
            "unknown (no standard project files found)",
        ))

    # CI/CD
    ci_indicators = {
        ".github/workflows": "GitHub Actions",
        ".gitlab-ci.yml": "GitLab CI",
        "Jenkinsfile": "Jenkins",
        ".circleci": "CircleCI",
        ".travis.yml": "Travis CI",
    }
    ci_found = []
    for path, name in ci_indicators.items():
        if os.path.exists(os.path.join(root, path)):
            ci_found.append(name)

    if ci_found:
        results.append(CheckResult("CI/CD", "ok", ", ".join(ci_found)))
    elif detected:
        results.append(CheckResult(
            "CI/CD", "info",
            "no CI config detected",
            fix="Consider adding GitHub Actions for CI",
        ))

    # Pre-commit hooks
    if os.path.exists(os.path.join(root, ".pre-commit-config.yaml")):
        results.append(CheckResult("Pre-commit", "ok", "configured"))
    elif detected:
        results.append(CheckResult(
            "Pre-commit", "info",
            "not configured",
            fix="pip install pre-commit && pre-commit install",
        ))

    # Linter/formatter config
    linters = {
        ".eslintrc.js": "ESLint", ".eslintrc.json": "ESLint", ".eslintrc.cjs": "ESLint",
        "eslint.config.js": "ESLint",
        ".prettierrc": "Prettier", ".prettierrc.json": "Prettier",
        "prettier.config.js": "Prettier",
        ".pylintrc": "Pylint",
        "pyproject.toml": None,  # checked separately for [tool.ruff] etc.
        ".rubocop.yml": "RuboCop",
        ".golangci.yml": "golangci-lint",
    }
    linter_found = set()
    for fname, tool in linters.items():
        if os.path.exists(os.path.join(root, fname)):
            if tool:
                linter_found.add(tool)

    # Check pyproject.toml for ruff/black
    ppt = _read_file(os.path.join(root, "pyproject.toml"))
    if ppt:
        if "ruff" in ppt:
            linter_found.add("Ruff")
        if "black" in ppt:
            linter_found.add("Black")

    if linter_found:
        results.append(CheckResult("Linters", "ok", ", ".join(sorted(linter_found))))
    elif detected:
        results.append(CheckResult(
            "Linters", "info",
            "no linter config found",
            fix="Consider adding ruff/eslint/golangci-lint",
        ))

    return results


# ═══════════════════════════════════════════════════════════════
# .envcheck.toml config support
# ═══════════════════════════════════════════════════════════════

def load_config(root: str) -> dict:
    """Load .envcheck.toml project config if present."""
    config_path = os.path.join(root, ".envcheck.toml")
    if not os.path.exists(config_path):
        return {}

    content = _read_file(config_path)
    if not content:
        return {}

    config: dict = {
        "ignore": [],
        "required_tools": [],
        "required_ports": [],
        "required_env_vars": [],
        "custom_checks": [],
    }

    current_section = None
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Section header
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1]
            continue

        if "=" in line and current_section is None:
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip().strip('"').strip("'")

            if key == "ignore" and val:
                config["ignore"] = [v.strip() for v in val.split(",")]
            elif key == "required_tools" and val:
                config["required_tools"] = [v.strip() for v in val.split(",")]
            elif key == "required_ports" and val:
                config["required_ports"] = [int(v.strip()) for v in val.split(",")]

    return config


def check_custom_requirements(root: str, config: dict) -> list[CheckResult]:
    """Run checks defined in .envcheck.toml."""
    results: list[CheckResult] = []

    for tool in config.get("required_tools", []):
        if not _which(tool):
            results.append(CheckResult(
                f"Required: {tool}",
                "error",
                f"'{tool}' is required by .envcheck.toml but not installed",
                fix=f"Install {tool}",
            ))
        else:
            results.append(CheckResult(f"Required: {tool}", "ok", "installed"))

    for port in config.get("required_ports", []):
        if _check_port(port):
            results.append(CheckResult(
                f"Required port {port}", "ok", f"port {port} is listening",
            ))
        else:
            results.append(CheckResult(
                f"Required port {port}",
                "error",
                f"port {port} is required but not listening",
                fix=f"Start the service on port {port}",
            ))

    return results


# ═══════════════════════════════════════════════════════════════
# Run all
# ═══════════════════════════════════════════════════════════════

def run_all_checks(root: str = ".", config: Optional[dict] = None) -> list[CheckResult]:
    root = os.path.abspath(root)
    if config is None:
        config = load_config(root)
    ignore_list = config.get("ignore", [])

    all_results: list[CheckResult] = []

    modules: list[tuple[str, list[Callable]]] = [
        ("Project",      [check_project_config]),
        ("Languages",    [check_python, check_node, check_rust, check_go, check_java, check_ruby]),
        ("Dependencies", [check_virtual_envs]),
        ("Docker",       [check_docker_compose]),
        ("Databases",    [check_databases]),
        ("Tools",        [check_tools]),
        ("Ports",        [check_ports]),
        ("Env Vars",     [check_env_vars]),
        ("System",       [check_system]),
        ("Custom",       [lambda r=root: check_custom_requirements(r, config)]),
    ]

    for _group, funcs in modules:
        for func in funcs:
            try:
                results = func(root)
                # Filter out ignored check names
                results = [r for r in results if r.name not in ignore_list]
                all_results.extend(results)
            except Exception as e:
                all_results.append(CheckResult(
                    func.__name__, "error", f"check failed: {e}"
                ))

    return all_results