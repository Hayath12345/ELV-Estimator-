"""Shared extraction helpers: units, label-to-boundary matching, result skeleton."""
from __future__ import annotations

import re
import statistics

from .. import geometry as G
from . import classify as C

UNITS_TO_M = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0, 10: 0.9144, 14: 0.1}
UNIT_NAMES = {0.001: "mm", 0.01: "cm", 1.0: "m", 0.0254: "in", 0.3048: "ft", 0.1: "dm", 0.9144: "yd"}
STD_SCALES = [20, 25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 750, 1000, 1250, 1500, 2000, 2500]
RE_AREA_TEXT = re.compile(r"\d+(?:[.,]\d+)?\s*(?:m2|m²|sqm|sq\.?\s?m|m\^2)\b|^AREA\s*[:=]", re.I)


def empty_result(kind: str) -> dict:
    return {
        "kind": kind, "extents": [0, 0, 1, 1], "unit_m": None, "scale_conf": "Not found", "scale_note": "",
        "plot_scale": None, "rooms": [], "doors": [], "furniture": [], "grids": [], "linework": [],
        "warnings": [], "counts": {}, "insunits": 0,
    }


def standard_scale(n: float | int | None) -> int | None:
    if not n:
        return None
    return min(STD_SCALES, key=lambda s: abs(s - n) / s)


def _plausible(unit_m: float, extent: tuple[float, float], areas: list[float]) -> float:
    """Score how plausible a unit is for a building floor plan (0..2)."""
    w = max(extent) * unit_m
    score = 0.0
    if 8 <= w <= 1500:
        score += 1
    if areas:
        med = statistics.median(areas) * unit_m * unit_m
        if 3 <= med <= 300:
            score += 1
    return score


def infer_units(insunits: int, extent: tuple[float, float], areas: list[float]) -> tuple[float | None, str, str]:
    cands = [0.001, 0.01, 1.0, 0.0254, 0.3048]
    declared = UNITS_TO_M.get(insunits)
    if declared:
        s = _plausible(declared, extent, areas)
        if s >= 1.5 or (s >= 1 and not areas):
            return declared, "High", f"Units {UNIT_NAMES.get(declared, declared)} (drawing header)"
        best = max(cands, key=lambda u: _plausible(u, extent, areas))
        if _plausible(best, extent, areas) > s:
            return best, "Medium", (f"Header says {UNIT_NAMES.get(declared)}, sizes suggest "
                                    f"{UNIT_NAMES.get(best)} — verify")
        return declared, "Medium", f"Units {UNIT_NAMES.get(declared)} (header; sizes unusual)"
    scored = sorted(cands, key=lambda u: -_plausible(u, extent, areas))
    best = scored[0]
    sb = _plausible(best, extent, areas)
    if sb >= 2 or (sb >= 1 and not areas):
        return best, "Medium", f"Units inferred from room sizes ({UNIT_NAMES.get(best)})"
    return None, "Not found", "Scale not found – calibrate manually"


def _is_name(text: str) -> bool:
    return C.looks_like_room_name(text) and not RE_AREA_TEXT.search(text)


def assign_labels(polys: list[dict], labels: list[dict], unit_m: float, poly_conf: str) -> list[dict]:
    """Match label texts to the smallest closed boundary that contains them."""
    labels = [l for l in labels if not RE_AREA_TEXT.search(l["text"])]
    areas = [G.area(p["pts"]) for p in polys]
    boxes = [G.bbox(p["pts"]) for p in polys]

    def owners(pt):
        out = []
        for i, p in enumerate(polys):
            x0, y0, x1, y1 = boxes[i]
            if x0 <= pt[0] <= x1 and y0 <= pt[1] <= y1 and G.contains(p["pts"], pt):
                out.append(i)
        return out

    owner_lists = [owners(tuple(l["pt"])) for l in labels]
    # boundaries that hold several room names are outlines (building, zone) — drop them
    name_counts: dict[int, int] = {}
    for l, own in zip(labels, owner_lists):
        if _is_name(l["text"]):
            for i in own:
                name_counts[i] = name_counts.get(i, 0) + 1
    outlines = {i for i, n in name_counts.items() if n > 3}

    groups: dict[int, list[dict]] = {}
    orphans: list[dict] = []
    for l, own in zip(labels, owner_lists):
        own = [i for i in own if i not in outlines]
        if not own:
            if _is_name(l["text"]):
                orphans.append(l)
            continue
        best = min(own, key=lambda i: areas[i])
        groups.setdefault(best, []).append(l)

    rooms = []
    for i, ls in groups.items():
        names = [l for l in ls if _is_name(l["text"])]
        nums = [l for l in ls if C.looks_like_room_number(l["text"]) and not _is_name(l["text"])]
        others = [l for l in ls if l not in names and l not in nums]
        if not names and not nums and not others:
            continue
        names.sort(key=lambda l: (-l["pt"][1], l["pt"][0]))
        name = " ".join(l["text"] for l in names) if names else ""
        if not name and others:
            name = others[0]["text"]
        number = nums[0]["text"] if nums else ""
        if not name:
            name = f"Room {number}" if number else "Room"
        label_pt = (names or nums or others)[0]["pt"]
        rooms.append({"name": name, "number": number, "poly": [list(p) for p in polys[i]["pts"]],
                      "label_pt": list(label_pt), "conf": poly_conf, "boundary": "drawn"})

    # names without a boundary: estimate a 4 m square so devices can still be placed
    side = 4.0 / unit_m if unit_m else 4.0
    seen_pts = []
    for l in orphans:
        x, y = l["pt"]
        if any(G.dist((x, y), q) < side * 0.6 for q in seen_pts):
            continue  # second line of the same multi-line label
        seen_pts.append((x, y))
        h = side / 2
        rooms.append({"name": l["text"], "number": "",
                      "poly": [[x - h, y - h], [x + h, y - h], [x + h, y + h], [x - h, y + h]],
                      "label_pt": [x, y], "conf": "Low", "boundary": "estimated"})
    return rooms


def finalise_rooms(rooms: list[dict], unit_m: float) -> list[dict]:
    out = []
    rooms = sorted(rooms, key=lambda r: (-G.centroid([tuple(p) for p in r["poly"]])[1],
                                         G.centroid([tuple(p) for p in r["poly"]])[0]))
    for i, r in enumerate(rooms, 1):
        poly = [tuple(p) for p in r["poly"]]
        cat = C.classify(r["name"])
        out.append({
            "id": f"R{i:03d}", "name": r["name"], "number": r.get("number", ""), "category": cat,
            "comms": C.comms_role(r["name"]) if cat in ("comms", "server") else None,
            "poly": [[round(x, 3), round(y, 3)] for x, y in poly],
            "label_pt": [round(v, 3) for v in r["label_pt"]],
            "area_m2": round(G.area(poly) * unit_m * unit_m, 2) if unit_m else None,
            "conf": r["conf"], "boundary": r["boundary"],
        })
    return out
