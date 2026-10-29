"""Price library (SQLite): one row per catalogue item with the user's list price,
currency, discount, source, date checked and confidence; exchange rates; CSV import/export.
"""
from __future__ import annotations

import csv
import io
import re
import sqlite3
import threading
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from . import catalog
from .currencies import CODES, DEFAULT_RATES, NAMES
from .money import dec

FIELDS = ["key", "system", "category", "description", "manufacturer", "part_no", "unit", "list_price", "currency",
          "discount", "source", "date_checked", "confidence", "notes", "is_custom", "updated_at"]
CONFIDENCE = {"H": "High", "M": "Medium", "B": "Budgetary", "O": "Other"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
  key TEXT PRIMARY KEY, system TEXT, category TEXT, description TEXT, manufacturer TEXT, part_no TEXT, unit TEXT,
  list_price TEXT, currency TEXT, discount TEXT, source TEXT, date_checked TEXT, confidence TEXT, notes TEXT,
  is_custom INTEGER DEFAULT 0, updated_at TEXT);
CREATE TABLE IF NOT EXISTS fx(code TEXT PRIMARY KEY, rate TEXT, as_of TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT, field TEXT, old TEXT, new TEXT,
  changed_at TEXT);
"""


class PriceLibrary:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._con = sqlite3.connect(path, check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        with self._lock:
            self._con.executescript(SCHEMA)
            self.seed()

    def close(self):
        with self._lock:
            self._con.close()

    # ------------------------------------------------------------- seeding
    def seed(self) -> None:
        """Insert catalogue items and currencies that are not in the library yet (prices blank)."""
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock, self._con:
            have = {r[0] for r in self._con.execute("SELECT key FROM items")}
            for it in catalog.ITEMS:
                if it.key in have:
                    continue
                self._con.execute(
                    "INSERT INTO items(key,system,category,description,manufacturer,part_no,unit,list_price,currency,"
                    "discount,source,date_checked,confidence,notes,is_custom,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
                    (it.key, it.system, it.category, it.description, it.manufacturer, it.part_no, it.unit, None,
                     it.currency, it.discount if it.discount != "0" else "", "", "", "", it.notes, now))
            have_fx = {r[0] for r in self._con.execute("SELECT code FROM fx")}
            for code in CODES:
                if code not in have_fx:
                    self._con.execute("INSERT INTO fx(code,rate,as_of,source) VALUES(?,?,?,?)",
                                      (code, str(DEFAULT_RATES[code]), "", "Indicative default"))

    # ------------------------------------------------------------- items
    def rows(self) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._con.execute("SELECT * FROM items ORDER BY rowid")]

    def as_map(self) -> dict[str, dict]:
        return {r["key"]: r for r in self.rows()}

    def get(self, key: str) -> dict | None:
        with self._lock:
            r = self._con.execute("SELECT * FROM items WHERE key=?", (key,)).fetchone()
            return dict(r) if r else None

    def update(self, key: str, patch: dict) -> dict:
        allowed = {"description", "manufacturer", "part_no", "unit", "list_price", "currency", "discount", "source",
                   "date_checked", "confidence", "notes"}
        cur = self.get(key)
        if cur is None:
            raise KeyError(key)
        sets = {}
        for k, v in patch.items():
            if k not in allowed:
                continue
            if k == "list_price":
                d = dec(v, None)
                if v not in (None, "") and d is None:
                    raise ValueError(f"'{v}' is not a valid price")
                if d is not None and d < 0:
                    raise ValueError("Price cannot be negative")
                v = None if d is None else format(d, "f")
            if k == "discount":
                d = dec(v, None)
                if d is not None and not (0 <= d < 100):
                    raise ValueError("Discount must be between 0 and 100")
                v = "" if d is None else format(d, "f")
            if k == "currency" and v and v not in CODES:
                raise ValueError(f"Unknown currency {v}")
            sets[k] = v
        if "list_price" in sets or "currency" in sets:
            if sets.get("list_price", cur["list_price"]) is not None and "date_checked" not in sets:
                sets["date_checked"] = date.today().isoformat()
            if not cur.get("confidence") and "confidence" not in sets and sets.get("list_price", cur["list_price"]):
                sets["confidence"] = "M"
        if not sets:
            return cur
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock, self._con:
            for k, v in sets.items():
                if str(cur.get(k)) != str(v):
                    self._con.execute("INSERT INTO history(key,field,old,new,changed_at) VALUES(?,?,?,?,?)",
                                      (key, k, None if cur.get(k) is None else str(cur.get(k)), None if v is None else str(v), now))
            cols = ", ".join(f"{k}=?" for k in sets) + ", updated_at=?"
            self._con.execute(f"UPDATE items SET {cols} WHERE key=?", (*sets.values(), now, key))
        return self.get(key)

    def add_custom(self, data: dict) -> dict:
        base = re.sub(r"[^a-z0-9]+", "_", (data.get("part_no") or data.get("description") or "item").lower()).strip("_")
        key = "cus_" + base[:40]
        n = 2
        while self.get(key):
            key = f"cus_{base[:36]}_{n}"
            n += 1
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock, self._con:
            self._con.execute(
                "INSERT INTO items(key,system,category,description,manufacturer,part_no,unit,list_price,currency,discount,"
                "source,date_checked,confidence,notes,is_custom,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)",
                (key, data.get("system") or "optional", data.get("category") or "Device", data.get("description") or "New item",
                 data.get("manufacturer") or "", data.get("part_no") or "", data.get("unit") or "ea", None,
                 data.get("currency") or "USD", "", "", "", "", "", now))
        if data.get("list_price") not in (None, ""):
            self.update(key, {"list_price": data["list_price"], "confidence": data.get("confidence") or "M"})
        return self.get(key)

    # ------------------------------------------------------------- FX
    def fx_rows(self) -> list[dict]:
        with self._lock:
            rows = {r["code"]: dict(r) for r in self._con.execute("SELECT * FROM fx")}
        return [{"code": c, "name": NAMES.get(c, c), **rows.get(c, {"rate": str(DEFAULT_RATES.get(c, 1)), "as_of": "", "source": ""})}
                for c in CODES]

    def fx(self) -> dict[str, Decimal]:
        return {r["code"]: dec(r["rate"], None) for r in self.fx_rows() if dec(r["rate"], None)}

    def set_fx(self, code: str, rate, source: str = "Manual") -> None:
        d = dec(rate, None)
        if d is None or d <= 0:
            raise ValueError("Exchange rate must be a positive number")
        if code == "QAR":
            return
        with self._lock, self._con:
            self._con.execute("INSERT INTO fx(code,rate,as_of,source) VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET "
                              "rate=excluded.rate, as_of=excluded.as_of, source=excluded.source",
                              (code, format(d, "f"), date.today().isoformat(), source))

    # ------------------------------------------------------------- CSV
    HEADER_MAP = {
        "key": ["key", "item key", "code"],
        "part_no": ["part no", "part no.", "part number", "part", "partno", "part_no", "sku", "model", "item code"],
        "description": ["description", "desc", "item", "item description", "name"],
        "manufacturer": ["manufacturer", "brand", "mfr", "make", "vendor"],
        "list_price": ["list price", "price", "unit price", "list", "listprice", "list_price", "cost"],
        "currency": ["currency", "curr", "curr.", "ccy"],
        "discount": ["discount", "disc", "disc %", "discount %", "disc."],
        "source": ["source", "quote", "reference", "quote ref"],
        "date_checked": ["date", "date checked", "date_checked", "checked", "price date"],
        "confidence": ["confidence", "conf"],
        "unit": ["unit", "uom"],
    }

    def _map_headers(self, headers: list[str]) -> dict[str, int]:
        out = {}
        norm = [h.strip().lower() for h in headers]
        for field_, names in self.HEADER_MAP.items():
            for i, h in enumerate(norm):
                if h in names and field_ not in out:
                    out[field_] = i
        return out

    def import_csv(self, text: str, commit: bool = False, filename: str = "") -> dict:
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))
        if not rows:
            return {"rows": 0, "updates": 0, "new": 0, "warnings": 0, "preview": [], "mapped": []}
        hmap = self._map_headers(rows[0])
        if "list_price" not in hmap or ("part_no" not in hmap and "key" not in hmap and "description" not in hmap):
            raise ValueError("CSV needs a price column and a part number, key or description column.")
        lib = self.rows()
        by_key = {r["key"]: r for r in lib}
        by_part = {(r["part_no"] or "").strip().lower(): r for r in lib if r["part_no"] and r["part_no"] != "TBC"}
        by_desc = {(r["description"] or "").strip().lower(): r for r in lib}
        preview, updates, new, warns = [], 0, 0, 0
        for raw in rows[1:]:
            if not any(c.strip() for c in raw):
                continue
            val = {f: (raw[i].strip() if i < len(raw) else "") for f, i in hmap.items()}
            target = (by_key.get(val.get("key", "")) or by_part.get(val.get("part_no", "").lower())
                      or by_desc.get(val.get("description", "").lower()))
            price = dec(val.get("list_price"), None)
            cur = (val.get("currency") or "").upper()
            status = "Update" if target else "New"
            warn = ""
            if price is None:
                status, warn = "Skipped", "no price"
            elif cur and cur not in CODES:
                warn = f"unknown currency {cur}"
            elif not cur:
                warn = "currency missing"
            if warn:
                warns += 1
            if status == "Update":
                updates += 1
            elif status == "New":
                new += 1
            preview.append({"part": val.get("part_no") or (target or {}).get("part_no", ""),
                            "desc": val.get("description") or (target or {}).get("description", ""),
                            "old": (target or {}).get("list_price"), "new": None if price is None else format(price, "f"),
                            "status": "No currency" if warn == "currency missing" and status != "Skipped" else status,
                            "warn": warn})
            if commit and price is not None:
                patch = {"list_price": price, "source": val.get("source") or (f"CSV import {filename}".strip()),
                         "confidence": (val.get("confidence") or "H")[:1].upper() if val.get("confidence") else "H"}
                if cur in CODES:
                    patch["currency"] = cur
                if val.get("discount"):
                    patch["discount"] = val["discount"].replace("%", "")
                if val.get("date_checked"):
                    patch["date_checked"] = _norm_date(val["date_checked"])
                if target:
                    if val.get("manufacturer"):
                        patch["manufacturer"] = val["manufacturer"]
                    self.update(target["key"], patch)
                else:
                    self.add_custom({"description": val.get("description") or val.get("part_no"),
                                     "manufacturer": val.get("manufacturer", ""), "part_no": val.get("part_no", ""),
                                     "currency": cur if cur in CODES else "USD", "unit": val.get("unit") or "ea",
                                     "list_price": price})
        return {"rows": len(preview), "updates": updates, "new": new, "warnings": warns, "preview": preview,
                "mapped": sorted(hmap), "columns": len(rows[0])}

    def export_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Key", "System", "Category", "Description", "Manufacturer", "Part No.", "Unit", "List price",
                    "Currency", "Discount %", "Source", "Date checked", "Confidence"])
        for r in self.rows():
            w.writerow([r["key"], r["system"], r["category"], r["description"], r["manufacturer"], r["part_no"], r["unit"],
                        r["list_price"] or "", r["currency"], r["discount"] or "", r["source"] or "", r["date_checked"] or "",
                        CONFIDENCE.get(r["confidence"] or "", "")])
        return buf.getvalue()


def _norm_date(s: str) -> str:
    for fmt_ in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt_).date().isoformat()
        except ValueError:
            continue
    return s
