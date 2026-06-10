"""envcheck auto-fixer — one command to fix common issues"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Optional

from .checks import _which, _run, CheckResult


def _can_fix(result: CheckResult) -> bool:
    """Check if this issue has a known auto-fix."""
    fixable = [
        "node_modules",
        "Python venv",
        "Compose services",
        ".env",
    ]
    return any(f in result.name for f in fixable)


def apply_fixes(results: list[CheckResult], root: str, dry_run: bool = False) -> list[str]:
    """Attempt to auto-fix issues. Returns list of actions taken."""
    actions: list[str] = []

    for r in results:
        if r.status not in ("warn", "error"):
            continue

        # Missing node_modules
        if "node_modules" in r.name and r.status == "warn":
            if os.path.exists(os.path.join(root, "package.json")):
                pm = _detect_node_pm(root)
                if not dry_run:
                    _run([pm, "install"], cwd=root, timeout=120)
                actions.append(f"Ran `{pm} install`")

        # Missing Python venv
        if "Python venv" in r.name and r.status == "warn":
            venv_path = os.path.join(root, ".venv")
            if not dry_run:
                _run([sys.executable, "-m", "venv", venv_path], timeout=60)
            actions.append("Created .venv/")

            # Install package if pyproject.toml
            if os.path.exists(os.path.join(root, "pyproject.toml")):
                pip = os.path.join(venv_path, "Scripts", "pip.exe") if sys.platform == "win32" \
                    else os.path.join(venv_path, "bin", "pip")
                if not dry_run:
                    _run([pip, "install", "-e", "."], cwd=root, timeout=120)
                actions.append("Ran `pip install -e .` in .venv")

        # Compose services down
        if "Compose services" in r.name:
            if not dry_run:
                _run(["docker", "compose", "up", "-d"], cwd=root, timeout=120)
            actions.append("Ran `docker compose up -d`")

        # Missing .env
        if ".env" in r.name and "missing" in r.message.lower() and not r.name.startswith("Required"):
            example_paths = [
                os.path.join(root, ".env.example"),
                os.path.join(root, ".env.template"),
                os.path.join(root, ".env.sample"),
            ]
            for src in example_paths:
                if os.path.exists(src):
                    dst = os.path.join(root, ".env")
                    if not dry_run:
                        shutil.copy(src, dst)
                    actions.append(f"Copied {os.path.basename(src)} → .env")
                    break

    return actions


def _detect_node_pm(root: str) -> str:
    """Detect which Node.js package manager to use."""
    if os.path.exists(os.path.join(root, "pnpm-lock.yaml")):
        return "pnpm"
    if os.path.exists(os.path.join(root, "yarn.lock")):
        return "yarn"
    return "npm"