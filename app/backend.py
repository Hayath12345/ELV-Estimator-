"""Application backend: project/session state, view models for each screen, mutations
and background jobs. UI-agnostic — exposed to the window by ``api.py`` (pywebview
js_api) and to the browser dev server by ``server.py``.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import threading
import traceback
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from elv_engine import __version__, catalog, pipeline
from elv_engine import extract as ex_mod
from elv_engine.boq import all_lines, tab_json
from elv_engine.currencies import CODES, CURRENCIES, NAMES, TICKER
from elv_engine.layout import ADD_TYPES, default_add, new_id, type_label
from elv_engine.layout.place import camera_range
from elv_engine.money import ZERO, dec, fmt, fmt_qty
from elv_engine.params import CAT_OPTIONS, COMMERCIAL_DEFAULTS, ROOM_CATEGORY_LABELS, SYSTEM_PARAMS, merged
from elv_engine.pricelib import PriceLibrary
from elv_engine.project import ProjectStore, now_iso
from elv_engine.systems import BY_KEY as SYS, SYSTEM_KEYS, SYSTEMS, TAB_ORDER, tab_name

from . import paths

STATUS = ["Draft", "In review", "Approved", "Sent", "Changes requested"]
EXPORTS = [
    ("full", "Complete quotation", "PDF + Excel"),
    ("per", "Per-system quotations", "PDF per system"),
    ("summary", "Combined summary", "PDF"),
    ("layout", "Layout drawings", "PDF, per floor and system"),
    ("racks", "Rack elevations", "PDF"),
    ("cost", "Internal costing workbook", "Excel — internal only"),
    ("zip", "Zip package", "All selected files"),
]
STEP_KEYS = ["drawings", "systems", "layout", "comms", "boq", "checks"]


class UserError(Exception):
    """Message shown to the user as-is."""


def _dt(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso)
        return d.strftime("%d %b %Y, %H:%M")
    except ValueError:
        return iso


def _d(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso[:10]).strftime("%d %b %Y")
    except ValueError:
        return iso


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "EE"


class Backend:
    def __init__(self, data_dir: Path | None = None, projects_dir: Path | None = None,
                 emit: Callable[[dict], None] | None = None):
        self.data_dir = Path(data_dir or paths.data_dir())
        self.settings_path = self.data_dir / "settings.json"
        self.settings = self._load_settings()
        root = Path(projects_dir or self.settings.get("projects_dir") or paths.default_projects_dir())
        self.settings["projects_dir"] = str(root)
        self.store = ProjectStore(str(root))
        self.lib = PriceLibrary(str(self.data_dir / "prices.sqlite"))
        self.emit = emit or (lambda ev: None)
        self.lock = threading.RLock()
        self.project: dict | None = None
        self.folder: Path | None = None
        self._res = None
        self._res_key = None
        self._lib_ver = 0
        self._proj_ver = 0
        self.jobs: dict[str, dict] = {}

    # ================================================================ settings
    def _load_settings(self) -> dict:
        base = {
            "user": {"name": "", "role": "ELV Estimator"},
            "company": {"name": "", "address": "", "phone": "", "email": "", "cr": "", "website": ""},
            "signoff": {"prepared": {"name": "", "role": "ELV Estimator"},
                        "checked": {"name": "", "role": "Lead ELV Engineer"},
                        "approved": {"name": "", "role": "Operations Manager"}},
            "commercial": dict(COMMERCIAL_DEFAULTS),
            "ref_prefix": "QTN",
        }
        try:
            with open(self.settings_path, encoding="utf-8") as fh:
                s = json.load(fh)
            for k, v in base.items():
                if isinstance(v, dict):
                    s.setdefault(k, {})
                    for k2, v2 in v.items():
                        s[k].setdefault(k2, v2)
                else:
                    s.setdefault(k, v)
            return s
        except (OSError, ValueError):
            return base

    def _save_settings(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.settings_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.settings, fh, indent=1, ensure_ascii=False)
        os.replace(tmp, self.settings_path)

    def get_settings(self, _=None) -> dict:
        return {"settings": self.settings, "fx": self._fx_rows(global_only=True), "dataDir": str(self.data_dir)}

    def update_settings(self, a: dict) -> dict:
        with self.lock:
            for k in ("user", "company", "signoff", "commercial"):
                if k in a and isinstance(a[k], dict):
                    if k == "signoff":
                        for step, v in a[k].items():
                            self.settings["signoff"].setdefault(step, {}).update(v)
                    else:
                        self.settings[k].update(a[k])
            if a.get("ref_prefix") is not None:
                self.settings["ref_prefix"] = a["ref_prefix"]
            if a.get("projects_dir"):
                p = Path(a["projects_dir"])
                p.mkdir(parents=True, exist_ok=True)
                self.settings["projects_dir"] = str(p)
                self.store = ProjectStore(str(p))
            self._save_settings()
        return self.get_settings()

    def set_fx(self, a: dict) -> dict:
        """Set a rate globally (library) or as a project override (scope='project')."""
        code = a["code"]
        if code not in CODES:
            raise UserError(f"Unknown currency {code}")
        if a.get("scope") == "project":
            p = self._need()
            if a.get("rate") in (None, ""):
                p["fx_overrides"].pop(code, None)
            else:
                d = dec(a["rate"], None)
                if not d or d <= 0:
                    raise UserError("Exchange rate must be a positive number")
                p["fx_overrides"][code] = format(d, "f")
            self._touch()
        else:
            try:
                self.lib.set_fx(code, a["rate"], a.get("source") or "Manual")
            except ValueError as e:
                raise UserError(str(e))
            self._lib_ver += 1
        return {"ok": True, "fx": self._fx_rows()}

    def _fx(self) -> dict:
        over = self.project.get("fx_overrides") if self.project else None
        return pipeline.effective_fx(self.lib.fx(), over)

    def _fx_rows(self, global_only=False) -> list[dict]:
        over = {} if global_only or not self.project else self.project.get("fx_overrides", {})
        out = []
        for r in self.lib.fx_rows():
            o = over.get(r["code"])
            out.append({"code": r["code"], "name": r["name"], "rate": o or r["rate"], "libRate": r["rate"],
                        "asOf": r.get("as_of") or "", "source": r.get("source") or "", "project": bool(o)})
        return out

    # ================================================================ app info
    def app_info(self, _=None) -> dict:
        from elv_engine.extract.dwg import find_tool
        fx = self.lib.fx()
        ticker = " · ".join(f"{c} {fx.get(c, Decimal(0)).normalize():f}" for c in TICKER if c in fx)
        u = self.settings["user"]
        return {
            "version": __version__,
            "libredwg": bool(find_tool("dwgread") or find_tool("dwg2dxf")),
            "user": {"name": u.get("name") or "Estimator", "role": u.get("role") or "ELV Estimator",
                     "initials": _initials(u.get("name") or "ELV Estimator")},
            "company": self.settings["company"],
            "ticker": ticker,
            "currencies": [{"code": c["code"], "name": c["name"], "symbol": c["symbol"]} for c in CURRENCIES],
            "systems": [{"key": s.key, "name": s.name, "full": s.full, "abbr": s.abbr, "color": s.color} for s in SYSTEMS],
            "roomCategories": CAT_OPTIONS,
            "categories": catalog.CATEGORIES,
            "projectsDir": self.settings["projects_dir"],
            "libraryCount": len(self.lib.rows()),
            "status": STATUS,
            "addTypes": {k: [{"value": t, "label": type_label({"item": t, **default_add(k)})} for t in v]
                         for k, v in ADD_TYPES.items()},
        }

    # ================================================================ projects
    def _need(self) -> dict:
        if not self.project:
            raise UserError("Open a quotation first.")
        return self.project

    def _touch(self, save=True) -> None:
        self._proj_ver += 1
        self._res = None
        if save and self.project and self.folder:
            self.store.save(self.project, self.folder)

    def result(self):
        p = self._need()
        key = (id(p), self._proj_ver, self._lib_ver)
        if self._res is None or self._res_key != key:
            self._res = pipeline.compute(p, self.lib.as_map(), self._fx())
            self._res_key = key
        return self._res

    def list_projects(self, _=None) -> dict:
        rows = []
        total = ZERO
        for entry in self.store.list():
            p = entry["project"]
            info = p.get("info", {})
            tot = dec(p.get("summary", {}).get("base"), ZERO) or ZERO
            total += tot
            sel = p.get("systems", {}).get("selected", [])
            rows.append({
                "id": p["id"], "name": info.get("name", ""), "scope": info.get("scope", ""), "client": info.get("client", ""),
                "ref": info.get("ref", ""), "rev": f"Rev {p.get('revision', {}).get('current', 0)}",
                "systems": [{"key": s, "name": SYS[s].name, "color": SYS[s].color, "ab": SYS[s].abbr} for s in SYSTEM_KEYS if s in sel],
                "total": str(tot), "totalF": fmt(tot), "status": info.get("status", "Draft"),
                "edited": _dt(p.get("updated")), "by": p.get("updated_by", ""), "updated": p.get("updated", ""),
                "folder": entry["folder"],
            })
        rows.sort(key=lambda r: r["updated"], reverse=True)
        st = [r["status"] for r in rows]
        return {"rows": rows, "kpis": {"active": len(rows), "review": st.count("In review"),
                                       "changes": st.count("Changes requested"), "pipelineF": fmt(total)},
                "openId": self.project["id"] if self.project else None}

    def create_project(self, a: dict) -> dict:
        info = dict(a or {})
        if not (info.get("name") or "").strip():
            raise UserError("Enter a project name.")
        with self.lock:
            p, d = self.store.create(info)
            p["commercial"] = {**COMMERCIAL_DEFAULTS, **self.settings.get("commercial", {})}
            p["info"]["validity_days"] = int(info.get("validity_days") or p["commercial"].get("validity_days", 30))
            for step in ("prepared", "checked", "approved"):
                s = self.settings["signoff"].get(step, {})
                p["signoff"][step] = {"name": s.get("name", ""), "role": s.get("role", ""), "at": None}
            if not p["info"]["ref"]:
                p["info"]["ref"] = f"{self.settings.get('ref_prefix') or 'QTN'}-{datetime.now():%y%m%d}-ELV-ALL-001"
            p["updated_by"] = self._user_short()
            self.store.save(p, d)
            self.project, self.folder = p, d
            self._touch(save=False)
        return self.project_state()

    def open_project(self, a: dict) -> dict:
        with self.lock:
            d = self.store.folder(a["id"])
            self.project = self.store.load(d)
            self.folder = d
            self._touch(save=False)
        return self.project_state()

    def open_sample_project(self, _=None) -> dict:
        """Create a demo quotation from two generated sample floor plans (DXF)."""
        import tempfile
        from elv_engine.samples import make_set
        self.create_project({"name": "Sample HQ Fit-Out", "client": "Sample Client", "scope": "2nd & 3rd Floors",
                             "location": "Sample office building", "pmc": "Sample PMC"})
        files = make_set(tempfile.mkdtemp(prefix="elv-sample-"))
        r = self.import_drawings({"paths": files})
        return {**self.project_state(), "job": r["job"]}

    def close_project(self, _=None) -> dict:
        with self.lock:
            self.project = self.folder = None
            self._res = None
        return {"ok": True}

    def duplicate_project(self, a: dict) -> dict:
        with self.lock:
            p, d = self.store.duplicate(a["id"], a.get("name"))
        return {"ok": True, "id": p["id"]}

    def update_project_info(self, a: dict) -> dict:
        p = self._need()
        with self.lock:
            for k, v in (a.get("info") or {}).items():
                if k in p["info"]:
                    p["info"][k] = int(v) if k == "validity_days" and str(v).isdigit() else v
            if "company" in a:
                p["company"] = {k: v for k, v in a["company"].items()}
            if "signoff" in a:
                for step, v in a["signoff"].items():
                    p["signoff"].setdefault(step, {}).update({k: v[k] for k in ("name", "role") if k in v})
            self._touch()
        return self.project_state()

    def _user_short(self) -> str:
        n = (self.settings["user"].get("name") or "").split()
        return (n[0][0] + ". " + n[-1]) if len(n) >= 2 else (n[0] if n else "")

    # ---------------------------------------------------------------- header / steps
    def project_state(self, _=None) -> dict:
        p = self._need()
        info = p["info"]
        res = self.result() if p.get("drawings") else None
        header = self._header(res)
        n_dw = len(p["drawings"])
        floors = res.floors if res else []
        scales = sorted({f"1:{d['extraction'].get('plot_scale')}" for d in p["drawings"]
                         if d.get("extraction") and d["extraction"].get("plot_scale")})
        sel = p["systems"]["selected"]
        steps_sub = {
            "drawings": f"{n_dw} drawing{'s' if n_dw != 1 else ''}" + (f" · {scales[0]}" if scales else ""),
            "systems": ("All six combined" if len(sel) == 6 and p["systems"]["combined"] else
                        f"{len(sel)} system{'s' if len(sel) != 1 else ''}" + (", combined" if p["systems"]["combined"] and len(sel) > 1 else "")),
            "layout": f"{sum(1 for d in res.devices if d['sys'] in sel):,} devices" if res else "No devices",
            "comms": self._comms_sub(res),
            "boq": f"QAR {self._short_money(res.boq['totals']['base'])}" if res else "QAR 0",
            "checks": f"{res.checks['passed']} / {res.checks['total']} passed" if res else "Not run",
        }
        done = {
            "drawings": n_dw > 0 and all(d.get("extraction") for d in p["drawings"]),
            "systems": bool(sel), "layout": bool(res and res.devices), "comms": bool(res and res.sizing["rooms"]),
            "boq": bool(res and res.boq["unpriced"] == 0 and res.boq["totals"]["base"] > 0),
            "checks": bool(res and res.checks["blocking"] == 0),
        }
        labels = {"drawings": "Drawings", "systems": "Systems", "layout": "Device Layout", "comms": "Comms Rooms",
                  "boq": "BOQ & Pricing", "checks": "Checks & Export"}
        return {
            "id": p["id"], "info": info, "folder": str(self.folder), "revLabel": f"Rev {p['revision']['current']}",
            "rev": p["revision"]["current"], "status": info.get("status", "Draft"), "header": header,
            "steps": [{"key": k, "label": labels[k], "sub": steps_sub[k], "done": done[k]} for k in STEP_KEYS],
            "floors": [{"key": f.key, "name": f.name} for f in floors],
            "company": p.get("company") or {}, "signoff": p.get("signoff", {}),
            "drawingRefs": info.get("drawing_refs") or " / ".join(Path(d["file"]).stem for d in p["drawings"][:2]),
            "commercial": {k: str(v) for k, v in p["commercial"].items()},
        }

    def _short_money(self, v: Decimal) -> str:
        v = float(v)
        if v >= 1e6:
            return f"{v / 1e6:.2f}M"
        if v >= 1e3:
            return f"{v / 1e3:.0f}k"
        return f"{v:,.0f}"

    def _comms_sub(self, res) -> str:
        if not res or not res.sizing["rooms"]:
            return "None identified"
        roles = [r.role for r in res.sizing["rooms"]]
        return f"{roles.count('MDF')} MDF · {roles.count('IDF')} IDF"

    def _header(self, res) -> dict:
        if not res:
            return {"baseLabel": "COMBINED BASE (QAR)", "baseF": "0.00", "networkF": "0.00", "savingF": "0.00",
                    "combined": True}
        t = res.boq["totals"]
        comb = res.boq["combined"]
        self._store_summary(t)
        return {"baseLabel": "COMBINED BASE (QAR)" if comb else "BASE TOTAL (QAR)", "baseF": fmt(t["base"]),
                "networkF": fmt(t["network"]), "savingF": fmt(t["saving"]) if comb else "—", "combined": comb}

    def _store_summary(self, t) -> None:
        """Keep the dashboard total in project.json without forcing a save on every view."""
        p = self.project
        s = {"base": str(t["base"]), "network": str(t["network"])}
        if p.get("summary") != s:
            p["summary"] = s
            if self.folder:
                self.store.save(p, self.folder)

    # ================================================================ drawings
    def pick_drawings(self, paths_: list[str]) -> dict:
        return self.import_drawings({"paths": paths_})

    def import_drawings(self, a: dict) -> dict:
        p = self._need()
        files = [f for f in (a.get("paths") or []) if f]
        if not files:
            raise UserError("No files selected.")
        bad = [f for f in files if ex_mod.kind_of(f) == "unknown"]
        if bad:
            raise UserError("Only DWG, DXF and PDF files can be imported: " + ", ".join(Path(b).name for b in bad))
        added = []
        with self.lock:
            ddir = self.folder / "drawings"
            ddir.mkdir(exist_ok=True)
            for f in files:
                src = Path(f)
                if src.stat().st_size > 200 * 1024 * 1024:
                    raise UserError(f"{src.name} is larger than 200 MB.")
                dst = ddir / src.name
                if src.resolve() != dst.resolve():
                    shutil.copy2(src, dst)
                kind = ex_mod.kind_of(str(dst))
                pages = 1
                if kind == "pdf":
                    from elv_engine.extract.pdf import page_count
                    try:
                        pages = page_count(str(dst))
                    except Exception:
                        pages = 1
                for pg in range(pages):
                    did = "dw" + uuid.uuid4().hex[:6]
                    order = len(p["drawings"])
                    name = src.name + (f" (p{pg + 1})" if pages > 1 else "")
                    p["drawings"].append({
                        "id": did, "file": dst.name, "kind": kind, "page": pg, "name": name,
                        "floor": ex_mod.guess_floor(src.name if pages == 1 else f"{src.stem} {pg + 1}F", f"{order + 1}F"),
                        "order": order, "size": dst.stat().st_size, "status": "Queued", "error": None,
                        "extraction": None, "calibration": None, "role": "plan", "added": now_iso(),
                    })
                    added.append(did)
            self._touch()
        job = self._start_job("extract", lambda job: self._extract_job(job, added))
        return {"ok": True, "job": job, "added": added}

    def retry_drawing(self, a: dict) -> dict:
        p = self._need()
        d = self._drawing(a["id"])
        d["status"], d["error"] = "Queued", None
        self._touch()
        return {"ok": True, "job": self._start_job("extract", lambda job: self._extract_job(job, [d["id"]]))}

    def _drawing(self, did: str) -> dict:
        for d in self._need()["drawings"]:
            if d["id"] == did:
                return d
        raise UserError("Drawing not found.")

    def _extract_job(self, job: dict, ids: list[str]) -> dict:
        n = len(ids)
        done = 0
        for i, did in enumerate(ids):
            with self.lock:
                d = self._drawing(did)
                d["status"] = "Extracting…"
                path = str(self.folder / "drawings" / d["file"])
                cache = str(self.folder / "cache")
                page = d.get("page", 0)
                fname = d["name"]

            def prog(f, msg, i=i, fname=fname):
                self._job_progress(job, (i + f) / n, f"{fname} · {msg}")
            try:
                res = ex_mod.extract_drawing(path, cache, did, page, prog)
                with self.lock:
                    d = self._drawing(did)
                    d["extraction"] = res
                    d["status"] = "Scale missing" if not res.get("unit_m") else "Extracted"
                    d["error"] = None
                    self._touch()
                done += 1
            except Exception as exc:  # noqa: BLE001 — shown to the user per file
                msg = str(exc) if isinstance(exc, (ex_mod.DwgError, ValueError, UserError)) else \
                    f"{type(exc).__name__}: {exc}"
                with self.lock:
                    d = self._drawing(did)
                    d["status"], d["error"] = "Failed", msg
                    self._touch()
                traceback.print_exc()
        return {"extracted": done, "failed": n - done}

    def remove_drawing(self, a: dict) -> dict:
        p = self._need()
        with self.lock:
            p["drawings"] = [d for d in p["drawings"] if d["id"] != a["id"]]
            p["rooms_overrides"].pop(a["id"], None)
            ed = p["layout_edits"]
            ed["added"] = [x for x in ed["added"] if x.get("floor") != a["id"]]
            for i, d in enumerate(sorted(p["drawings"], key=lambda d: d["order"])):
                d["order"] = i
            self._touch()
        return {"ok": True}

    def update_drawing(self, a: dict) -> dict:
        d = self._drawing(a["id"])
        with self.lock:
            if "floor" in a:
                d["floor"] = (a["floor"] or "").strip().upper()[:8] or d["floor"]
            if "role" in a and a["role"] in ("plan", "reference"):
                d["role"] = a["role"]
            if "move" in a:
                ds = sorted(self.project["drawings"], key=lambda x: x["order"])
                i = ds.index(d)
                j = max(0, min(len(ds) - 1, i + int(a["move"])))
                ds[i], ds[j] = ds[j], ds[i]
                for k, x in enumerate(ds):
                    x["order"] = k
            self._touch()
        return {"ok": True}

    def calibrate(self, a: dict) -> dict:
        """Two-point calibration: p1, p2 in drawing units and the known distance in metres.
        Or set unit_m directly. Applies to one drawing or to all (apply_all)."""
        p = self._need()
        if a.get("unit_m"):
            unit_m = float(a["unit_m"])
            note = a.get("note") or "Manual scale"
        else:
            (x1, y1), (x2, y2) = a["p1"], a["p2"]
            dist_u = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            dist_m = float(dec(a["distance_m"], None) or 0)
            if dist_u <= 0 or dist_m <= 0:
                raise UserError("Pick two different points and enter the known distance.")
            unit_m = dist_m / dist_u
            note = f"{a.get('label') or 'Two-point'} = {dist_m:.2f} m"
        targets = p["drawings"] if a.get("apply_all") else [self._drawing(a["id"])]
        with self.lock:
            for d in targets:
                if not d.get("extraction"):
                    continue
                d["calibration"] = {"unit_m": unit_m, "note": note, "at": now_iso(),
                                    "measured_units": a.get("measured_units")}
                if d["status"] == "Scale missing":
                    d["status"] = "Extracted"
            self._touch()
        return {"ok": True, "unit_m": unit_m}

    def get_drawings(self, _=None) -> dict:
        p = self._need()
        res = self.result() if any(d.get("extraction") for d in p["drawings"]) else None
        files = []
        for d in sorted(p["drawings"], key=lambda x: x["order"]):
            ex = d.get("extraction") or {}
            cal = d.get("calibration") or {}
            unit_m = cal.get("unit_m") or ex.get("unit_m")
            meta = [f"{d['floor']}"]
            if ex.get("plot_scale"):
                meta.append(f"1:{ex['plot_scale']}")
            meta.append(f"{(d.get('size') or 0) / 1048576:.1f} MB")
            st = d["status"]
            st_fg = {"Extracted": "#1E7D46", "Failed": "#C62828", "Scale missing": "#8A5A00"}.get(st, "#1F3B70")
            conf = "Calibrated" if cal.get("unit_m") else ex.get("scale_conf", "")
            files.append({
                "id": d["id"], "name": d["name"], "file": d["file"], "ext": d["kind"].upper(), "kind": d["kind"],
                "floor": d["floor"], "order": d["order"], "meta": " · ".join(meta), "status": st, "stFg": st_fg,
                "error": d.get("error"), "role": d.get("role", "plan"),
                "scale": {"unit_m": unit_m, "conf": conf, "note": cal.get("note") or ex.get("scale_note", ""),
                          "plot": ex.get("plot_scale")},
                "warnings": ex.get("warnings", []), "counts": ex.get("counts", {}),
            })
        # extraction table per floor
        rows = []
        if res:
            fl = res.floors
            def per(fn):
                return [fn(f) for f in fl]
            rooms = per(lambda f: len(f.rooms))
            doors = per(lambda f: sum(1 for x in f.doors if not x.inferred))
            tags = per(lambda f: sum(1 for x in f.doors if x.tag))
            wps = per(lambda f: sum(len(r.wps) for r in f.rooms))
            comms = per(lambda f: len(f.comms_rooms))
            est = per(lambda f: sum(1 for r in f.rooms if r.boundary == "estimated"))
            def conf_of(vals, good):
                return ("High", "high") if good else ("Medium", "med")
            rows = [
                {"item": "Rooms", "vals": [str(v) for v in rooms], "conf": "High" if not any(est) else "Medium",
                 "tone": "high" if not any(est) else "med",
                 "note": "Room names + closed boundaries" + (f" · {sum(est)} boundaries estimated" if any(est) else "")},
                {"item": "Doors", "vals": [str(v) for v in doors], "conf": "High" if all(doors) else "Low",
                 "tone": "high" if all(doors) else "bud",
                 "note": f"{sum(tags)} with door tags" + ("" if all(doors) else " · some inferred from boundaries")},
                {"item": "Work positions", "vals": [str(v) for v in wps], "conf": "Medium" if any(wps) else "Low",
                 "tone": "med" if any(wps) else "bud",
                 "note": f"{sum(wps)} total · furniture blocks" if any(wps) else "No furniture blocks — estimated from area"},
                {"item": "Comms rooms", "vals": [str(v) for v in comms], "conf": "High" if sum(comms) else "Not found",
                 "tone": "high" if sum(comms) else "bud",
                 "note": ", ".join(r.name for f in fl for r in f.comms_rooms) or "Mark a room as MDF/IDF below"},
            ]
            scale_vals, ok = [], True
            for f in fl:
                d = self._drawing(f.key)
                ex = d["extraction"]
                if not f.calibrated:
                    ok = False
                scale_vals.append(f"1:{ex['plot_scale']}" if ex.get("plot_scale") else ("✓" if f.calibrated else "—"))
            notes = [((self._drawing(f.key).get("calibration") or {}).get("note") or
                      self._drawing(f.key)["extraction"].get("scale_note", "")) for f in fl]
            rows.append({"item": "Scale", "vals": scale_vals, "conf": "Calibrated" if ok else "Not found",
                         "tone": "high" if ok else "bud", "note": notes[0] if notes else ""})
        state = "empty"
        if p["drawings"]:
            st = [d["status"] for d in p["drawings"]]
            if any(s in ("Queued", "Extracting…") for s in st):
                state = "loading"
            elif any(s == "Failed" for s in st) and not any(s == "Extracted" for s in st):
                state = "error"
            elif any(s == "Scale missing" for s in st) or (res and not all(f.calibrated for f in res.floors)):
                state = "warn"
            else:
                state = "results"
        errors = [{"id": d["id"], "name": d["name"], "message": d["error"]} for d in p["drawings"] if d.get("error")]
        n_ok = sum(1 for d in p["drawings"] if d.get("extraction"))
        caption = {"empty": "Waiting for files", "loading": f"Processing {len(p['drawings'])} drawing(s)",
                   "error": f"{len(errors)} of {len(p['drawings'])} drawings failed",
                   "warn": "Action required — calibrate scale",
                   "results": (f"{n_ok} drawing{'s' if n_ok != 1 else ''} · {sum(len(f.rooms) for f in res.floors)} rooms · "
                               f"{sum(len(f.doors) for f in res.floors)} doors") if res else ""}[state]
        room_rows = []
        if res:
            for f in res.floors:
                for r in sorted(f.rooms, key=lambda r: r.name):
                    room_rows.append({"id": r.rid, "drawing": f.key, "floor": f.name, "name": r.name, "category": r.category,
                                      "categoryLabel": ROOM_CATEGORY_LABELS.get(r.category, r.category),
                                      "area": f"{r.area_m2:,.1f}", "comms": r.comms or "", "conf": r.conf,
                                      "boundary": r.boundary, "wps": len(r.wps)})
        return {"files": files, "rows": rows, "floors": [f.name for f in res.floors] if res else [],
                "state": state, "caption": caption, "errors": errors, "rooms": room_rows,
                "jobs": [j for j in self.jobs.values() if j["kind"] == "extract" and not j["done"]],
                "libredwg": self.app_info()["libredwg"]}

    def update_room(self, a: dict) -> dict:
        p = self._need()
        with self.lock:
            ov = p["rooms_overrides"].setdefault(a["drawing"], {}).setdefault(a["id"], {})
            for k in ("category", "comms", "name", "deleted"):
                if k in a:
                    ov[k] = a[k]
            self._touch()
        return {"ok": True}

    def get_background(self, a: dict) -> dict:
        """Background image of a drawing as a data URL (cached by the UI)."""
        import base64
        d = self._drawing(a["id"])
        bg = (d.get("extraction") or {}).get("background")
        if not bg:
            return {"url": None}
        f = self.folder / "cache" / bg["png"]
        if not f.exists():
            return {"url": None}
        return {"url": "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode("ascii"),
                "extents": bg["extents"], "width": bg["width"], "height": bg["height"]}

    def get_calibration_view(self, a: dict) -> dict:
        d = self._drawing(a["id"])
        ex = d.get("extraction") or {}
        grids = ex.get("grids", [])
        return {"id": d["id"], "name": d["name"], "extents": ex.get("extents"), "grids": grids,
                "unit_m": (d.get("calibration") or {}).get("unit_m") or ex.get("unit_m"),
                "note": (d.get("calibration") or {}).get("note") or ex.get("scale_note", "")}

    # ================================================================ systems
    def get_systems(self, _=None) -> dict:
        p = self._need()
        res = self.result() if p["drawings"] else None
        sel = p["systems"]["selected"]
        comb = p["systems"]["combined"]
        t = res.boq["totals"] if res else None
        info = res.qres["info"] if res else {}
        rows = []
        for s in SYSTEMS:
            on = s.key in sel
            qty, detail = self._sys_qty(s.key, res, info)
            st = t["systems"].get(s.key) if t else None
            rows.append({"key": s.key, "full": s.full, "name": s.name, "color": s.color, "on": on, "qty": qty,
                         "detail": detail, "standaloneF": fmt(st["standalone"]) if st else "—",
                         "combinedF": fmt(st["combined"]) if st and comb and len(sel) > 1 else (fmt(st["standalone"]) if st else "—")})
        params = {}
        for k, specs in SYSTEM_PARAMS.items():
            vals = merged(k, p["systems"]["params"].get(k))
            params[k] = [{**sp, "value": vals[sp["key"]]} for sp in specs]
        all_on = len(sel) == 6 and comb
        return {
            "systems": rows, "allOn": all_on, "combined": comb, "selected": sel,
            "sharedF": fmt(t["shared"]) if t and comb and len(sel) > 1 else "—",
            "baseStandaloneF": fmt(t["standalone"]) if t else "0.00",
            "baseCombinedF": fmt(t["combined"] if comb and len(sel) > 1 else t["standalone"]) if t else "0.00",
            "savingF": fmt(t["saving"]) if t and comb and len(sel) > 1 else "Not applicable",
            "summary": (f"Award: {'all six' if len(sel) == 6 else str(len(sel)) + ' systems'} "
                        f"{'combined' if comb and len(sel) > 1 else 'standalone'} · QAR {fmt(t['base']) if t else '0.00'}"),
            "params": params,
        }

    def _sys_qty(self, key, res, info) -> tuple[str, str]:
        if not res:
            return "—", "upload drawings first"
        i = info.get(key, {})
        devs = [d for d in res.devices if d["sys"] == key]
        if key == "cctv":
            n = len(devs)
            return f"{n} cameras", (f"{i.get('retention', 0):.0f}-day recording · {i.get('nvr', 0)} recorder(s), "
                                    f"{i.get('storage_tb', 0):.0f} TB needed") if n else "no cameras placed"
        if key == "access":
            return f"{i.get('doors', 0)} doors", f"{i.get('leaves', 0)} leaves · {i.get('readers', 0)} readers · {i.get('controllers', 0)} controllers"
        if key == "iptv":
            bs = i.get("by_size", {})
            return f"{i.get('tvs', 0)} TVs", " · ".join(f"{v} × {k}\"" for k, v in sorted(bs.items(), key=lambda x: int(x[0])))
        if key == "cabling":
            return f"{i.get('outlets', 0)} outlets", f"Cat6A incl. {i.get('aps', 0)} Wi-Fi APs"
        if key == "intercom":
            return f"{i.get('devices', 0)} devices", "Video, audio-only and answering units"
        if key == "intrusion":
            g = merged("intrusion", self.project["systems"]["params"].get("intrusion")).get("grade", "3")
            return f"{i.get('devices', 0)} devices", f"Grade {g} (EN 50131) · {i.get('zones', 0)} zones"
        return "", ""

    def set_systems(self, a: dict) -> dict:
        p = self._need()
        with self.lock:
            if "selected" in a:
                sel = [s for s in SYSTEM_KEYS if s in a["selected"]]
                if not sel:
                    raise UserError("Select at least one system.")
                p["systems"]["selected"] = sel
            if "combined" in a:
                p["systems"]["combined"] = bool(a["combined"])
            self._touch()
        return {"ok": True}

    def set_params(self, a: dict) -> dict:
        p = self._need()
        sys_ = a["system"]
        if sys_ not in SYSTEM_PARAMS:
            raise UserError("Unknown system")
        specs = {s["key"]: s for s in SYSTEM_PARAMS[sys_]}
        with self.lock:
            cur = p["systems"]["params"].setdefault(sys_, {})
            for k, v in (a.get("values") or {}).items():
                if k not in specs:
                    continue
                if specs[k]["type"] == "number":
                    d = dec(v, None)
                    if d is None or d < 0:
                        raise UserError(f"{specs[k]['label']}: enter a number ≥ 0")
                    v = float(d)
                cur[k] = v
            if a.get("reset"):
                p["systems"]["params"].pop(sys_, None)
            self._touch()
        return {"ok": True}

    # ================================================================ layout
    def get_layout(self, a: dict) -> dict:
        p = self._need()
        res = self.result()
        if not res.floors:
            return {"floors": [], "floor": None}
        fkey = a.get("floor") or res.floors[0].key
        fl = next((f for f in res.floors if f.key == fkey), res.floors[0])
        sel = set(p["systems"]["selected"])
        rooms_by = {r.id: r for f in res.floors for r in f.rooms}
        devs = []
        for d in res.devices:
            if d["floor"] != fl.key:
                continue
            rt = res.routes.get(d["id"])
            r = rooms_by.get(d.get("room") or "")
            dd = {"id": d["id"], "sys": d["sys"], "item": d["item"], "sub": d.get("sub"), "x": d["x"], "y": d["y"],
                  "a": d.get("a", 0), "type": type_label(d), "location": f"{r.name if r else 'Unassigned'}, {fl.name}",
                  "edited": bool(d.get("edited")), "auto": d.get("auto", True), "on": d["sys"] in sel}
            if d["sys"] == "cctv":
                tgt = d.get("target") or "Recognise"
                pp = merged("cctv", p["systems"]["params"].get("cctv"))
                ppm = {"Identify": pp["ppm_identify"], "Recognise": pp["ppm_recognise"], "Observe": pp["ppm_observe"]}
                dd["target"] = tgt
                dd["range_m"] = round(camera_range(d["item"], float(ppm[tgt])), 1)
            if d["sys"] == "access":
                dd.update({"leaves": d.get("leaves", 1), "readers": d.get("readers", 1), "lock": d.get("lock"),
                           "tag": d.get("tag", "")})
            if d["sys"] == "cabling":
                dd["ports"] = d.get("ports", 2)
            if rt:
                dd.update({"idf": rooms_by[rt["room"]].name if rt["room"] in rooms_by else rt["room"],
                           "len": rt["len_m"], "over": rt["over"], "pts": rt["pts"], "riser": rt["riser"]})
            devs.append(dd)
        def counts(devices):
            c = {k: 0 for k in SYSTEM_KEYS}
            c["ap"] = 0
            for d in devices:
                c[d["sys"]] += 1
                if d.get("sub") == "ap":
                    c["ap"] += 1
            return c
        floor_devs = [d for d in res.devices if d["floor"] == fl.key]
        lens = [res.routes[d["id"]]["len_m"] for d in floor_devs if d["id"] in res.routes and d["sys"] in sel and d["sys"] != "intrusion"]
        long_ = sum(1 for d in floor_devs if d["sys"] in sel and res.routes.get(d["id"], {}).get("over"))
        dwg = self._drawing(fl.key)
        ex = dwg["extraction"]
        cal = dwg.get("calibration") or {}
        scale = []
        if ex.get("plot_scale"):
            scale.append(f"Scale 1:{ex['plot_scale']}")
        note = cal.get("note") or ex.get("scale_note") or ""
        if "grid" in note:
            scale.append(note[note.index("grid"):])
        elif note:
            scale.append(note)
        return {
            "floors": [{"key": f.key, "name": f.name} for f in res.floors], "floor": fl.key, "floorName": fl.name,
            "extents": fl.extents, "unitM": fl.unit_m, "calibrated": fl.calibrated,
            "rooms": [{"id": r.id, "rid": r.rid, "name": r.name, "cat": r.category, "poly": r.poly, "comms": r.comms,
                       "label": r.label_pt, "area": round(r.area_m2, 1)} for r in fl.rooms],
            "grids": ex.get("grids", []),
            "devices": devs,
            "counts": {"floor": counts([d for d in floor_devs if d["sys"] in sel]),
                       "total": counts([d for d in res.devices if d["sys"] in sel]),
                       "devices": sum(1 for d in floor_devs if d["sys"] in sel),
                       "max": f"{max(lens):.1f}" if lens else "0.0", "long": long_},
            "scale": " · ".join(scale), "hasBg": bool(ex.get("background")),
        }

    def _floor_code(self, fkey: str) -> str:
        from elv_engine.layout.floor import floor_code
        return floor_code(self._drawing(fkey)["floor"])

    def add_device(self, a: dict) -> dict:
        p = self._need()
        sys_ = a["sys"]
        if sys_ not in SYSTEM_KEYS:
            raise UserError("Unknown system")
        res = self.result()
        existing = {d["id"] for d in res.devices} | {x["id"] for x in p["layout_edits"]["added"]}
        base = default_add(sys_)
        if a.get("item"):
            base["item"] = a["item"]
            if sys_ == "cabling" and a["item"] == "sc_ap":
                base.update({"sub": "ap", "kind": "ap"})
            if sys_ == "iptv":
                base["size"] = int(a["item"][3:])
        did = new_id(sys_, self._floor_code(a["floor"]), existing, base.get("sub"))
        fl = next(f for f in res.floors if f.key == a["floor"])
        room = fl.room_at((a["x"], a["y"]))
        dev = {"id": did, "sys": sys_, "floor": a["floor"], "x": round(a["x"], 3), "y": round(a["y"], 3),
               "room": room.id if room else None, **base}
        with self.lock:
            p["layout_edits"]["added"].append(dev)
            self._touch()
        return {"ok": True, "id": did}

    def move_device(self, a: dict) -> dict:
        p = self._need()
        with self.lock:
            res = self.result()
            dev = next((d for d in res.devices if d["id"] == a["id"]), None)
            if not dev:
                raise UserError("Device not found")
            fl = next(f for f in res.floors if f.key == dev["floor"])
            room = fl.room_at((a["x"], a["y"]))
            added = next((x for x in p["layout_edits"]["added"] if x["id"] == a["id"]), None)
            if added:
                added["x"], added["y"] = round(a["x"], 3), round(a["y"], 3)
                added["room"] = room.id if room else None
            else:
                p["layout_edits"]["moved"][a["id"]] = [round(a["x"], 3), round(a["y"], 3)]
                p["layout_edits"]["props"].setdefault(a["id"], {})["room"] = room.id if room else None
            self._touch()
        return {"ok": True}

    def delete_device(self, a: dict) -> dict:
        p = self._need()
        with self.lock:
            ed = p["layout_edits"]
            before = len(ed["added"])
            ed["added"] = [x for x in ed["added"] if x["id"] != a["id"]]
            if len(ed["added"]) == before:
                if a["id"] not in ed["deleted"]:
                    ed["deleted"].append(a["id"])
            ed["moved"].pop(a["id"], None)
            ed["props"].pop(a["id"], None)
            self._touch()
        return {"ok": True}

    def duplicate_device(self, a: dict) -> dict:
        res = self.result()
        dev = next((d for d in res.devices if d["id"] == a["id"]), None)
        if not dev:
            raise UserError("Device not found")
        off = 1.0 / next(f for f in res.floors if f.key == dev["floor"]).unit_m
        return self.add_device({"sys": dev["sys"], "item": dev["item"], "floor": dev["floor"],
                                "x": dev["x"] + off, "y": dev["y"] - off})

    def update_device(self, a: dict) -> dict:
        p = self._need()
        allowed = {"target", "a", "item", "leaves", "readers", "lock", "ports"}
        patch = {k: v for k, v in (a.get("props") or {}).items() if k in allowed}
        if "item" in patch and str(patch["item"]).startswith("tv_"):
            patch["size"] = int(patch["item"][3:])
        with self.lock:
            added = next((x for x in p["layout_edits"]["added"] if x["id"] == a["id"]), None)
            if added:
                added.update(patch)
            else:
                p["layout_edits"]["props"].setdefault(a["id"], {}).update(patch)
            self._touch()
        return {"ok": True}

    def reset_layout(self, a: dict) -> dict:
        p = self._need()
        with self.lock:
            if a.get("floor"):
                f = a["floor"]
                res = self.result()
                ids = {d["id"] for d in res.auto if d["floor"] == f}
                ed = p["layout_edits"]
                ed["added"] = [x for x in ed["added"] if x["floor"] != f]
                ed["deleted"] = [i for i in ed["deleted"] if i not in ids]
                ed["moved"] = {k: v for k, v in ed["moved"].items() if k not in ids}
                ed["props"] = {k: v for k, v in ed["props"].items() if k not in ids}
            else:
                p["layout_edits"] = {"moved": {}, "added": [], "deleted": [], "props": {}}
            self._touch()
        return {"ok": True}

    # ================================================================ comms
    def get_comms(self, _=None) -> dict:
        p = self._need()
        res = self.result()
        reserved = p["comms"].get("reserved", {})
        rooms = []
        for rs in res.sizing["rooms"]:
            pct = int(round(rs.poe_load_w / rs.poe_budget_w * 100)) if rs.poe_budget_w else 0
            racks = []
            for rk in rs.racks:
                res_u = reserved.get(rk.name, [])
                racks.append({"name": rk.name, "used": rk.used, "reserved": res_u,
                              "items": [{"label": i.label, "size": i.size, "kind": i.kind, "u": i.u} for i in rk.items]})
            rooms.append({
                "id": rs.id, "name": rs.name, "floor": rs.floor_name, "role": rs.role,
                "served": sum(rs.served.values()),
                "mix": [{"name": s.name, "color": s.color, "n": rs.served.get(s.key, 0)} for s in SYSTEMS],
                "poe": rs.poe_load_w, "budget": rs.poe_budget_w, "poeF": f"{rs.poe_load_w:,.0f} W",
                "budgetF": f"{rs.poe_budget_w:,.0f} W", "pct": pct, "over": pct > 80,
                "switches": rs.elv_switches + rs.user_switches, "elvSwitches": rs.elv_switches, "userSwitches": rs.user_switches,
                "elvPorts": rs.elv_ports, "dataPorts": rs.data_ports, "loadW": rs.load_w,
                "ups": (f"{catalog.get(rs.ups).part_no}" + (f" × {rs.ups_qty}" if rs.ups_qty > 1 else "") +
                        (f" + {rs.packs_qty} battery pack{'s' if rs.packs_qty > 1 else ''}" if rs.packs_qty else "")) if rs.ups else "—",
                "runtime": int(rs.runtime_min), "runtimeOk": rs.runtime_min >= 60,
                "rackList": " · ".join(f"{r.name} {r.used}U" for r in rs.racks), "racks": racks,
                "uUsed": rs.u_used, "uTotal": len(rs.racks) * 42,
            })
        return {"rooms": rooms, "scenario": ", ".join(SYS[s].name for s in res.selected),
                "candidates": [{"id": r.rid, "drawing": f.key, "name": r.name, "floor": f.name, "comms": r.comms or ""}
                               for f in res.floors for r in f.rooms if r.category not in ("corridor", "toilet", "stair", "lift")]}

    def reserve_u(self, a: dict) -> dict:
        p = self._need()
        with self.lock:
            lst = p["comms"].setdefault("reserved", {}).setdefault(a["rack"], [])
            u = int(a["u"])
            if u in lst:
                lst.remove(u)
            else:
                lst.append(u)
            self._touch()
        return {"ok": True}

    # ================================================================ BOQ
    def get_boq(self, a: dict | None = None) -> dict:
        p = self._need()
        res = self.result()
        b = res.boq
        t = b["totals"]
        is_comb = b["combined"]
        tabs = [tab_json(b["tabs"][k], "combined", is_comb) for k in TAB_ORDER if k in b["tabs"]]
        sys_rows = [{"key": s, "name": SYS[s].name, "color": SYS[s].color,
                     "sa": fmt(t["systems"][s]["standalone"]), "co": fmt(t["systems"][s]["combined"]) if is_comb else "—"}
                    for s in res.selected]
        lib = self.lib.as_map()
        labour = [{"key": k, "role": v, "rate": lib[k]["list_price"] or "", "currency": lib[k]["currency"]}
                  for k, v in catalog.LABOUR_ROLES.items()]
        com = p["commercial"]
        used_cur = sorted({l.currency for l in all_lines(b, True) if l.currency != "QAR"} | {"USD", "EUR", "GBP"})
        fxr = {r["code"]: r for r in self._fx_rows()}
        return {
            "tabs": tabs, "combined": is_comb, "sysRows": sys_rows,
            "m": {"shared": fmt(t["shared"]), "standalone": fmt(t["standalone"]), "combinedBase": fmt(t["combined"]),
                  "base": fmt(t["base"]), "saving": fmt(t["saving"]), "network": fmt(t["network"]),
                  "optional": fmt(t["optional"])},
            "confMix": b["conf_mix"], "unpriced": b["unpriced"], "rfq": b["rfq"],
            "commercial": {k: com.get(k, "") for k in ("markup", "duty", "freight", "labour_markup", "pm_pct")},
            "fx": [fxr[c] for c in used_cur if c in fxr], "labour": labour,
        }

    def update_boq_line(self, a: dict) -> dict:
        p = self._need()
        key = a["key"]
        patch = a.get("patch") or {}
        with self.lock:
            custom = next((c for c in p["boq"]["extra_lines"] if c["id"] == key), None)
            ov = p["boq"]["overrides"].setdefault(key, {})
            for k, v in patch.items():
                if k == "qty":
                    if v in (None, ""):
                        ov.pop("qty", None)
                        continue
                    d = dec(v, None)
                    if d is None or d < 0:
                        raise UserError("Quantity must be a number ≥ 0")
                    ov["qty"] = format(d, "f")
                    if custom:
                        custom["qty"] = format(d, "f")
                elif k == "list_price":
                    if v in (None, ""):
                        ov.pop("list_price", None)
                        if custom:
                            custom["list_price"] = None
                        continue
                    d = dec(v, None)
                    if d is None or d < 0:
                        raise UserError("Price must be a number ≥ 0")
                    ov["list_price"] = format(d, "f")
                    if custom:
                        custom["list_price"] = format(d, "f")
                elif k == "currency":
                    if v not in CODES:
                        raise UserError("Unknown currency")
                    ov["currency"] = v
                    if custom:
                        custom["currency"] = v
                elif k == "discount":
                    if v in (None, ""):
                        ov.pop("discount", None)
                        continue
                    d = dec(v, None)
                    if d is None or not (0 <= d < 100):
                        raise UserError("Discount must be between 0 and 100")
                    ov["discount"] = format(d, "f")
                    if custom:
                        custom["discount"] = format(d, "f")
                elif k == "description" and custom:
                    custom["description"] = v
                elif k == "reset":
                    p["boq"]["overrides"].pop(key, None)
            if not ov and key in p["boq"]["overrides"]:
                p["boq"]["overrides"].pop(key, None)
            if a.get("to_library") and not custom:
                item = a.get("item")
                if item and "list_price" in patch:
                    self.lib.update(item, {"list_price": patch["list_price"], "currency": patch.get("currency") or ov.get("currency")})
                    self._lib_ver += 1
                    p["boq"]["overrides"].get(key, {}).pop("list_price", None)
            self._touch()
        return {"ok": True}

    def add_boq_line(self, a: dict) -> dict:
        p = self._need()
        item = a.get("item")
        it = catalog.BY_KEY.get(item or "") if item else None
        libr = self.lib.get(item) if item else None
        line = {"id": "x" + uuid.uuid4().hex[:8], "tab": a["tab"], "section": a["section"], "item": item,
                "description": a.get("description") or (libr or {}).get("description") or (it.description if it else "New item"),
                "manufacturer": a.get("manufacturer") or (libr or {}).get("manufacturer", ""),
                "part_no": a.get("part_no") or (libr or {}).get("part_no", ""),
                "unit": a.get("unit") or (libr or {}).get("unit") or "ea",
                "category": a.get("category") or (libr or {}).get("category") or "Device",
                "qty": str(a.get("qty") or 1), "list_price": a.get("list_price") if not item else None,
                "currency": a.get("currency") or (libr or {}).get("currency") or "USD", "discount": a.get("discount")}
        with self.lock:
            p["boq"]["extra_lines"].append(line)
            self._touch()
        return {"ok": True, "id": line["id"]}

    def delete_boq_line(self, a: dict) -> dict:
        p = self._need()
        with self.lock:
            n = len(p["boq"]["extra_lines"])
            p["boq"]["extra_lines"] = [c for c in p["boq"]["extra_lines"] if c["id"] != a["key"]]
            if len(p["boq"]["extra_lines"]) == n:  # computed line: set quantity to zero
                p["boq"]["overrides"].setdefault(a["key"], {})["qty"] = "0"
            else:
                p["boq"]["overrides"].pop(a["key"], None)
            self._touch()
        return {"ok": True}

    def set_commercial(self, a: dict) -> dict:
        p = self._need()
        with self.lock:
            for k in ("markup", "duty", "freight", "labour_markup", "pm_pct", "payment_terms", "delivery", "warranty"):
                if k in a:
                    v = a[k]
                    if k in ("markup", "duty", "freight", "pm_pct") or (k == "labour_markup" and v not in (None, "")):
                        d = dec(v, None)
                        if d is None or d < 0 or d > 500:
                            raise UserError(f"{k.replace('_', ' ').title()}: enter a percentage")
                        v = format(d.normalize(), "f")
                    p["commercial"][k] = v
            self._touch()
        return {"ok": True}

    def set_labour_rate(self, a: dict) -> dict:
        try:
            self.lib.update(a["key"], {"list_price": a.get("rate"), "currency": a.get("currency") or "QAR",
                                       "confidence": "L" if a.get("rate") not in (None, "") else ""})
        except ValueError as e:
            raise UserError(str(e))
        self._lib_ver += 1
        return {"ok": True}

    # ================================================================ price library
    def get_prices(self, a: dict | None = None) -> dict:
        a = a or {}
        q = (a.get("q") or "").strip().lower()
        system = a.get("system") or ""
        cat = a.get("category") or ""
        only_used = bool(a.get("used"))
        only_unpriced = bool(a.get("unpriced"))
        used: dict[str, Decimal] = {}
        if self.project and self.project.get("drawings"):
            for l in all_lines(self.result().boq):
                if l.item:
                    used[l.item] = used.get(l.item, ZERO) + l.qty
        rows = []
        all_rows = self.lib.rows()
        today = date.today()
        for r in all_rows:
            if system and r["system"] != system:
                continue
            if cat and r["category"] != cat:
                continue
            if only_used and r["key"] not in used:
                continue
            if only_unpriced and r["list_price"] is not None:
                continue
            if q and not any(q in (r.get(f) or "").lower() for f in ("description", "manufacturer", "part_no", "source", "key")):
                continue
            stale = False
            if r["date_checked"]:
                try:
                    stale = (today - datetime.strptime(r["date_checked"][:10], "%Y-%m-%d").date()).days > 90
                except ValueError:
                    pass
            rows.append({
                "key": r["key"], "system": r["system"], "systemName": tab_name(r["system"]) if r["system"] in TAB_ORDER else ("Labour" if r["system"] == "labour" else r["system"]),
                "category": r["category"], "desc": r["description"], "mfr": r["manufacturer"], "part": r["part_no"],
                "unit": r["unit"], "list": r["list_price"] or "", "cur": r["currency"], "disc": r["discount"] or "",
                "source": r["source"] or "", "date": r["date_checked"] or "", "dateF": _d(r["date_checked"]),
                "conf": r["confidence"] or "", "stale": stale, "custom": bool(r["is_custom"]),
                "used": fmt_qty(used[r["key"]]) if r["key"] in used else "",
            })
        priced = sum(1 for r in all_rows if r["list_price"] is not None)
        return {"rows": rows, "total": len(all_rows), "shown": len(rows), "priced": priced,
                "usedCount": len(used), "unpricedUsed": sum(1 for k in used if not (self.lib.get(k) or {}).get("list_price"))}

    def update_price(self, a: dict) -> dict:
        try:
            row = self.lib.update(a["key"], a.get("patch") or {})
        except ValueError as e:
            raise UserError(str(e))
        except KeyError:
            raise UserError("Item not found")
        self._lib_ver += 1
        self._res = None
        return {"ok": True, "row": row}

    def add_price_item(self, a: dict) -> dict:
        row = self.lib.add_custom(a)
        self._lib_ver += 1
        return {"ok": True, "row": row}

    def import_prices(self, a: dict) -> dict:
        text = a.get("text")
        if text is None and a.get("path"):
            raw = Path(a["path"]).read_bytes()
            for enc in ("utf-8-sig", "cp1252", "latin-1"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
        if not text:
            raise UserError("The CSV file is empty.")
        try:
            out = self.lib.import_csv(text, commit=bool(a.get("commit")), filename=a.get("name") or "")
        except ValueError as e:
            raise UserError(str(e))
        if a.get("commit"):
            self._lib_ver += 1
        out["name"] = a.get("name") or (Path(a["path"]).name if a.get("path") else "")
        return out

    def export_prices(self, a: dict | None = None) -> dict:
        a = a or {}
        target = a.get("path") or str((self.folder or self.data_dir) / f"price-library-{date.today().isoformat()}.csv")
        Path(target).write_text(self.lib.export_csv(), encoding="utf-8-sig")
        return {"ok": True, "path": target}

    # ================================================================ texts
    def get_texts(self, _=None) -> dict:
        p = self._need()
        return {"texts": p["texts"]}

    def update_texts(self, a: dict) -> dict:
        p = self._need()
        kind = a["kind"]
        if kind not in ("assumptions", "exclusions", "rfis", "terms"):
            raise UserError("Unknown list")
        with self.lock:
            p["texts"][kind] = [str(x).strip() for x in a.get("items", []) if str(x).strip()]
            self._touch()
        return {"ok": True, "texts": p["texts"]}

    def reset_texts(self, a: dict) -> dict:
        from elv_engine import texts
        p = self._need()
        with self.lock:
            p["texts"][a["kind"]] = texts.defaults()[a["kind"]]
            self._touch()
        return {"ok": True, "texts": p["texts"]}

    # ================================================================ checks / export
    def get_checks(self, _=None) -> dict:
        p = self._need()
        res = self.result()
        ck = res.checks
        rev = p["revision"]["current"]
        sel = p["exports"]["selected"]
        exports = [{"id": k, "name": n, "fmt": f, "on": bool(sel.get(k))} for k, n, f in EXPORTS]
        if len(res.selected) < 2:
            exports = [e for e in exports if e["id"] != "summary" or True]
        so = p["signoff"]
        approval = []
        for step, label in (("prepared", "Prepared"), ("checked", "Checked"), ("approved", "Approved")):
            s = so.get(step, {})
            approval.append({"step": step, "label": label, "who": s.get("name") or "Name not set", "role": s.get("role") or "",
                             "done": bool(s.get("at")), "when": _dt(s.get("at"))})
        ov = p["checks"].get("override")
        last = p["exports"].get("last")
        return {
            "groups": ck["groups"], "total": ck["total"], "passed": ck["passed"], "blocking": ck["blocking"],
            "lastRun": datetime.now().strftime("%d %b %Y, %H:%M"), "rev": rev,
            "exports": exports, "bump": p["exports"].get("bump", True), "changeLog": p["exports"].get("change_log", ""),
            "approval": approval, "override": ov, "canIssue": ck["blocking"] == 0 or bool(ov),
            "last": last, "status": p["info"].get("status", "Draft"),
        }

    def set_export_options(self, a: dict) -> dict:
        p = self._need()
        with self.lock:
            if "selected" in a:
                p["exports"]["selected"].update({k: bool(v) for k, v in a["selected"].items()})
            if "bump" in a:
                p["exports"]["bump"] = bool(a["bump"])
            if "change_log" in a:
                p["exports"]["change_log"] = a["change_log"]
            self._touch()
        return {"ok": True}

    def set_override(self, a: dict) -> dict:
        p = self._need()
        reason = (a.get("reason") or "").strip()
        with self.lock:
            if not reason:
                p["checks"]["override"] = None
            else:
                p["checks"]["override"] = {"reason": reason, "by": self.settings["user"].get("name") or "",
                                           "at": now_iso(), "failing": self.result().checks["blocking"]}
            self._touch()
        return {"ok": True}

    def sign(self, a: dict) -> dict:
        p = self._need()
        step = a["step"]
        with self.lock:
            s = p["signoff"].setdefault(step, {})
            if s.get("at"):
                s["at"] = None
                if step == "approved" and p["info"]["status"] == "Approved":
                    p["info"]["status"] = "In review"
            else:
                if not s.get("name"):
                    raise UserError(f"Enter the {step} name in Project details first.")
                if step == "approved":
                    res = self.result()
                    if res.checks["blocking"] and not p["checks"].get("override"):
                        raise UserError("Checks are failing. Fix them or record an override reason before approval.")
                s["at"] = now_iso()
                if step == "checked" and p["info"]["status"] == "Draft":
                    p["info"]["status"] = "In review"
                if step == "approved":
                    p["info"]["status"] = "Approved"
            self._touch()
        return {"ok": True}

    def set_status(self, a: dict) -> dict:
        p = self._need()
        if a["status"] not in STATUS:
            raise UserError("Unknown status")
        with self.lock:
            p["info"]["status"] = a["status"]
            self._touch()
        return {"ok": True}

    def generate(self, a: dict) -> dict:
        p = self._need()
        res = self.result()
        if res.checks["blocking"] and not p["checks"].get("override"):
            raise UserError(f"{res.checks['blocking']} check(s) failing. Fix them or record an override reason to issue.")
        sel = {k for k, v in p["exports"]["selected"].items() if v}
        if not sel:
            raise UserError("Select at least one output.")
        bump = bool(a.get("bump", p["exports"].get("bump", True)))
        note = a.get("change_log", p["exports"].get("change_log", "")) or ""
        return {"ok": True, "job": self._start_job("export", lambda job: self._export_job(job, sel, bump, note))}

    def _export_job(self, job, sel: set[str], bump: bool, note: str) -> dict:
        from elv_engine.outputs import package
        with self.lock:
            p = self.project
            if bump:
                self._bump_revision(note)
            res = self.result()
            snap = copy.deepcopy(p)
            folder = self.folder
            company = {**self.settings["company"], **{k: v for k, v in (p.get("company") or {}).items() if v}}
            user = self.settings["user"]
        out = package.generate(snap, res, folder, sel, company, user,
                               progress=lambda f, m: self._job_progress(job, f, m))
        with self.lock:
            p["exports"]["last"] = {"at": now_iso(), "rev": p["revision"]["current"], "folder": out["folder"],
                                    "files": out["files"], "zip": out.get("zip")}
            p["exports"]["change_log"] = ""
            self._touch()
        self.open_folder({"path": out["folder"]})
        return out

    def _bump_revision(self, note: str) -> None:
        p = self.project
        res = self.result()
        t = res.boq["totals"]
        new = p["revision"]["current"] + 1  # Rev n -> n+1 (first issue: Rev 0 -> Rev 1)
        snap_lines = {l.key: {"qty": str(l.qty), "unit": None if l.unit_qar is None else str(l.unit_qar),
                              "total": str(l.total), "desc": l.description, "tab": l.tab}
                      for l in all_lines(res.boq, True)}
        p["revision"]["history"].append({
            "rev": new, "at": now_iso(), "by": self._user_short() or self.settings["user"].get("name", ""),
            "note": note, "status": p["info"].get("status", "Draft"),
            "totals": {k: str(v) for k, v in t.items() if not isinstance(v, dict)},
            "systems": {k: {kk: str(vv) for kk, vv in v.items()} for k, v in t["systems"].items()},
            "commercial": dict(p["commercial"]), "fx": {k: str(v) for k, v in res.fx.items()},
            "lines": snap_lines, "selected": list(res.selected), "combined": res.boq["combined"],
        })
        p["revision"]["current"] = new

    def get_history(self, a: dict | None = None) -> dict:
        p = self._need()
        hist = sorted(p["revision"]["history"], key=lambda h: h["rev"], reverse=True)
        res = self.result() if p["drawings"] else None
        cur_total = res.boq["totals"]["base"] if res else ZERO
        revs = [{"rev": h["rev"], "label": f"Rev {h['rev']}", "at": _d(h["at"]), "by": h.get("by", ""),
                 "note": h.get("note", ""), "status": h.get("status", ""), "totalF": fmt(dec(h["totals"]["base"]))} for h in hist]
        sel = (a or {}).get("rev")
        changes, compare = [], None
        if hist:
            to = next((h for h in hist if h["rev"] == sel), hist[0])
            frm = next((h for h in hist if h["rev"] < to["rev"]), None)
            if frm:
                changes = self._diff(frm, to)
                a_, b_ = dec(frm["totals"]["base"]), dec(to["totals"]["base"])
                delta = b_ - a_
                compare = {"from": f"Rev {frm['rev']}", "to": f"Rev {to['rev']}", "fromF": fmt(a_), "toF": fmt(b_),
                           "deltaF": ("+" if delta >= 0 else "−") + fmt(abs(delta)) +
                                     (f" ({'+' if delta >= 0 else '−'}{abs(delta) / a_ * 100:.2f}%)" if a_ else ""),
                           "up": delta >= 0}
            else:
                compare = {"from": None, "to": f"Rev {to['rev']}", "toF": fmt(dec(to["totals"]["base"]))}
            sel = to["rev"]
        return {"revisions": revs, "selected": sel, "changes": changes, "compare": compare,
                "current": {"rev": p["revision"]["current"], "totalF": fmt(cur_total), "unsaved": True}}

    def _diff(self, a: dict, b: dict) -> list[dict]:
        out = []
        for s in sorted(set(a.get("systems", {})) | set(b.get("systems", {})), key=lambda k: SYSTEM_KEYS.index(k)):
            va = dec(a.get("systems", {}).get(s, {}).get("combined" if b.get("combined") else "standalone"), ZERO) or ZERO
            vb = dec(b.get("systems", {}).get(s, {}).get("combined" if b.get("combined") else "standalone"), ZERO) or ZERO
            if va != vb:
                la, lb = a.get("lines", {}), b.get("lines", {})
                notes = []
                for k in sorted(set(la) | set(lb)):
                    if (la.get(k) or lb.get(k))["tab"] != s:
                        continue
                    qa = dec((la.get(k) or {}).get("qty"), ZERO) or ZERO
                    qb = dec((lb.get(k) or {}).get("qty"), ZERO) or ZERO
                    if qa != qb and (lb.get(k) or la.get(k))["desc"]:
                        d = qb - qa
                        notes.append(f"{'+' if d > 0 else '−'}{fmt_qty(abs(d))} {(lb.get(k) or la.get(k))['desc'].split(',')[0]}")
                out.append({"area": SYS[s].name, "what": "; ".join(notes[:3]) or "prices / quantities updated",
                            "delta": str(vb - va), "deltaF": ("+" if vb >= va else "−") + fmt(abs(vb - va)), "pos": vb > va})
        for k, label in (("shared", "Shared infrastructure"), ("network", "Network Active"), ("optional", "Optional")):
            va, vb = dec(a["totals"].get(k), ZERO) or ZERO, dec(b["totals"].get(k), ZERO) or ZERO
            if va != vb:
                out.append({"area": label, "what": "re-sized / re-priced", "delta": str(vb - va),
                            "deltaF": ("+" if vb >= va else "−") + fmt(abs(vb - va)), "pos": vb > va})
        ca, cb = a.get("commercial", {}), b.get("commercial", {})
        for k, label in (("markup", "Markup"), ("duty", "Duty"), ("freight", "Freight")):
            if str(ca.get(k)) != str(cb.get(k)):
                out.append({"area": "Commercial", "what": f"{label} changed from {ca.get(k)}% to {cb.get(k)}%",
                            "delta": "", "deltaF": "", "pos": False})
        for c in sorted(set(a.get("fx", {})) & set(b.get("fx", {}))):
            if c != "QAR" and a["fx"][c] != b["fx"][c]:
                out.append({"area": "Commercial", "what": f"{c} rate updated {a['fx'][c]} → {b['fx'][c]} QAR",
                            "delta": "", "deltaF": "", "pos": False})
        return out

    def open_folder(self, a: dict | None = None) -> dict:
        path = (a or {}).get("path") or (str(self.folder / "outputs") if self.folder else None)
        if not path or not os.path.exists(path):
            return {"ok": False}
        if os.environ.get("ELV_NO_OPEN"):
            return {"ok": True}
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return {"ok": False}
        return {"ok": True}

    # ================================================================ search
    def search(self, a: dict) -> dict:
        q = (a.get("q") or "").strip().lower()
        if len(q) < 2:
            return {"projects": [], "items": []}
        projects = [r for r in self.list_projects()["rows"]
                    if q in (r["name"] + r["client"] + r["ref"]).lower()][:6]
        items = [r for r in self.get_prices({"q": q})["rows"]][:8]
        return {"projects": projects, "items": items}

    # ================================================================ jobs
    def _start_job(self, kind: str, fn: Callable[[dict], Any]) -> dict:
        jid = uuid.uuid4().hex[:10]
        job = {"id": jid, "kind": kind, "pct": 0.0, "message": "Starting", "done": False, "error": None,
               "result": None}
        self.jobs[jid] = job

        def run():
            try:
                job["result"] = fn(job)
            except UserError as e:
                job["error"] = str(e)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                job["error"] = f"{type(e).__name__}: {e}"
            job["done"] = True
            job["pct"] = 1.0
            self.emit({"type": "job", **self._job_public(job)})
        threading.Thread(target=run, daemon=True, name=f"job-{kind}").start()
        return self._job_public(job)

    def _job_progress(self, job, pct, message) -> None:
        job["pct"] = max(job["pct"], min(0.99, float(pct)))
        job["message"] = message
        self.emit({"type": "job", **self._job_public(job)})

    def _job_public(self, job) -> dict:
        return {k: job[k] for k in ("id", "kind", "pct", "message", "done", "error")} | {
            "result": job["result"] if job["done"] else None}

    def get_job(self, a: dict) -> dict:
        j = self.jobs.get(a["id"])
        if not j:
            raise UserError("Unknown job")
        return self._job_public(j)
