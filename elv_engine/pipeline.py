"""End-to-end calculation: drawings -> floors -> devices -> routes -> comms rooms ->
quantities -> BOQ -> checks. Pure function of the project dict + price library + FX.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import boq as boq_mod
from . import checks as checks_mod
from . import comms
from . import quantities
from .layout import apply_edits
from .layout.floor import Floor, build_floors
from .layout.place import place_all
from .layout.routing import assign, trunk_length_m
from .money import dec
from .params import merged, num
from .systems import SYSTEM_KEYS


@dataclass
class Result:
    floors: list[Floor]
    devices: list[dict]
    routes: dict
    backbone: list[dict]
    qres: dict
    sizing: dict  # combined scenario (selected systems) — the physical comms-room design
    sizing_by_sys: dict
    boq: dict
    checks: dict
    selected: list[str]
    fx: dict
    commercial: dict
    auto: list[dict]  # rule-based placement before user edits


def _ceil10(x: float) -> int:
    return int(math.ceil(x / 10.0) * 10) if x > 0 else 0


def infra_for(scenario: set[str], floors, devices, routes, backbone, qres, params) -> tuple[dict, dict]:
    acc = merged("access", params.get("access"))
    sizing = comms.size_scenario(floors, devices, routes, backbone, scenario, qres["q"], acc)
    t = comms.totals(sizing)
    infra: dict[str, tuple] = {}
    n_rooms = sum(1 for r in sizing["rooms"] if r.racks)

    def put(k, v, note):
        if v:
            infra[k] = (v, note)
    put("inf_rack42", t.get("inf_rack42", 0), f"{n_rooms} comms rooms, ≤ 80% fill")
    put("inf_cablemgr", t.get("inf_cablemgr", 0), "1 per 2 panels / switches")
    put("inf_pdu", t.get("inf_pdu", 0), "1 per rack")
    for k in ("inf_ups_1500", "inf_ups_2k", "inf_ups_3k", "inf_ups_6k", "inf_ups_10k"):
        put(k, t.get(k, 0), "sized per comms room load")
    for k in ("inf_bp_48", "inf_bp_72", "inf_bp_96", "inf_bp_192"):
        put(k, t.get(k, 0), "for ≥ 60 min runtime")
    put("inf_poe24", t.get("inf_poe24", 0), "ports + 10% spare, PoE ≤ 80%")
    put("elv_panels", t.get("elv_panels", 0), "ELV ports ÷ 24 per room")
    put("sc_fpp", t.get("sc_fpp", 0), "backbone terminations")
    active_rooms = {r.id for r in sizing["rooms"] if r.racks}
    fib = sum(l["len_m"] for l in backbone if l["from"] in active_rooms) * 1.1
    put("sc_fibre", _ceil10(fib), f"{sum(1 for l in backbone if l['from'] in active_rooms)} IDF uplinks + 10%")
    put("drop_cable", quantities.drop_cable_m(devices, routes, scenario, params), "Σ routed ELV device drops + waste")
    tray = trunk_length_m(floors, [d for d in devices if d["sys"] in scenario], routes) * 1.1
    put("inf_tray", int(math.ceil(tray)), "corridor runs used + 10%")
    return infra, sizing


def network_qty(sizing: dict, devices: list[dict], backbone: list[dict]) -> dict:
    n_sw = sum(r.user_switches for r in sizing["rooms"])
    aps = sum(1 for d in devices if d["sys"] == "cabling" and d.get("sub") == "ap")
    if not n_sw and not aps:
        return {}
    links = len(backbone)
    q = {"net_core": (2, "stacked pair"), "net_sfp": (max(2, links * 4), f"{links} uplinks × 4 (both ends, redundant)"),
         "net_access48": (n_sw, "user outlets + APs, 10% spare"), "net_cfg": (1, "lump sum")}
    if aps:
        q["net_ap"] = (aps, f"{aps} on layout")
        q["net_wlc"] = (1, "1 per site")
    return q


def compute(project: dict, library: dict, fx: dict) -> Result:
    params = project.get("systems", {}).get("params", {})
    selected = [s for s in project["systems"].get("selected", SYSTEM_KEYS) if s in SYSTEM_KEYS]
    combined = bool(project["systems"].get("combined", True))
    floors = build_floors(project)
    auto = place_all(floors, params)
    devices = apply_edits(auto, project.get("layout_edits"))
    cab = merged("cabling", params.get("cabling"))
    rt = assign(floors, devices, cab)
    routes, backbone = rt["routes"], rt["backbone"]
    qres = quantities.compute(devices, routes, params)

    infra_sa, sizing_by = {}, {}
    for s in selected:
        infra_sa[s], sizing_by[s] = infra_for({s}, floors, devices, routes, backbone, qres, params)
    infra_comb, sizing = infra_for(set(selected), floors, devices, routes, backbone, qres, params)
    net = {}
    if "cabling" in selected:
        net = network_qty(sizing, devices, backbone)
    state = {"q": qres["q"], "infra_standalone": infra_sa, "infra_combined": infra_comb, "network": net}
    bq = project.get("boq", {})
    commercial = project.get("commercial", {})
    boq = boq_mod.build(state, library, bq.get("project_prices", {}), dict(bq.get("overrides", {})),
                        bq.get("extra_lines", []), commercial, fx, selected, combined)
    ck = checks_mod.run({"boq": boq, "selected": selected, "qinfo": qres["info"], "devices": devices,
                         "routes": routes, "floors": floors, "sizing": sizing, "fx": fx, "commercial": commercial})
    return Result(floors, devices, routes, backbone, qres, sizing, sizing_by, boq, ck, selected, fx, commercial, auto)


def effective_fx(lib_fx: dict, overrides: dict | None) -> dict:
    fx = dict(lib_fx)
    for k, v in (overrides or {}).items():
        d = dec(v, None)
        if d:
            fx[k] = d
    fx["QAR"] = dec(1)
    return fx
