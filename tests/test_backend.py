"""Drives the application backend exactly as the UI does (through the js_api dispatcher)."""
import time

import pytest

from app.api import dispatch
from app.backend import Backend
from tests.conftest import TEST_PRICES


def call(b, method, args=None):
    r = dispatch(b, method, args or {})
    assert r["ok"], r.get("error")
    return r["data"]


def wait_job(b, job_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        j = call(b, "get_job", {"id": job_id})
        if j["done"]:
            assert not j["error"], j["error"]
            return j
        time.sleep(0.1)
    raise AssertionError("job timed out")


@pytest.fixture()
def backend(tmp_path, monkeypatch):
    monkeypatch.setenv("ELV_NO_OPEN", "1")
    events = []
    b = Backend(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects", emit=events.append)
    b._events = events
    yield b
    b.lib.close()


@pytest.fixture()
def project(backend, sample_dxfs):
    call(backend, "create_project", {"name": "Es'hailSat HQ Fit-Out", "client": "Qatar Satellite Company", "pmc": "KEIC"})
    r = call(backend, "import_drawings", {"paths": sample_dxfs})
    wait_job(backend, r["job"]["id"])
    return backend


def price_all(b):
    for row in call(b, "get_prices")["rows"]:
        lp, cur, disc, conf = TEST_PRICES[row["category"]]
        call(b, "update_price", {"key": row["key"], "patch": {"list_price": lp, "currency": cur, "discount": disc, "confidence": conf}})


def test_errors_are_messages_not_crashes(backend):
    r = dispatch(backend, "get_layout", {})
    assert not r["ok"] and "Open a quotation" in r["error"]
    assert not dispatch(backend, "no_such_method")["ok"]
    assert not dispatch(backend, "create_project", {"name": " "})["ok"]


def test_import_extract_and_screens(project, backend):
    st = call(backend, "project_state")
    assert [f["name"] for f in st["floors"]] == ["2F", "3F"]
    dr = call(backend, "get_drawings")
    assert dr["state"] == "results" and len(dr["files"]) == 2
    assert dr["rows"][0]["item"] == "Rooms" and dr["rows"][0]["vals"] == ["39", "39"]
    assert any(e["type"] == "job" and e["done"] for e in backend._events), "progress events are pushed"
    lay = call(backend, "get_layout", {"floor": st["floors"][0]["key"]})
    assert lay["devices"] and lay["rooms"] and lay["grids"]
    assert all("pts" in d for d in lay["devices"][:20])
    sysv = call(backend, "get_systems")
    assert sysv["allOn"] and sysv["params"]["cctv"][0]["key"] == "retention_days"
    comms = call(backend, "get_comms")
    assert len(comms["rooms"]) == 4 and comms["rooms"][0]["racks"]
    boq = call(backend, "get_boq")
    assert boq["unpriced"] > 0 and [t["key"] for t in boq["tabs"]][-3:] == ["shared", "network", "optional"]
    ck = call(backend, "get_checks")
    assert ck["blocking"] >= 1 and not ck["canIssue"]
    bg = call(backend, "get_background", {"id": st["floors"][0]["key"]})
    assert bg["url"].startswith("data:image/png;base64,")


def test_pricing_flow_and_totals(project, backend):
    price_all(backend)
    st = call(backend, "project_state")
    assert st["header"]["baseF"] != "0.00"
    ck = call(backend, "get_checks")
    assert ck["blocking"] == 0 and ck["canIssue"], [r for g in ck["groups"] for r in g["rows"] if not r["pass"]]
    boq = call(backend, "get_boq")
    line = boq["tabs"][0]["sections"][0]["lines"][0]
    call(backend, "update_boq_line", {"key": line["key"], "patch": {"list_price": "999", "currency": "EUR", "discount": "10"}})
    boq2 = call(backend, "get_boq")
    l2 = boq2["tabs"][0]["sections"][0]["lines"][0]
    assert l2["list"] == "999" and l2["cur"] == "EUR" and "list_price" in l2["overridden"]
    assert not dispatch(backend, "update_boq_line", {"key": line["key"], "patch": {"discount": "150"}})["ok"]
    call(backend, "update_boq_line", {"key": line["key"], "patch": {"reset": True}})
    assert call(backend, "get_boq")["tabs"][0]["sections"][0]["lines"][0]["overridden"] == []
    call(backend, "set_commercial", {"markup": "20"})
    assert call(backend, "project_state")["header"]["baseF"] != st["header"]["baseF"]
    call(backend, "set_fx", {"code": "USD", "rate": "3.70", "scope": "project"})
    assert any(f["code"] == "USD" and f["project"] for f in call(backend, "get_boq")["fx"])
    # custom line in Optional
    call(backend, "add_boq_line", {"tab": "optional", "section": "Optional items (client to confirm)", "description": "LPR kit",
                                   "qty": 2, "list_price": "3100", "currency": "USD"})
    assert call(backend, "get_boq")["m"]["optional"] != "0.00"


def test_layout_edits_persist(project, backend):
    st = call(backend, "project_state")
    f = st["floors"][0]["key"]
    lay = call(backend, "get_layout", {"floor": f})
    n = len(lay["devices"])
    d = lay["devices"][0]
    call(backend, "move_device", {"id": d["id"], "x": d["x"] + 2000, "y": d["y"]})
    r = call(backend, "add_device", {"sys": "cctv", "item": "cctv_ptz_2mp", "floor": f, "x": d["x"], "y": d["y"]})
    call(backend, "delete_device", {"id": lay["devices"][1]["id"]})
    call(backend, "update_device", {"id": r["id"], "props": {"target": "Identify"}})
    # reopen from disk: edits are in project.json
    pid = st["id"]
    call(backend, "close_project")
    call(backend, "open_project", {"id": pid})
    lay2 = call(backend, "get_layout", {"floor": f})
    by = {x["id"]: x for x in lay2["devices"]}
    assert len(lay2["devices"]) == n
    assert by[d["id"]]["x"] == pytest.approx(d["x"] + 2000) and by[d["id"]]["edited"]
    assert by[r["id"]]["item"] == "cctv_ptz_2mp" and by[r["id"]]["target"] == "Identify"
    call(backend, "reset_layout", {"floor": f})
    assert len(call(backend, "get_layout", {"floor": f})["devices"]) == n


def test_calibration_and_rooms(project, backend):
    st = call(backend, "project_state")
    f = st["floors"][0]["key"]
    # 9 m grid measured as 9000 units -> 0.001 m/unit
    call(backend, "calibrate", {"id": f, "p1": [0, 0], "p2": [9000, 0], "distance_m": "9"})
    dr = call(backend, "get_drawings")
    assert dr["files"][0]["scale"]["conf"] == "Calibrated"
    room = next(r for r in dr["rooms"] if r["name"] == "Store" and r["floor"] == "2F")
    call(backend, "update_room", {"drawing": room["drawing"], "id": room["id"], "comms": "IDF"})
    assert len(call(backend, "get_comms")["rooms"]) == 5


def test_override_and_signoff(project, backend):
    ck = call(backend, "get_checks")
    assert not ck["canIssue"]
    r = dispatch(backend, "generate", {})
    assert not r["ok"] and "failing" in r["error"]
    call(backend, "set_override", {"reason": "Budget quotation for client review before supplier quotes"})
    assert call(backend, "get_checks")["canIssue"]
    assert not dispatch(backend, "sign", {"step": "checked"})["ok"]  # no name yet
    call(backend, "update_project_info", {"signoff": {"checked": {"name": "Ravi Menon", "role": "Lead ELV Engineer"}}})
    call(backend, "sign", {"step": "checked"})
    assert call(backend, "project_state")["status"] == "In review"


def test_price_library_csv_and_search(project, backend):
    pv = call(backend, "import_prices", {"text": "Part No.,List price,Currency\nXND-8081REV,412,USD\n", "name": "q.csv"})
    assert pv["updates"] == 1
    call(backend, "import_prices", {"text": "Part No.,List price,Currency\nXND-8081REV,412,USD\n", "commit": True})
    rows = call(backend, "get_prices", {"q": "XND-8081"})["rows"]
    assert rows[0]["list"] == "412" and rows[0]["used"]
    used = call(backend, "get_prices", {"used": True})
    assert used["shown"] == used["usedCount"] > 0
    s = call(backend, "search", {"q": "eshail"})
    assert s["projects"] == [] or s["projects"][0]["name"].startswith("Es")
    s = call(backend, "search", {"q": "hail"})
    assert s["projects"] and s["projects"][0]["client"] == "Qatar Satellite Company"


def test_dashboard_and_duplicate(project, backend):
    price_all(backend)
    call(backend, "project_state")  # stores the summary
    lst = call(backend, "list_projects")
    assert lst["kpis"]["active"] == 1 and lst["rows"][0]["totalF"] != "0.00"
    call(backend, "duplicate_project", {"id": lst["rows"][0]["id"]})
    assert call(backend, "list_projects")["kpis"]["active"] == 2
