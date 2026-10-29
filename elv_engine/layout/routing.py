"""Orthogonal cable routing to the nearest allowed MDF/IDF.

Cables leave the device vertically or horizontally to the nearest corridor spine (the
"core detour"), run along the corridor, then drop into the comms room. Floors without a
comms room are routed through the riser to the nearest floor that has one.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import geometry as G
from ..params import num
from .floor import Floor, Room

LIMITED = {"cctv", "access", "iptv", "cabling", "intercom"}  # copper Ethernet: 90 m permanent link


@dataclass
class Spine:
    axis: str  # 'h' (runs along x at y=c) | 'v' (runs along y at x=c)
    c: float
    lo: float
    hi: float


def spines(floor: Floor) -> list[Spine]:
    out = []
    for r in floor.rooms:
        if r.category != "corridor":
            continue
        x0, y0, x1, y1 = r.bbox
        if (x1 - x0) >= (y1 - y0):
            out.append(Spine("h", (y0 + y1) / 2, x0, x1))
        else:
            out.append(Spine("v", (x0 + x1) / 2, y0, y1))
    return out


def _len(pts) -> float:
    return sum(abs(pts[i][0] - pts[i - 1][0]) + abs(pts[i][1] - pts[i - 1][1]) for i in range(1, len(pts)))


def route_pts(pt, dest, sps: list[Spine]):
    """Shortest orthogonal path via one spine (or a plain L if the floor has no corridors)."""
    best = None
    for i, s in enumerate(sps):
        if s.axis == "h":
            pts = [pt, (pt[0], s.c), (dest[0], s.c), dest]
        else:
            pts = [pt, (s.c, pt[1]), (s.c, dest[1]), dest]
        L = _len(pts)
        if best is None or L < best[0]:
            best = (L, pts, i)
    if best is None:
        pts = [pt, (pt[0], dest[1]), dest]
        return _len(pts), pts, -1
    return best


def assign(floors: list[Floor], devices: list[dict], cab_params: dict) -> dict:
    """Route every device; returns per-device route info and the backbone links."""
    slack = 1 + num(cab_params, "slack_pct", 10) / 100
    drop = num(cab_params, "ceiling_drop_m", 3) + num(cab_params, "rack_drop_m", 4)
    fh = num(cab_params, "floor_height_m", 4.5)
    max_link = num(cab_params, "max_link_m", 90)
    by_key = {f.key: f for f in floors}
    sp = {f.key: spines(f) for f in floors}
    comms_floors = [f for f in floors if f.comms_rooms]
    routes: dict[str, dict] = {}
    for d in devices:
        fl = by_key.get(d["floor"])
        if not fl:
            continue
        pt = (d["x"], d["y"])
        best = None
        if fl.comms_rooms:
            for c in fl.comms_rooms:
                L, pts, si = route_pts(pt, c.centroid, sp[fl.key])
                m = fl.m(L) * slack + drop
                if best is None or m < best["len_m"]:
                    best = {"room": c.id, "room_floor": fl.key, "pts": pts, "len_m": m, "spine": si, "riser": False}
        elif comms_floors:
            other = min(comms_floors, key=lambda f: (abs(f.order - fl.order), f.order))
            for c in other.comms_rooms:
                L, pts, si = route_pts(pt, c.centroid, sp[fl.key])
                m = fl.m(L) * slack + drop + abs(other.order - fl.order) * fh
                if best is None or m < best["len_m"]:
                    best = {"room": c.id, "room_floor": other.key, "pts": pts, "len_m": m, "spine": si, "riser": True}
        if best is None:
            continue
        best["len_m"] = round(best["len_m"], 1)
        best["over"] = d["sys"] in LIMITED and best["len_m"] > max_link
        routes[d["id"]] = best
    return {"routes": routes, "backbone": backbone(floors, sp, slack, fh, num(cab_params, "rack_drop_m", 4))}


def mdf_of(floors: list[Floor]) -> tuple[Floor, Room] | None:
    allc = [(f, r) for f in floors for r in f.comms_rooms]
    if not allc:
        return None
    mdf = [x for x in allc if x[1].comms == "MDF"]
    if mdf:
        return mdf[0]
    return max(allc, key=lambda x: (x[1].category == "server", x[1].area_m2))


def backbone(floors, sp, slack, fh, rack_drop) -> list[dict]:
    m = mdf_of(floors)
    if not m:
        return []
    mf, mr = m
    links = []
    for f in floors:
        for r in f.comms_rooms:
            if r is mr:
                continue
            if f is mf:
                L, pts, _ = route_pts(r.centroid, mr.centroid, sp[f.key])
                length = f.m(L) * slack + 2 * rack_drop
            else:
                h = abs(r.centroid[0] - mr.centroid[0]) + abs(r.centroid[1] - mr.centroid[1])
                length = f.m(h) * slack + abs(f.order - mf.order) * fh + 2 * rack_drop + 10
            links.append({"from": r.id, "from_floor": f.key, "to": mr.id, "len_m": round(length, 1)})
    return links


def trunk_length_m(floors: list[Floor], devices: list[dict], routes: dict) -> float:
    """Cable tray length: union of corridor runs actually used by the given devices."""
    by_key = {f.key: f for f in floors}
    sp = {f.key: spines(f) for f in floors}
    ext: dict[tuple, list[float]] = {}
    for d in devices:
        r = routes.get(d["id"])
        if not r:
            continue
        fl = by_key[d["floor"]]
        pts = r["pts"]
        si = r["spine"]
        if si >= 0:
            s = sp[fl.key][si]
            a = pts[1][0] if s.axis == "h" else pts[1][1]
            b = pts[2][0] if s.axis == "h" else pts[2][1]
            key = (fl.key, "s", si)
        else:
            a, b = pts[0][0], pts[1][0]
            key = (fl.key, "L", r["room"], round(pts[1][1], 0))
        lo, hi = min(a, b), max(a, b)
        e = ext.setdefault(key, [lo, hi])
        e[0], e[1] = min(e[0], lo), max(e[1], hi)
    total = 0.0
    for key, (lo, hi) in ext.items():
        total += by_key[key[0]].m(hi - lo)
    return total
