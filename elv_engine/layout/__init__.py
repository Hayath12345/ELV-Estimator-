"""Device layout: placement, user edits and routing."""
from __future__ import annotations

import copy

from .. import catalog

SHORT = {
    "cctv_dome_4mp": "Fixed dome 4MP", "cctv_bullet_8mp": "Bullet 8MP", "cctv_ptz_2mp": "PTZ 2MP",
    "cctv_fisheye_12mp": "Fisheye 12MP", "ic_video": "Video door station", "ic_audio": "Audio-only station",
    "ic_answer": "Answering unit", "int_pir": "Dual-tech PIR, Grade 3", "int_contact": "Door contact, Grade 3",
    "int_panic": "Panic button", "int_keypad": "Keypad", "int_sounder": "Internal sounder",
}
OUTLET_KIND = {"wp": "work position", "meeting": "meeting table", "desk": "desk", "services": "services",
               "printer": "printer / services"}

# Types offered by "Add device" per system (layout item keys).
ADD_TYPES = {
    "cctv": ["cctv_dome_4mp", "cctv_bullet_8mp", "cctv_ptz_2mp", "cctv_fisheye_12mp"],
    "access": ["acs_reader"],
    "iptv": ["tv_43", "tv_55", "tv_65", "tv_75", "tv_85"],
    "cabling": ["sc_outlet", "sc_ap"],
    "intercom": ["ic_video", "ic_audio", "ic_answer"],
    "intrusion": ["int_pir", "int_contact", "int_panic", "int_keypad", "int_sounder"],
}
PREFIX = {"cctv": "C", "access": "A", "iptv": "TV", "intercom": "IC", "intrusion": "I"}


def type_label(d: dict) -> str:
    item = d.get("item", "")
    if item in SHORT:
        return SHORT[item]
    if item == "acs_reader":
        lock = "maglock" if d.get("lock") == "maglock" else "electric strike"
        rd = "in/out readers" if d.get("readers", 1) == 2 else "reader + REX"
        return f"Card reader door · {rd} · {lock} · {d.get('leaves', 1)} leaf" + ("s" if d.get("leaves", 1) > 1 else "")
    if item.startswith("tv_"):
        return f'{item[3:]}" display'
    if item == "sc_outlet":
        return f"Cat6A outlet × {d.get('ports', 2)}, {OUTLET_KIND.get(d.get('kind'), 'outlet')}"
    if item == "sc_ap":
        return f"Wi-Fi AP outlet, {d.get('ports', 2)} × Cat6A"
    it = catalog.BY_KEY.get(item)
    return it.description if it else item


def default_add(sys: str) -> dict:
    return {
        "cctv": {"item": "cctv_dome_4mp", "target": "Recognise", "a": 0},
        "access": {"item": "acs_reader", "sub": "door", "leaves": 1, "readers": 1, "lock": "strike"},
        "iptv": {"item": "tv_55", "size": 55, "a": 0},
        "cabling": {"item": "sc_outlet", "sub": "data", "kind": "wp", "ports": 2},
        "intercom": {"item": "ic_video"},
        "intrusion": {"item": "int_pir"},
    }[sys]


def new_id(sys: str, floor_code: str, existing: set[str], sub: str | None = None) -> str:
    pre = ("W" if sub == "ap" else "D") if sys == "cabling" else PREFIX[sys]
    width = 3 if pre == "D" else 2
    n = 1
    while f"{pre}{floor_code}-{n:0{width}d}" in existing:
        n += 1
    return f"{pre}{floor_code}-{n:0{width}d}"


def apply_edits(auto: list[dict], edits: dict | None) -> list[dict]:
    edits = edits or {}
    deleted = set(edits.get("deleted", []))
    moved = edits.get("moved", {})
    props = edits.get("props", {})
    out = []
    for d in auto:
        if d["id"] in deleted:
            continue
        d = copy.copy(d)
        if d["id"] in moved:
            d["x"], d["y"] = moved[d["id"]]
            d["edited"] = True
        if d["id"] in props:
            d.update(props[d["id"]])
            d["edited"] = True
        out.append(d)
    for a in edits.get("added", []):
        if a["id"] in deleted:
            continue
        a = copy.copy(a)
        if a["id"] in moved:
            a["x"], a["y"] = moved[a["id"]]
        if a["id"] in props:
            a.update(props[a["id"]])
        a["auto"] = False
        out.append(a)
    return out
