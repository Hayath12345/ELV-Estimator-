"""Comms room sizing: ports, PoE load, switches, patch panels, UPS + runtime, racks and
42U rack elevations — for any scenario (one system standalone, or the combined award).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import catalog
from .catalog import UPS_MODELS
from .params import COMMS_DEFAULTS, num

ELV_IP = {"cctv", "access", "iptv", "intercom"}  # devices that land on ELV PoE switches
POE24 = catalog.get("inf_poe24")
NET48 = catalog.get("net_access48")
POE24_BUDGET = 370.0
NET48_BUDGET = 740.0


@dataclass
class RackItem:
    label: str
    item: str
    size: int
    kind: str
    u: int = 0  # lowest U occupied


@dataclass
class Rack:
    name: str
    items: list[RackItem] = field(default_factory=list)

    @property
    def used(self) -> int:
        return sum(i.size for i in self.items)


@dataclass
class RoomSizing:
    id: str
    name: str
    floor: str
    floor_name: str
    role: str
    served: dict  # sys -> device count
    elv_ports: int = 0
    elv_poe_w: float = 0.0
    data_ports: int = 0
    ap_count: int = 0
    ap_poe_w: float = 0.0
    elv_switches: int = 0
    user_switches: int = 0
    poe_budget_w: float = 0.0
    poe_load_w: float = 0.0
    elv_panels: int = 0
    data_panels: int = 0
    fibre_panels: int = 0
    cable_mgrs: int = 0
    pdus: int = 0
    equipment: list[tuple[str, int]] = field(default_factory=list)  # (item key, qty) head-end in this room
    load_w: float = 0.0
    ups: str | None = None
    ups_qty: int = 0
    packs: str | None = None
    packs_qty: int = 0
    runtime_min: float = 0.0
    racks: list[Rack] = field(default_factory=list)

    @property
    def u_used(self) -> int:
        return sum(r.used for r in self.racks)


def device_ports(d: dict) -> int:
    if d["sys"] == "cabling":
        return int(d.get("ports", 2))
    if d["sys"] in ELV_IP:
        return 1
    return 0


def device_poe(d: dict) -> float:
    item = d.get("item", "")
    if d["sys"] == "iptv":
        return catalog.get("iptv_receiver").poe_w
    if d["sys"] == "access":
        return 0.0  # powered through the door controller (counted per controller)
    it = catalog.BY_KEY.get(item)
    return it.poe_w if it else 0.0


def head_end(scenario: set[str], qty: dict) -> list[tuple[str, int]]:
    """Rack-mounted head-end equipment that lives in the MDF."""
    def n(sys, key, default=0):
        v = qty.get(sys, {}).get(key)
        return int(v[0]) if v else default

    eq = []
    if "cctv" in scenario and qty.get("cctv"):
        eq += [("cctv_nvr", n("cctv", "cctv_nvr")), ("cctv_vms_server", n("cctv", "cctv_vms_server"))]
    if "access" in scenario and qty.get("access"):
        eq.append(("acs_server_hw", n("access", "acs_server_hw")))
    if "iptv" in scenario and qty.get("iptv"):
        eq.append(("iptv_headend", n("iptv", "iptv_headend")))
    if "intrusion" in scenario and qty.get("intrusion"):
        eq.append(("int_panel", n("intrusion", "int_panel")))
    return [e for e in eq if e[1] > 0]


def size_scenario(floors, devices, routes, backbone, scenario: set[str], qty: dict,
                  access_params: dict, comms_params: dict | None = None) -> dict:
    cp = dict(COMMS_DEFAULTS)
    cp.update(comms_params or {})
    headroom = num(cp, "poe_headroom_pct", 80) / 100
    spare = 1 + num(cp, "spare_ports_pct", 10) / 100
    fill = num(cp, "rack_fill_pct", 80) / 100
    min_rt = num(cp, "ups_min_runtime_min", 60)
    ups_load = num(cp, "ups_load_pct", 80) / 100
    eff = num(cp, "psu_efficiency", 0.9)
    derate = num(cp, "battery_derate", 0.72)
    dpc = max(1, int(num(access_params, "doors_per_controller", 2)))
    with_network = "cabling" in scenario

    rooms: dict[str, RoomSizing] = {}
    fl_name = {f.key: f.name for f in floors}
    for f in floors:
        for r in f.comms_rooms:
            rooms[r.id + "@" + f.key] = RoomSizing(r.id, r.name, f.key, f.name, r.comms or "IDF", {})
    from .layout.routing import mdf_of
    m = mdf_of(floors)
    mdf_key = (m[1].id + "@" + m[0].key) if m else None
    if mdf_key and mdf_key in rooms:
        rooms[mdf_key].role = "MDF"

    doors_per_room: dict[str, int] = {}
    for d in devices:
        if d["sys"] not in scenario:
            continue
        rt = routes.get(d["id"])
        if not rt:
            continue
        key = rt["room"] + "@" + rt["room_floor"]
        rs = rooms.get(key)
        if not rs:
            continue
        rs.served[d["sys"]] = rs.served.get(d["sys"], 0) + 1
        if d["sys"] == "cabling":
            if d.get("sub") == "ap":
                rs.ap_count += 1
                rs.ap_poe_w += catalog.get("net_ap").poe_w
            rs.data_ports += device_ports(d)
        elif d["sys"] == "access":
            doors_per_room[key] = doors_per_room.get(key, 0) + 1
        elif d["sys"] in ELV_IP:
            rs.elv_ports += 1
            rs.elv_poe_w += device_poe(d)
    for key, n in doors_per_room.items():
        ctrl = math.ceil(n / dpc)
        rooms[key].elv_ports += ctrl
        rooms[key].elv_poe_w += ctrl * catalog.get("acs_controller").poe_w

    n_links = len(backbone)
    for key, rs in rooms.items():
        if rs.elv_ports:
            rs.elv_switches = max(math.ceil(rs.elv_ports * spare / 24), math.ceil(rs.elv_poe_w / (POE24_BUDGET * headroom)))
            rs.elv_panels = math.ceil(rs.elv_ports / 24)
        if with_network and rs.data_ports:
            rs.user_switches = max(math.ceil(rs.data_ports * spare / 48), math.ceil(rs.ap_poe_w / (NET48_BUDGET * headroom)))
            rs.data_panels = math.ceil(rs.data_ports / 24)
        rs.poe_budget_w = rs.elv_switches * POE24_BUDGET + rs.user_switches * NET48_BUDGET
        rs.poe_load_w = rs.elv_poe_w + (rs.ap_poe_w if with_network else 0)
        if key == mdf_key:
            rs.equipment = head_end(scenario, qty)
            if with_network:
                rs.equipment.append(("net_core", 2))
        active = rs.elv_ports or (with_network and rs.data_ports) or rs.equipment
        if not active:
            continue
        if n_links:
            rs.fibre_panels = math.ceil(n_links / 2) if key == mdf_key else 1
        rs.cable_mgrs = math.ceil((rs.elv_panels + rs.data_panels + rs.elv_switches + rs.user_switches) / 2)
        # power
        load = rs.poe_load_w / eff + rs.elv_switches * POE24.power_w + rs.user_switches * NET48.power_w
        for item, q in rs.equipment:
            load += catalog.get(item).power_w * q
        rs.load_w = round(load, 1)
        _choose_ups(rs, ups_load, min_rt, derate)
        _build_racks(rs, fill)
    return {"rooms": [rooms[k] for k in rooms if rooms[k].racks or rooms[k].served], "mdf": mdf_key,
            "backbone": backbone, "floor_names": fl_name}


def _choose_ups(rs: RoomSizing, ups_load: float, min_rt: float, derate: float) -> None:
    if rs.load_w <= 0:
        return
    model = None
    qty = 1
    for m in UPS_MODELS:
        if m[1] * ups_load >= rs.load_w:
            model = m
            break
    if model is None:
        model = UPS_MODELS[-1]
        qty = math.ceil(rs.load_w / (model[1] * ups_load))
    key, cap, pack, internal, per_pack = model
    per_ups = rs.load_w / qty
    packs = 0
    while True:
        rt = (internal + packs * per_pack) * derate / per_ups * 60
        if rt >= min_rt or packs >= 10:
            break
        packs += 1
    rs.ups, rs.ups_qty = key, qty
    rs.packs, rs.packs_qty = (pack if packs else None), packs * qty
    rs.runtime_min = round(rt, 0)


KIND_TXT = {"inf_poe24": "PoE+ switch 24-port 370 W", "net_access48": "PoE+ switch 48-port 740 W",
            "sc_panel24": "Cat6A patch panel 24-port", "sc_fpp": "Fibre patch panel 24F",
            "inf_cablemgr": "Cable manager 1U", "inf_pdu": "Switched PDU"}


def _label(item: str) -> str:
    if item in KIND_TXT:
        return KIND_TXT[item]
    it = catalog.get(item)
    if item.startswith("inf_ups") or item.startswith("inf_bp"):
        return f"{'UPS' if 'ups' in item else 'Battery pack'} {it.part_no}"
    return f"{it.description.split(',')[0]} — {it.part_no}" if it.part_no not in ("TBC", "") else it.description.split(",")[0]


def _build_racks(rs: RoomSizing, fill: float) -> None:
    cap = max(1, int(42 * fill))
    # ELV group: fibre, panels + switches interleaved with managers, head-end
    elv: list[RackItem] = []
    sc: list[RackItem] = []
    pw: list[RackItem] = []

    def add(lst, item, n=1):
        it = catalog.get(item)
        for _ in range(n):
            lst.append(RackItem(_label(item), item, max(1, it.rack_u), it.rack_kind or "mgmt"))

    def patch_block(lst, panels, switches):
        """2 panels, 1 switch, 1 manager … like a real patching field."""
        while panels or switches:
            for _ in range(min(2, panels)):
                add(lst, "sc_panel24")
                panels -= 1
            if switches:
                add(lst, "inf_poe24" if lst is elv else "net_access48")
                switches -= 1
            add(lst, "inf_cablemgr")

    if rs.fibre_panels:
        add(sc if rs.data_panels else elv, "sc_fpp", rs.fibre_panels)
    patch_block(elv, rs.elv_panels, rs.elv_switches)
    for item, q in rs.equipment:
        if item == "net_core":
            add(sc, item, q)
        else:
            add(elv, item, q)
    patch_block(sc, rs.data_panels, rs.user_switches)
    if rs.ups:
        add(pw, rs.ups, rs.ups_qty)
    if rs.packs:
        add(pw, rs.packs, rs.packs_qty)

    groups = [g for g in (elv, sc, pw) if g]
    total = sum(i.size for g in groups for i in g)
    if total == 0:
        return
    n_racks = max(1, math.ceil((total + 1) / cap))  # +1U PDU per rack
    racks: list[Rack] = []
    # pack: power at the bottom of the last racks, the rest top-down
    seq = elv + sc
    cur = Rack("")
    for it in seq:
        if cur.used + it.size > cap - 1 and cur.items:
            racks.append(cur)
            cur = Rack("")
        cur.items.append(it)
    if cur.items:
        racks.append(cur)
    for it in pw:
        target = None
        for r in reversed(racks):
            if r.used + it.size <= cap - 1:
                target = r
                break
        if target is None:
            target = Rack("")
            racks.append(target)
        target.items.append(it)
    if len(racks) < n_racks:
        pass
    for i, r in enumerate(racks, 1):
        r.name = rs.name if len(racks) == 1 else f"{rs.name} R{i}"
        r.items.append(RackItem("Switched PDU", "inf_pdu", 1, "power"))
        top, bottom = 42, 1
        for it in r.items:
            if it.kind in ("power", "battery") and it.item != "inf_pdu":
                it.u = bottom
                bottom += it.size
        for it in r.items:
            if not (it.kind in ("power", "battery") and it.item != "inf_pdu"):
                it.u = top - it.size + 1
                top -= it.size
    rs.racks = racks
    rs.pdus = len(racks)


def totals(sizing: dict) -> dict:
    """Infrastructure quantities for the BOQ from a sized scenario."""
    t: dict[str, float] = {}

    def inc(k, v):
        if v:
            t[k] = t.get(k, 0) + v
    for rs in sizing["rooms"]:
        inc("inf_rack42", len(rs.racks))
        inc("inf_cablemgr", sum(1 for r in rs.racks for i in r.items if i.item == "inf_cablemgr"))
        inc("inf_pdu", rs.pdus)
        if rs.ups:
            inc(rs.ups, rs.ups_qty)
        if rs.packs:
            inc(rs.packs, rs.packs_qty)
        inc("inf_poe24", rs.elv_switches)
        inc("elv_panels", rs.elv_panels)
        inc("data_panels", rs.data_panels)
        inc("sc_fpp", rs.fibre_panels)
        inc("net_access48", rs.user_switches)
    return t
