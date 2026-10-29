"""BOQ assembly and pricing: per-system tabs (with their shared-eligible infrastructure),
Shared infrastructure, Network Active and Optional, standalone vs combined totals.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal

from . import catalog
from .catalog import LABOUR_ROLES
from .money import ZERO, dec, fmt, fmt_price, fmt_qty, r2
from .pricing import factors, line_total, unit_cost, unit_sell
from .systems import SYSTEM_KEYS, tab_color, tab_name

SECTIONS: dict[str, list[tuple[str, list[str]]]] = {
    "cctv": [
        ("Cameras", ["cctv_dome_4mp", "cctv_bullet_8mp", "cctv_ptz_2mp", "cctv_fisheye_12mp"]),
        ("Recording & storage", ["cctv_nvr", "cctv_vms_server", "cctv_hdd_spare"]),
        ("VMS & licences", ["cctv_vms_base", "cctv_vms_cam", "cctv_vms_care"]),
        ("Workstations & video wall", ["cctv_workstation", "cctv_videowall"]),
        ("Mounts & accessories", ["cctv_mount", "cctv_jbox"]),
        ("Installation, testing & commissioning", ["cctv_tc"]),
    ],
    "access": [
        ("Controllers & readers", ["acs_controller", "acs_reader", "acs_rex", "acs_breakglass"]),
        ("Locking hardware", ["acs_maglock", "acs_strike", "acs_contact", "acs_psu"]),
        ("Software & credentials", ["acs_server_hw", "acs_server", "acs_door_lic", "acs_mobile"]),
        ("Installation, testing & commissioning", ["acs_tc"]),
    ],
    "iptv": [
        ("Displays", ["tv_43", "tv_55", "tv_65", "tv_75", "tv_85"]),
        ("Headend & streaming", ["iptv_headend", "iptv_receiver", "iptv_middleware"]),
        ("Mounting", ["iptv_bracket"]),
        ("Installation & programming", ["iptv_tc"]),
    ],
    "cabling": [
        ("Outlets & panels", ["sc_jack", "sc_faceplate", "sc_panel24", "sc_cord"]),
        ("Cable", ["sc_cable"]),
        ("Installation & certification", ["sc_tc"]),
    ],
    "intercom": [
        ("Stations", ["ic_video", "ic_audio", "ic_answer"]),
        ("Licences", ["ic_sip"]),
        ("Installation & commissioning", ["ic_tc"]),
    ],
    "intrusion": [
        ("Panel & keypads", ["int_panel", "int_keypad", "int_expander", "int_sounder", "int_rps"]),
        ("Detectors", ["int_pir", "int_contact", "int_panic"]),
        ("Cable", ["int_cable"]),
        ("Installation & commissioning", ["int_tc"]),
    ],
}

SHARED_SECTIONS = [
    ("Racks & cable management", ["inf_rack42", "inf_cablemgr", "inf_pdu"]),
    ("UPS & batteries", ["inf_ups_1500", "inf_ups_2k", "inf_ups_3k", "inf_ups_6k", "inf_ups_10k",
                         "inf_bp_48", "inf_bp_72", "inf_bp_96", "inf_bp_192"]),
    ("ELV network switches", ["inf_poe24"]),
    ("Backbone & containment", ["elv_panels", "sc_fpp", "sc_fibre", "drop_cable", "inf_tray"]),
    ("Installation", []),
]

NETWORK_SECTIONS = [
    ("Core", ["net_core", "net_sfp"]),
    ("Access switching", ["net_access48"]),
    ("Wireless", ["net_ap", "net_wlc"]),
    ("Configuration", ["net_cfg"]),
]

# Line-specific labels for catalogue items reused in another role.
ALIAS = {"elv_panels": ("sc_panel24", "Patch panel 24-port Cat6A, angled (ELV devices)"),
         "drop_cable": ("sc_cable", "Cat6A U/FTP cable, LSZH (system drops)")}

CONF_LABEL = {"H": "High", "M": "Medium", "L": "Labour rate", "B": "Budgetary", "O": "Other"}


@dataclass
class Line:
    key: str
    tab: str
    section: str
    item: str | None
    description: str
    manufacturer: str
    part_no: str
    unit: str
    category: str
    qty_auto: Decimal
    qty: Decimal
    note: str = ""
    list_price: Decimal | None = None
    currency: str = "USD"
    discount: Decimal = ZERO
    confidence: str | None = None
    source: str = ""
    date_checked: str = ""
    unit_cost: Decimal | None = None
    unit_qar: Decimal | None = None
    total: Decimal = ZERO
    cost_total: Decimal = ZERO
    shared: bool = False  # shared-eligible (moves to Shared infrastructure when combined)
    custom: bool = False
    overridden: list[str] = field(default_factory=list)

    @property
    def budget(self) -> bool:
        return self.confidence == "B"

    @property
    def unpriced(self) -> bool:
        return self.list_price is None and self.qty > 0

    def to_json(self) -> dict:
        conf = "L" if self.category == "Labour" and self.list_price is not None else self.confidence
        return {
            "key": self.key, "tab": self.tab, "section": self.section, "item": self.item,
            "desc": self.description, "mfr": self.manufacturer, "part": self.part_no, "unit": self.unit,
            "category": self.category, "qty": str(self.qty), "qtyF": fmt_qty(self.qty), "qtyAuto": str(self.qty_auto),
            "note": self.note, "list": None if self.list_price is None else str(self.list_price),
            "listF": "—" if self.list_price is None else fmt_price(self.list_price), "cur": self.currency,
            "disc": str(self.discount), "discF": f"{fmt_qty(self.discount)}%" if self.discount else "—",
            "conf": conf, "confLabel": "No price" if self.list_price is None else CONF_LABEL.get(conf or "", "Other"),
            "unitQ": None if self.unit_qar is None else str(self.unit_qar),
            "unitF": "—" if self.unit_qar is None else fmt(self.unit_qar),
            "total": str(self.total), "totalF": fmt(self.total), "shared": self.shared,
            "budget": self.budget, "unpriced": self.unpriced, "custom": self.custom,
            "overridden": self.overridden, "source": self.source, "date": self.date_checked,
        }


@dataclass
class Section:
    id: str
    name: str
    lines: list[Line]
    shared: bool = False

    @property
    def total(self) -> Decimal:
        return sum((l.total for l in self.lines), ZERO)


@dataclass
class Tab:
    key: str
    sections: list[Section]
    shared_section: Section | None = None

    @property
    def combined(self) -> Decimal:
        return sum((s.total for s in self.sections), ZERO)

    @property
    def standalone(self) -> Decimal:
        return self.combined + (self.shared_section.total if self.shared_section else ZERO)


def _mk_line(tab, section, key_item, qty, note, shared=False) -> Line:
    item_key, desc = ALIAS.get(key_item, (key_item, None))
    it = catalog.get(item_key)
    q = dec(qty) or ZERO
    return Line(key=f"{tab}|{'sh' if shared else section}|{key_item}", tab=tab, section=section, item=item_key,
                description=desc or it.description, manufacturer=it.manufacturer, part_no=it.part_no,
                unit=it.unit, category=it.category, qty_auto=q, qty=q, note=note, currency=it.currency,
                shared=shared)


def _labour_lines(tab, section, lines: list[Line], pm_pct: float, shared=False) -> list[Line]:
    hours: dict[str, float] = {}
    for l in lines:
        it = catalog.BY_KEY.get(l.item or "")
        if not it or not it.labour:
            continue
        for role, h in it.labour.items():
            hours[role] = hours.get(role, 0.0) + h * float(l.qty)
    total = sum(hours.values())
    if total and pm_pct:
        hours["lab_pm"] = hours.get("lab_pm", 0.0) + total * pm_pct / 100
    out = []
    for role in LABOUR_ROLES:
        h = hours.get(role, 0.0)
        if h <= 0:
            continue
        out.append(_mk_line(tab, section, role, math.ceil(h), "labour norms × quantities", shared))
    return out


def infra_section_lines(tab: str, section_name: str, infra: dict, shared: bool, pm_pct: float,
                        inst_key: str) -> list[tuple[str, list[Line]]]:
    """Infrastructure quantities -> sections (Shared tab) or one flat list (shared-eligible)."""
    secs = []
    for name, keys in SHARED_SECTIONS:
        lines = []
        for k in keys:
            qv = infra.get(k)
            if qv:
                q, note = qv if isinstance(qv, tuple) else (qv, "")
                lines.append(_mk_line(tab, section_name if shared else name, k, q, note, shared))
        secs.append((name, lines))
    all_lines = [l for _, ls in secs for l in ls]
    if all_lines:
        inst = _mk_line(tab, section_name if shared else "Installation", inst_key, 1, "lump sum", shared)
        lab = _labour_lines(tab, section_name if shared else "Installation", all_lines, pm_pct, shared)
        secs[-1] = ("Installation", lab + [inst])
    return secs


def build(state: dict, library: dict, project_prices: dict, overrides: dict, extra_lines: list[dict],
          commercial: dict, fx: dict, selected: list[str], combined: bool) -> dict:
    """state = {'q': per-system quantities, 'infra_standalone': {sys: infra}, 'infra_combined': infra,
    'network': {...}}."""
    f = factors(commercial)
    pm_pct = float(dec(commercial.get("pm_pct", 10)) or 0)
    tabs: dict[str, Tab] = {}

    def price(line: Line):
        ov = overrides.get(line.key, {})
        lib = library.get(line.item or "", {}) if line.item else {}
        pp = project_prices.get(line.item or "", {}) if line.item else {}
        if "qty" in ov and ov["qty"] not in (None, ""):
            line.qty = dec(ov["qty"]) or ZERO
            line.overridden.append("qty")
        src = {**lib, **{k: v for k, v in pp.items() if v not in (None, "")}}
        for k in ("list_price", "currency", "discount"):
            if k in ov and ov[k] not in (None, ""):
                src[k] = ov[k]
                line.overridden.append(k)
        line.list_price = dec(src.get("list_price"), None)
        line.currency = src.get("currency") or line.currency
        line.discount = dec(src.get("discount"), ZERO) or ZERO
        line.confidence = src.get("confidence") or ("L" if line.category == "Labour" else None)
        if line.list_price is None:
            line.confidence = None
        line.source = src.get("source", "") or ""
        line.date_checked = src.get("date_checked", "") or ""
        cat_item = catalog.BY_KEY.get(line.item or "")
        alias_desc = bool(cat_item) and line.description != cat_item.description and not line.custom
        for k in ("manufacturer", "part_no"):
            if src.get(k) and not line.custom:
                setattr(line, k, src[k])
        if src.get("description") and not alias_desc and not line.custom:
            line.description = src["description"]
        if ov.get("description"):
            line.description = ov["description"]
        line.unit_cost = unit_cost(line.list_price, line.currency, line.discount, line.category, fx, f)
        line.unit_qar = unit_sell(line.list_price, line.currency, line.discount, line.category, fx, f)
        line.total = line_total(line.unit_qar, line.qty)
        line.cost_total = r2((line.unit_cost or ZERO) * line.qty)

    def custom_lines(tab, section_name, shared=False) -> list[Line]:
        out = []
        for c in extra_lines:
            if c.get("tab") != tab or c.get("section") != section_name:
                continue
            it = catalog.BY_KEY.get(c.get("item") or "")
            q = dec(c.get("qty"), ZERO) or ZERO
            l = Line(key=c["id"], tab=tab, section=section_name, item=c.get("item"),
                     description=c.get("description") or (it.description if it else "Item"),
                     manufacturer=c.get("manufacturer") or (it.manufacturer if it else ""),
                     part_no=c.get("part_no") or (it.part_no if it else ""), unit=c.get("unit") or (it.unit if it else "ea"),
                     category=c.get("category") or (it.category if it else "Device"), qty_auto=q, qty=q,
                     note="added by estimator", currency=c.get("currency") or (it.currency if it else "USD"),
                     shared=shared, custom=True)
            if c.get("list_price") not in (None, ""):
                ov = overrides.setdefault(l.key, {})
                ov.setdefault("list_price", c.get("list_price"))
                ov.setdefault("currency", c.get("currency") or l.currency)
                if c.get("discount") not in (None, ""):
                    ov.setdefault("discount", c.get("discount"))
            out.append(l)
        return out

    for sys in selected:
        qd = state["q"].get(sys, {})
        sections = []
        for i, (name, keys) in enumerate(SECTIONS[sys]):
            sid = f"{sys}-{i}"
            lines = [_mk_line(sys, name, k, qd[k][0], qd[k][1]) for k in keys if k in qd and qd[k][0]]
            sections.append(Section(sid, name, lines))
        all_sys = [l for s in sections for l in s.lines]
        lab = _labour_lines(sys, sections[-1].name, all_sys, pm_pct)
        sections[-1].lines = lab + sections[-1].lines
        for s in sections:
            s.lines += custom_lines(sys, s.name)
        infra = state["infra_standalone"].get(sys, {})
        sh_lines = [l for _, ls in infra_section_lines(sys, "Shared-eligible items", infra, True, pm_pct,
                                                       f"inst_{sys}") for l in ls]
        sh_lines += custom_lines(sys, "Shared-eligible items", shared=True)
        tabs[sys] = Tab(sys, [s for s in sections], Section(f"{sys}-sh", "Shared-eligible items", sh_lines, True))

    if combined and len(selected) > 1:
        secs = []
        for i, (name, lines) in enumerate(infra_section_lines("shared", "", state["infra_combined"], False,
                                                              pm_pct, "inst_shared")):
            secs.append(Section(f"shared-{i}", name, lines + custom_lines("shared", name)))
        tabs["shared"] = Tab("shared", secs)
    if "cabling" in selected and state.get("network"):
        secs = []
        nq = state["network"]
        lines_all = []
        for i, (name, keys) in enumerate(NETWORK_SECTIONS):
            lines = [_mk_line("network", name, k, nq[k][0], nq[k][1]) for k in keys if k in nq and nq[k][0]]
            lines_all += lines
            secs.append(Section(f"network-{i}", name, lines))
        lab = _labour_lines("network", "Configuration", lines_all, pm_pct)
        secs[-1].lines = lab + secs[-1].lines
        for s in secs:
            s.lines += custom_lines("network", s.name)
        tabs["network"] = Tab("network", secs)
    opt = custom_lines("optional", "Optional items (client to confirm)")
    tabs["optional"] = Tab("optional", [Section("optional-0", "Optional items (client to confirm)", opt)])

    for t in tabs.values():
        for s in t.sections + ([t.shared_section] if t.shared_section else []):
            for l in s.lines:
                price(l)
            s.lines = [l for l in s.lines if l.qty > 0 or l.overridden or l.custom]

    return summarise(tabs, selected, combined)


def summarise(tabs: dict[str, Tab], selected: list[str], combined: bool) -> dict:
    is_comb = combined and len(selected) > 1
    shared = tabs["shared"].combined if "shared" in tabs else ZERO
    standalone_base = sum((tabs[s].standalone for s in selected), ZERO)
    combined_base = sum((tabs[s].combined for s in selected), ZERO) + shared
    base = combined_base if is_comb else standalone_base
    network = tabs["network"].combined if "network" in tabs else ZERO
    optional = tabs["optional"].combined
    saving = standalone_base - combined_base if is_comb else ZERO

    # price confidence by value (base + network)
    mix: dict[str, Decimal] = {"High": ZERO, "Medium": ZERO, "Company labour rate": ZERO, "Budgetary": ZERO, "Other": ZERO}
    unpriced = 0
    rfq = 0
    lines_in_scope = []
    for k, t in tabs.items():
        if k == "optional":
            continue
        secs = list(t.sections)
        if t.shared_section and not is_comb:
            secs.append(t.shared_section)
        for s in secs:
            lines_in_scope += s.lines
    for l in lines_in_scope:
        if l.unpriced:
            unpriced += 1
            continue
        if l.budget:
            rfq += 1
        key = ("Company labour rate" if l.category == "Labour" else
               {"H": "High", "M": "Medium", "B": "Budgetary"}.get(l.confidence or "", "Other"))
        mix[key] += l.total
    tot_mix = sum(mix.values(), ZERO)
    conf_mix = [{"k": k, "v": int((v / tot_mix * 100).quantize(Decimal("1"))) if tot_mix else 0, "amount": fmt(v),
                 "tone": {"High": "high", "Medium": "med", "Company labour rate": "lab", "Budgetary": "bud"}.get(k, "oth")}
                for k, v in mix.items()]
    return {
        "tabs": tabs, "combined": is_comb,
        "totals": {"shared": shared, "standalone": standalone_base, "combined": combined_base, "base": base,
                   "saving": saving, "network": network, "optional": optional,
                   "systems": {s: {"standalone": tabs[s].standalone, "combined": tabs[s].combined} for s in selected}},
        "conf_mix": conf_mix, "unpriced": unpriced, "rfq": rfq, "lines_in_scope": len(lines_in_scope),
    }


def tab_json(t: Tab, view: str, is_comb: bool) -> dict:
    secs = []
    for s in t.sections + ([t.shared_section] if t.shared_section else []):
        secs.append({"id": s.id, "name": s.name, "count": len(s.lines), "isShared": s.shared,
                     "sub": str(s.total), "subF": fmt(s.total), "lines": [l.to_json() for l in s.lines],
                     "excluded": bool(s.shared and is_comb)})
    is_sys = t.key in SYSTEM_KEYS
    return {"key": t.key, "name": tab_name(t.key), "color": tab_color(t.key), "isSystem": is_sys,
            "combined": str(t.combined), "standalone": str(t.standalone), "combinedF": fmt(t.combined),
            "standaloneF": fmt(t.standalone), "sections": secs}


def all_lines(boq: dict, include_excluded=False) -> list[Line]:
    out = []
    for k, t in boq["tabs"].items():
        out += [l for s in t.sections for l in s.lines]
        if t.shared_section and (include_excluded or not boq["combined"]):
            out += t.shared_section.lines
    return out
