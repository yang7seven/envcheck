"""Rich rendering for envcheck"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from .checks import CheckResult, Status

console = Console()

STATUS_ICONS: dict[Status, str] = {
    "ok":    "✅",
    "warn":  "⚠️",
    "error": "❌",
    "info":  "ℹ️",
}

STATUS_STYLES: dict[Status, str] = {
    "ok":    "green",
    "warn":  "yellow",
    "error": "bold red",
    "info":  "dim",
}


def print_report(results: list[CheckResult], root: str, verbose: bool = False):
    """Print the full environment report"""
    # Header
    ok_count = sum(1 for r in results if r.status == "ok")
    warn_count = sum(1 for r in results if r.status == "warn")
    err_count = sum(1 for r in results if r.status == "error")
    info_count = sum(1 for r in results if r.status == "info")

    # Health score: errors are bad
    total = len(results)
    score = max(0, 100 - (warn_count * 5 + err_count * 15)) if total > 0 else 100
    color = "green" if score >= 80 else ("yellow" if score >= 50 else "red")

    console.print()
    console.print(Panel(
        Text.assemble(
            ("🏥 envcheck — ", "bold"),
            (root, "bold white"),
            ("\n", ""),
            (f"健康分 {score}/100  ", f"bold {color}"),
            (f"✅{ok_count} ⚠️{warn_count} ❌{err_count} ℹ️{info_count}", ""),
        ),
        border_style=color,
    ))
    console.print()

    # Group results
    groups = {
        "语言运行时": [],
        "开发工具": [],
        "后台服务": [],
        "网络端口": [],
        "环境变量": [],
        "系统资源": [],
        "其它": [],
    }

    group_map = {
        "Python 版本": "语言运行时", "Python 版本匹配": "语言运行时", "Python 版本要求": "语言运行时",
        "Node.js": "语言运行时", "Node 版本匹配": "语言运行时", "Node engines": "语言运行时",
        "Rust": "语言运行时", "Rust toolchain": "语言运行时",
        "Git": "开发工具", "Make": "开发工具", "Docker": "开发工具",
        "Curl": "开发工具", "Ssh": "开发工具",
        "PostgreSQL": "后台服务", "Redis": "后台服务", "MySQL": "后台服务",
        "MongoDB": "后台服务",
        "端口占用": "网络端口", "可用端口": "网络端口",
        "环境变量": "环境变量", "环境变量缺失": "环境变量", "额外环境变量": "环境变量",
        ".env": "环境变量",
        "操作系统": "系统资源", "磁盘空间": "系统资源", "包管理器": "系统资源",
    }

    for r in results:
        g = group_map.get(r.name, "其它")
        groups[g].append(r)

    # Render each group
    for group_name in ["语言运行时", "开发工具", "后台服务", "网络端口", "环境变量", "系统资源"]:
        items = groups.get(group_name, [])
        if not items:
            continue

        console.print(f"  ── {group_name} ──", style="bold underline")

        table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        table.add_column("icon", width=2)
        table.add_column("name", width=16)
        table.add_column("message", ratio=1)
        table.add_column("fix", ratio=1)

        for r in items:
            icon = STATUS_ICONS.get(r.status, "?")
            style = STATUS_STYLES.get(r.status, "")
            table.add_row(
                icon,
                Text(r.name, style="bold"),
                Text(r.message, style=style),
                Text(r.fix, style="dim") if r.fix and verbose else Text(r.detail, style="dim"),
            )

        console.print(table)

    # Errors summary
    errors = [r for r in results if r.status == "error"]
    if errors:
        console.print()
        console.print("  ❌ 必须修复:", style="bold red")
        for r in errors:
            console.print(f"     • {r.name}: {r.message}")

    warnings = [r for r in results if r.status == "warn"]
    if warnings:
        console.print()
        console.print("  ⚠️ 建议修复:", style="bold yellow")
        for r in warnings[:8]:
            fix_hint = f" → {r.fix}" if r.fix else ""
            console.print(f"     • {r.name}: {r.message}{fix_hint}")

    console.print()


def print_json(results: list[CheckResult], root: str):
    """JSON output"""
    import json
    ok_count = sum(1 for r in results if r.status == "ok")
    warn_count = sum(1 for r in results if r.status == "warn")
    err_count = sum(1 for r in results if r.status == "error")

    output = {
        "root": root,
        "ok": ok_count,
        "warn": warn_count,
        "error": err_count,
        "health_score": max(0, 100 - (warn_count * 5 + err_count * 15)),
        "results": [
            {
                "name": r.name,
                "status": r.status,
                "message": r.message,
                "fix": r.fix,
            }
            for r in results
        ],
    }
    console.print(json.dumps(output, ensure_ascii=False, indent=2))