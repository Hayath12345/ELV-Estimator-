"""Quantities per system from the device layout, routes and design parameters.

Returns ``{system: {item_key: (qty, note)}}`` plus cable lengths, so every BOQ
quantity can be traced back to the layout ("66 cameras on layout").
"""
from __future__ import annotations

import math
from collections import Counter

from . import catalog
from .params import merged, num

ELV_DROP_SYSTEMS = ("cctv", "access", "iptv", "intercom")


def _ceil10(x: float) -> int:
    return int(math.ceil(x / 10.0) * 10) if x > 0 else 0


def storage_tb(cams: Counter, p: dict) -> float:
    days = num(p, "retention_days", 120)
    fps = num(p, "fps", 15)
    codec = 1.0 if p.get("codec", "H.265") == "H.265" else 1.6
    mode = 0.5 if str(p.get("recording", "24/7")).startswith("Motion") else 1.0
    mbps = sum(catalog.CAMERA_BITRATE.get(k, 4.0) * n for k, n in cams.items()) * (fps / 15.0) * codec * mode
    return mbps * 86400 * days / 8 / 1e6 * 1.1  # TB incl. 10% file-system overhead


def raid_usable(p: dict) -> float:
    raw = num(p, "nvr_raw_tb", 192)
    return raw * (10 / 12 if p.get("raid", "RAID 6") == "RAID 6" else 11 / 12)


def route_len(routes, d) -> float:
    r = routes.get(d["id"])
    return r["len_m"] if r else 0.0


def compute(devices: list[dict], routes: dict, params: dict) -> dict:
    pp = {k: merged(k, params.get(k)) for k in ("cctv", "access", "iptv", "cabling", "intercom", "intrusion")}
    waste = 1 + num(pp["cabling"], "waste_pct", 5) / 100
    by_sys: dict[str, list[dict]] = {}
    for d in devices:
        by_sys.setdefault(d["sys"], []).append(d)
    q: dict[str, dict[str, tuple[float, str]]] = {k: {} for k in pp}
    info: dict[str, dict] = {k: {} for k in pp}

    # ---- CCTV
    cams = Counter(d["item"] for d in by_sys.get("cctv", []))
    n_cam = sum(cams.values())
    c = q["cctv"]
    for k, n in cams.items():
        c[k] = (n, f"{n} on layout")
    if n_cam:
        p = pp["cctv"]
        need = storage_tb(cams, p)
        usable = raid_usable(p)
        nvr = max(1, math.ceil(need / usable))
        info["cctv"].update(storage_tb=round(need, 1), usable_tb=round(usable * nvr, 1), nvr=nvr,
                            retention=num(p, "retention_days", 120), cameras=n_cam)
        c["cctv_nvr"] = (nvr, f"{need:.1f} TB needed at {num(p, 'retention_days', 120):.0f} days ÷ {usable:.0f} TB usable")
        c["cctv_vms_server"] = (1, "1 per system")
        spares = nvr * int(num(p, "spare_drives_per_nvr", 2))
        if spares:
            c["cctv_hdd_spare"] = (spares, f"{int(num(p, 'spare_drives_per_nvr', 2))} per recorder")
        c["cctv_vms_base"] = (1, "1 per system")
        c["cctv_vms_cam"] = (n_cam, f"{n_cam} cameras")
        c["cctv_vms_care"] = (n_cam, f"{n_cam} cameras")
        ws = int(num(p, "workstations", 2))
        vw = int(num(p, "videowall", 4))
        if ws:
            c["cctv_workstation"] = (ws, "design parameter")
        if vw:
            c["cctv_videowall"] = (vw, "design parameter")
        mounts = cams["cctv_dome_4mp"] + cams["cctv_fisheye_12mp"] + cams["cctv_ptz_2mp"]
        if mounts:
            c["cctv_mount"] = (mounts, "1 per dome / fisheye / PTZ")
        if cams["cctv_bullet_8mp"]:
            c["cctv_jbox"] = (cams["cctv_bullet_8mp"], "1 per bullet")
        c["cctv_tc"] = (1, "lump sum")

    # ---- Access control
    doors = by_sys.get("access", [])
    a = q["access"]
    if doors:
        p = pp["access"]
        dpc = max(1, int(num(p, "doors_per_controller", 2)))
        per_room = Counter((routes.get(d["id"]) or {}).get("room", "?") for d in doors)
        ctrl = sum(math.ceil(n / dpc) for n in per_room.values())
        leaves = sum(int(d.get("leaves", 1)) for d in doors)
        readers = sum(int(d.get("readers", 1)) for d in doors)
        single = sum(1 for d in doors if int(d.get("readers", 1)) == 1)
        mag_doors = [d for d in doors if d.get("lock") == "maglock"]
        mags = sum(int(d.get("leaves", 1)) for d in mag_doors)
        strikes = sum(1 for d in doors if d.get("lock") != "maglock")
        nd = len(doors)
        info["access"].update(doors=nd, leaves=leaves, readers=readers, controllers=ctrl)
        a["acs_controller"] = (ctrl, f"{nd} doors ÷ {dpc} per controller, per comms room")
        a["acs_reader"] = (readers, f"{nd} doors, {readers - nd} with in/out reading")
        if single:
            a["acs_rex"] = (single, "1 per single-reader door")
        if mags:
            a["acs_maglock"] = (mags, f"{len(mag_doors)} doors, 1 per leaf")
            a["acs_breakglass"] = (len(mag_doors), "1 per maglocked door (civil defence)")
        if strikes:
            a["acs_strike"] = (strikes, "1 per strike door")
        a["acs_contact"] = (leaves, f"{leaves} leaves")
        a["acs_psu"] = (ctrl, "1 per controller")
        a["acs_server_hw"] = (1, "1 per system")
        a["acs_server"] = (1, "1 per system")
        a["acs_door_lic"] = (nd, f"{nd} doors")
        mp = int(num(p, "mobile_packs", 1))
        if mp:
            a["acs_mobile"] = (mp, "design parameter")
        a["acs_tc"] = (1, "lump sum")

    # ---- IPTV
    tvs = Counter(d["item"] for d in by_sys.get("iptv", []))
    t = q["iptv"]
    n_tv = sum(tvs.values())
    if n_tv:
        for k in sorted(tvs, key=lambda x: int(x[3:])):
            t[k] = (tvs[k], f"{tvs[k]} on layout")
        t["iptv_headend"] = (1, f"{int(num(pp['iptv'], 'channels', 24))} channels")
        t["iptv_receiver"] = (n_tv, "1 per display")
        t["iptv_middleware"] = (1, "1 per system")
        t["iptv_bracket"] = (n_tv, "1 per display")
        t["iptv_tc"] = (1, "lump sum")
        info["iptv"].update(tvs=n_tv, by_size={k[3:]: v for k, v in tvs.items()})

    # ---- Structured cabling
    sc = by_sys.get("cabling", [])
    s = q["cabling"]
    if sc:
        ports = sum(int(d.get("ports", 2)) for d in sc)
        aps = sum(1 for d in sc if d.get("sub") == "ap")
        ap_ports = sum(int(d.get("ports", 2)) for d in sc if d.get("sub") == "ap")
        per_room = Counter()
        for d in sc:
            per_room[(routes.get(d["id"]) or {}).get("room", "?")] += int(d.get("ports", 2))
        panels = sum(math.ceil(n / 24) for n in per_room.values())
        cable = sum(route_len(routes, d) * int(d.get("ports", 2)) for d in sc) * waste
        info["cabling"].update(outlets=ports, aps=aps, ap_ports=ap_ports, points=len(sc), cable_m=_ceil10(cable))
        s["sc_jack"] = (ports * 2, f"{ports} outlets × 2 ends")
        s["sc_faceplate"] = (len(sc) - aps, f"{len(sc) - aps} outlet locations")
        s["sc_panel24"] = (panels, "outlets ÷ 24 per comms room")
        s["sc_cord"] = (ports, "1 per panel port")
        s["sc_cable"] = (_ceil10(cable), f"Σ {ports} routed links + {num(pp['cabling'], 'waste_pct', 5):.0f}% waste")
        s["sc_tc"] = (1, "lump sum")

    # ---- Intercom
    ic = Counter(d["item"] for d in by_sys.get("intercom", []))
    i = q["intercom"]
    if sum(ic.values()):
        for k in ("ic_video", "ic_audio", "ic_answer"):
            if ic[k]:
                i[k] = (ic[k], f"{ic[k]} on layout")
        i["ic_sip"] = (1, "1 per system")
        i["ic_tc"] = (1, "lump sum")
        info["intercom"].update(devices=sum(ic.values()))

    # ---- Intrusion
    it_devs = by_sys.get("intrusion", [])
    n = q["intrusion"]
    if it_devs:
        cnt = Counter(d["item"] for d in it_devs)
        contacts = sum(int(d.get("leaves", 1)) for d in it_devs if d["item"] == "int_contact")
        zones = cnt["int_pir"] + contacts + cnt["int_panic"]
        panels = max(1, math.ceil(zones / 599))
        exp = math.ceil(max(0, zones - 8 * panels) / 8)
        cable = sum(route_len(routes, d) for d in it_devs) * waste
        n["int_panel"] = (panels, f"{zones} zones")
        if cnt["int_keypad"]:
            n["int_keypad"] = (cnt["int_keypad"], f"{cnt['int_keypad']} on layout")
        else:
            n["int_keypad"] = (1, "minimum 1")
        if exp:
            n["int_expander"] = (exp, f"{zones} zones − {8 * panels} on panel, ÷ 8")
        if cnt["int_pir"]:
            n["int_pir"] = (cnt["int_pir"], f"{cnt['int_pir']} on layout")
        if contacts:
            n["int_contact"] = (contacts, f"{cnt['int_contact']} doors, 1 per leaf")
        if cnt["int_panic"]:
            n["int_panic"] = (cnt["int_panic"], f"{cnt['int_panic']} on layout")
        if cnt["int_sounder"]:
            n["int_sounder"] = (cnt["int_sounder"], "1 per floor")
        n["int_rps"] = (1, "1 per system")
        n["int_cable"] = (_ceil10(cable), "Σ routed runs + waste")
        n["int_tc"] = (1, "lump sum")
        info["intrusion"].update(devices=len(it_devs), zones=zones)
    return {"q": q, "info": info, "params": pp}


def drop_cable_m(devices, routes, sys_set, params) -> float:
    """Cat6A for ELV IP devices (shared-eligible)."""
    pp = {k: merged(k, params.get(k)) for k in ("access", "cabling")}
    waste = 1 + num(pp["cabling"], "waste_pct", 5) / 100
    cpd = num(pp["access"], "cables_per_door", 2)
    total = 0.0
    for d in devices:
        if d["sys"] in sys_set and d["sys"] in ELV_DROP_SYSTEMS:
            total += route_len(routes, d) * (cpd if d["sys"] == "access" else 1)
    return _ceil10(total * waste)
