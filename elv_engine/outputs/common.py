"""Shared helpers for the output generators."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from ..money import ZERO, fmt
from ..systems import BY_KEY, SYSTEM_KEYS, TAB_ORDER, tab_name

_REPL = {"≤": "<=", "≥": ">=", "→": "->", "⇄": "", "≈": "~", "✓": "OK", "✗": "X", "•": "-", "″": '"', "′": "'",
         "−": "-", " ": " ", "₹": "INR ", "₱": "PHP ", "₩": "KRW ", "₺": "TRY ", "₽": "RUB ", "৳": "BDT "}


def safe(text) -> str:
    """Text safe for the built-in PDF fonts (WinAnsi)."""
    s = str(text if text is not None else "")
    for a, b in _REPL.items():
        s = s.replace(a, b)
    return s.encode("cp1252", "replace").decode("cp1252")


def file_ref(project: dict) -> str:
    ref = project["info"].get("ref") or project["info"].get("name") or "Quotation"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", ref).strip("-")[:60] or "Quotation"


def rev_label(project: dict) -> str:
    return f"Rev {project['revision']['current']}"


def quote_date(project: dict) -> date:
    try:
        return datetime.strptime(project["info"].get("date", "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def valid_until(project: dict) -> date:
    return quote_date(project) + timedelta(days=int(project["info"].get("validity_days") or 30))


def dstr(d: date) -> str:
    return d.strftime("%d %B %Y")


def client_tabs(boq: dict, selected: list[str]) -> list[str]:
    """Tabs shown on the complete quotation, in order."""
    return [k for k in TAB_ORDER if k in boq["tabs"] and (k in selected or k in ("shared", "network", "optional"))]


def tab_sections(boq: dict, key: str, standalone: bool = False):
    """Sections to print for a tab. Standalone prints the system's own infrastructure too."""
    t = boq["tabs"][key]
    secs = [s for s in t.sections if s.lines]
    if standalone and t.shared_section and t.shared_section.lines:
        secs.append(t.shared_section)
    elif not boq["combined"] and t.shared_section and t.shared_section.lines:
        secs.append(t.shared_section)
    return secs


def tab_total(boq: dict, key: str, standalone: bool = False) -> Decimal:
    t = boq["tabs"][key]
    if key in SYSTEM_KEYS and (standalone or not boq["combined"]):
        return t.standalone
    return t.combined


def section_title(sec) -> str:
    return "System infrastructure (racks, UPS, network, cabling)" if sec.shared else sec.name


def company_lines(company: dict) -> list[str]:
    out = []
    if company.get("address"):
        out += [l.strip() for l in str(company["address"]).splitlines() if l.strip()]
    contact = " · ".join(x for x in (company.get("phone"), company.get("email"), company.get("website")) if x)
    if contact:
        out.append(contact)
    if company.get("cr"):
        out.append(f"CR {company['cr']}")
    return out


def system_name(key: str) -> str:
    return BY_KEY[key].full if key in BY_KEY else tab_name(key)


def money(v) -> str:
    return fmt(v if v is not None else ZERO)
