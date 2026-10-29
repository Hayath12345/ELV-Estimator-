"""Floor model built from extraction results plus the user's room overrides."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .. import geometry as G

PRIORITY = {
    "comms": 10, "server": 10, "electrical": 9, "plant": 8, "security": 8, "store": 7, "executive": 7,
    "office": 6, "meeting": 6, "boardroom": 6, "training": 6, "print": 5, "pantry": 5, "medical": 5,
    "open_office": 5, "toilet": 5, "prayer": 5, "reception": 4, "other": 4, "entrance": 3, "parking": 3,
    "loading": 3, "lift_lobby": 2, "lift": 2, "corridor": 1, "stair": 1,
}


@dataclass
class Door:
    id: str
    pt: tuple[float, float]
    leaves: int
    tag: str
    rooms: list[str] = field(default_factory=list)
    served: str | None = None
    inferred: bool = False


@dataclass
class Room:
    id: str  # unique across the project: "<drawing id>:<room id>"
    rid: str  # room id within its drawing (keys user overrides)
    name: str
    category: str
    poly: list[tuple[float, float]]
    area_m2: float
    centroid: tuple[float, float]
    bbox: tuple[float, float, float, float]
    comms: str | None
    label_pt: tuple[float, float]
    conf: str
    boundary: str
    doors: list[Door] = field(default_factory=list)
    wps: list[tuple[float, float]] = field(default_factory=list)
    wp_source: str = ""


@dataclass
class Floor:
    key: str  # drawing id
    name: str  # e.g. "2F"
    code: str  # e.g. "2"
    order: int
    unit_m: float
    extents: list[float]
    rooms: list[Room]
    doors: list[Door]
    calibrated: bool

    def m(self, units: float) -> float:
        return units * self.unit_m

    def u(self, metres: float) -> float:
        return metres / self.unit_m

    @property
    def comms_rooms(self) -> list[Room]:
        return [r for r in self.rooms if r.comms in ("MDF", "IDF")]

    def room_at(self, p) -> Room | None:
        best = None
        for r in self.rooms:
            x0, y0, x1, y1 = r.bbox
            if x0 <= p[0] <= x1 and y0 <= p[1] <= y1 and G.contains(r.poly, p):
                if best is None or r.area_m2 < best.area_m2:
                    best = r
        return best


def floor_code(name: str) -> str:
    n = (name or "").upper().strip()
    m = re.fullmatch(r"(\d{1,2})F", n)
    if m:
        return m.group(1)
    if n in ("GF", "G"):
        return "G"
    return re.sub(r"[^A-Z0-9]", "", n)[:3] or "X"


def build_floor(drawing: dict, order: int, overrides: dict | None) -> Floor | None:
    ex = drawing.get("extraction")
    if not ex:
        return None
    cal = drawing.get("calibration") or {}
    unit_m = cal.get("unit_m") or ex.get("unit_m")
    calibrated = bool(cal.get("unit_m")) or ex.get("scale_conf") in ("High", "Medium")
    if not unit_m:
        unit_m = 0.001 if ex.get("kind") != "pdf" else 0.0254 / 72 * 100
        calibrated = False
    overrides = overrides or {}
    rooms: list[Room] = []
    for r in ex.get("rooms", []):
        ov = overrides.get(r["id"], {})
        if ov.get("deleted"):
            continue
        poly = [tuple(p) for p in r["poly"]]
        cat = ov.get("category") or r["category"]
        comms = ov["comms"] if "comms" in ov else r.get("comms")
        if comms in ("", "none"):
            comms = None
        if cat in ("comms", "server") and comms is None and "comms" not in ov:
            comms = "IDF"
        rooms.append(Room(
            id=f"{drawing['id']}:{r['id']}", rid=r["id"], name=ov.get("name") or r["name"], category=cat, poly=poly,
            area_m2=G.area(poly) * unit_m * unit_m, centroid=G.centroid(poly), bbox=G.bbox(poly),
            comms=comms, label_pt=tuple(r.get("label_pt") or G.centroid(poly)), conf=r.get("conf", "Medium"),
            boundary=r.get("boundary", "drawn")))
    doors: list[Door] = []
    tol = 0.8 / unit_m
    for i, d in enumerate(ex.get("doors", []), 1):
        door = Door(id=f"{drawing['id']}-D{i:03d}", pt=tuple(d["pt"]), leaves=int(d.get("leaves", 1) or 1),
                    tag=d.get("tag", ""))
        near = []
        for r in rooms:
            x0, y0, x1, y1 = r.bbox
            if x0 - tol <= door.pt[0] <= x1 + tol and y0 - tol <= door.pt[1] <= y1 + tol:
                if G.contains(r.poly, door.pt) or G.poly_dist(r.poly, door.pt) <= tol:
                    near.append(r)
        door.rooms = [r.id for r in near]
        if near:
            served = max(near, key=lambda r: (PRIORITY.get(r.category, 4), -r.area_m2))
            door.served = served.id
            served.doors.append(door)
        doors.append(door)
    # work positions from furniture blocks
    desks = [tuple(f["pt"]) for f in ex.get("furniture", []) if f["kind"] == "desk"]
    chairs = [tuple(f["pt"]) for f in ex.get("furniture", []) if f["kind"] == "chair"]
    by_room_desk: dict[str, list] = {}
    by_room_chair: dict[str, list] = {}
    fl = Floor(drawing["id"], drawing.get("floor") or "1F", floor_code(drawing.get("floor") or "1F"), order,
               unit_m, ex.get("extents", [0, 0, 1, 1]), rooms, doors, calibrated)
    for p in desks:
        r = fl.room_at(p)
        if r:
            by_room_desk.setdefault(r.id, []).append(p)
    for p in chairs:
        r = fl.room_at(p)
        if r:
            by_room_chair.setdefault(r.id, []).append(p)
    for r in rooms:
        if by_room_desk.get(r.id):
            r.wps, r.wp_source = by_room_desk[r.id], "furniture"
        elif by_room_chair.get(r.id) and r.category in ("office", "open_office", "executive"):
            r.wps, r.wp_source = by_room_chair[r.id], "chairs"
    # rooms without any door get one inferred door toward the nearest corridor
    corridors = [r for r in rooms if r.category in ("corridor", "lift_lobby", "entrance")]
    for r in rooms:
        if r.doors or r.category in ("corridor", "lift", "stair", "plant"):
            continue
        target = None
        if corridors:
            target = min((c for c in corridors if c is not r), key=lambda c: G.dist(c.centroid, r.centroid),
                         default=None)
        tp = target.centroid if target else (r.centroid[0], r.bbox[1] - 1)
        pt = _boundary_toward(r, tp)
        d = Door(id=f"{drawing['id']}-{r.id}-DI", pt=pt, leaves=1, tag="", rooms=[r.id], served=r.id, inferred=True)
        r.doors.append(d)
        doors.append(d)
    return fl


def _boundary_toward(room: Room, target) -> tuple[float, float]:
    """Point on the room boundary closest to the target point."""
    best, bd = room.centroid, math.inf
    n = len(room.poly)
    for i in range(n):
        a, b = room.poly[i], room.poly[(i + 1) % n]
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy or 1e-12
        t = max(0.0, min(1.0, ((target[0] - ax) * dx + (target[1] - ay) * dy) / L2))
        p = (ax + t * dx, ay + t * dy)
        d = G.dist(p, target)
        if d < bd:
            best, bd = p, d
    return best


def build_floors(project: dict) -> list[Floor]:
    floors = []
    overrides = project.get("rooms_overrides", {})
    drawings = [d for d in project.get("drawings", []) if d.get("extraction") and d.get("role", "plan") == "plan"]
    drawings.sort(key=lambda d: d.get("order", 0))
    for i, d in enumerate(drawings):
        f = build_floor(d, i, overrides.get(d["id"]))
        if f:
            floors.append(f)
    return floors
