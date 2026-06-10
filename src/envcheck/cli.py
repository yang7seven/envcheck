"""envcheck CLI v2 — dev environment doctor"""

from __future__ import annotations

import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import typer

from .checks import run_all_checks, load_config
from .display import (
    print_compact, print_verbose, print_summary, print_json, console,
)
from .fixer import apply_fixes

app = typer.Typer(
    name="envcheck",
    help="Dev environment doctor — check your entire dev setup in one command",
    add_completion=False,
)


@app.callback()
def common():
    pass


@app.command()
def check(
    path: str = typer.Argument(
        ".",
        help="Project directory to check (default: current)",
    ),
    mode: str = typer.Option(
        "compact",
        "--mode", "-m",
        help="Output mode: compact (issues only), verbose (all), summary (one-liners), json",
    ),
    json_output: bool = typer.Option(
        False, "--json", "-j",
        help="JSON output for scripting/CI (shorthand for --mode json)",
    ),
):
    """Run all environment checks on a project."""
    root = os.path.abspath(os.path.expanduser(path))

    if not os.path.isdir(root):
        console.print(f"❌ Directory not found: {root}", style="bold red")
        raise typer.Exit(code=1)

    config = load_config(root)
    results = run_all_checks(root, config)

    if json_output:
        mode = "json"

    if mode == "json":
        print_json(results, root)
    elif mode == "verbose":
        print_verbose(results, root)
    elif mode == "summary":
        print_summary(results, root)
    else:
        print_compact(results, root)

    err_count = sum(1 for r in results if r.status == "error")
    if err_count > 0:
        raise typer.Exit(code=2)


@app.command()
def onboard(
    path: str = typer.Argument(
        ".",
        help="Project directory",
    ),
):
    """Quick onboarding — what do I need to install to start contributing?"""
    root = os.path.abspath(os.path.expanduser(path))
    config = load_config(root)
    results = run_all_checks(root, config)

    errors = [r for r in results if r.status == "error"]
    warnings = [r for r in results if r.status == "warn"]

    console.print()
    console.print("🚀 Onboarding Check", style="bold")
    console.print(f"   Project: {root}")
    console.print()

    if errors:
        console.print("Must fix first:", style="bold red")
        for r in errors:
            console.print(f"  ❌ {r.name}: {r.message}")
            if r.fix:
                console.print(f"     → {r.fix}", style="dim")

    if warnings:
        console.print()
        console.print("Recommended:", style="bold yellow")
        for r in warnings:
            console.print(f"  ⚠️ {r.name}: {r.message}")
            if r.fix:
                console.print(f"     → {r.fix}", style="dim")

    if not errors and not warnings:
        console.print("  ✅ All good — ready to code!", style="bold green")

    # Quick summary of what's installed
    console.print()
    console.print("Quick status:", style="bold")
    for r in results:
        if r.status in ("ok",) and r.name in (
            "Python", "Node.js", "Docker", "Git", "Project type",
        ):
            console.print(f"  ✅ {r.name}: {r.message}")

    console.print()


@app.command()
def fix(
    path: str = typer.Argument(
        ".",
        help="Project directory",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n",
        help="Show what would be done, don't actually do it",
    ),
):
    """Auto-fix common issues (missing venv, node_modules, .env, etc.)."""
    root = os.path.abspath(os.path.expanduser(path))
    config = load_config(root)
    results = run_all_checks(root, config)

    issues = [r for r in results if r.status in ("warn", "error")]
    if not issues:
        console.print("✅ Nothing to fix!", style="bold green")
        return

    console.print()
    if dry_run:
        console.print("🔍 Dry run — showing what would be fixed:", style="bold")
        for r in issues:
            if r.fix:
                console.print(f"  • {r.name}: {r.fix}")
    else:
        console.print("🔧 Auto-fixing...", style="bold")
        actions = apply_fixes(issues, root, dry_run=False)
        if actions:
            for a in actions:
                console.print(f"  ✅ {a}")
        else:
            console.print("  ℹ️ No auto-fixable issues found (manual fixes needed)")
        console.print()
        console.print("Re-run `envcheck check` to verify.", style="dim")


@app.command()
def init(
    path: str = typer.Argument(
        ".",
        help="Project directory",
    ),
):
    """Create a .envcheck.toml config file for this project."""
    root = os.path.abspath(os.path.expanduser(path))
    config_path = os.path.join(root, ".envcheck.toml")

    if os.path.exists(config_path):
        console.print(f"⚠️ {config_path} already exists", style="yellow")
        raise typer.Exit(code=1)

    template = '''# envcheck project configuration
# See https://github.com/yang7seven/envcheck

# Checks to skip (comma-separated)
# ignore = "MongoDB,Redis"

# Tools required for this project
# required_tools = "docker,just,pre-commit"

# Ports that must be listening
# required_ports = "5432,6379"
'''

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(template)

    console.print(f"✅ Created {config_path}", style="bold green")
    console.print("   Edit this file to customize envcheck for your project.", style="dim")


def main():
    app()


if __name__ == "__main__":
    main()