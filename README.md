# ELV Estimator

Windows desktop app that turns AutoCAD floor plans (DWG, DXF or vector PDF) into complete,
ready-to-send quotations for six ELV systems — **CCTV incl. MDF/IDF, Access Control,
Smart TV / IPTV, Structured Cabling, Intercom, Intrusion** — per system or as a combined award.

The UI follows Claude Design direction **1a "Enterprise Ledger"** (spreadsheet-first, navy
sidebar, six-step stepper).

## Workflow

1. **Drawings** — drop DWG/DXF/PDF files. Rooms (name + boundary), door blocks/tags,
   furniture blocks (work positions), grid lines and scale are extracted, with confidence and
   warning states. Calibrate scale with two clicks (snaps to grid lines). Review room
   categories and mark MDF/IDF rooms.
2. **Systems** — choose any of the six or all six (combined award); edit design parameters
   (retention, pixel-density targets, lock type, TV size rules, outlet and Wi-Fi rules, etc.).
3. **Device Layout** — rule-based placement per system on the plan; drag, add, delete,
   change type/target/direction; cable routes to the nearest MDF/IDF via corridor spines;
   links over 90 m flagged. Edits are saved in `project.json` and survive parameter changes.
4. **Comms Rooms** — per room: ports, PoE load vs budget, switches, patch panels, UPS and
   battery runtime, interactive 42U rack elevations (reserve U).
5. **BOQ & Pricing** — tabs per system + Shared infrastructure + Network Active + Optional;
   edit quantity, list price, currency and discount inline; confidence badges, Budgetary rows
   flagged *RFQ required*; markup, duty, freight, FX, labour rates; live standalone vs combined.
6. **Checks & Export** — reconciliation checks (layout vs BOQ, PoE, ports, storage, licences,
   UPS, rack fill, link length, pricing, totals). *Issue* is blocked while a blocking check
   fails unless an override reason is recorded. Generates the outputs below into the project's
   `outputs/Rev<n>/` folder and opens it.

**Price Library** lists every device, software, licence, accessory, infrastructure item,
service lot and labour rate the engine can use, each with a **price box and a currency
drop-down (40 popular currencies)**, source, date checked and confidence. Prices are entered
once and used by every quotation; CSV import (with preview) and export are included.
Exchange rates to QAR are editable in Settings (library default) and per quotation.

### Outputs

| File | Content |
|---|---|
| `…_Quotation.pdf` | cover letter, price summary, standalone vs combined, BOQ, assumptions, exclusions, RFIs, terms, Prepared/Checked/Approved |
| `…_Quotation.xlsx` | same BOQ with live formulas (line = ROUND(qty × unit), SUM subtotals and summary) |
| `…_<SYS>_Quotation.pdf` | per-system quotations at standalone pricing |
| `…_Combined_Summary.pdf` | systems, quantities, comms rooms, checks |
| `…_Layouts.pdf` | A1 layouts per floor (all systems + one page per system) at a standard scale, legend, title block |
| `…_Rack_Elevations.pdf` | every rack from the comms-room design |
| `…_Internal_Costing.xlsx` | internal only: inputs (markup, duty, freight, FX), full cost/sell build-up as formulas, margins, reconciliation |
| `…_Package.zip` | client files (internal costing excluded) |

The client quotation shows quantities, unit prices and totals only; list prices, discounts and
markup appear only in the internal costing workbook.

## Pricing formula (QAR, 2 decimals)

```
imported item:  list × FX × (1 − discount) × (1 + duty) × (1 + freight) × (1 + markup)
local (QAR):    list × (1 − discount) × (1 + markup)
labour:         rate × (1 + labour markup)
unit price rounded half-up to 2 dp; line total = round(unit × qty, 2)
```

## Project layout

```
app/            desktop shell: pywebview window, js_api bridge, backend (view models, jobs), local UI server, self-test
elv_engine/     calculation engine
  extract/      DWG (LibreDWG dwgread → DXF), DXF (ezdxf), PDF (PyMuPDF); classification, units/scale
  layout/       floor model, rule-based placement, orthogonal routing
  comms.py      comms-room sizing and rack packing
  quantities.py, boq.py, pricing.py, checks.py, pricelib.py (SQLite), project.py (project.json)
  outputs/      PDF/XLSX quotations, layouts, racks, costing, package
ui/             React + TypeScript + Vite (design tokens as CSS variables, fonts bundled)
packaging/      PyInstaller spec, Inno Setup script, icon
scripts/        fetch_libredwg.py (downloads the LibreDWG Windows release at build time)
vendor/libredwg COPYING + README (binaries are fetched into bin/, not committed)
tests/          pytest: engine, extraction, placement, golden totals, backend API, outputs, DWG round trip
```

Each project is a folder (default `Documents\ELV Estimator\Projects\<name>`) with
`project.json`, `drawings/`, `cache/` and `outputs/`. The price library and settings live in
`%APPDATA%\ELV Estimator`.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cd ui && npm ci && npm run build && cd ..
python -m pytest
python -m app.main --dev --port 8765     # open http://127.0.0.1:8765 in a browser
python -m app.main --selftest            # headless end-to-end check
```

`python -m elv_engine.samples OUTDIR` writes two sample floor plans (DXF); the empty dashboard
also offers **Open sample project**.

## Building the installer (Windows)

```powershell
cd ui; npm ci; npm run build; cd ..
pip install -r requirements-dev.txt
python scripts/fetch_libredwg.py
pyinstaller packaging/elv_estimator.spec --noconfirm --clean
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" packaging\installer.iss   # -> dist\ELV-Estimator-Setup.exe
```

The GitHub Actions workflow (`.github/workflows/build.yml`, windows-latest) does all of this
on every push: builds the UI, runs the tests (including the DWG round trip with the real
LibreDWG binaries), freezes the app, runs the frozen self-test, builds the installer and
uploads `ELV-Estimator-Setup` and the self-test outputs as artifacts.

The app runs fully offline. It needs the Microsoft Edge WebView2 Runtime, which ships with
Windows 11.

## Status and known limits

- The verified engine (`elv-engine/`) and the Es'hailSat fixtures referenced in the brief
  were not available, so the calculation engine was written from the brief and the design.
  The golden Es'hailSat totals therefore cannot be reproduced yet; the regression test runs
  on a synthetic two-floor project instead (`tests/golden/sample_totals.json`). When the
  original engine and fixtures are added, its rules and constants can replace these modules
  and the Es'hailSat golden test can be added.
- Manufacturers and part numbers in the catalogue are editable defaults taken from the
  design; prices are blank until entered or imported.
- Placement is rule-based on room names and areas; review the layout before issue.
- See `THIRD_PARTY_NOTICES.md` for licences (LibreDWG is GPL-3.0 as a separate program;
  PyMuPDF is AGPL-3.0 or commercial).
