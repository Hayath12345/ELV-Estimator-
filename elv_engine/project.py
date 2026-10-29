"""Project storage: one folder per project with project.json, drawings/, cache/ and outputs/."""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import date, datetime
from pathlib import Path

from . import texts
from .params import COMMERCIAL_DEFAULTS
from .systems import SYSTEM_KEYS

SCHEMA = 1


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", name or "").strip("-")
    return s[:60] or "Project"


def new_project(info: dict) -> dict:
    today = date.today().isoformat()
    p = {
        "schema": SCHEMA,
        "id": uuid.uuid4().hex[:12],
        "created": now_iso(),
        "updated": now_iso(),
        "info": {
            "name": info.get("name") or "New quotation",
            "scope": info.get("scope", ""),
            "client": info.get("client", ""),
            "attention": info.get("attention", ""),
            "pmc": info.get("pmc", ""),
            "consultant": info.get("consultant", ""),
            "location": info.get("location", ""),
            "ref": info.get("ref", ""),
            "drawing_refs": info.get("drawing_refs", ""),
            "date": info.get("date") or today,
            "validity_days": int(info.get("validity_days") or COMMERCIAL_DEFAULTS["validity_days"]),
            "status": "Draft",
            "subject": info.get("subject", ""),
        },
        "company": {},  # per-project override of the quoting company (blank = settings)
        "revision": {"current": 0, "history": []},
        "signoff": {"prepared": {}, "checked": {}, "approved": {}},
        "drawings": [],
        "rooms_overrides": {},
        "systems": {"selected": list(SYSTEM_KEYS), "combined": True, "params": {}},
        "layout_edits": {"moved": {}, "added": [], "deleted": [], "props": {}},
        "boq": {"overrides": {}, "extra_lines": [], "project_prices": {}},
        "commercial": {k: v for k, v in COMMERCIAL_DEFAULTS.items()},
        "fx_overrides": {},
        "texts": texts.defaults(),
        "checks": {"override": None},
        "comms": {"reserved": {}},
        "exports": {"selected": {"full": True, "per": True, "summary": True, "layout": True, "racks": True,
                                 "cost": False, "zip": True}, "last": None},
    }
    if info.get("ref"):
        pass
    return p


def migrate(p: dict) -> dict:
    """Fill keys added in later versions so old project files keep opening."""
    base = new_project(p.get("info", {}))
    for k, v in base.items():
        if k not in p:
            p[k] = v
        elif isinstance(v, dict) and isinstance(p[k], dict):
            for k2, v2 in v.items():
                p[k].setdefault(k2, v2)
    for k, v in base["info"].items():
        p["info"].setdefault(k, v)
    p["schema"] = SCHEMA
    return p


class ProjectStore:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ---- paths
    def folder(self, pid: str) -> Path:
        for d in self.root.iterdir():
            if d.is_dir() and (d / "project.json").exists():
                try:
                    with open(d / "project.json", encoding="utf-8") as fh:
                        head = json.load(fh)
                    if head.get("id") == pid:
                        return d
                except (OSError, ValueError):
                    continue
        raise KeyError(f"Project {pid} not found")

    def _unique_dir(self, name: str) -> Path:
        base = slugify(name)
        d = self.root / base
        i = 2
        while d.exists():
            d = self.root / f"{base}-{i}"
            i += 1
        return d

    # ---- CRUD
    def list(self) -> list[dict]:
        out = []
        for d in sorted(self.root.iterdir()):
            f = d / "project.json"
            if not f.exists():
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    p = json.load(fh)
                out.append({"project": p, "folder": str(d)})
            except (OSError, ValueError):
                continue
        return out

    def create(self, info: dict) -> tuple[dict, Path]:
        p = new_project(info)
        d = self._unique_dir(p["info"]["name"])
        for sub in ("drawings", "cache", "outputs"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        self.save(p, d)
        return p, d

    def load(self, folder: Path) -> dict:
        with open(folder / "project.json", encoding="utf-8") as fh:
            return migrate(json.load(fh))

    def save(self, p: dict, folder: Path) -> None:
        p["updated"] = now_iso()
        folder.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".project.", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(p, fh, indent=1, ensure_ascii=False)
        os.replace(tmp, folder / "project.json")

    def duplicate(self, pid: str, new_name: str | None = None) -> tuple[dict, Path]:
        src = self.folder(pid)
        p = self.load(src)
        q = copy.deepcopy(p)
        q["id"] = uuid.uuid4().hex[:12]
        q["created"] = now_iso()
        q["info"]["name"] = new_name or (p["info"]["name"] + " (copy)")
        q["info"]["status"] = "Draft"
        q["revision"] = {"current": 0, "history": []}
        q["signoff"] = {"prepared": {}, "checked": {}, "approved": {}}
        q["checks"] = {"override": None}
        q["exports"]["last"] = None
        d = self._unique_dir(q["info"]["name"])
        shutil.copytree(src / "drawings", d / "drawings", dirs_exist_ok=True)
        shutil.copytree(src / "cache", d / "cache", dirs_exist_ok=True)
        (d / "outputs").mkdir(parents=True, exist_ok=True)
        self.save(q, d)
        return q, d
