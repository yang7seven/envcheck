"""Rich rendering for envcheck v2 — compact, verbose, and summary modes"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from .checks import CheckResult, Status

console = Console()

ICONS: dict[Status, str] = {
    "ok": "✅", "warn": "⚠️", "error": "❌", "info": "ℹ️",
}
STYLES: dict[Status, str] = {
    "ok": "green", "warn": "yellow", "error": "bold red", "info": "dim",
}


def _health_score(results: list[CheckResult]) -> int:
    total = len(results)
    if total == 0:
        return 100
    warn_count = sum(1 for r in results if r.status == "warn")
    err_count = sum(1 for r in results if r.status == "error")
    return max(0, 100 - (warn_count * 5 + err_count * 15))


def _counts(results: list[CheckResult]) -> tuple[int, int, int, int]:
    return (
        sum(1 for r in results if r.status == "ok"),
        sum(1 for r in results if r.status == "warn"),
        sum(1 for r in results if r.status == "error"),
        sum(1 for r in results if r.status == "info"),
    )


def print_summary(results: list[CheckResult], root: str):
    """Ultra-compact one-line-per-issue output."""
    score = _health_score(results)
    color = "green" if score >= 80 else ("yellow" if score >= 50 else "red")
    console.print()
    console.print(f"🏥 [bold]{root}[/]  health [bold {color}]{score}/100[/]")

    for r in results:
        if r.status in ("warn", "error"):
            icon = ICONS[r.status]
            fix = f" → {r.fix}" if r.fix else ""
            console.print(f"  {icon} {r.name}: {r.message}{fix}")


def print_compact(results: list[CheckResult], root: str):
    """Grouped view, only show issues."""
    score = _health_score(results)
    ok, warn, err, info = _counts(results)
    color = "green" if score >= 80 else ("yellow" if score >= 50 else "red")

    console.print()
    console.print(Panel(
        Text.assemble(
            ("🏥 envcheck — ", "bold"),
            (root, "bold white"),
            (f"\nHealth {score}/100  ", f"bold {color}"),
            (f"✅{ok} ⚠️{warn} ❌{err} ℹ️{info}", ""),
        ),
        border_style=color,
    ))

    # Only show warnings and errors
    issues = [r for r in results if r.status in ("warn", "error")]
    if not issues:
        console.print("  ✅ All checks passed!", style="bold green")
        return

    # Group issues
    groups: dict[str, list[CheckResult]] = {}
    group_order = [
        "Languages", "Dependencies", "Docker", "Databases",
        "Tools", "Ports", "Env Vars", "System", "Project", "Custom",
    ]
    for g in group_order:
        groups[g] = []

    _group_map = {
        "Python": "Languages", "Python version": "Languages",
        "Node.js": "Languages", "Node.js version": "Languages",
        "Rust": "Languages", "Rust toolchain": "Languages", "Cargo.toml": "Languages",
        "Go": "Languages", "Go version": "Languages", "go.mod": "Languages",
        "Java": "Languages", "Gradle": "Languages", "Maven": "Languages",
        "Ruby": "Languages", "Ruby version": "Languages", "Gemfile": "Languages",
        "Python venv": "Dependencies", "node_modules": "Dependencies",
        "Lock file": "Dependencies",
        "Docker Compose": "Docker", "Compose services": "Docker",
        "Docker Compose status": "Docker",
        "PostgreSQL": "Databases", "Redis": "Databases", "MySQL": "Databases",
        "MongoDB": "Databases", "DB config": "Databases",
    }

    for r in issues:
        g = _group_map.get(r.name, "Tools" if r.name.capitalize() in
            ["Git", "Make", "Docker", "Curl", "Ssh", "Wget", "Htop", "Jq", "Tmux"]
            else ("Ports" if "port" in r.name.lower() else
                  ("Env Vars" if "env" in r.name.lower() else
                   ("System" if r.name in ("OS", "Disk space", "Memory", "CPU", "Package manager") else
                    ("Project" if r.name in ("Project type", "CI/CD", "Pre-commit", "Linters") else
                     "Custom")))))
        if r.name.startswith("Required"):
            g = "Custom"
        groups.setdefault(g, []).append(r)

    for g in group_order:
        items = groups.get(g, [])
        if items:
            console.print(f"  ── {g} ──", style="bold underline")
            for r in items:
                icon = ICONS[r.status]
                style = STYLES[r.status]
                fix = f" → [dim]{r.fix}[/]" if r.fix else ""
                console.print(f"    {icon} [{style}]{r.name}[/]: {r.message}{fix}")

    console.print()


def print_verbose(results: list[CheckResult], root: str):
    """Full output with all checks, including passed ones."""
    score = _health_score(results)
    ok, warn, err, info = _counts(results)
    color = "green" if score >= 80 else ("yellow" if score >= 50 else "red")

    console.print()
    console.print(Panel(
        Text.assemble(
            ("🏥 envcheck — ", "bold"),
            (root, "bold white"),
            (f"\nHealth {score}/100  ", f"bold {color}"),
            (f"✅{ok} ⚠️{warn} ❌{err} ℹ️{info}", ""),
        ),
        border_style=color,
    ))
    console.print()

    # Group ALL results
    groups: dict[str, list[CheckResult]] = {}
    for r in results:
        g = "Other"
        for prefix in ["Python", "Node.js", "Rust", "Go", "Java", "Ruby", "Cargo", "Gemfile"]:
            if r.name.startswith(prefix):
                g = "Languages"
                break
        for kw in ["venv", "node_modules", "Lock"]:
            if kw in r.name:
                g = "Dependencies"
                break
        for kw in ["Compose", "Compose service"]:
            if kw in r.name:
                g = "Docker"
                break
        for db in ["PostgreSQL", "Redis", "MySQL", "MongoDB", "DB config"]:
            if r.name == db:
                g = "Databases"
                break
        for tool in ["Git", "Make", "Docker", "Curl", "Ssh", "Wget", "Htop", "Jq", "Tmux"]:
            if r.name == tool:
                g = "Tools"
                break
        if "port" in r.name.lower():
            g = "Ports"
        if "env" in r.name.lower() and "envcheck" not in r.name.lower():
            g = "Env Vars"
        for sys_name in ["OS", "Disk space", "Memory", "CPU", "Package manager"]:
            if r.name == sys_name:
                g = "System"
                break
        for proj_name in ["Project type", "CI/CD", "Pre-commit", "Linters"]:
            if r.name == proj_name:
                g = "Project"
                break

        groups.setdefault(g, []).append(r)

    for g_name in ["Languages", "Dependencies", "Docker", "Databases",
                    "Tools", "Ports", "Env Vars", "Project", "System", "Custom"]:
        items = groups.get(g_name, [])
        if not items:
            continue

        console.print(f"  ── {g_name} ──", style="bold underline")
        table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        table.add_column("", width=2)
        table.add_column("Check", width=18)
        table.add_column("Status", ratio=1)
        table.add_column("Fix", ratio=1)

        for r in items:
            icon = ICONS[r.status]
            style = STYLES[r.status]
            table.add_row(
                icon,
                Text(r.name, style="bold"),
                Text(r.message, style=style),
                Text(r.fix, style="dim") if r.fix else Text(r.detail, style="dim"),
            )

        console.print(table)

    console.print()


def print_json(results: list[CheckResult], root: str):
    score = _health_score(results)
    ok, warn, err, info = _counts(results)
    output = {
        "root": root,
        "health_score": score,
        "ok": ok, "warn": warn, "error": err, "info": info,
        "results": [
            {"name": r.name, "status": r.status, "message": r.message, "fix": r.fix}
            for r in results
        ],
    }
    console.print(json.dumps(output, ensure_ascii=False, indent=2))


import json  # noqa: E402 (import at top but referenced in function)