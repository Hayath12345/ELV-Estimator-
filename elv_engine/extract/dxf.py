"""Extract rooms, door tags, work positions, grid lines and scale from a DXF file.

DWG files are first converted to DXF with LibreDWG (see ``dwg.py``). All coordinates
returned are in drawing units, model space, y up. ``unit_m`` converts units to metres.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Callable, Iterator

from .. import geometry as G
from . import classify as C
from .common import (UNITS_TO_M, assign_labels, empty_result, finalise_rooms, infer_units,
                     standard_scale)

Progress = Callable[[float, str], None]

RE_ROOM_LAYER = re.compile(r"ROOM|\bRM\b|RM[-_]|SPACE|AREA|ZONE|A-AREA|NAME", re.I)
RE_LABEL_LAYER = re.compile(r"ROOM|\bRM\b|RM[-_]|SPACE|AREA|NAME|TAG|IDEN|TEXT|ANNO", re.I)
RE_DOOR = re.compile(r"DOOR|^DR\d|^DR[-_ ]|[-_]DR[-_]|^D\d+[A-Z]?$|DOOR|PORTE", re.I)
RE_DOOR_TAG_LAYER = re.compile(r"DOOR.*(TAG|IDEN|NUM|NO)|(TAG|IDEN).*DOOR", re.I)
RE_DOOR_TAG = re.compile(r"^D[-\s]?\d{1,4}[A-Z]?$|^\d{1,2}[.\-]?D\d{1,3}[A-Z]?$", re.I)
RE_DOUBLE = re.compile(r"DOUBLE|DBL|\bDD\b|[-_]DD|2L|PAIR|D2\b|TWIN", re.I)
RE_DESK = re.compile(r"DESK|WORK ?STATION|WKSTN|WKST|\bWS\b|^WS[-_\d]|[-_]WS[-_\d]|CUBICLE|POD", re.I)
RE_CHAIR = re.compile(r"CHAIR|SEAT|STOOL", re.I)
RE_TABLE = re.compile(r"TABLE|CONF", re.I)
RE_FURN_LAYER = re.compile(r"FURN|FF&?E|A-EQPM|I-FURN|FURNITURE|MOBILIER", re.I)
RE_GRID_LAYER = re.compile(r"GRID|AXIS|AXES|S-GRID|A-GRID|C-GRID", re.I)
RE_SCALE_TEXT = re.compile(r"\b1\s*:\s*(\d{2,4})\b")

MAX_DEPTH = 4
MAX_LINEWORK = 400_000  # segments kept for background rendering


def _vec(p) -> tuple[float, float]:
    return (float(p[0]), float(p[1]))


def _walk(entities, depth: int, skip_block: Callable[[object], bool]) -> Iterator[tuple[object, int]]:
    for e in entities:
        t = e.dxftype()
        if t == "INSERT":
            yield e, depth
            if depth >= MAX_DEPTH or skip_block(e):
                continue
            try:
                inserts = e.multi_insert() if getattr(e, "mcount", 1) > 1 else [e]
                for ins in inserts:
                    yield from _walk(ins.virtual_entities(), depth + 1, skip_block)
            except Exception:  # broken block definitions are skipped
                continue
        else:
            yield e, depth


def _closed_points(e, flat: float) -> list[tuple[float, float]] | None:
    from ezdxf import path as ezpath
    t = e.dxftype()
    try:
        if t == "LWPOLYLINE":
            if not (e.closed or (len(e) > 2 and _same(e[0], e[-1]))):
                return None
            pts = [_vec(v) for v in ezpath.make_path(e).flattening(flat)]
        elif t == "POLYLINE":
            if not e.is_2d_polyline:
                return None
            vs = list(e.points())
            if not (e.is_closed or (len(vs) > 2 and _same(vs[0], vs[-1]))):
                return None
            pts = [_vec(v) for v in ezpath.make_path(e).flattening(flat)]
        else:
            return None
    except Exception:
        return None
    if len(pts) > 3 and _same(pts[0], pts[-1]):
        pts = pts[:-1]
    return pts if len(pts) >= 3 else None


def _same(a, b, tol=1e-6) -> bool:
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def _hatch_polys(e, flat: float) -> list[list[tuple[float, float]]]:
    from ezdxf import path as ezpath
    out = []
    try:
        for p in ezpath.from_hatch(e):
            pts = [_vec(v) for v in p.flattening(flat)]
            if len(pts) > 3 and _same(pts[0], pts[-1]):
                pts = pts[:-1]
            if len(pts) >= 3:
                out.append(pts)
    except Exception:
        pass
    return out


def _text_of(e) -> tuple[str, tuple[float, float], float] | None:
    t = e.dxftype()
    try:
        if t == "TEXT" or t == "ATTRIB":
            txt = e.dxf.text
            ha = e.dxf.get("halign", 0)
            va = e.dxf.get("valign", 0)
            p = e.dxf.align_point if (ha or va) and e.dxf.hasattr("align_point") else e.dxf.insert
            h = float(e.dxf.get("height", 0) or 0)
            x, y = _vec(p)
            if not (ha or va):  # left-aligned: approximate the visual centre
                x += 0.3 * h * len(txt)
                y += 0.5 * h
            return txt, (x, y), h
        if t == "MTEXT":
            txt = e.plain_text().replace("\n", " ")
            h = float(e.dxf.get("char_height", 0) or 0)
            x, y = _vec(e.dxf.insert)
            ap = int(e.dxf.get("attachment_point", 1) or 1)
            width = float(e.dxf.get("width", 0) or 0) or 0.6 * h * len(txt)
            # shift to the visual centre based on attachment point (1=TL ... 9=BR)
            col, row = (ap - 1) % 3, (ap - 1) // 3
            x += (1 - col) * width / 2
            y += (row - 1) * h / 2 * -1 if row != 1 else 0
            return txt, (x, y), h
    except Exception:
        return None
    return None


def _clean(txt: str) -> str:
    txt = re.sub(r"\\[A-Za-z][^;]*;", "", txt or "")  # residual MTEXT codes
    txt = re.sub(r"%%[cdpu]", "", txt, flags=re.I)
    return " ".join(txt.replace("{", "").replace("}", "").split())


def extract_dxf(path: str, progress: Progress | None = None) -> dict:
    import ezdxf
    from ezdxf import bbox as ezbbox
    from ezdxf import recover

    progress = progress or (lambda f, m: None)
    res = empty_result("dxf")
    progress(0.05, "Reading DXF")
    try:
        doc = ezdxf.readfile(path)
    except ezdxf.DXFStructureError:
        doc, auditor = recover.readfile(path)
        res["warnings"].append("Drawing had structural errors and was recovered.")
    msp = doc.modelspace()

    insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    res["insunits"] = insunits

    door_blocks: set[str] = set()
    furn_blocks: dict[str, str] = {}

    def block_kind(ins) -> str | None:
        name = ins.dxf.name or ""
        layer = ins.dxf.layer or ""
        if name.startswith("*"):  # anonymous (dimensions, hatches, dynamic blocks)
            name_eff = getattr(ins, "block", lambda: None)()
            name = getattr(name_eff, "name", name) if name_eff is not None else name
        if RE_DOOR.search(name) or (re.search(r"DOOR", layer, re.I) and not RE_DOOR_TAG_LAYER.search(layer)):
            if not re.search(r"TAG|IDEN|SCHED|SYMB", name, re.I):
                return "door"
        if RE_DESK.search(name):
            return "desk"
        if RE_CHAIR.search(name):
            return "chair"
        if RE_TABLE.search(name) and (RE_FURN_LAYER.search(layer) or True):
            return "table"
        if RE_FURN_LAYER.search(layer):
            return "furniture"
        return None

    def skip_block(ins) -> bool:
        k = block_kind(ins)
        return k in ("door", "desk", "chair", "table", "furniture")

    texts: list[dict] = []
    polys: list[dict] = []
    doors: list[dict] = []
    furniture: list[dict] = []
    grid_lines: list[dict] = []
    grid_circles: list[tuple[tuple[float, float], float]] = []
    dims: list[dict] = []
    linework: list[list[float]] = []
    all_pts: list[tuple[float, float]] = []

    # First pass: rough extents to choose a flattening tolerance.
    try:
        ext = ezbbox.extents(msp, fast=True)
        span = max(ext.size.x, ext.size.y) if ext.has_data else 1000.0
    except Exception:
        span = 1000.0
    flat = max(span / 4000.0, 1e-6)

    from ezdxf import path as ezpath

    n_seen = 0
    progress(0.15, "Scanning entities")
    for e, depth in _walk(msp, 0, skip_block):
        n_seen += 1
        if n_seen % 20000 == 0:
            progress(min(0.6, 0.15 + n_seen / 400000), f"Scanning entities ({n_seen:,})")
        t = e.dxftype()
        layer = e.dxf.get("layer", "") or ""
        if t == "INSERT":
            kind = block_kind(e)
            name = e.dxf.name or ""
            try:
                bb = ezbbox.extents([e], fast=True)
                if bb.has_data:
                    cx, cy = bb.center.x, bb.center.y
                    w = max(bb.size.x, bb.size.y)
                else:
                    cx, cy = _vec(e.dxf.insert)
                    w = 0.0
            except Exception:
                cx, cy = _vec(e.dxf.insert)
                w = 0.0
            if kind == "door":
                doors.append({"pt": [cx, cy], "block": name, "layer": layer, "width_u": w,
                              "double": bool(RE_DOUBLE.search(name))})
            elif kind in ("desk", "chair", "table", "furniture"):
                furniture.append({"pt": [cx, cy], "kind": kind, "block": name, "layer": layer})
            # attributes (room tags, door tags)
            try:
                attribs = list(e.attribs)
            except Exception:
                attribs = []
            if attribs:
                parts = []
                for a in attribs:
                    tt = _text_of(a)
                    if tt and _clean(tt[0]):
                        parts.append((a.dxf.tag or "", _clean(tt[0]), tt[1], tt[2]))
                if parts:
                    ip = _vec(e.dxf.insert)
                    texts.append({"text": " ".join(p[1] for p in parts), "pt": [ip[0], ip[1]],
                                  "h": max(p[3] for p in parts), "layer": layer, "block": name,
                                  "tags": {p[0].upper(): p[1] for p in parts}})
            continue
        if t in ("TEXT", "MTEXT"):
            tt = _text_of(e)
            if tt:
                txt = _clean(tt[0])
                if txt:
                    texts.append({"text": txt, "pt": [tt[1][0], tt[1][1]], "h": tt[2], "layer": layer})
            continue
        if t == "DIMENSION":
            try:
                meas = float(e.get_measurement() or 0)
            except Exception:
                meas = 0.0
            dims.append({"measure": meas, "text": e.dxf.get("text", "") or "", "layer": layer})
            continue
        if t == "HATCH":
            if RE_ROOM_LAYER.search(layer):
                for pts in _hatch_polys(e, flat):
                    polys.append({"pts": pts, "layer": layer, "src": "hatch"})
            continue
        if t in ("LWPOLYLINE", "POLYLINE"):
            pts = _closed_points(e, flat)
            if pts:
                polys.append({"pts": pts, "layer": layer, "src": t})
        if t == "CIRCLE" and RE_GRID_LAYER.search(layer):
            grid_circles.append((_vec(e.dxf.center), float(e.dxf.radius)))
        if t in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"):
            if t == "LINE" and RE_GRID_LAYER.search(layer):
                a, b = _vec(e.dxf.start), _vec(e.dxf.end)
                grid_lines.append({"a": list(a), "b": list(b), "layer": layer})
                continue
            if RE_GRID_LAYER.search(layer):
                continue
            if len(linework) < MAX_LINEWORK:
                try:
                    vs = [_vec(v) for v in ezpath.make_path(e).flattening(flat)]
                except Exception:
                    vs = []
                if len(vs) >= 2:
                    flat_list = [round(c, 3) for v in vs for c in v]
                    linework.append(flat_list)
                    if len(all_pts) < 200000:
                        all_pts.append(vs[0])
                        all_pts.append(vs[-1])

    progress(0.62, "Resolving units and scale")
    # ---- units -------------------------------------------------------------
    pts_for_extent = all_pts or [tuple(p["pts"][0]) for p in polys] or [tuple(t["pt"]) for t in texts]
    if pts_for_extent:
        x0, y0, x1, y1 = _robust_extents(pts_for_extent)
    else:
        x0, y0, x1, y1 = 0.0, 0.0, 1.0, 1.0
    res["extents"] = [x0, y0, x1, y1]
    poly_areas = [G.area(p["pts"]) for p in polys if RE_ROOM_LAYER.search(p["layer"])] or \
                 [G.area(p["pts"]) for p in polys]
    unit_m, conf, note = infer_units(insunits, (x1 - x0, y1 - y0), poly_areas)

    # grid lines: keep long ones, label them from bubbles/texts
    grids = _grids(grid_lines, grid_circles, texts, max(x1 - x0, y1 - y0))
    grid_note = _grid_note(grids, unit_m)

    # dimension cross-check: text overrides tell us real distance vs measured units
    dim_ratio = _dim_ratio(dims)
    if dim_ratio and unit_m:
        implied = unit_m * dim_ratio
        if abs(dim_ratio - 1) > 0.02:
            note += f" · dimension overrides imply ×{dim_ratio:.3f}"
            conf = "Medium" if conf == "High" else conf

    # plot scale from paper-space viewports (for information)
    plot_scale = _viewport_scale(doc, insunits)
    if not plot_scale:
        found = [int(m.group(1)) for t in texts for m in [RE_SCALE_TEXT.search(t["text"])] if m]
        if found:
            plot_scale = Counter(found).most_common(1)[0][0]
    res["plot_scale"] = standard_scale(plot_scale) if plot_scale else None
    res["unit_m"] = unit_m
    res["scale_conf"] = conf
    res["scale_note"] = (note + (" · " + grid_note if grid_note else "")).strip(" ·")
    res["grids"] = grids

    progress(0.7, "Matching room names to boundaries")
    # ---- rooms -------------------------------------------------------------
    um = unit_m or 0.001
    min_a, max_a = 1.0 / (um * um), 6000.0 / (um * um)
    cand = [p for p in polys if min_a <= G.area(p["pts"]) <= max_a]
    room_layer_cand = [p for p in cand if RE_ROOM_LAYER.search(p["layer"])]
    use = room_layer_cand if len(room_layer_cand) >= 3 else cand
    poly_conf = "High" if use is room_layer_cand and room_layer_cand else "Medium"

    labels = [t for t in texts if not RE_DOOR_TAG.match(t["text"]) and not _is_grid_label(t, grids)
              and (C.looks_like_room_name(t["text"]) or C.looks_like_room_number(t["text"])
                   or RE_LABEL_LAYER.search(t["layer"]) and len(t["text"]) <= 40)]
    rooms = assign_labels(use, labels, um, poly_conf)
    res["rooms"] = finalise_rooms(rooms, um)

    progress(0.82, "Doors, tags and work positions")
    # ---- doors -------------------------------------------------------------
    tags = [t for t in texts if RE_DOOR_TAG.match(t["text"]) or RE_DOOR_TAG_LAYER.search(t["layer"])]
    res["doors"] = _doors(doors, tags, um)
    res["furniture"] = [{"pt": f["pt"], "kind": f["kind"], "block": f["block"]} for f in furniture]
    res["linework"] = linework
    res["counts"] = {
        "entities": n_seen, "texts": len(texts), "closed_polylines": len(polys),
        "door_blocks": len(doors), "door_tags": len(tags), "furniture": len(furniture),
        "grid_lines": len(grids), "dimensions": len(dims),
    }
    if not doors and not tags:
        res["warnings"].append("No door blocks or door tags found — door positions will be inferred from room boundaries.")
    if not res["rooms"]:
        res["warnings"].append("No room names found. Check that room tags are TEXT/MTEXT or block attributes in model space.")
    progress(0.95, "Extraction complete")
    return res


def _robust_extents(pts):
    xs = sorted(p[0] for p in pts)
    ys = sorted(p[1] for p in pts)
    n = len(xs)
    if n < 20:
        return xs[0], ys[0], xs[-1], ys[-1]
    k = max(1, n // 500)  # drop 0.2% outliers (stray title blocks far away)
    lo, hi = k, n - 1 - k
    x0, x1, y0, y1 = xs[lo], xs[hi], ys[lo], ys[hi]
    pad_x, pad_y = (x1 - x0) * 0.02, (y1 - y0) * 0.02
    return x0 - pad_x, y0 - pad_y, x1 + pad_x, y1 + pad_y


def _grids(lines, circles, texts, span):
    out = []
    long_lines = [l for l in lines if G.dist(tuple(l["a"]), tuple(l["b"])) >= 0.15 * span]
    for l in long_lines:
        a, b = tuple(l["a"]), tuple(l["b"])
        vertical = abs(a[0] - b[0]) < abs(a[1] - b[1])
        label = ""
        best = None
        for (c, r) in circles:
            d = min(G.dist(c, a), G.dist(c, b))
            if d <= r * 3 and (best is None or d < best[0]):
                best = (d, c, r)
        if best:
            _, c, r = best
            near = [t for t in texts if G.dist(tuple(t["pt"]), c) <= r * 1.5 and len(t["text"]) <= 4]
            if near:
                label = min(near, key=lambda t: G.dist(tuple(t["pt"]), c))["text"]
        out.append({"a": list(a), "b": list(b), "axis": "x" if vertical else "y", "label": label})
    # de-duplicate collinear segments
    uniq = {}
    for g in out:
        key = (g["axis"], round(g["a"][0] if g["axis"] == "x" else g["a"][1], 1))
        if key not in uniq or (g["label"] and not uniq[key]["label"]):
            uniq[key] = g
    return sorted(uniq.values(), key=lambda g: (g["axis"], g["a"][0] if g["axis"] == "x" else -g["a"][1]))


def _is_grid_label(t, grids) -> bool:
    return any(g["label"] and g["label"] == t["text"] for g in grids) and len(t["text"]) <= 3


def _grid_note(grids, unit_m):
    if not unit_m:
        return ""
    xs = [g for g in grids if g["axis"] == "x" and g["label"]]
    if len(xs) >= 2:
        a, b = xs[0], xs[1]
        d = abs(a["a"][0] - b["a"][0]) * unit_m
        return f"grid {a['label']}–{b['label']} = {d:.2f} m"
    ys = [g for g in grids if g["axis"] == "y" and g["label"]]
    if len(ys) >= 2:
        a, b = ys[0], ys[1]
        d = abs(a["a"][1] - b["a"][1]) * unit_m
        return f"grid {a['label']}–{b['label']} = {d:.2f} m"
    return ""


def _dim_ratio(dims):
    ratios = []
    for d in dims:
        txt = (d["text"] or "").strip()
        if not txt or txt == "<>" or d["measure"] <= 0:
            continue
        m = re.search(r"(\d+(?:\.\d+)?)", txt.replace(",", ""))
        if not m:
            continue
        val = float(m.group(1))
        ratios.append(round(val / d["measure"], 3))
    if not ratios:
        return None
    r, n = Counter(ratios).most_common(1)[0]
    return r if n >= 2 else None


def _viewport_scale(doc, insunits):
    try:
        model_u = UNITS_TO_M.get(insunits) or 0.001
        best = []
        for layout in doc.layouts:
            if layout.name == "Model":
                continue
            paper_u = 0.001 if int(layout.dxf_layout.dxf.get("plot_paper_units", 1) or 1) == 1 else 0.0254
            for vp in layout.query("VIEWPORT"):
                if vp.dxf.get("id", 0) == 1:
                    continue
                h = float(vp.dxf.get("height", 0) or 0)
                vh = float(vp.dxf.get("view_height", 0) or 0)
                if h > 0 and vh > 0:
                    best.append(round(vh * model_u / (h * paper_u)))
        if best:
            return Counter(best).most_common(1)[0][0]
    except Exception:
        return None
    return None


def _doors(doors, tags, um):
    out = []
    used_tags = set()
    for i, d in enumerate(doors):
        width_m = d["width_u"] * um
        leaves = 2 if d["double"] or width_m >= 1.3 else 1
        tag = ""
        best = None
        for j, t in enumerate(tags):
            if j in used_tags:
                continue
            dd = G.dist(tuple(d["pt"]), tuple(t["pt"])) * um
            if dd <= 2.5 and (best is None or dd < best[0]):
                best = (dd, j)
        if best:
            used_tags.add(best[1])
            tag = tags[best[1]]["text"]
        out.append({"pt": d["pt"], "leaves": leaves, "width_m": round(width_m, 2), "tag": tag,
                    "block": d["block"], "src": "block"})
    # tags without a door block become doors (position of the tag)
    for j, t in enumerate(tags):
        if j not in used_tags and RE_DOOR_TAG.match(t["text"]):
            out.append({"pt": t["pt"], "leaves": 1, "width_m": 0.0, "tag": t["text"], "block": "", "src": "tag"})
    return out
