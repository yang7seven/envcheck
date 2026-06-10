"""envcheck CLI — dev environment doctor"""

from __future__ import annotations

import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import typer

from .checks import run_all_checks
from .display import print_report, print_json, console

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
    json_output: bool = typer.Option(
        False, "--json", "-j",
        help="JSON output for scripting/CI",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Show fix suggestions inline",
    ),
):
    """Run all environment checks on a project"""
    root = os.path.abspath(os.path.expanduser(path))

    if not os.path.isdir(root):
        console.print(f"❌ Directory not found: {root}", style="bold red")
        raise typer.Exit(code=1)

    results = run_all_checks(root)

    if json_output:
        print_json(results, root)
    else:
        print_report(results, root, verbose=verbose)

    # Exit code based on errors
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
    """Quick onboarding check — what do I need to install to start contributing?"""
    root = os.path.abspath(os.path.expanduser(path))
    results = run_all_checks(root)

    errors = [r for r in results if r.status == "error"]
    warnings = [r for r in results if r.status == "warn"]

    console.print()
    console.print("🚀 快速上手检查", style="bold")
    console.print(f"   项目: {root}")
    console.print()

    if errors:
        console.print("必须先安装/修复:", style="bold red")
        for r in errors:
            console.print(f"  ❌ {r.name}: {r.message}")
            if r.fix:
                console.print(f"     → {r.fix}", style="dim")

    if warnings:
        console.print()
        console.print("建议处理:", style="bold yellow")
        for r in warnings:
            console.print(f"  ⚠️ {r.name}: {r.message}")
            if r.fix:
                console.print(f"     → {r.fix}", style="dim")

    if not errors and not warnings:
        console.print("  ✅ 环境一切就绪，可以开始开发！", style="bold green")

    console.print()


def main():
    app()


if __name__ == "__main__":
    main()