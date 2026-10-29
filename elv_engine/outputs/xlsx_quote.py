"""Client quotation workbook (openpyxl) with live formulas.

Line totals are =ROUND(Qty × Unit price, 2); section subtotals, tab totals and the
summary are SUM formulas referencing those cells, so editing a quantity or unit price
in Excel updates every total. Unit prices are the engine's sell prices (QAR, 2 dp);
the cost build-up lives in the internal costing workbook.
"""
from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..money import amount_in_words
from ..systems import SYSTEM_KEYS
from .common import client_tabs, company_lines, dstr, quote_date, rev_label, section_title, system_name, tab_sections, valid_until

NAVY = "1F3B70"
TH = PatternFill("solid", fgColor="D9E1F2")
SEC = PatternFill("solid", fgColor="F4F6FA")
TOT = PatternFill("solid", fgColor="E9EDF3")
BUD = PatternFill("solid", fgColor="FFF7E0")
THIN = Side(style="thin", color="D5DBE6")
B = Border(bottom=THIN)
MONEY = '#,##0.00;[Red]-#,##0.00'
QTY = '#,##0.##'


def _sheet_name(name: str, used: set[str]) -> str:
    n = name.replace("/", "-").replace("\\", "-").replace("?", "").replace("*", "").replace("[", "(").replace("]", ")").replace(":", "-")[:31]
    base, i = n, 2
    while n in used:
        n = f"{base[:28]} {i}"
        i += 1
    used.add(n)
    return n


def _head(ws, project: dict, company: dict, title: str) -> int:
    ws["A1"] = company.get("name") or "Quotation"
    ws["A1"].font = Font(bold=True, size=14, color=NAVY)
    r = 2
    for line in company_lines(company)[:3]:
        ws.cell(row=r, column=1, value=line).font = Font(size=9, color="5E6A7D")
        r += 1
    r += 1
    ws.cell(row=r, column=1, value=title).font = Font(bold=True, size=12, color="14254A")
    info = project["info"]
    meta = [("Project", info.get("name", "")), ("Client", info.get("client", "")), ("Reference", f"{info.get('ref', '')}  {rev_label(project)}"),
            ("Date", dstr(quote_date(project)))]
    r += 1
    for k, v in meta:
        ws.cell(row=r, column=1, value=k).font = Font(size=9, color="5E6A7D")
        ws.cell(row=r, column=2, value=v).font = Font(size=9)
        r += 1
    return r + 1


def build(path: str, project: dict, res, company: dict, standalone_system: str | None = None) -> dict:
    """Write the quotation workbook. Returns the cell addresses of totals (for tests)."""
    boq = res.boq
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    used = {"Summary"}
    totals: dict[str, str] = {}
    tabs = [standalone_system] if standalone_system else client_tabs(boq, res.selected)
    standalone = bool(standalone_system) or not boq["combined"]

    for key in tabs:
        secs = tab_sections(boq, key, standalone=standalone)
        if not secs:
            continue
        name = _sheet_name(system_name(key) if key in SYSTEM_KEYS else {"shared": "Shared infrastructure", "network": "Network Active", "optional": "Optional"}[key], used)
        ws = wb.create_sheet(name)
        r = _head(ws, project, company, system_name(key))
        heads = ["No.", "Description", "Manufacturer", "Part No.", "Unit", "Qty", "Unit price (QAR)", "Total (QAR)", "Note"]
        widths = [7, 58, 20, 20, 7, 10, 16, 17, 24]
        for c, (h, w) in enumerate(zip(heads, widths), 1):
            cell = ws.cell(row=r, column=c, value=h)
            cell.font = Font(bold=True, size=9, color="14254A")
            cell.fill = TH
            cell.alignment = Alignment(horizontal="right" if c in (6, 7, 8) else "left", vertical="center")
            ws.column_dimensions[get_column_letter(c)].width = w
        ws.freeze_panes = ws.cell(row=r + 1, column=1)
        r += 1
        sub_cells = []
        for si, sec in enumerate(secs, 1):
            c = ws.cell(row=r, column=1, value=f"{si}")
            ws.cell(row=r, column=2, value=section_title(sec))
            for col in range(1, 10):
                ws.cell(row=r, column=col).fill = SEC
                ws.cell(row=r, column=col).font = Font(bold=True, size=9, color="14254A")
            r += 1
            first = r
            for li, l in enumerate(sec.lines, 1):
                ws.cell(row=r, column=1, value=f"{si}.{li}").font = Font(size=9, color="5E6A7D")
                ws.cell(row=r, column=2, value=l.description)
                ws.cell(row=r, column=3, value=l.manufacturer)
                ws.cell(row=r, column=4, value=l.part_no)
                ws.cell(row=r, column=5, value=l.unit)
                q = ws.cell(row=r, column=6, value=float(l.qty))
                q.number_format = QTY
                u = ws.cell(row=r, column=7, value=float(l.unit_qar) if l.unit_qar is not None else None)
                u.number_format = MONEY
                t = ws.cell(row=r, column=8, value=f"=ROUND(F{r}*G{r},2)")
                t.number_format = MONEY
                note = "Budgetary — RFQ required" if l.budget else ("Price to be advised" if l.unit_qar is None else "")
                ws.cell(row=r, column=9, value=note)
                for col in range(1, 10):
                    cell = ws.cell(row=r, column=col)
                    cell.border = B
                    if col not in (1,):
                        cell.font = Font(size=9)
                    if l.budget:
                        cell.fill = BUD
                ws.cell(row=r, column=2).alignment = Alignment(wrap_text=True, vertical="top")
                r += 1
            last = r - 1
            ws.cell(row=r, column=2, value=f"Subtotal — {section_title(sec)}").font = Font(bold=True, size=9)
            st = ws.cell(row=r, column=8, value=f"=SUM(H{first}:H{last})" if last >= first else 0)
            st.number_format = MONEY
            st.font = Font(bold=True, size=9)
            sub_cells.append(f"H{r}")
            r += 2
        label = f"{system_name(key)} — {'standalone' if (standalone and key in SYSTEM_KEYS) else 'total'}"
        ws.cell(row=r, column=2, value=label.upper()).font = Font(bold=True, size=10, color="14254A")
        tc = ws.cell(row=r, column=8, value="=" + "+".join(sub_cells) if sub_cells else 0)
        tc.number_format = MONEY
        tc.font = Font(bold=True, size=10, color="14254A")
        for col in range(1, 10):
            ws.cell(row=r, column=col).fill = TOT
            ws.cell(row=r, column=col).border = Border(top=Side(style="medium", color=NAVY))
        totals[key] = f"'{name}'!H{r}"
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToHeight = 0

    # ---------------- Summary
    ws = summary
    r = _head(ws, project, company, "QUOTATION — PRICE SUMMARY")
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 36
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 20
    ws.cell(row=r - 1, column=1, value=f"Valid until {dstr(valid_until(project))}").font = Font(size=9, color="5E6A7D")
    hdr = ["Description", "", "Amount (QAR)"]
    for c, h in enumerate(hdr, 1):
        cell = ws.cell(row=r, column=c, value=h)
        cell.font = Font(bold=True, size=10, color="14254A")
        cell.fill = TH
    r += 1
    base_rows = []
    sys_keys = [k for k in tabs if k in SYSTEM_KEYS and k in totals]
    for k in sys_keys:
        ws.cell(row=r, column=1, value=system_name(k))
        c = ws.cell(row=r, column=3, value=f"={totals[k]}")
        c.number_format = MONEY
        base_rows.append(r)
        r += 1
    if not standalone and "shared" in totals:
        ws.cell(row=r, column=1, value="Shared infrastructure (racks, UPS, backbone, containment)")
        c = ws.cell(row=r, column=3, value=f"={totals['shared']}")
        c.number_format = MONEY
        base_rows.append(r)
        r += 1
    ws.cell(row=r, column=1, value="TOTAL BASE PRICE (QAR)").font = Font(bold=True, size=11, color="14254A")
    bt = ws.cell(row=r, column=3, value="=" + "+".join(f"C{x}" for x in base_rows) if base_rows else 0)
    bt.number_format = MONEY
    bt.font = Font(bold=True, size=11, color="14254A")
    for col in range(1, 4):
        ws.cell(row=r, column=col).fill = TOT
        ws.cell(row=r, column=col).border = Border(top=Side(style="medium", color=NAVY))
    totals["base"] = f"Summary!C{r}"
    r += 1
    base_val = boq["tabs"][standalone_system].standalone if standalone_system else boq["totals"]["base"]
    ws.cell(row=r, column=1, value=amount_in_words(base_val)).font = Font(italic=True, size=9, color="3D475A")
    r += 2
    if not standalone_system:
        for key, label in (("network", "Network Active equipment (quoted separately, not in base total)"),
                           ("optional", "Optional items (client to confirm, not in base total)")):
            if key in totals:
                ws.cell(row=r, column=1, value=label)
                c = ws.cell(row=r, column=3, value=f"={totals[key]}")
                c.number_format = MONEY
                totals[key + "_summary"] = f"Summary!C{r}"
                r += 1
        if boq["combined"]:
            r += 1
            for c, h in enumerate(["Standalone vs combined award", "", "Standalone (QAR)", "Combined (QAR)"], 1):
                cell = ws.cell(row=r, column=c, value=h)
                cell.font = Font(bold=True, size=9, color="14254A")
                cell.fill = TH
            r += 1
            first = r
            for k in sys_keys:
                ws.cell(row=r, column=1, value=system_name(k))
                ws.cell(row=r, column=3, value=float(boq["tabs"][k].standalone)).number_format = MONEY
                ws.cell(row=r, column=4, value=f"={totals[k]}").number_format = MONEY
                r += 1
            ws.cell(row=r, column=1, value="Shared infrastructure")
            ws.cell(row=r, column=4, value=f"={totals['shared']}" if "shared" in totals else 0).number_format = MONEY
            r += 1
            ws.cell(row=r, column=1, value="Base total").font = Font(bold=True)
            ws.cell(row=r, column=3, value=f"=SUM(C{first}:C{r - 1})").number_format = MONEY
            ws.cell(row=r, column=4, value=f"=SUM(D{first}:D{r - 1})").number_format = MONEY
            r += 1
            ws.cell(row=r, column=1, value="Saving with combined award").font = Font(bold=True, color="1E7D46")
            sv = ws.cell(row=r, column=4, value=f"=C{r - 1}-D{r - 1}")
            sv.number_format = MONEY
            sv.font = Font(bold=True, color="1E7D46")
            totals["saving"] = f"Summary!D{r}"
            r += 1

    # ---------------- Terms
    tw = wb.create_sheet(_sheet_name("Terms", used))
    tw.column_dimensions["A"].width = 6
    tw.column_dimensions["B"].width = 120
    from ..texts import render_terms
    rr = 1
    texts = project.get("texts", {})
    blocks = [("ASSUMPTIONS", texts.get("assumptions", [])), ("EXCLUSIONS", texts.get("exclusions", [])),
              ("CLARIFICATIONS REQUIRED (RFIs)", texts.get("rfis", [])),
              ("TERMS & CONDITIONS", render_terms(texts.get("terms", []), project.get("commercial", {}),
                                                  int(project["info"].get("validity_days") or 30)))]
    for title, items in blocks:
        tw.cell(row=rr, column=1, value=title).font = Font(bold=True, color="14254A")
        rr += 1
        for i, t in enumerate(items, 1):
            tw.cell(row=rr, column=1, value=i)
            c = tw.cell(row=rr, column=2, value=t)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            rr += 1
        rr += 1
    wb.active = 0
    wb.properties.title = f"{project['info'].get('name', '')} — Quotation {rev_label(project)}"
    wb.properties.creator = company.get("name") or "ELV Estimator"
    wb.save(path)
    return totals
