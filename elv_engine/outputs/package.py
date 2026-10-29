"""Generate the selected outputs into <project>/outputs/Rev<n>/ and zip them."""
from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..money import fmt
from . import pdf_layout, pdf_quote, pdf_racks, xlsx_costing, xlsx_quote
from .common import file_ref, system_name


def generate(project: dict, res, folder: Path, selected: set[str], company: dict, user: dict,
             progress: Callable[[float, str], None] | None = None) -> dict:
    progress = progress or (lambda f, m: None)
    rev = project["revision"]["current"]
    out = Path(folder) / "outputs" / f"Rev{rev}"
    out.mkdir(parents=True, exist_ok=True)
    ref = file_ref(project)
    files: list[str] = []
    steps = [k for k in ("full", "per", "summary", "layout", "racks", "cost") if k in selected]
    n = max(1, len(steps) + (1 if "zip" in selected else 0))
    done = 0

    def step(msg):
        nonlocal done
        progress(done / n, msg)
        done += 1

    if "full" in selected:
        step("Complete quotation (PDF + Excel)")
        p = out / f"{ref}_Rev{rev}_Quotation.pdf"
        pdf_quote.build_complete(str(p), project, res, company)
        files.append(str(p))
        x = out / f"{ref}_Rev{rev}_Quotation.xlsx"
        xlsx_quote.build(str(x), project, res, company)
        files.append(str(x))
    if "per" in selected:
        step("Per-system quotations")
        for s in res.selected:
            short = {"cctv": "CCTV", "access": "ACS", "iptv": "IPTV", "cabling": "SC", "intercom": "IC", "intrusion": "INT"}[s]
            p = out / f"{ref}_Rev{rev}_{short}_Quotation.pdf"
            pdf_quote.build_system(str(p), project, res, company, s)
            files.append(str(p))
    if "summary" in selected:
        step("Combined summary")
        p = out / f"{ref}_Rev{rev}_Combined_Summary.pdf"
        pdf_quote.build_summary(str(p), project, res, company)
        files.append(str(p))
    if "layout" in selected and res.floors:
        step("Layout drawings")
        p = out / f"{ref}_Rev{rev}_Layouts.pdf"
        pdf_layout.build(str(p), project, res, company, Path(folder),
                         progress=lambda f, m: progress((done - 1 + f) / n, m))
        files.append(str(p))
    if "racks" in selected:
        step("Rack elevations")
        p = out / f"{ref}_Rev{rev}_Rack_Elevations.pdf"
        pdf_racks.build(str(p), project, res, company, project.get("comms", {}).get("reserved"))
        files.append(str(p))
    if "cost" in selected:
        step("Internal costing workbook")
        p = out / f"{ref}_Rev{rev}_Internal_Costing.xlsx"
        xlsx_costing.build(str(p), project, res, project.get("checks", {}).get("override"))
        files.append(str(p))
    t = res.boq["totals"]
    issue = {
        "project": project["info"].get("name"), "ref": project["info"].get("ref"), "rev": rev,
        "generated": datetime.now().isoformat(timespec="seconds"), "by": user.get("name", ""),
        "systems": [system_name(s) for s in res.selected], "combined": res.boq["combined"],
        "totals": {k: fmt(v) for k, v in t.items() if not isinstance(v, dict)},
        "checks": f"{res.checks['passed']}/{res.checks['total']}", "override": project.get("checks", {}).get("override"),
        "files": [Path(f).name for f in files],
    }
    (out / "issue.json").write_text(json.dumps(issue, indent=1, ensure_ascii=False), encoding="utf-8")
    zpath = None
    if "zip" in selected and files:
        step("Zip package")
        zpath = out / f"{ref}_Rev{rev}_Package.zip"
        client_files = [f for f in files if "Internal_Costing" not in f]
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for f in client_files:
                z.write(f, Path(f).name)
        files.append(str(zpath))
    progress(1.0, "Outputs generated")
    return {"folder": str(out), "files": [Path(f).name for f in files], "zip": str(zpath) if zpath else None}
