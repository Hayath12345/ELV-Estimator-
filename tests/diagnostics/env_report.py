"""Test-only helper: record the test environment (section 1 of the test report).

Usage: python tests/diagnostics/env_report.py OUT_FILE
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=30, cwd=ROOT)
        return (p.stdout or p.stderr).strip()
    except Exception as exc:  # noqa: BLE001
        return f"(not available: {exc.__class__.__name__}: {exc})"


def ver(pkg: str) -> str:
    try:
        return metadata.version(pkg)
    except metadata.PackageNotFoundError:
        return "NOT INSTALLED"


def main(out: str) -> None:
    lines = []
    add = lines.append
    add("ELV Estimator — test environment")
    add("=" * 40)
    add(f"OS: {platform.platform()}  ({platform.system()} {platform.release()})")
    add(f"Windows version: {'n/a — tests ran on ' + platform.system() if os.name != 'nt' else platform.win32_ver()}")
    add(f"Machine: {platform.machine()}  CPU: {run(['sh', '-c', 'grep -m1 \"model name\" /proc/cpuinfo'])}  cores: {os.cpu_count()}")
    mem = run(["sh", "-c", "grep MemTotal /proc/meminfo"])
    add(f"RAM: {mem}")
    add(f"Python (interpreter used): {sys.version.split()[0]}  [{sys.executable}]")
    add(f"Node: {run(['node', '--version'])}   npm: {run(['npm', '--version'])}")
    for pkg in ("pywebview", "pyinstaller", "pymupdf", "openpyxl", "reportlab", "ezdxf", "matplotlib", "pytest", "numpy", "pillow"):
        add(f"{pkg}: {ver(pkg)}")
    try:
        sys.path.insert(0, str(ROOT))
        from elv_engine.extract.dwg import find_tool, libredwg_version
        add(f"LibreDWG dwgread: {find_tool('dwgread') or 'NOT INSTALLED in this environment'}  version: {libredwg_version()}")
    except Exception as exc:  # noqa: BLE001
        add(f"LibreDWG: error {exc}")
    add(f"Inno Setup (ISCC): {shutil.which('ISCC') or shutil.which('iscc') or 'NOT INSTALLED (Windows-only tool)'}")
    add(f"Microsoft Excel: {'not applicable (Linux) — LibreOffice used instead' if os.name != 'nt' else 'check via COM'}")
    add(f"LibreOffice: {run(['soffice', '--version'])}")
    add(f"Chromium/Playwright: {run(['sh', '-c', 'ls /opt/pw-browsers'])}")
    pkg = json.loads((ROOT / "ui" / "package.json").read_text(encoding="utf-8"))
    add(f"UI package.json dependencies: {pkg.get('dependencies')}")
    add(f"UI package.json devDependencies: {pkg.get('devDependencies')}")
    for m in ("react", "react-dom", "vite", "typescript", "@vitejs/plugin-react"):
        f = ROOT / "ui" / "node_modules" / m / "package.json"
        add(f"  installed {m}: {json.loads(f.read_text())['version'] if f.exists() else 'not installed'}")
    add(f"requirements.txt:\n{(ROOT / 'requirements.txt').read_text()}")
    add(f"git commit: {run(['git', 'rev-parse', 'HEAD'])}")
    add(f"git branch: {run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])}")
    add(f"git log -5:\n{run(['git', 'log', '--oneline', '-5'])}")
    add(f"git status --short (before test run; untracked diagnostics may appear):\n{run(['git', 'status', '--short']) or '(clean)'}")
    add(f"ui/dist built: {run(['sh', '-c', 'ls -la --time-style=full-iso ui/dist/index.html'])}")
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1])
