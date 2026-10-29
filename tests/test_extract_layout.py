from collections import Counter

from elv_engine.extract import guess_floor
from elv_engine.extract.classify import classify, comms_role
from elv_engine.layout.floor import build_floors
from elv_engine.layout.place import place_all
from elv_engine.layout.routing import assign


def test_classify_room_names():
    cases = {
        "IDF-2W": "comms", "MDF-3F": "comms", "Server Room": "server", "Lift Lobby": "lift_lobby",
        "Open Office West": "open_office", "Boardroom 3F.M2": "boardroom", "Meeting 2F.M1": "meeting",
        "CEO Office": "executive", "Office 2.01": "office", "WC": "toilet", "Prayer Room": "prayer",
        "Pantry / Riser": "pantry", "Corridor": "corridor", "Reception": "reception", "Entrance Lobby": "entrance",
        "Electrical Room": "electrical", "Store": "store", "Stair 1": "stair",
    }
    for name, cat in cases.items():
        assert classify(name) == cat, name
    assert comms_role("MDF-3F") == "MDF"
    assert comms_role("IDF-2W") == "IDF"
    assert comms_role("Office") is None


def test_guess_floor():
    assert guess_floor("1396-QSC-KEIC-TN-AR-100 2nd Floor.dwg", "1F") == "2F"
    assert guess_floor("Plan_L03.dxf", "1F") == "3F"
    assert guess_floor("Ground floor GF.pdf", "1F") == "GF"
    assert guess_floor("Third floor.pdf", "1F") == "3F"
    assert guess_floor("plan.dwg", "1F") == "1F"


def test_dxf_extraction(extracted):
    a, b = extracted
    assert a["unit_m"] == 0.001 and a["scale_conf"] == "High"
    assert "grid 1–2 = 9.00 m" in a["scale_note"]
    assert len(a["rooms"]) == 39
    cats = Counter(r["category"] for r in a["rooms"])
    assert cats["comms"] == 2 and cats["open_office"] == 2 and cats["meeting"] == 6 and cats["corridor"] == 2
    names = {r["name"]: r for r in a["rooms"]}
    assert names["IDF-2W"]["comms"] == "IDF" and names["IDF-2W"]["area_m2"] == 48.0
    assert len(a["doors"]) == 33 and sum(d["leaves"] for d in a["doors"]) == 38
    assert all(d["tag"].startswith("D-2") for d in a["doors"])
    furn = Counter(f["kind"] for f in a["furniture"])
    assert furn["desk"] == 67 and furn["table"] == 6
    assert len(a["grids"]) == 14 and {g["label"] for g in a["grids"]} >= {"1", "9", "A", "E"}
    mdf = [r for r in b["rooms"] if r["comms"] == "MDF"]
    assert len(mdf) == 1 and mdf[0]["name"] == "Server Room MDF"


def test_placement_rules(sample_project):
    floors = build_floors(sample_project)
    assert [f.name for f in floors] == ["2F", "3F"]
    devs = place_all(floors, {})
    ids = [d["id"] for d in devs]
    assert len(ids) == len(set(ids)), "device ids must be unique"
    f2 = [d for d in devs if d["floor"] == "dw1"]
    by = Counter(d["sys"] for d in f2)
    assert by["cctv"] > 0 and by["access"] > 0 and by["iptv"] > 0 and by["cabling"] > 0
    rooms = {r.id: r for r in floors[0].rooms}
    # privacy: no cameras in toilets or prayer rooms
    assert not [d for d in f2 if d["sys"] == "cctv" and rooms[d["room"]].category in ("toilet", "prayer")]
    # access control on comms rooms and the entrance
    acc_rooms = {rooms[d["room"]].category for d in f2 if d["sys"] == "access"}
    assert {"comms", "entrance"} <= acc_rooms
    # work positions from furniture: open office west has 24 desks x 2 outlets
    ow = [r for r in floors[0].rooms if r.name == "Open Office West"][0]
    assert ow.wp_source == "furniture" and len(ow.wps) == 24
    assert sum(d["ports"] for d in f2 if d["room"] == ow.id and d.get("kind") == "wp") == 48
    # TV sizes follow the meeting-room area rules (48 m² -> 75")
    tv = {rooms[d["room"]].name: d["item"] for d in f2 if d["sys"] == "iptv"}
    assert tv["Meeting Room 2.M1"] == "tv_75" and tv["Reception"] == "tv_55" and tv["Pantry"] == "tv_43"


def test_routing_orthogonal_and_assigned(sample_project):
    floors = build_floors(sample_project)
    devs = place_all(floors, {})
    rt = assign(floors, devs, {})
    routes = rt["routes"]
    assert len(routes) == len(devs)
    for d in devs[:50]:
        pts = routes[d["id"]]["pts"]
        for p, q in zip(pts, pts[1:]):
            assert abs(p[0] - q[0]) < 1e-6 or abs(p[1] - q[1]) < 1e-6, "routes must be orthogonal"
    comms_ids = {r.id for f in floors for r in f.comms_rooms}
    assert {r["room"] for r in routes.values()} <= comms_ids
    assert len(rt["backbone"]) == 3  # IDF-2W, IDF-2E, IDF-3W -> MDF
