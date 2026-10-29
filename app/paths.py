"""Application folders (PyInstaller-aware)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ELV Estimator"


def resource_root() -> Path:
    """Folder holding bundled resources (ui/dist, vendor/). Works frozen and from source."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def ui_dist() -> Path:
    return resource_root() / "ui" / "dist"


def data_dir() -> Path:
    env = os.environ.get("ELV_DATA_DIR")
    if env:
        p = Path(env)
    elif os.name == "nt":
        p = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    else:
        p = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "elv-estimator"
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_projects_dir() -> Path:
    env = os.environ.get("ELV_PROJECTS_DIR")
    if env:
        return Path(env)
    docs = Path.home() / "Documents"
    return docs / APP_NAME / "Projects"
