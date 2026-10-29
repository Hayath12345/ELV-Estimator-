"""Layout drawings (PyMuPDF): A1 landscape, one page per floor for all systems plus one
page per system, at a standard scale (1:50 … 1:500) with legend and title block.
The drawing background is the original vector linework (DWG/DXF) or the original PDF
page, placed once as a reusable XObject.
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import date
from pathlib import Path

from ..layout import type_label
from ..systems import BY_KEY, SYSTEMS
from .common import dstr, quote_date, rev_label, safe

MM = 72 / 25.4
A1 = (841 * MM, 594 * MM)
STD = [50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 750, 1000]


def _rgb(hexs: str):
    h = hexs.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


NAVY = _rgb("#1F3B70")
INK = _rgb("#14254A")
GREY = _rgb("#5E6A7D")
LINE = _rgb("#D5DBE6")


def _symbol(shape, sys: str, x: float, y: float, r: float, sub: str | None):
    c = _rgb(BY_KEY[sys].color)
    w = (1, 1, 1)
    if sys == "cctv":
        shape.draw_circle((x, y), r)
        shape.finish(color=w, fill=c, width=r * 0.25)
    elif sys == "access":
        shape.draw_rect((x - r * .82, y - r * .82, x + r * .82, y + r * .82))
        shape.finish(color=w, fill=c, width=r * 0.2)
    elif sys == "iptv":
        shape.draw_rect((x - r * 1.3, y - r * .55, x + r * 1.3, y + r * .55))
        shape.finish(color=w, fill=c, width=r * 0.18)
    elif sys == "cabling":
        if sub == "ap":
            shape.draw_circle((x, y), r * 1.05)
            shape.finish(color=c, fill=w, width=r * 0.35)
            shape.draw_circle((x, y), r * 0.32)
            shape.finish(color=c, fill=c, width=0)
        else:
            shape.draw_rect((x - r * .45, y - r * .45, x + r * .45, y + r * .45))
            shape.finish(color=c, fill=c, width=0)
    elif sys == "intercom":
        shape.draw_polyline([(x, y - r * 1.15), (x + r * 1.15, y), (x, y + r * 1.15), (x - r * 1.15, y), (x, y - r * 1.15)])
        shape.finish(color=w, fill=c, width=r * 0.2, closePath=True)
    else:
        shape.draw_polyline([(x, y - r), (x + r, y + r * .82), (x - r, y + r * .82), (x, y - r)])
        shape.finish(color=w, fill=c, width=r * 0.18, closePath=True)


def build(path: str, project: dict, res, company: dict, folder: Path, progress=None) -> int:
    import pymupdf as fitz
    from ..extract.render import draw_linework, load_linework

    doc = fitz.open()
    sel = res.selected
    pages = 0
    by_floor: dict[str, list[dict]] = {}
    for d in res.devices:
        if d["sys"] in sel:
            by_floor.setdefault(d["floor"], []).append(d)
    drawings = {d["id"]: d for d in project["drawings"]}
    n_floors = max(1, len(res.floors))
    for fi, fl in enumerate(res.floors):
        if progress:
            progress(fi / n_floors, f"Layout drawings · {fl.name}")
        dw = drawings.get(fl.key, {})
        ex = dw.get("extraction") or {}
        x0, y0, x1, y1 = fl.extents
        W, H = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
        PW, PH = A1
        side = 120 * MM
        margin = 12 * MM
        area = fitz.Rect(margin, margin, PW - side - margin, PH - margin)
        if fl.calibrated and fl.unit_m:
            need = max(W * fl.unit_m * 1000 / (area.width / MM), H * fl.unit_m * 1000 / (area.height / MM))
            denom = next((s for s in STD if s >= need), int(math.ceil(need / 100) * 100))
            s = fl.unit_m * 1000 / denom * MM  # pt per drawing unit
            scale_txt = f"1:{denom} at A1"
        else:
            s = min(area.width / W, area.height / H)
            denom = None
            scale_txt = "Not to scale (scale not calibrated)"
        ox = area.x0 + (area.width - W * s) / 2
        oy = area.y0 + (area.height - H * s) / 2
        bg_rect = fitz.Rect(ox, oy, ox + W * s, oy + H * s)

        def T(x, y):
            return (ox + (x - x0) * s, oy + (y1 - y) * s)

        # background as one reusable XObject
        src = fitz.open()
        if ex.get("kind") == "pdf":
            pdf_path = folder / "drawings" / dw.get("file", "")
            srcpdf = fitz.open(str(pdf_path))
            bg_page_src, bg_pno = srcpdf, int(ex.get("page", 0))
        else:
            sp = src.new_page(width=bg_rect.width, height=bg_rect.height)
            lw = load_linework(str(folder / "cache" / (ex.get("linework_file") or f"{fl.key}.lines.json.gz")))
            draw_linework(sp, lw, fl.extents, sp.rect, color=(0.55, 0.59, 0.66), width=0.35)
            bg_page_src, bg_pno = src, 0
        xref = 0
        floor_devs = by_floor.get(fl.key, [])
        for sys_page in [None] + [k for k in sel if any(d["sys"] == k for d in floor_devs)]:
            page = doc.new_page(width=PW, height=PH)
            pages += 1
            page.draw_rect(fitz.Rect(6 * MM, 6 * MM, PW - 6 * MM, PH - 6 * MM), color=INK, width=1.2)
            page.show_pdf_page(bg_rect, bg_page_src, bg_pno)
            sh = page.new_shape()
            # comms rooms and room names
            for r in fl.rooms:
                pts = [T(*p) for p in r.poly]
                if r.comms:
                    sh.draw_polyline(pts + [pts[0]])
                    sh.finish(color=NAVY, fill=NAVY, fill_opacity=0.18, width=1.2, closePath=True)
            sh.commit()
            if ex.get("kind") != "pdf":
                for r in fl.rooms:
                    lx, ly = T(*r.label_pt)
                    fs = 2.2 * MM if not r.comms else 2.8 * MM
                    tw = fitz.get_text_length(safe(r.name), fontname="helv", fontsize=fs)
                    page.insert_text((lx - tw / 2, ly + fs * 0.35), safe(r.name), fontsize=fs, fontname="hebo" if r.comms else "helv",
                                     color=NAVY if r.comms else GREY)
            devs = [d for d in floor_devs if sys_page is None or d["sys"] == sys_page]
            rr = 1.5 * MM if sys_page is None else 2.0 * MM
            if sys_page in (None, "cctv"):
                fov = page.new_shape()
                for d in devs:
                    if d["sys"] != "cctv" or not fl.unit_m:
                        continue
                    from ..layout.place import camera_range
                    rng = camera_range(d["item"], {"Identify": 250, "Recognise": 125, "Observe": 62}.get(d.get("target") or "Recognise", 125))
                    rad = rng / fl.unit_m * s
                    cx, cy = T(d["x"], d["y"])
                    a = -math.radians(d.get("a", 0) or 0)
                    arc = [(cx + rad * math.cos(a - 0.62 + 1.24 * i / 12), cy + rad * math.sin(a - 0.62 + 1.24 * i / 12)) for i in range(13)]
                    fov.draw_polyline([(cx, cy)] + arc + [(cx, cy)])
                    fov.finish(color=_rgb("#E07A1F"), fill=_rgb("#E07A1F"), fill_opacity=0.05, stroke_opacity=0.25, width=0.3)
                fov.commit()
            sh = page.new_shape()
            for d in devs:
                x, y = T(d["x"], d["y"])
                _symbol(sh, d["sys"], x, y, rr, d.get("sub"))
            sh.commit()
            if sys_page is not None:
                for d in devs:
                    x, y = T(d["x"], d["y"])
                    page.insert_text((x + rr * 1.4, y - rr * 0.6), safe(d["id"]), fontsize=1.7 * MM, fontname="helv", color=INK)
            _side_panel(page, project, company, fl, sys_page, devs, scale_txt, denom, s)
        try:
            src.close()
        except Exception:
            pass
    if pages == 0:
        page = doc.new_page(width=A1[0], height=A1[1])
        page.insert_text((40, 60), "No floors to draw.", fontsize=20)
    doc.set_metadata({"title": safe(f"{project['info'].get('name', '')} — ELV layouts {rev_label(project)}"),
                      "author": safe(company.get("name") or "ELV Estimator"), "creator": "ELV Estimator"})
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return pages


def _side_panel(page, project, company, fl, sys_page, devs, scale_txt, denom, s):
    import pymupdf as fitz
    PW, PH = A1
    x0 = PW - 120 * MM - 6 * MM
    page.draw_line((x0, 6 * MM), (x0, PH - 6 * MM), color=INK, width=1)
    x = x0 + 6 * MM
    y = 18 * MM
    title = "ALL ELV SYSTEMS" if sys_page is None else BY_KEY[sys_page].full.upper()
    page.insert_text((x, y), "LEGEND", fontsize=4 * MM, fontname="hebo", color=INK)
    y += 8 * MM
    sh = page.new_shape()
    counts = Counter(d["sys"] for d in devs)
    for sysd in SYSTEMS:
        if sys_page is not None and sysd.key != sys_page:
            continue
        if not counts.get(sysd.key):
            continue
        _symbol(sh, sysd.key, x + 3 * MM, y - 1.2 * MM, 2 * MM, None)
        sh.commit()
        sh = page.new_shape()
        page.insert_text((x + 9 * MM, y), safe(f"{sysd.full} — {counts[sysd.key]}"), fontsize=3 * MM, fontname="helv", color=INK)
        y += 7 * MM
        if sys_page is not None:
            types = Counter(type_label(d) for d in devs)
            for t, n in types.most_common(12):
                page.insert_text((x + 9 * MM, y), safe(f"{n} × {t}")[:70], fontsize=2.5 * MM, fontname="helv", color=GREY)
                y += 5 * MM
            if sys_page == "cabling":
                aps = sum(1 for d in devs if d.get("sub") == "ap")
                _symbol(sh, "cabling", x + 3 * MM, y - 1.2 * MM, 2 * MM, "ap")
                sh.commit()
                sh = page.new_shape()
                page.insert_text((x + 9 * MM, y), safe(f"Wi-Fi access point outlet — {aps}"), fontsize=2.5 * MM, fontname="helv", color=GREY)
                y += 6 * MM
    y += 4 * MM
    page.draw_rect(fitz.Rect(x + 1 * MM, y - 3 * MM, x + 6 * MM, y + 1 * MM), color=NAVY, fill=NAVY, fill_opacity=0.18, width=0.8)
    page.insert_text((x + 9 * MM, y), "Comms room (MDF / IDF)", fontsize=2.8 * MM, fontname="helv", color=INK)
    y += 12 * MM
    notes = ["Device positions are indicative and subject to coordination at shop-drawing stage.",
             "Cable routes follow corridor containment to the nearest comms room; links over 90 m are flagged in the design report.",
             "Read with the quotation, BOQ and assumptions of the same revision."]
    page.insert_text((x, y), "NOTES", fontsize=3.2 * MM, fontname="hebo", color=INK)
    y += 5 * MM
    for i, n in enumerate(notes, 1):
        rect = fitz.Rect(x, y - 3 * MM, x + 106 * MM, y + 12 * MM)
        page.insert_textbox(rect, safe(f"{i}. {n}"), fontsize=2.4 * MM, fontname="helv", color=GREY)
        y += 11 * MM
    # scale bar
    if denom:
        y += 4 * MM
        bar_m = next((b for b in (1, 2, 5, 10, 20, 50) if b / fl.unit_m * s >= 30 * MM), 50)
        L = bar_m / fl.unit_m * s
        page.draw_rect(fitz.Rect(x, y, x + L / 2, y + 2 * MM), color=INK, fill=INK, width=0.5)
        page.draw_rect(fitz.Rect(x + L / 2, y, x + L, y + 2 * MM), color=INK, width=0.5)
        page.insert_text((x, y + 6 * MM), "0", fontsize=2.4 * MM, fontname="helv", color=GREY)
        page.insert_text((x + L - 8 * MM, y + 6 * MM), f"{bar_m} m", fontsize=2.4 * MM, fontname="helv", color=GREY)
    # title block
    info = project["info"]
    tb_y = PH - 6 * MM - 92 * MM
    page.draw_line((x0, tb_y), (PW - 6 * MM, tb_y), color=INK, width=1)
    rows = [("", safe(company.get("name") or ""), 4.2), ("PROJECT", safe(info.get("name", "")), 3.4),
            ("CLIENT", safe(info.get("client", "")), 3.0), ("DRAWING", safe(f"ELV layout — {fl.name} — {title}"), 3.0),
            ("SCALE", scale_txt, 3.0), ("DRAWING NO.", safe(f"{info.get('ref', '')}-LAY-{fl.name}-{(sys_page or 'ALL').upper()}"), 2.8),
            ("REVISION / DATE", safe(f"{rev_label(project)} · {dstr(quote_date(project))}"), 3.0)]
    yy = tb_y + 9 * MM
    for label, val, fs in rows:
        if label:
            page.insert_text((x, yy - fs * MM - 0.8 * MM), label, fontsize=2.1 * MM, fontname="helv", color=GREY)
        page.insert_text((x, yy), val[:60], fontsize=fs * MM, fontname="hebo" if not label or label == "DRAWING" else "helv", color=INK)
        yy += 12 * MM
