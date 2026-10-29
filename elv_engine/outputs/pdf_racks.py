"""Rack elevations (PyMuPDF): A3 landscape, up to five 42U racks per page."""
from __future__ import annotations

from .common import dstr, quote_date, rev_label, safe

MM = 72 / 25.4
A3 = (420 * MM, 297 * MM)
KIND = {"patch": "#C9D2E1", "mgr": "#E6EAF1", "fibre": "#9ED3D0", "switch": "#7EA6DA", "server": "#1F3B70", "storage": "#5A4E9C",
        "av": "#8A5CD6", "panel": "#D0457A", "mgmt": "#AEB7C6", "power": "#E0A526", "battery": "#C98A12"}
LIGHT = {"server", "storage", "av", "panel", "switch", "battery"}
NAMES = {"patch": "Patch panel", "mgr": "Cable manager", "fibre": "Fibre panel", "switch": "Switch", "server": "Server",
         "storage": "Recorder / storage", "av": "AV / headend", "panel": "Alarm panel", "power": "UPS / PDU", "battery": "Battery"}


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def build(path: str, project: dict, res, company: dict, reserved: dict | None = None) -> int:
    import pymupdf as fitz
    reserved = reserved or {}
    racks = [(rs, rk) for rs in res.sizing["rooms"] for rk in rs.racks]
    doc = fitz.open()
    PW, PH = A3
    per_page = 5
    pages = 0
    for start in range(0, max(1, len(racks)), per_page):
        chunk = racks[start:start + per_page]
        page = doc.new_page(width=PW, height=PH)
        pages += 1
        page.draw_rect(fitz.Rect(6 * MM, 6 * MM, PW - 6 * MM, PH - 6 * MM), color=_rgb("#14254A"), width=1)
        page.insert_text((14 * MM, 16 * MM), "RACK ELEVATIONS", fontsize=5 * MM, fontname="hebo", color=_rgb("#14254A"))
        info = project["info"]
        page.insert_text((14 * MM, 22 * MM), safe(f"{info.get('name', '')} · {info.get('ref', '')} {rev_label(project)} · {dstr(quote_date(project))}"),
                         fontsize=3 * MM, fontname="helv", color=_rgb("#5E6A7D"))
        page.insert_text((PW - 110 * MM, 16 * MM), safe(company.get("name") or ""), fontsize=3.6 * MM, fontname="hebo", color=_rgb("#14254A"))
        if not chunk:
            page.insert_text((14 * MM, 40 * MM), "No racks in the current design.", fontsize=4 * MM)
            break
        uh = 5.0 * MM
        top = 40 * MM
        col_w = (PW - 28 * MM) / per_page
        for i, (rs, rk) in enumerate(chunk):
            x = 14 * MM + i * col_w + 10 * MM
            w = col_w - 22 * MM
            page.insert_text((x, top - 10 * MM), safe(f"{rk.name}"), fontsize=3.4 * MM, fontname="hebo", color=_rgb("#14254A"))
            res_u = set(reserved.get(rk.name, []))
            used = rk.used + len(res_u)
            page.insert_text((x, top - 5.5 * MM), safe(f"{rs.floor_name} · {rs.role} · {used} U used / 42 U · {round(used / 42 * 100)}%"),
                             fontsize=2.4 * MM, fontname="helv", color=_rgb("#5E6A7D"))
            frame = fitz.Rect(x, top, x + w, top + 42 * uh)
            page.draw_rect(fitz.Rect(frame.x0 - 2 * MM, frame.y0 - 3 * MM, frame.x1 + 2 * MM, frame.y1 + 3 * MM), color=_rgb("#2B3345"),
                           fill=_rgb("#2B3345"), width=0)
            page.draw_rect(frame, color=_rgb("#E1E6EE"), fill=(1, 1, 1), width=0.3)
            for u in range(1, 43):
                y = top + (42 - u) * uh
                page.insert_text((x - 7 * MM, y + uh * 0.72), f"{u:>2}", fontsize=2.1 * MM, fontname="helv", color=_rgb("#6B7486"))
                page.draw_line((x, y + uh), (x + w, y + uh), color=_rgb("#EEF1F5"), width=0.2)
                if u in res_u:
                    page.draw_rect(fitz.Rect(x, y, x + w, y + uh), color=None, fill=_rgb("#FFE9C7"), width=0)
                    page.insert_text((x + 1.5 * MM, y + uh * 0.7), "Reserved", fontsize=2.1 * MM, fontname="helv", color=_rgb("#8A5A00"))
            for it in rk.items:
                y = top + (42 - (it.u + it.size - 1)) * uh
                r = fitz.Rect(x + 0.5, y + 0.6, x + w - 0.5, y + it.size * uh - 0.6)
                page.draw_rect(r, color=_rgb("#7A8396"), fill=_rgb(KIND.get(it.kind, "#AEB7C6")), width=0.3)
                fc = (1, 1, 1) if it.kind in LIGHT else _rgb("#1B2333")
                label = safe(it.label)
                fs = min(2.5 * MM, uh * 0.62)
                while fitz.get_text_length(label, fontname="helv", fontsize=fs) > w - 12 * MM and len(label) > 8:
                    label = label[:-2]
                page.insert_text((x + 1.5 * MM, y + it.size * uh / 2 + fs * 0.35), label, fontsize=fs, fontname="helv", color=fc)
                page.insert_text((x + w - 6 * MM, y + it.size * uh / 2 + fs * 0.35), f"{it.size}U", fontsize=fs * 0.9, fontname="helv", color=fc)
        # legend
        lx, ly = 14 * MM, PH - 14 * MM
        for k, name in NAMES.items():
            page.draw_rect(fitz.Rect(lx, ly - 3 * MM, lx + 5 * MM, ly), color=_rgb("#7A8396"), fill=_rgb(KIND[k]), width=0.3)
            page.insert_text((lx + 6.5 * MM, ly - 0.6 * MM), name, fontsize=2.5 * MM, fontname="helv", color=_rgb("#3D475A"))
            lx += 36 * MM
    doc.set_metadata({"title": safe(f"{project['info'].get('name', '')} — rack elevations {rev_label(project)}"), "creator": "ELV Estimator"})
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return pages
