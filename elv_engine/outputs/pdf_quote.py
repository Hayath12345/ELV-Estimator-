"""Quotation PDFs (reportlab): complete quotation, per-system quotations and the
combined summary. A4 portrait, company header, numbered footer "Page x of y".
"""
from __future__ import annotations

from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from ..money import ZERO, amount_in_words, fmt, fmt_qty
from ..systems import SYSTEM_KEYS
from ..texts import render_terms
from .common import (client_tabs, company_lines, dstr, quote_date, rev_label, safe, section_title, system_name,
                     tab_sections, tab_total, valid_until)

NAVY = colors.HexColor("#1F3B70")
INK = colors.HexColor("#14254A")
TH = colors.HexColor("#D9E1F2")
SEC = colors.HexColor("#F4F6FA")
LINE = colors.HexColor("#D5DBE6")
MUTED = colors.HexColor("#5E6A7D")
OK = colors.HexColor("#1E7D46")
BUD = colors.HexColor("#FFF7E0")

S = {
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13.5),
    "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8, leading=10.5, textColor=MUTED),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=9.6),
    "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.2, leading=9.8, textColor=INK),
    "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=INK, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=INK, spaceBefore=8, spaceAfter=5),
    "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=INK, spaceBefore=6, spaceAfter=3),
    "right": ParagraphStyle("right", fontName="Helvetica", fontSize=8, leading=9.6, alignment=TA_RIGHT),
    "li": ParagraphStyle("li", fontName="Helvetica", fontSize=9, leading=12.5, leftIndent=14, firstLineIndent=-14, spaceAfter=2),
}


def P(text, style="cell") -> Paragraph:
    t = safe(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(t, S[style])


class _Doc:
    def __init__(self, path, project, company, title):
        self.path, self.project, self.company, self.title = path, project, company, title

    def header_footer(self, c: rl_canvas.Canvas, doc):
        W, H = A4
        c.saveState()
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(18 * mm, H - 14 * mm, safe(self.company.get("name") or ""))
        c.setFont("Helvetica", 7.5)
        c.setFillColor(MUTED)
        y = H - 18 * mm
        for line in company_lines(self.company)[:2]:
            c.drawString(18 * mm, y, safe(line)[:110])
            y -= 3.4 * mm
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(W - 18 * mm, H - 14 * mm, safe(self.title))
        c.setFont("Helvetica", 8)
        c.setFillColor(MUTED)
        c.drawRightString(W - 18 * mm, H - 18 * mm, safe(f"{self.project['info'].get('ref', '')}  ·  {rev_label(self.project)}"))
        c.setStrokeColor(NAVY)
        c.setLineWidth(1.2)
        c.line(18 * mm, H - 26 * mm, W - 18 * mm, H - 26 * mm)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.line(18 * mm, 14 * mm, W - 18 * mm, 14 * mm)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(MUTED)
        c.drawString(18 * mm, 9.5 * mm, safe(f"{self.project['info'].get('name', '')}  ·  {dstr(quote_date(self.project))}"))
        c.restoreState()


def _numbered(total_label="Page"):
    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            n = len(self._saved)
            for st in self._saved:
                self.__dict__.update(st)
                self.setFont("Helvetica", 7.5)
                self.setFillColor(MUTED)
                self.drawRightString(A4[0] - 18 * mm, 9.5 * mm, f"{total_label} {self._pageNumber} of {n}")
                super().showPage()
            super().save()
    return NumberedCanvas


def _table(rows, widths, header_rows=1, styles=None) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=header_rows)
    base = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), TH),
        ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), INK),
        ("FONT", (0, 0), (-1, header_rows - 1), "Helvetica-Bold", 8),
        ("LINEBELOW", (0, header_rows), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    t.setStyle(TableStyle(base + (styles or [])))
    return t


def _signoff(project) -> Table:
    so = project.get("signoff", {})
    rows = [["", "Name", "Role", "Date"]]
    for step in ("prepared", "checked", "approved"):
        s = so.get(step, {})
        at = s.get("at")
        when = datetime.fromisoformat(at).strftime("%d %b %Y") if at else ""
        rows.append([step.capitalize(), P(s.get("name", "")), P(s.get("role", "")), when])
    return _table(rows, [28 * mm, 60 * mm, 60 * mm, 26 * mm], styles=[("FONT", (0, 1), (0, -1), "Helvetica-Bold", 8)])


def _cover(project, res, company, systems: list[str], base, standalone: bool, network=None, optional=None, subject=None):
    info = project["info"]
    story = []
    meta = [["Date", dstr(quote_date(project)), "Our ref.", f"{info.get('ref', '')}  {rev_label(project)}"],
            ["To", info.get("client", ""), "Valid until", dstr(valid_until(project))],
            ["Attention", info.get("attention", ""), "PMC", info.get("pmc", "")],
            ["Project", info.get("name", ""), "Consultant", info.get("consultant", "")]]
    mt = Table([[P(a, "cellb"), P(b), P(c, "cellb"), P(d)] for a, b, c, d in meta], colWidths=[22 * mm, 66 * mm, 24 * mm, 62 * mm])
    mt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story += [mt, Spacer(1, 6 * mm)]
    sys_names = ", ".join(system_name(s) for s in systems)
    subj = subject or info.get("subject") or f"Quotation for the supply, installation, testing and commissioning of ELV systems — {sys_names}"
    story.append(P(f"Subject: {subj}", "h2"))
    scope = ", ".join(x for x in (info.get("scope"), info.get("location")) if x)
    refs = info.get("drawing_refs") or ", ".join(d.get("file", "") for d in project.get("drawings", []))
    story.append(P("Dear Sir / Madam,", "body"))
    story.append(Spacer(1, 2 * mm))
    story.append(P(f"We are pleased to submit our {'combined ' if (len(systems) > 1 and not standalone) else ''}quotation for "
                   f"the {sys_names} works{(' at ' + scope) if scope else ''}. Quantities are measured from the drawings "
                   f"{refs} and the device layout, comms-room design and assumptions enclosed. The price summary below is "
                   f"in Qatari Riyals and is detailed in the bill of quantities that follows.", "body"))
    story.append(Spacer(1, 4 * mm))
    rows = [["Description", "Amount (QAR)"]]
    for s in systems:
        rows.append([P(system_name(s)), P(fmt(tab_total(res.boq, s, standalone)), "right")])
    if not standalone and "shared" in res.boq["tabs"] and len(systems) > 1:
        rows.append([P("Shared infrastructure (racks, UPS, backbone, containment)"), P(fmt(res.boq["tabs"]["shared"].combined), "right")])
    rows.append([P("TOTAL BASE PRICE", "cellb"), P(fmt(base), "right")])
    styles = [("BACKGROUND", (0, len(rows) - 1), (-1, len(rows) - 1), SEC), ("LINEABOVE", (0, len(rows) - 1), (-1, len(rows) - 1), 1, NAVY),
              ("FONT", (0, len(rows) - 1), (-1, len(rows) - 1), "Helvetica-Bold", 9)]
    if network:
        rows.append([P("Network Active equipment — quoted separately, not included in the base price"), P(fmt(network), "right")])
    if optional:
        rows.append([P("Optional items — client to confirm, not included in the base price"), P(fmt(optional), "right")])
    story.append(_table(rows, [130 * mm, 44 * mm], styles=styles))
    story.append(Spacer(1, 2 * mm))
    story.append(P(f"Amount in words: {amount_in_words(base)}.", "small"))
    story.append(Spacer(1, 5 * mm))
    com = project.get("commercial", {})
    story.append(P(f"Validity: {info.get('validity_days', 30)} days. Payment: {com.get('payment_terms', '')}. "
                   f"Delivery: {com.get('delivery', '')}. Warranty: {com.get('warranty', '')}.", "body"))
    story.append(Spacer(1, 3 * mm))
    story.append(P("We trust our offer meets your requirements and remain at your disposal for any clarification.", "body"))
    story.append(Spacer(1, 3 * mm))
    story.append(P("Yours faithfully,", "body"))
    story.append(P(company.get("name") or "", "cellb"))
    story.append(Spacer(1, 5 * mm))
    story.append(KeepTogether([P("Approval", "h3"), _signoff(project)]))
    return story


def _boq_tables(res, keys: list[str], standalone: bool, numbering_start=1):
    story = []
    boq = res.boq
    any_budget = False
    for n, key in enumerate(keys, numbering_start):
        secs = tab_sections(boq, key, standalone=standalone)
        if not secs:
            continue
        story.append(CondPageBreak(60 * mm))
        label = system_name(key) if key in SYSTEM_KEYS else {"shared": "Shared infrastructure", "network": "Network Active (quoted separately)",
                                                            "optional": "Optional items (client to confirm)"}[key]
        story.append(P(f"{n}. {label}", "h2"))
        rows = [["No.", "Description", "Manufacturer", "Part No.", "Unit", "Qty", "Unit price", "Total (QAR)"]]
        styles = []
        for si, sec in enumerate(secs, 1):
            rows.append(["", P(section_title(sec), "cellb"), "", "", "", "", "", ""])
            styles += [("BACKGROUND", (0, len(rows) - 1), (-1, len(rows) - 1), SEC), ("SPAN", (1, len(rows) - 1), (4, len(rows) - 1))]
            for li, l in enumerate(sec.lines, 1):
                desc = l.description + (" †" if l.budget else "")
                unit = fmt(l.unit_qar) if l.unit_qar is not None else "TBA"
                rows.append([f"{n}.{si}.{li}", P(desc), P(l.manufacturer), P(l.part_no), l.unit, fmt_qty(l.qty), unit, fmt(l.total)])
                if l.budget:
                    any_budget = True
                    styles.append(("BACKGROUND", (0, len(rows) - 1), (-1, len(rows) - 1), BUD))
            rows.append(["", P(f"Subtotal — {section_title(sec)}", "cellb"), "", "", "", "", "", fmt(sec.total)])
            styles += [("FONT", (7, len(rows) - 1), (7, len(rows) - 1), "Helvetica-Bold", 8), ("SPAN", (1, len(rows) - 1), (6, len(rows) - 1))]
        total = tab_total(boq, key, standalone)
        rows.append(["", P(f"TOTAL — {label}", "cellb"), "", "", "", "", "", fmt(total)])
        styles += [("SPAN", (1, len(rows) - 1), (6, len(rows) - 1)), ("LINEABOVE", (0, len(rows) - 1), (-1, len(rows) - 1), 1, NAVY),
                   ("FONT", (7, len(rows) - 1), (7, len(rows) - 1), "Helvetica-Bold", 8.5),
                   ("ALIGN", (4, 1), (-1, -1), "RIGHT"), ("ALIGN", (4, 0), (-1, 0), "RIGHT"), ("FONT", (0, 1), (0, -1), "Helvetica", 7)]
        story.append(_table(rows, [13 * mm, 63 * mm, 24 * mm, 25 * mm, 9 * mm, 12 * mm, 17 * mm, 19 * mm], styles=styles))
    if any_budget:
        story.append(Spacer(1, 2 * mm))
        story.append(P("† Budgetary price — subject to supplier confirmation (RFQ) before order.", "small"))
    return story


def _texts(project):
    texts = project.get("texts", {})
    story = [PageBreak(), P("Assumptions, exclusions and terms", "h1")]
    terms = render_terms(texts.get("terms", []), project.get("commercial", {}), int(project["info"].get("validity_days") or 30))
    for title, items in (("Assumptions", texts.get("assumptions", [])), ("Exclusions", texts.get("exclusions", [])),
                         ("Clarifications required (RFIs)", texts.get("rfis", [])), ("Terms & conditions", terms)):
        if not items:
            continue
        story.append(P(title, "h2"))
        for i, t in enumerate(items, 1):
            story.append(P(f"{i}.&nbsp;&nbsp;{safe(t)}".replace("&nbsp;", " "), "li"))
    return story


def _build(path, project, company, title, story):
    d = _Doc(path, project, company, title)
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=31 * mm, bottomMargin=19 * mm,
                            title=safe(f"{project['info'].get('name', '')} — {title}"), author=safe(company.get("name") or "ELV Estimator"))
    doc.build(story, onFirstPage=d.header_footer, onLaterPages=d.header_footer, canvasmaker=_numbered())


def build_complete(path: str, project: dict, res, company: dict) -> None:
    boq = res.boq
    t = boq["totals"]
    standalone = not boq["combined"]
    story = [P("Quotation", "h1")]
    story += _cover(project, res, company, res.selected, t["base"], standalone,
                    network=t["network"] if "network" in boq["tabs"] else None,
                    optional=t["optional"] if boq["tabs"]["optional"].combined else None)
    if boq["combined"]:
        story += [PageBreak(), P("Price summary — standalone vs combined award", "h1")]
        rows = [["System", "Standalone (QAR)", "Combined (QAR)"]]
        for s in res.selected:
            rows.append([P(system_name(s)), fmt(t["systems"][s]["standalone"]), fmt(t["systems"][s]["combined"])])
        rows.append([P("Shared infrastructure"), "—", fmt(t["shared"])])
        rows.append([P("Base total", "cellb"), fmt(t["standalone"]), fmt(t["combined"])])
        rows.append([P("Saving with combined award", "cellb"), "", fmt(t["saving"])])
        n = len(rows)
        story.append(_table(rows, [94 * mm, 40 * mm, 40 * mm], styles=[
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("LINEABOVE", (0, n - 2), (-1, n - 2), 1, NAVY),
            ("FONT", (0, n - 2), (-1, -1), "Helvetica-Bold", 8.5), ("TEXTCOLOR", (0, n - 1), (-1, n - 1), OK)]))
        story.append(Spacer(1, 3 * mm))
        story.append(P("In a combined award racks, UPS, ELV network switches, backbone and containment are designed and priced "
                       "once (Shared infrastructure) instead of separately for each system.", "small"))
    story += [PageBreak(), P("Bill of quantities", "h1")]
    story += _boq_tables(res, client_tabs(boq, res.selected), standalone)
    story += _texts(project)
    _build(path, project, company, "QUOTATION", story)


def build_system(path: str, project: dict, res, company: dict, key: str) -> None:
    tab = res.boq["tabs"][key]
    story = [P(f"Quotation — {system_name(key)}", "h1")]
    story += _cover(project, res, company, [key], tab.standalone, True,
                    subject=f"Quotation for {system_name(key)} (standalone award)")
    story += [PageBreak(), P("Bill of quantities", "h1")]
    story += _boq_tables(res, [key], standalone=True)
    story += _texts(project)
    _build(path, project, company, f"QUOTATION — {system_name(key).upper()}", story)


def build_summary(path: str, project: dict, res, company: dict) -> None:
    boq = res.boq
    t = boq["totals"]
    info = project["info"]
    story = [P("Combined summary", "h1"),
             P(f"{info.get('name', '')} · {info.get('client', '')} · {info.get('ref', '')} {rev_label(project)} · {dstr(quote_date(project))}", "small"),
             Spacer(1, 5 * mm)]
    rows = [["System", "Quantities from layout", "Standalone (QAR)", "Combined (QAR)"]]
    q = res.qres["info"]
    desc = {
        "cctv": lambda i: f"{i.get('cameras', 0)} cameras · {i.get('retention', 0):.0f} days · {i.get('storage_tb', 0):.0f} TB",
        "access": lambda i: f"{i.get('doors', 0)} doors · {i.get('readers', 0)} readers · {i.get('controllers', 0)} controllers",
        "iptv": lambda i: f"{i.get('tvs', 0)} displays",
        "cabling": lambda i: f"{i.get('outlets', 0)} outlets incl. {i.get('aps', 0)} Wi-Fi APs",
        "intercom": lambda i: f"{i.get('devices', 0)} devices",
        "intrusion": lambda i: f"{i.get('devices', 0)} devices · {i.get('zones', 0)} zones",
    }
    for s in res.selected:
        rows.append([P(system_name(s)), P(desc[s](q.get(s, {}))), fmt(t["systems"][s]["standalone"]),
                     fmt(t["systems"][s]["combined"]) if boq["combined"] else "—"])
    if boq["combined"]:
        rows.append([P("Shared infrastructure"), P("Racks, UPS, ELV switches, backbone, containment"), "—", fmt(t["shared"])])
    rows.append([P("Base total", "cellb"), "", fmt(t["standalone"]), fmt(t["combined"]) if boq["combined"] else "—"])
    if boq["combined"]:
        rows.append([P("Saving with combined award", "cellb"), "", "", fmt(t["saving"])])
    rows.append([P("Network Active (separate)"), "", "", fmt(t["network"])])
    rows.append([P("Optional items (not in base)"), "", "", fmt(t["optional"])])
    story.append(_table(rows, [48 * mm, 70 * mm, 28 * mm, 28 * mm], styles=[("ALIGN", (2, 0), (-1, -1), "RIGHT")]))
    story.append(Spacer(1, 6 * mm))
    rooms = [["Comms room", "Floor", "Devices", "PoE load / budget", "UPS runtime", "Racks"]]
    for rs in res.sizing["rooms"]:
        rooms.append([P(rs.name), rs.floor_name, str(sum(rs.served.values())), f"{rs.poe_load_w:,.0f} / {rs.poe_budget_w:,.0f} W",
                      f"{rs.runtime_min:.0f} min" if rs.ups else "—", str(len(rs.racks))])
    story += [P("Comms rooms", "h2"), _table(rooms, [50 * mm, 16 * mm, 18 * mm, 40 * mm, 26 * mm, 24 * mm])]
    story.append(Spacer(1, 6 * mm))
    story.append(P(f"Checks: {res.checks['passed']} / {res.checks['total']} passed.", "small"))
    _build(path, project, company, "COMBINED SUMMARY", story)
