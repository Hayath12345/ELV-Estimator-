"""Extract rooms, door tags and scale from a vector PDF page (PyMuPDF).

Coordinates are PDF points converted to y-up (origin bottom-left). ``unit_m`` comes from
the drawing scale printed on the sheet (e.g. "1:150"); otherwise manual calibration.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Callable

from .. import geometry as G
from . import classify as C
from .common import assign_labels, empty_result, finalise_rooms, standard_scale

RE_SCALE = re.compile(r"\b1\s*:\s*(\d{2,4})\b")
RE_DOOR_TAG = re.compile(r"^D[-\s]?\d{1,4}[A-Z]?$", re.I)
PT_M = 0.0254 / 72.0  # metres per PDF point on paper


def page_count(path: str) -> int:
    import pymupdf as fitz
    with fitz.open(path) as doc:
        return doc.page_count


def extract_pdf(path: str, page_no: int = 0, progress: Callable[[float, str], None] | None = None) -> dict:
    import pymupdf as fitz

    progress = progress or (lambda f, m: None)
    res = empty_result("pdf")
    progress(0.05, "Opening PDF")
    doc = fitz.open(path)
    page = doc[page_no]
    H = page.rect.height
    W = page.rect.width
    res["extents"] = [0.0, 0.0, W, H]
    res["page"] = page_no
    res["page_size_mm"] = [round(W * 25.4 / 72), round(H * 25.4 / 72)]

    def yup(x, y):
        return (float(x), float(H - y))

    progress(0.2, "Reading text")
    texts = []
    words = page.get_text("dict")
    for b in words.get("blocks", []):
        for line in b.get("lines", []):
            txt = " ".join(s["text"] for s in line.get("spans", [])).strip()
            if not txt:
                continue
            x0, y0, x1, y1 = line["bbox"]
            sz = max((s.get("size", 0) for s in line.get("spans", [])), default=0)
            texts.append({"text": " ".join(txt.split()), "pt": list(yup((x0 + x1) / 2, (y0 + y1) / 2)),
                          "h": sz, "layer": ""})
    # join two-line labels in the same column ("OPEN" / "OFFICE")
    texts = _merge_lines(texts)

    progress(0.45, "Reading vector paths")
    polys = []
    linework = []
    for d in page.get_drawings():
        for it in d.get("items", []):
            op = it[0]
            if op == "l":
                a, b = it[1], it[2]
                linework.append([*yup(a.x, a.y), *yup(b.x, b.y)])
            elif op == "re":
                r = it[1]
                pts = [yup(r.x0, r.y0), yup(r.x1, r.y0), yup(r.x1, r.y1), yup(r.x0, r.y1)]
                polys.append({"pts": pts, "layer": d.get("layer") or "", "src": "re"})
                linework.append([c for p in pts + [pts[0]] for c in p])
            elif op == "qu":
                q = it[1]
                pts = [yup(q.ul.x, q.ul.y), yup(q.ur.x, q.ur.y), yup(q.lr.x, q.lr.y), yup(q.ll.x, q.ll.y)]
                polys.append({"pts": pts, "layer": d.get("layer") or "", "src": "qu"})
            elif op == "c":
                pts = [yup(p.x, p.y) for p in it[1:5]]
                linework.append([c for p in pts for c in p])
        if d.get("closePath"):
            pts = []
            for it in d.get("items", []):
                if it[0] == "l":
                    pts.append(yup(it[1].x, it[1].y))
            if len(pts) >= 3:
                polys.append({"pts": pts, "layer": d.get("layer") or "", "src": "path"})

    progress(0.7, "Resolving scale")
    found = [int(m.group(1)) for t in texts for m in [RE_SCALE.search(t["text"])] if m]
    if found:
        denom = standard_scale(Counter(found).most_common(1)[0][0])
        res["unit_m"] = PT_M * denom
        res["plot_scale"] = denom
        res["scale_conf"] = "Medium"
        res["scale_note"] = f"Scale 1:{denom} read from sheet text — verify with two-point calibration"
    else:
        res["scale_note"] = "Scale not found – calibrate manually"

    um = res["unit_m"] or PT_M * 100
    min_a, max_a = 1.0 / (um * um), 6000.0 / (um * um)
    cand = [p for p in polys if min_a <= G.area(p["pts"]) <= max_a]
    labels = [t for t in texts if C.looks_like_room_name(t["text"]) or C.looks_like_room_number(t["text"])]
    rooms = assign_labels(cand, labels, um, "Medium")
    res["rooms"] = finalise_rooms(rooms, res["unit_m"] or 0)
    res["doors"] = [{"pt": t["pt"], "leaves": 1, "width_m": 0.0, "tag": t["text"], "block": "", "src": "tag"}
                    for t in texts if RE_DOOR_TAG.match(t["text"])]
    res["linework"] = linework[:400_000]
    res["counts"] = {"texts": len(texts), "closed_paths": len(polys), "door_tags": len(res["doors"])}
    res["warnings"].append("PDF input: work positions are estimated from room areas; use the DWG for furniture blocks.")
    if not res["doors"]:
        res["warnings"].append("No door tags found on the sheet — door positions will be inferred.")
    doc.close()
    progress(0.95, "Extraction complete")
    return res


def _merge_lines(texts):
    out = []
    used = set()
    for i, t in enumerate(texts):
        if i in used:
            continue
        cur = dict(t)
        for j in range(i + 1, len(texts)):
            if j in used:
                continue
            u = texts[j]
            if (abs(u["pt"][0] - cur["pt"][0]) < max(cur["h"], 1) * 3
                    and 0 < cur["pt"][1] - u["pt"][1] < max(cur["h"], 1) * 1.6
                    and C.looks_like_room_name(cur["text"] + " " + u["text"])
                    and not C.looks_like_room_number(u["text"])
                    and len(cur["text"]) < 20 and len(u["text"]) < 20):
                cur["text"] = cur["text"] + " " + u["text"]
                used.add(j)
                break
        out.append(cur)
    return out


def render_page_png(path: str, page_no: int, out_png: str, max_px: int = 4096) -> dict:
    import pymupdf as fitz
    with fitz.open(path) as doc:
        page = doc[page_no]
        zoom = max_px / max(page.rect.width, page.rect.height)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pix.save(out_png)
        return {"png": out_png, "width": pix.width, "height": pix.height,
                "extents": [0.0, 0.0, page.rect.width, page.rect.height]}
