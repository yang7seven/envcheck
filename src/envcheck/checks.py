"""envcheck core checks — everything a dev environment needs"""

from __future__ import annotations

import os
import sys
import subprocess
import socket
import shutil
import platform
from dataclasses import dataclass, field
from typing import Optional, Literal

Status = Literal["ok", "warn", "error", "info"]


@dataclass
class CheckResult:
    name: str
    status: Status
    message: str
    detail: str = ""
    fix: str = ""  # how to fix


def _run(cmd: list[str], timeout: int = 10, **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
            **kwargs,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return subprocess.CompletedProcess(cmd, -1, "", "timeout/not found")


def _which(tool: str) -> Optional[str]:
    return shutil.which(tool)


def _check_port(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is in use (i.e., a service is listening)"""
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


# ═══════════════════════════════════════════════════════════════
# Language version checks
# ═══════════════════════════════════════════════════════════════

def check_python(root: str) -> list[CheckResult]:
    """Python version vs project requirements"""
    results: list[CheckResult] = []

    current = platform.python_version()
    results.append(CheckResult("Python 版本", "ok", f"Python {current}", f"路径: {sys.executable}"))

    # Check .python-version (pyenv)
    pv = _read_file(os.path.join(root, ".python-version"))
    if pv:
        pv = pv.strip()
        if pv not in current:
            results.append(CheckResult(
                "Python 版本匹配",
                "warn",
                f".python-version 要求 {pv}，当前是 {current}",
                fix=f"pyenv install {pv} && pyenv local {pv}",
            ))
        else:
            results.append(CheckResult("Python 版本匹配", "ok", f"匹配 .python-version ({pv})"))

    # Check pyproject.toml requires-python
    ppt = _read_file(os.path.join(root, "pyproject.toml"))
    if ppt and "requires-python" in ppt:
        # Simple extraction (not a full TOML parser)
        for line in ppt.splitlines():
            if "requires-python" in line:
                req = line.split("=", 1)[-1].strip().strip('"').strip("'")
                results.append(CheckResult(
                    "Python 版本要求",
                    "info",
                    f"pyproject.toml 要求: {req}",
                ))
                break

    return results


def check_node(root: str) -> list[CheckResult]:
    """Node.js version check"""
    results: list[CheckResult] = []

    node_path = _which("node")
    if not node_path:
        results.append(CheckResult(
            "Node.js", "warn", "未安装 Node.js",
            fix="从 https://nodejs.org 安装",
        ))
        return results

    r = _run(["node", "--version"])
    ver = r.stdout.strip()
    results.append(CheckResult("Node.js", "ok", ver if ver else "已安装"))

    # Check .nvmrc
    nvmrc = _read_file(os.path.join(root, ".nvmrc"))
    if nvmrc:
        nvmrc = nvmrc.strip().lstrip("v")
        if nvmrc not in ver:
            results.append(CheckResult(
                "Node 版本匹配",
                "warn",
                f".nvmrc 要求 {nvmrc}，当前是 {ver}",
                fix=f"nvm install {nvmrc} && nvm use {nvmrc}",
            ))

    # Check package.json engines
    pkg = _read_file(os.path.join(root, "package.json"))
    if pkg:
        try:
            import json
            data = json.loads(pkg)
            engines = data.get("engines", {})
            if engines.get("node"):
                results.append(CheckResult(
                    "Node engines",
                    "info",
                    f"package.json 要求 node {engines['node']}",
                ))
        except Exception:
            pass

    return results


def check_rust(root: str) -> list[CheckResult]:
    """Rust version check"""
    results: list[CheckResult] = []

    cargo_path = _which("cargo")
    if not cargo_path:
        results.append(CheckResult("Rust", "info", "未安装 Rust（如不需要可忽略）"))
        return results

    r = _run(["rustc", "--version"])
    ver = r.stdout.strip()
    results.append(CheckResult("Rust", "ok", ver if ver else "已安装"))

    # Check rust-toolchain.toml
    rtt = _read_file(os.path.join(root, "rust-toolchain.toml"))
    if rtt:
        results.append(CheckResult("Rust toolchain", "info", "rust-toolchain.toml 存在"))

    return results


# ═══════════════════════════════════════════════════════════════
# Service / tool checks
# ═══════════════════════════════════════════════════════════════

SERVICE_PORTS = {
    "PostgreSQL": 5432,
    "Redis": 6379,
    "MySQL": 3306,
    "MongoDB": 27017,
    "Docker": 2375,  # Docker API (daemon check via CLI is better)
}


def check_services(root: str) -> list[CheckResult]:
    """Check if common services are running"""
    results: list[CheckResult] = []

    for name, port in SERVICE_PORTS.items():
        if _check_port(port):
            results.append(CheckResult(name, "ok", f"{name} 正在运行 (port {port})"))
        else:
            results.append(CheckResult(name, "info", f"{name} 未运行"))

    # Docker special check (via CLI)
    docker = _which("docker")
    if docker:
        r = _run(["docker", "info"], timeout=5)
        if r.returncode == 0:
            results.append(CheckResult("Docker", "ok", "Docker daemon 运行中"))
        else:
            results.append(CheckResult(
                "Docker", "warn",
                "Docker 已安装但 daemon 可能未运行",
                fix="启动 Docker Desktop 或运行 sudo systemctl start docker",
            ))

    return results


def check_tools(root: str) -> list[CheckResult]:
    """Check essential dev tools are installed"""
    results: list[CheckResult] = []

    tools = {
        "git": "https://git-scm.com",
        "make": "brew install make / apt install build-essential",
        "docker": "https://docker.com",
        "curl": "通常系统自带",
        "ssh": "通常系统自带",
    }

    for tool, fix in tools.items():
        path = _which(tool)
        if path:
            results.append(CheckResult(tool.capitalize(), "ok", path))
        else:
            results.append(CheckResult(
                tool.capitalize(), "info",
                f"{tool} 未安装（如不需要可忽略）",
                fix=fix,
            ))

    return results


# ═══════════════════════════════════════════════════════════════
# Port / network
# ═══════════════════════════════════════════════════════════════

COMMON_PORTS = {
    3000: "Next.js / React dev server",
    5173: "Vite dev server",
    8080: "HTTP 开发服务器",
    8000: "Django / Python HTTP",
    4200: "Angular dev server",
    9000: "PHP built-in / SonarQube",
}


def check_ports(root: str) -> list[CheckResult]:
    """Check if common dev ports are available"""
    results: list[CheckResult] = []

    busy: list[int] = []
    free: list[int] = []
    for port in COMMON_PORTS:
        if _check_port(port):
            busy.append(port)
        else:
            free.append(port)

    if busy:
        results.append(CheckResult(
            "端口占用",
            "info",
            f"已占用: {', '.join(f'{p} ({COMMON_PORTS[p]})' for p in busy)}",
        ))
    if free:
        results.append(CheckResult(
            "可用端口",
            "ok",
            f"可用: {', '.join(f'{p}' for p in free[:6])}",
        ))

    return results


# ═══════════════════════════════════════════════════════════════
# Environment variables
# ═══════════════════════════════════════════════════════════════

def check_env_vars(root: str) -> list[CheckResult]:
    """Check .env.example vs .env completeness"""
    results: list[CheckResult] = []

    example = _read_file(os.path.join(root, ".env.example"))
    env_file = _read_file(os.path.join(root, ".env"))

    if not example:
        results.append(CheckResult(".env", "info", "没有 .env.example 文件（如不需要可忽略）"))
        return results

    # Parse keys from .env.example
    example_keys: set[str] = set()
    for line in example.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key = line.split("=")[0].strip()
            example_keys.add(key)

    if not env_file:
        results.append(CheckResult(
            ".env",
            "warn",
            f".env.example 存在但 .env 不存在（需要 {len(example_keys)} 个变量）",
            fix="cp .env.example .env 然后填入实际值",
        ))
        return results

    # Parse .env keys
    env_keys: set[str] = set()
    for line in env_file.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key = line.split("=")[0].strip()
            env_keys.add(key)

    missing = example_keys - env_keys
    extra = env_keys - example_keys

    if missing:
        results.append(CheckResult(
            "环境变量缺失",
            "warn",
            f"缺少 {len(missing)} 个变量: {', '.join(sorted(missing)[:8])}",
            fix="补齐 .env 中对应的配置",
        ))
    else:
        results.append(CheckResult("环境变量", "ok", f"{len(env_keys)} 个变量均已配置"))

    if extra:
        results.append(CheckResult(
            "额外环境变量",
            "info",
            f"有 {len(extra)} 个 .env.example 中未列出的变量",
        ))

    return results


# ═══════════════════════════════════════════════════════════════
# System resources
# ═══════════════════════════════════════════════════════════════

def check_system(root: str) -> list[CheckResult]:
    """System-level checks: disk, OS"""
    results: list[CheckResult] = []

    # OS
    results.append(CheckResult(
        "操作系统",
        "ok",
        f"{platform.system()} {platform.release()} ({platform.machine()})",
    ))

    # Disk space
    try:
        import shutil
        usage = shutil.disk_usage(root)
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        if free_gb < 5:
            results.append(CheckResult(
                "磁盘空间",
                "error",
                f"仅剩 {free_gb:.1f} GB / {total_gb:.0f} GB",
                fix="清理不必要的文件或扩展磁盘",
            ))
        elif free_gb < 20:
            results.append(CheckResult(
                "磁盘空间",
                "warn",
                f"剩余 {free_gb:.1f} GB / {total_gb:.0f} GB",
            ))
        else:
            results.append(CheckResult(
                "磁盘空间",
                "ok",
                f"{free_gb:.0f} GB 可用 / {total_gb:.0f} GB",
            ))
    except Exception:
        pass

    # Package manager
    for pm in ["brew", "apt", "choco", "winget", "yum", "dnf", "pacman"]:
        if _which(pm):
            results.append(CheckResult("包管理器", "ok", pm))
            break

    return results


# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════

def run_all_checks(root: str = ".") -> list[CheckResult]:
    """Run all environment checks"""
    root = os.path.abspath(root)
    all_results: list[CheckResult] = []

    modules = [
        ("语言运行时", [check_python, check_node, check_rust]),
        ("开发工具", [check_tools]),
        ("后台服务", [check_services]),
        ("网络端口", [check_ports]),
        ("环境变量", [check_env_vars]),
        ("系统资源", [check_system]),
    ]

    for _group_name, funcs in modules:
        for func in funcs:
            try:
                all_results.extend(func(root))
            except Exception as e:
                all_results.append(CheckResult(
                    func.__name__, "error", f"检查异常: {e}"
                ))

    return all_results