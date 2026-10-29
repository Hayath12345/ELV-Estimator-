import json

import pytest

from elv_engine import catalog
from elv_engine.currencies import CODES
from elv_engine.project import ProjectStore


def test_seed_has_every_catalogue_item_unpriced(library):
    rows = library.rows()
    assert {r["key"] for r in rows} == set(catalog.BY_KEY)
    assert all(r["list_price"] is None for r in rows)
    cats = {r["category"] for r in rows}
    assert {"Device", "Software", "Licence", "Labour"} <= cats


def test_popular_currencies_available(library):
    codes = [r["code"] for r in library.fx_rows()]
    for c in ("QAR", "USD", "EUR", "GBP", "SAR", "AED", "KWD", "BHD", "OMR", "INR", "CNY", "JPY", "CHF", "AUD", "CAD"):
        assert c in codes
    assert len(CODES) >= 30


def test_update_price_sets_date_and_confidence(library):
    r = library.update("cctv_dome_4mp", {"list_price": "412", "currency": "USD"})
    assert r["list_price"] == "412"
    assert r["date_checked"]
    assert r["confidence"] == "M"
    with pytest.raises(ValueError):
        library.update("cctv_dome_4mp", {"list_price": "abc"})
    with pytest.raises(ValueError):
        library.update("cctv_dome_4mp", {"currency": "ZZZ"})
    with pytest.raises(ValueError):
        library.update("cctv_dome_4mp", {"discount": "120"})
    r = library.update("cctv_dome_4mp", {"list_price": ""})
    assert r["list_price"] is None


def test_fx_edit(library):
    library.set_fx("USD", "3.64")
    assert str(library.fx()["USD"]) == "3.64"
    with pytest.raises(ValueError):
        library.set_fx("EUR", "-1")


def test_csv_preview_and_commit(library):
    csv_text = ("Part No.,Description,Manufacturer,List price,Currency,Source,Date\n"
                "XND-8081REV,Fixed dome camera 4MP,Hanwha Vision,398.00,USD,DQ-26-0866,14/10/2026\n"
                "NEW-123,New widget,Acme,10,,DQ-26-0866,14/10/2026\n"
                "SBP-300B,Junction box,Hanwha Vision,38.5,,DQ,14/10/2026\n")
    pre = library.import_csv(csv_text)
    assert pre["updates"] == 2 and pre["new"] == 1 and pre["warnings"] == 2
    assert library.get("cctv_dome_4mp")["list_price"] is None  # preview does not write
    library.import_csv(csv_text, commit=True, filename="dq.csv")
    r = library.get("cctv_dome_4mp")
    assert r["list_price"] == "398.00" and r["date_checked"] == "2026-10-14" and r["source"] == "DQ-26-0866"
    assert any(x["part_no"] == "NEW-123" for x in library.rows())
    out = library.export_csv()
    assert "XND-8081REV" in out and "398.00" in out


def test_project_store_roundtrip(tmp_path):
    st = ProjectStore(str(tmp_path / "Projects"))
    p, d = st.create({"name": "Es'hailSat HQ Fit-Out", "client": "Qatar Satellite Company"})
    assert (d / "project.json").exists() and (d / "drawings").is_dir() and (d / "outputs").is_dir()
    p["info"]["pmc"] = "KEIC"
    st.save(p, d)
    q = st.load(st.folder(p["id"]))
    assert q["info"]["pmc"] == "KEIC"
    dup, dd = st.duplicate(p["id"])
    assert dup["id"] != p["id"] and dup["info"]["name"].endswith("(copy)") and dd != d
    assert len(st.list()) == 2
    # migration fills new keys
    raw = json.loads((d / "project.json").read_text(encoding="utf-8"))
    del raw["texts"]
    (d / "project.json").write_text(json.dumps(raw), encoding="utf-8")
    assert "assumptions" in st.load(d)["texts"]
