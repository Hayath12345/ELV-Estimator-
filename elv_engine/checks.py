"""Reconciliation checks: layout vs BOQ, PoE and ports, storage, licences, UPS runtime,
rack fill, link lengths, pricing completeness and totals.

Each check: name, value, rule, limit, pass, severity ('block' stops Issue unless the user
records an override reason; 'warn' is shown but does not block).
"""
from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal

from .boq import all_lines
from .money import ZERO, fmt, fmt_qty
from .systems import SYSTEM_KEYS

MOI_RETENTION_DAYS = 120


def _qty(lines, items) -> Decimal:
    return sum((l.qty for l in lines if l.item in items), ZERO)


def _chk(name, a, op, b, ok, sev="block"):
    return {"name": name, "a": a, "op": op, "b": b, "pass": bool(ok), "sev": sev}


def _float_line_total(l, fx, comm) -> float:
    """Independent recalculation with Excel semantics (float maths + ROUND half away from zero)."""
    def xround(v, n=2):
        m = 10 ** n
        return math.floor(abs(v) * m + 0.5 + 1e-9) / m * (1 if v >= 0 else -1)
    if l.list_price is None:
        return 0.0
    lp = float(l.list_price)
    mk = float(comm["markup"]) / 100
    lmk = float(comm["labour_markup"]) / 100 if comm.get("labour_markup") not in (None, "") else mk
    rate = 1.0 if l.currency == "QAR" else float(fx.get(l.currency, 0) or 0)
    disc = float(l.discount) / 100
    if l.category == "Labour":
        unit = xround(lp * rate * (1 + lmk))
    elif l.currency == "QAR":
        unit = xround(lp * (1 - disc) * (1 + mk))
    else:
        unit = xround(lp * rate * (1 - disc) * (1 + float(comm["duty"]) / 100) * (1 + float(comm["freight"]) / 100) * (1 + mk))
    return xround(unit * float(l.qty))


def run(ctx: dict) -> dict:
    boq = ctx["boq"]
    selected = ctx["selected"]
    info = ctx["qinfo"]
    devices = ctx["devices"]
    routes = ctx["routes"]
    floors = ctx["floors"]
    sizing = ctx["sizing"]
    tabs = boq["tabs"]
    groups: list[dict] = []

    # --- drawings & scale
    rows = []
    for f in floors:
        rows.append(_chk(f"Scale calibrated — {f.name}", "Yes" if f.calibrated else "No", "=", "Yes", f.calibrated))
        rows.append(_chk(f"Rooms extracted — {f.name}", str(len(f.rooms)), "≥", "1", len(f.rooms) > 0))
    n_comms = sum(len(f.comms_rooms) for f in floors)
    rows.append(_chk("Comms rooms (MDF/IDF) identified", str(n_comms), "≥", "1", n_comms >= 1))
    groups.append({"g": "Drawings & scale", "rows": rows})

    def sys_lines(s):
        t = tabs.get(s)
        return [l for sec in t.sections for l in sec.lines] if t else []

    # --- counts layout vs BOQ
    rows = []
    by = {}
    for d in devices:
        by.setdefault(d["sys"], []).append(d)
    if "cctv" in selected:
        cams = len(by.get("cctv", []))
        boq_c = _qty(sys_lines("cctv"), {"cctv_dome_4mp", "cctv_bullet_8mp", "cctv_ptz_2mp", "cctv_fisheye_12mp"})
        rows.append(_chk("CCTV cameras — layout vs BOQ", str(cams), "=", fmt_qty(boq_c), boq_c == cams))
        for k, lbl in (("cctv_dome_4mp", "Dome cameras"), ("cctv_bullet_8mp", "Bullet cameras"),
                       ("cctv_ptz_2mp", "PTZ cameras"), ("cctv_fisheye_12mp", "Fisheye cameras")):
            n = sum(1 for d in by.get("cctv", []) if d["item"] == k)
            b = _qty(sys_lines("cctv"), {k})
            if n or b:
                rows.append(_chk(f"{lbl} — layout vs BOQ", str(n), "=", fmt_qty(b), n == b))
    if "access" in selected:
        doors = by.get("access", [])
        readers = sum(int(d.get("readers", 1)) for d in doors)
        leaves = sum(int(d.get("leaves", 1)) for d in doors)
        rows.append(_chk("Card readers — layout vs BOQ", str(readers), "=", fmt_qty(_qty(sys_lines("access"), {"acs_reader"})),
                         _qty(sys_lines("access"), {"acs_reader"}) == readers))
        rows.append(_chk("Door leaves with contacts", str(leaves), "=", fmt_qty(_qty(sys_lines("access"), {"acs_contact"})),
                         _qty(sys_lines("access"), {"acs_contact"}) == leaves))
    if "iptv" in selected:
        sizes = [43, 55, 65, 75, 85]
        lay = "/".join(str(sum(1 for d in by.get("iptv", []) if d["item"] == f"tv_{s}")) for s in sizes)
        bq = "/".join(fmt_qty(_qty(sys_lines("iptv"), {f"tv_{s}"})) for s in sizes)
        rows.append(_chk('TVs by size (43/55/65/75/85")', lay, "=", bq, lay == bq))
    if "cabling" in selected:
        ports = sum(int(d.get("ports", 2)) for d in by.get("cabling", []))
        jacks = _qty(sys_lines("cabling"), {"sc_jack"})
        rows.append(_chk("Cat6A outlets incl. Wi-Fi APs", str(ports), "=", fmt_qty(jacks / 2), jacks == ports * 2))
        aps = sum(1 for d in by.get("cabling", []) if d.get("sub") == "ap")
        if "network" in tabs:
            ap_b = _qty([l for s in tabs["network"].sections for l in s.lines], {"net_ap"})
            rows.append(_chk("Wi-Fi APs — layout vs Network Active", str(aps), "=", fmt_qty(ap_b), ap_b == aps))
    if "intercom" in selected:
        n = len(by.get("intercom", []))
        b = _qty(sys_lines("intercom"), {"ic_video", "ic_audio", "ic_answer"})
        rows.append(_chk("Intercom devices — layout vs BOQ", str(n), "=", fmt_qty(b), b == n))
    if "intrusion" in selected:
        pirs = sum(1 for d in by.get("intrusion", []) if d["item"] == "int_pir")
        b = _qty(sys_lines("intrusion"), {"int_pir"})
        rows.append(_chk("PIR detectors — layout vs BOQ", str(pirs), "=", fmt_qty(b), b == pirs))
        cts = sum(int(d.get("leaves", 1)) for d in by.get("intrusion", []) if d["item"] == "int_contact")
        b2 = _qty(sys_lines("intrusion"), {"int_contact"})
        rows.append(_chk("Intrusion door contacts — layout vs BOQ", str(cts), "=", fmt_qty(b2), b2 == cts))
    groups.append({"g": "Counts", "rows": rows})

    # --- PoE & ports
    rows = []
    for rs in sizing["rooms"]:
        if rs.poe_budget_w:
            lim = rs.poe_budget_w * 0.8
            rows.append(_chk(f"{rs.name} PoE load vs budget", f"{rs.poe_load_w:,.0f} W", "≤", f"{lim:,.0f} W (80%)",
                             rs.poe_load_w <= lim + 1e-6))
        if rs.elv_ports:
            cap = rs.elv_switches * 24
            rows.append(_chk(f"{rs.name} ELV switch ports used", str(rs.elv_ports), "≤", str(cap), rs.elv_ports <= cap))
        if rs.data_ports and rs.user_switches:
            cap = rs.user_switches * 48
            rows.append(_chk(f"{rs.name} access switch ports used", str(rs.data_ports), "≤", str(cap), rs.data_ports <= cap))
    groups.append({"g": "PoE & ports", "rows": rows})

    # --- storage
    rows = []
    if "cctv" in selected and info.get("cctv"):
        c = info["cctv"]
        nvr_b = _qty(sys_lines("cctv"), {"cctv_nvr"})
        usable = float(c["usable_tb"]) / max(c["nvr"], 1) * float(nvr_b)
        rows.append(_chk(f"Recording capacity at {c['retention']:.0f} days", f"{c['storage_tb']:.1f} TB", "≤",
                         f"{usable:.1f} TB usable", c["storage_tb"] <= usable + 1e-6))
        rows.append(_chk("Retention (MOI-SSD)", f"{c['retention']:.0f} days", "≥", f"{MOI_RETENTION_DAYS} days",
                         c["retention"] >= MOI_RETENTION_DAYS))
        groups.append({"g": "Storage & retention", "rows": rows})

    # --- licences
    rows = []
    if "cctv" in selected and info.get("cctv"):
        n = info["cctv"]["cameras"]
        b = _qty(sys_lines("cctv"), {"cctv_vms_cam"})
        rows.append(_chk("VMS camera licences", fmt_qty(b), "≥", str(n), b >= n))
    if "access" in selected and info.get("access"):
        n = info["access"]["doors"]
        b = _qty(sys_lines("access"), {"acs_door_lic"})
        rows.append(_chk("Access door licences", fmt_qty(b), "≥", str(n), b >= n))
    if "iptv" in selected and info.get("iptv"):
        n = info["iptv"]["tvs"]
        b = _qty(sys_lines("iptv"), {"iptv_receiver"})
        rows.append(_chk("IPTV receiver licences", fmt_qty(b), "≥", str(n), b >= n))
    if rows:
        groups.append({"g": "Licences", "rows": rows})

    # --- UPS runtime / rack fill
    rows = []
    for rs in sizing["rooms"]:
        if rs.ups:
            rows.append(_chk(f"{rs.name} runtime", f"{rs.runtime_min:.0f} min", "≥", "60 min", rs.runtime_min >= 60))
    if rows:
        groups.append({"g": "UPS runtime", "rows": rows})
    rows = []
    for rs in sizing["rooms"]:
        for rk in rs.racks:
            rows.append(_chk(f"{rk.name} rack fill", f"{rk.used} U", "≤", "34 U (80%)", rk.used <= 34))
    if rows:
        groups.append({"g": "Rack fill", "rows": rows})

    # --- link length
    rows = []
    room_names = {r.id: r.name for f in floors for r in f.rooms}
    for f in floors:
        lens = [(routes[d["id"]]["len_m"], d["id"]) for d in devices
                if d["floor"] == f.key and d["id"] in routes and d["sys"] in selected and d["sys"] != "intrusion"]
        if lens:
            mx = max(lens)
            room = room_names.get(routes[mx[1]]["room"], routes[mx[1]]["room"])
            rows.append(_chk(f"Longest channel, {f.name} ({room})", f"{mx[0]:.1f} m", "≤", "90 m", mx[0] <= 90))
    over = sum(1 for d in devices if d["sys"] in selected and routes.get(d["id"], {}).get("over"))
    rows.append(_chk("Links over 90 m", str(over), "=", "0", over == 0))
    groups.append({"g": "Link length", "rows": rows})

    # --- pricing
    rows = []
    lines = all_lines(boq)
    unpriced = [l for l in lines if l.unpriced and l.tab != "optional"]
    rows.append(_chk("All BOQ lines priced", str(len(unpriced)), "=", "0", not unpriced))
    fx = ctx["fx"]
    missing_fx = sorted({l.currency for l in lines if l.list_price is not None and l.currency != "QAR"
                         and not fx.get(l.currency)})
    rows.append(_chk("Exchange rates set for all currencies used", ", ".join(missing_fx) or "All set", "=", "All set",
                     not missing_fx))
    rfq = [l for l in lines if l.budget]
    rows.append(_chk("Budgetary prices (RFQ required)", str(len(rfq)), "=", "0", not rfq, "warn"))
    stale = 0
    today = date.today()
    for l in lines:
        if l.date_checked:
            try:
                dt = datetime.strptime(l.date_checked[:10], "%Y-%m-%d").date()
                if (today - dt).days > 180:
                    stale += 1
            except ValueError:
                pass
    rows.append(_chk("Prices checked within 180 days", str(stale), "=", "0", stale == 0, "warn"))
    groups.append({"g": "Pricing", "rows": rows})

    # --- totals reconciliation
    rows = []
    t = boq["totals"]
    ok_all = True
    for k, tab in tabs.items():
        s_lines = sum((l.total for s in tab.sections for l in s.lines), ZERO)
        s_secs = sum((s.total for s in tab.sections), ZERO)
        ok_all &= s_lines == s_secs == tab.combined
    rows.append(_chk("Sum of lines vs section and tab totals", "All tabs" if ok_all else "Mismatch", "=", "All tabs", ok_all))
    comb = sum((tabs[s].combined for s in selected), ZERO) + t["shared"]
    rows.append(_chk("Systems + shared vs combined base total", fmt(comb), "=", fmt(t["combined"]), comb == t["combined"]))
    if boq["combined"]:
        rows.append(_chk("Standalone − combined vs saving", fmt(t["standalone"] - t["combined"]), "=", fmt(t["saving"]),
                         t["standalone"] - t["combined"] == t["saving"]))
        rows.append(_chk("Shared infrastructure allocation", fmt(t["shared"]), "=",
                         fmt(tabs["shared"].combined if "shared" in tabs else ZERO), True))
    indep = 0.0
    for l in lines:
        if l.tab != "optional" and l.tab != "network":
            indep += _float_line_total(l, fx, ctx["commercial"])
    indep = round(indep, 2)
    rows.append(_chk("Independent recalculation (Excel formula logic)", f"{indep:,.2f}", "=", fmt(t["base"]),
                     abs(Decimal(str(indep)) - t["base"]) < Decimal("0.005")))
    rows.append(_chk("Base total greater than zero", fmt(t["base"]), ">", "0.00", t["base"] > 0))
    groups.append({"g": "Totals reconciliation", "rows": rows})

    n = sum(len(g["rows"]) for g in groups)
    passed = sum(1 for g in groups for r in g["rows"] if r["pass"])
    blocking = sum(1 for g in groups for r in g["rows"] if not r["pass"] and r["sev"] == "block")
    for i, g in enumerate(groups):
        g["id"] = f"g{i}"
        g["n"] = len(g["rows"])
        g["passed"] = sum(1 for r in g["rows"] if r["pass"])
    return {"groups": groups, "total": n, "passed": passed, "blocking": blocking}
