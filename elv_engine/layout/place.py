"""Rule-based device placement for the six systems.

Every rule reads its constants from the per-project system parameters (params.py), so
the estimator can see and change why a device was (or was not) placed. Devices are
returned in drawing units with a stable id per floor and system.
"""
from __future__ import annotations

import math

from .. import catalog
from .. import geometry as G
from ..extract.classify import OCCUPIED, PRIVATE
from ..params import merged, num
from .floor import Floor, Room

PREFIX = {"cctv": "C", "access": "A", "iptv": "TV", "intercom": "IC", "intrusion": "I"}


def _dev(sys, item, floor: Floor, pt, room: Room | None, **kw) -> dict:
    d = {"sys": sys, "item": item, "floor": floor.key, "x": round(pt[0], 3), "y": round(pt[1], 3),
         "room": room.id if room else None, "auto": True}
    d.update(kw)
    return d


def _main_door(room: Room):
    return room.doors[0] if room.doors else None


def _door_pt(room: Room):
    d = _main_door(room)
    return d.pt if d else (room.centroid[0], room.bbox[1])


def _offset(p, toward, d_units):
    """Move p toward (positive) or away from (negative) a point."""
    L = G.dist(p, toward)
    if L < 1e-9:
        return p
    return (p[0] + (toward[0] - p[0]) / L * d_units, p[1] + (toward[1] - p[1]) / L * d_units)


def _corner(room: Room, near, inset_u, farthest=False):
    pick = max if farthest else min
    v = pick(room.poly, key=lambda q: G.dist(q, near))
    p = G.inset_toward(v, room.centroid, inset_u)
    if not G.contains(room.poly, p):
        p = G.inset_toward(v, room.centroid, inset_u * 2)
    return p


def _wall_opposite(room: Room, door_pt, inset_u):
    x0, y0, x1, y1 = room.bbox
    cx, cy = room.centroid
    sides = [((x0 + inset_u, cy), 0), ((x1 - inset_u, cy), 180), ((cx, y0 + inset_u), 90), ((cx, y1 - inset_u), -90)]
    p, ang = max(sides, key=lambda s: G.dist(s[0], door_pt))
    if not G.contains(room.poly, p):
        p = room.centroid
    return p, ang


def _sorted_rooms(floor: Floor) -> list[Room]:
    return sorted(floor.rooms, key=lambda r: (-round(r.centroid[1], 0), round(r.centroid[0], 0)))


def _number(devs: list[dict], floor: Floor) -> None:
    by_prefix: dict[str, list[dict]] = {}
    for d in devs:
        if d["sys"] == "cabling":
            pre = "W" if d.get("sub") == "ap" else "D"
        else:
            pre = PREFIX[d["sys"]]
        by_prefix.setdefault(pre, []).append(d)
    for pre, lst in by_prefix.items():
        lst.sort(key=lambda d: (-round(d["y"] * floor.unit_m, 0), round(d["x"] * floor.unit_m, 1)))
        width = 3 if pre == "D" else 2
        for i, d in enumerate(lst, 1):
            d["id"] = f"{pre}{floor.code}-{i:0{width}d}"


# ---------------------------------------------------------------- CCTV
def place_cctv(floor: Floor, p: dict) -> list[dict]:
    out = []
    cats = set(p.get("categories") or [])
    spacing = num(p, "corridor_spacing_m", 15)
    open_m2 = num(p, "open_area_m2", 80)
    default = p.get("default_camera") or "cctv_dome_4mp"
    ppm = {"Identify": num(p, "ppm_identify", 250), "Recognise": num(p, "ppm_recognise", 125),
           "Observe": num(p, "ppm_observe", 62)}
    inset = floor.u(0.5)
    for r in _sorted_rooms(floor):
        if r.category in PRIVATE or r.category not in cats:
            continue
        cam = default
        if r.category in ("parking", "loading"):
            cam = "cctv_bullet_8mp"
        target = ("Identify" if r.category in ("entrance", "reception")
                  else "Observe" if r.category in ("open_office", "parking", "loading") else "Recognise")
        if r.category == "corridor":
            a, b, length_u, _ = G.principal_axis(r.poly)
            n = max(1, math.ceil(floor.m(length_u) / spacing))
            pts = G.along(a, b, n)
            ang = G.angle_deg(a, b)
            for i, pt in enumerate(pts):
                out.append(_dev("cctv", cam, floor, pt, r, a=round(ang + (180 if i % 2 else 0), 1), target=target))
            continue
        if r.category in ("parking", "loading"):
            n = max(2 if r.category == "loading" else 1, math.ceil(r.area_m2 / (150 if r.category == "parking" else 100)))
        elif r.category in ("open_office", "training"):
            n = max(1, math.ceil(r.area_m2 / open_m2))
        elif r.category in ("entrance", "reception", "lift_lobby"):
            n = max(1, math.ceil(r.area_m2 / 60))
        else:
            n = 1 if r.area_m2 <= open_m2 * 1.5 else math.ceil(r.area_m2 / open_m2)
        if n == 1:
            pt = _corner(r, _door_pt(r), inset)
            pts = [pt]
        else:
            pts = G.grid_points(r.poly, n, margin=floor.u(1.0))
        for pt in pts:
            ang = G.angle_deg(pt, r.centroid) if G.dist(pt, r.centroid) > floor.u(0.5) else 0.0
            out.append(_dev("cctv", cam, floor, pt, r, a=round(ang, 1), target=target))
    for d in out:
        d["range_m"] = {k: round(camera_range(d["item"], v), 1) for k, v in ppm.items()}
    return out


def camera_range(item: str, ppm: float) -> float:
    o = catalog.CAMERA_OPTICS.get(item, {"hres": 2560, "hfov": 90})
    hfov = min(o["hfov"], 120)
    return o["hres"] / (max(ppm, 1) * 2 * math.tan(math.radians(hfov / 2)))


# ---------------------------------------------------------------- Access control
def lock_for(leaves: int, lock_type: str) -> str:
    if lock_type == "maglock":
        return "maglock"
    if lock_type == "strike":
        return "strike"
    return "maglock" if leaves >= 2 else "strike"


def place_access(floor: Floor, p: dict) -> list[dict]:
    out = []
    cats = set(p.get("categories") or [])
    in_out = set(p.get("in_out") or [])
    lock_type = p.get("lock_type") or "auto"
    rooms = {r.id: r for r in floor.rooms}
    for door in floor.doors:
        r = rooms.get(door.served or "")
        if not r or r.category not in cats:
            continue
        pt = _offset(door.pt, r.centroid, -floor.u(0.45))
        out.append(_dev("access", "acs_reader", floor, pt, r, sub="door", door=door.id, tag=door.tag,
                        leaves=door.leaves, readers=2 if r.category in in_out else 1,
                        lock=lock_for(door.leaves, lock_type), inferred=door.inferred))
    return out


# ---------------------------------------------------------------- IPTV
def tv_size(r: Room, p: dict) -> int:
    def sz(key, default):
        try:
            return int(p.get(key, default))
        except (TypeError, ValueError):
            return default
    a = r.area_m2
    if r.category == "meeting":
        if a <= num(p, "meeting_small_m2", 15):
            return 55
        if a <= num(p, "meeting_medium_m2", 30):
            return 65
        if a <= num(p, "meeting_large_m2", 50):
            return 75
        return 85
    if r.category == "boardroom":
        return sz("boardroom_size", 85)
    if r.category == "training":
        return 85
    if r.category == "reception" or (r.category == "entrance" and a >= 20):
        return sz("reception_size", 55)
    if r.category == "pantry":
        return sz("pantry_size", 43)
    if r.category == "executive":
        return sz("executive_size", 43)
    return 0


def place_iptv(floor: Floor, p: dict) -> list[dict]:
    out = []
    for r in _sorted_rooms(floor):
        s = tv_size(r, p)
        if not s:
            continue
        pt, ang = _wall_opposite(r, _door_pt(r), floor.u(0.35))
        out.append(_dev("iptv", f"tv_{s}", floor, pt, r, size=s, a=ang))
    return out


# ---------------------------------------------------------------- Structured cabling
def place_cabling(floor: Floor, p: dict) -> list[dict]:
    out = []
    per_wp = int(num(p, "outlets_per_wp", 2))
    total_wp = 0
    margin = floor.u(0.8)
    for r in _sorted_rooms(floor):
        cat = r.category
        if cat in ("office", "executive", "open_office"):
            if r.wps:
                pts = r.wps
                src = r.wp_source
            else:
                m2 = num(p, "open_m2_per_wp" if cat == "open_office" else "office_m2_per_wp", 10)
                n = max(1, round(r.area_m2 / max(m2, 1)))
                pts = G.grid_points(r.poly, n, margin=margin)
                src = "area"
            total_wp += len(pts)
            for pt in pts:
                out.append(_dev("cabling", "sc_outlet", floor, pt, r, sub="data", kind="wp", ports=per_wp, src=src))
        elif cat in ("meeting", "boardroom", "training"):
            ports = int(num(p, "meeting_outlets", 4))
            if cat in ("boardroom", "training") and r.area_m2 > 20:
                ports += 2 * int((r.area_m2 - 20) // 20)
            for pt in G.grid_points(r.poly, max(1, math.ceil(ports / 2)), margin=margin):
                out.append(_dev("cabling", "sc_outlet", floor, pt, r, sub="data", kind="meeting", ports=2))
        elif cat in ("reception", "security"):
            for pt in G.grid_points(r.poly, 2, margin=margin):
                out.append(_dev("cabling", "sc_outlet", floor, pt, r, sub="data", kind="desk", ports=2))
        elif cat in ("pantry", "medical"):
            pt, _ = _wall_opposite(r, _door_pt(r), floor.u(0.3))
            out.append(_dev("cabling", "sc_outlet", floor, pt, r, sub="data", kind="services", ports=2))
    # printer points
    n_print = int(total_wp // max(num(p, "wp_per_printer", 20), 1))
    hosts = [r for r in floor.rooms if r.category == "print"] or \
            sorted([r for r in floor.rooms if r.category == "open_office"], key=lambda r: -r.area_m2)
    for i in range(n_print if hosts else 0):
        r = hosts[i % len(hosts)]
        k = i // len(hosts)
        pts = G.grid_points(r.poly, k + 2, margin=margin)
        out.append(_dev("cabling", "sc_outlet", floor, pts[-1], r, sub="data", kind="printer", ports=2))
    # Wi-Fi access points on a grid over occupied rooms
    cov = num(p, "ap_coverage_m2", 120)
    ap_ports = int(num(p, "ap_ports", 2))
    s = floor.u(math.sqrt(max(cov, 10)))
    occ = [r for r in floor.rooms if r.category in OCCUPIED]
    if occ:
        x0 = min(r.bbox[0] for r in occ)
        y0 = min(r.bbox[1] for r in occ)
        x1 = max(r.bbox[2] for r in occ)
        y1 = max(r.bbox[3] for r in occ)
        aps = []
        y = y1 - s / 2
        while y > y0:
            x = x0 + s / 2
            while x < x1:
                r = floor.room_at((x, y))
                if r and r.category in OCCUPIED:
                    aps.append(((x, y), r))
                x += s
            y -= s
        have = {r.id for _, r in aps}
        for r in occ:
            if r.id not in have and (r.area_m2 >= 0.6 * cov or (r.category in ("meeting", "boardroom", "training")
                                                                  and r.area_m2 >= 25)):
                aps.append((r.centroid if G.contains(r.poly, r.centroid) else G.grid_points(r.poly, 1)[0], r))
        for pt, r in aps:
            out.append(_dev("cabling", "sc_ap", floor, pt, r, sub="ap", kind="ap", ports=ap_ports))
    return out


# ---------------------------------------------------------------- Intercom
def place_intercom(floor: Floor, p: dict) -> list[dict]:
    out = []
    video = set(p.get("video_at") or [])
    audio = set(p.get("audio_at") or [])
    answer = set(p.get("answer_at") or [])
    for r in _sorted_rooms(floor):
        d = _main_door(r)
        if r.category in video and d:
            out.append(_dev("intercom", "ic_video", floor, _offset(d.pt, r.centroid, -floor.u(0.9)), r, door=d.id))
        elif r.category in audio and d:
            out.append(_dev("intercom", "ic_audio", floor, _offset(d.pt, r.centroid, -floor.u(0.9)), r, door=d.id))
        if r.category in answer:
            pt = _offset(_door_pt(r), r.centroid, floor.u(1.0))
            out.append(_dev("intercom", "ic_answer", floor, pt, r))
    return out


# ---------------------------------------------------------------- Intrusion
def place_intrusion(floor: Floor, p: dict, access_cats: set[str]) -> list[dict]:
    out = []
    cats = set(p.get("categories") or [])
    pir_m2 = num(p, "pir_m2", 60)
    spacing = num(p, "corridor_pir_m", 15)
    panic = set(p.get("panic_at") or [])
    keypad = set(p.get("keypad_at") or [])
    inset = floor.u(0.4)
    rooms = {r.id: r for r in floor.rooms}
    for r in _sorted_rooms(floor):
        if r.category in cats:
            if r.category == "corridor":
                a, b, length_u, _ = G.principal_axis(r.poly)
                n = max(1, math.ceil(floor.m(length_u) / spacing))
                for pt in G.along(a, b, n):
                    out.append(_dev("intrusion", "int_pir", floor, pt, r))
            else:
                n = max(1, math.ceil(r.area_m2 / max(pir_m2, 1)))
                pts = [_corner(r, _door_pt(r), inset, farthest=True)] if n == 1 else \
                    G.grid_points(r.poly, n, margin=floor.u(1.0))
                for pt in pts:
                    out.append(_dev("intrusion", "int_pir", floor, pt, r))
        if r.category in panic:
            pt, _ = _wall_opposite(r, _door_pt(r), floor.u(0.6))
            out.append(_dev("intrusion", "int_panic", floor, pt, r))
        if r.category in keypad and r.doors:
            out.append(_dev("intrusion", "int_keypad", floor, _offset(r.doors[0].pt, r.centroid, floor.u(0.8)), r))
    contact_cats = access_cats | {"entrance"}
    for door in floor.doors:
        r = rooms.get(door.served or "")
        if r and r.category in contact_cats:
            out.append(_dev("intrusion", "int_contact", floor, _offset(door.pt, r.centroid, floor.u(0.3)), r,
                            door=door.id, leaves=door.leaves))
    hubs = sorted([r for r in floor.rooms if r.category in ("corridor", "entrance", "lift_lobby")],
                  key=lambda r: -r.area_m2)
    if hubs or floor.rooms:
        r = hubs[0] if hubs else max(floor.rooms, key=lambda r: r.area_m2)
        out.append(_dev("intrusion", "int_sounder", floor, r.centroid, r))
    return out


# ---------------------------------------------------------------- driver
def place_all(floors: list[Floor], params: dict[str, dict]) -> list[dict]:
    pp = {k: merged(k, params.get(k)) for k in ("cctv", "access", "iptv", "cabling", "intercom", "intrusion")}
    access_cats = set(pp["access"].get("categories") or [])
    devices: list[dict] = []
    for fl in floors:
        devs = (place_cctv(fl, pp["cctv"]) + place_access(fl, pp["access"]) + place_iptv(fl, pp["iptv"])
                + place_cabling(fl, pp["cabling"]) + place_intercom(fl, pp["intercom"])
                + place_intrusion(fl, pp["intrusion"], access_cats))
        _number(devs, fl)
        devices += devs
    # at least one answering unit when there are door stations
    if any(d["item"] in ("ic_video", "ic_audio") for d in devices) and not any(d["item"] == "ic_answer" for d in devices):
        for fl in floors:
            hosts = [r for r in fl.rooms if r.category in ("reception", "security", "entrance", "office")]
            if hosts:
                r = hosts[0]
                d = _dev("intercom", "ic_answer", fl, r.centroid, r, note="added: no reception/security room")
                d["id"] = f"IC{fl.code}-{sum(1 for x in devices if x['floor'] == fl.key and x['sys'] == 'intercom') + 1:02d}"
                devices.append(d)
                break
    return devices
