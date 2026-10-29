"""Test-only helper: call engine functions with explicit, synthetic inputs and record what they
return. These are function-level probes, not project results — every input is listed in the
output so a reviewer can re-run them.

Usage: python tests/diagnostics/probe_functions.py OUT_DIR
Writes OUT_DIR/json/probes.json and OUT_DIR/logs/probes.txt
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from elv_engine import catalog  # noqa: E402
from elv_engine import geometry as G  # noqa: E402
from elv_engine.extract import guess_floor  # noqa: E402
from elv_engine.extract.classify import OCCUPIED, PRIVATE, classify, looks_like_room_name  # noqa: E402
from elv_engine.extract.common import assign_labels, finalise_rooms, infer_units  # noqa: E402
from elv_engine.layout.floor import build_floor  # noqa: E402
from elv_engine.layout.place import camera_range, place_all  # noqa: E402
from elv_engine.params import merged  # noqa: E402

WEDGE_HALF_RAD = 0.62  # literal used in ui/src/components/FloorPlan.tsx and elv_engine/outputs/pdf_layout.py

BASEMENT_LABELS = [
    "CAR PARK", "CAR PARKING", "PARKING", "BASEMENT PARKING", "PARKING AREA", "PARKING BAY", "RAMP", "RAMP UP",
    "DRIVEWAY", "DRIVE AISLE", "AISLE", "FAHU", "FAHU ROOM", "VRF", "VRF ROOM", "VRF AREA", "SERVICE ROOM", "SERVICE AREA",
    "LV ROOM", "ELEC. ROOM", "ELECTRICAL ROOM", "GENERATOR ROOM", "GEN SET ROOM", "TRANSFORMER ROOM", "PUMP ROOM",
    "FIRE PUMP ROOM", "WATER TANK", "WATER TANK ROOM", "SUMP PIT", "STP ROOM", "REFUSE ROOM", "GARBAGE ROOM",
    "BMS ROOM", "ELV ROOM", "TELECOM ROOM", "MDF ROOM", "SECURITY ROOM", "GUARD ROOM", "DRIVERS ROOM", "WATCHMAN ROOM",
    "LIFT LOBBY", "LIFT", "STAIR 01", "STAIRCASE", "FIRE EXIT", "ENTRY", "EXIT", "PEDESTRIAN ENTRANCE", "STORE",
    "STORE ROOM", "JANITOR", "TOILET", "MOSQUE", "SPRINKLER VALVE ROOM", "EXHAUST FAN ROOM", "SHAFT", "RISER",
]
FILENAMES = ["B1 Basement Plan.dwg", "BASEMENT FLOOR PLAN.dwg", "Basement-01.dwg", "LOWER GROUND.dwg", "LG Floor.dwg",
             "P1 Parking Level.dwg", "B2_PARKING.dwg", "Ground Floor.dwg", "GF.dwg", "Level 03.dwg", "Roof.dwg"]


def probe_classification() -> list[dict]:
    cctv = set(merged("cctv", None)["categories"])
    out = []
    for t in BASEMENT_LABELS:
        cat = classify(t)
        out.append({"label": t, "accepted_as_room_name": looks_like_room_name(t), "category": cat,
                    "cctv_default": cat in cctv and cat not in PRIVATE, "wifi_ap_eligible(OCCUPIED)": cat in OCCUPIED})
    return out


def _lab(text, x_m, y_m):
    return {"text": text, "pt": [x_m * 1000, y_m * 1000]}


def _rect(x0, y0, x1, y1):
    return {"pts": [(x0 * 1000, y0 * 1000), (x1 * 1000, y0 * 1000), (x1 * 1000, y1 * 1000), (x0 * 1000, y1 * 1000)]}


def probe_labels() -> list[dict]:
    """Units are mm (unit_m=0.001); coordinates given in metres below for readability."""
    cases = []

    def run(name, polys, labels, note):
        rooms = assign_labels(polys, labels, 0.001, "High")
        fin = finalise_rooms(rooms, 0.001)
        cases.append({"case": name, "note": note,
                      "inputs": {"polylines_m": [[(round(x / 1000, 3), round(y / 1000, 3)) for x, y in p["pts"]] for p in polys],
                                 "labels_m": [{"text": l["text"], "pt": [l["pt"][0] / 1000, l["pt"][1] / 1000]} for l in labels]},
                      "rooms": [{"id": r["id"], "name": r["name"], "category": r["category"], "area_m2": r["area_m2"],
                                 "boundary": r["boundary"], "conf": r["conf"]} for r in fin]})

    run("A: 8 x 'CAR PARK' labels, 6 m apart, no closed boundary", [],
        [_lab("CAR PARK", 6 * i, 0) for i in range(8)],
        "Typical basement: the same label repeated across one large car park drawn with open lines.")
    run("B: same label at 2.0 m / 2.5 m / 3.0 m spacing, no boundary", [],
        [_lab("PARKING", 0, 0), _lab("PARKING", 2.0, 0), _lab("PARKING", 4.5, 0), _lab("PARKING", 7.5, 0)],
        "De-dup radius for unbounded labels is 0.6 x 4 m = 2.4 m.")
    run("C: one 60x40 m boundary holding 4 room names", [_rect(0, 0, 60, 40)],
        [_lab("CAR PARK", 30, 20), _lab("FAHU ROOM", 5, 35), _lab("VRF ROOM", 15, 35), _lab("LIFT LOBBY", 50, 35)],
        "Boundaries that contain more than 3 names are treated as outlines and dropped.")
    run("D: one 60x40 m boundary holding 3 room names", [_rect(0, 0, 60, 40)],
        [_lab("CAR PARK", 30, 20), _lab("FAHU ROOM", 5, 35), _lab("VRF ROOM", 15, 35)],
        "Same as C with 3 names: kept as one room; the names are joined.")
    run("E: 'FAHU' label without the word ROOM inside its own boundary", [_rect(0, 0, 6, 5)],
        [_lab("FAHU", 3, 2.5)], "Label text not recognised as a room name.")
    run("F: car park boundary + 'CAR PARK' label + 3 parking-bay numbers inside it", [_rect(0, 0, 50, 30)],
        [_lab("CAR PARK", 25, 15), _lab("P01", 3, 3), _lab("P02", 6, 3), _lab("P03", 9, 3)],
        "Bay numbers look like room numbers (^[A-Z]{1,3}\\d{2,4}).")
    return cases


def probe_units() -> list[dict]:
    rows = []
    for ins, ext, areas, note in [
        (4, (72000, 40000), [48e6] * 10, "mm header, mm geometry (72 x 40 m plan)"),
        (6, (72, 40), [48.0] * 10, "m header, m geometry"),
        (4, (72, 40), [48.0] * 10, "mm header but drawn in metres"),
        (0, (72000, 40000), [48e6] * 10, "unitless header, mm geometry"),
        (0, (72, 40), [48.0] * 10, "unitless header, m geometry"),
        (0, (7200, 4000), [4.8e5] * 10, "unitless header, cm geometry"),
        (4, (250000, 180000), [], "mm header, 250 x 180 m basement, no closed rooms"),
        (4, (2_500_000, 1_800_000), [], "mm header, extents inflated by a far-away stray entity (2.5 km)"),
        (6, (2500, 1800), [], "m header, extents inflated (2.5 km)"),
    ]:
        u, conf, msg = infer_units(ins, ext, areas)
        rows.append({"insunits": ins, "extent": ext, "median_area_units2": areas[0] if areas else None,
                     "note": note, "unit_m": u, "confidence": conf, "message": msg})
    return rows


def probe_fov() -> dict:
    p = merged("cctv", None)
    ppm = {"Identify": float(p["ppm_identify"]), "Recognise": float(p["ppm_recognise"]), "Observe": float(p["ppm_observe"])}
    rows = []
    for item, o in catalog.CAMERA_OPTICS.items():
        row = {"item": item, "hres_px": o["hres"], "hfov_deg_catalogue": o["hfov"], "hfov_used_in_range": min(o["hfov"], 120),
               "wedge_full_angle_drawn_deg": round(math.degrees(2 * WEDGE_HALF_RAD), 1),
               "wedge_vs_hfov_deg": round(math.degrees(2 * WEDGE_HALF_RAD) - o["hfov"], 1)}
        for k, v in ppm.items():
            row[f"range_m_{k}"] = round(camera_range(item, v), 2)
        rows.append(row)
    return {"formula": "range = hres / (ppm x 2 x tan(min(hfov,120)/2))", "ppm": ppm,
            "wedge_half_angle_rad": WEDGE_HALF_RAD, "rows": rows}


def probe_floors() -> list[dict]:
    rows = []
    for f in FILENAMES:
        rows.append({"file": f, "floor": guess_floor(f, "<fallback: order+1>F")})
    return rows


def probe_parking() -> dict:
    """Synthetic basement floor: 80x50 m car park (drawn boundary), 6 m drive aisle as a corridor-less
    space, lift lobby, stair, FAHU ROOM, VRF ROOM, LV ROOM, IDF. mm units."""
    def room(rid, name, x0, y0, x1, y1):
        poly = [[x0 * 1000, y0 * 1000], [x1 * 1000, y0 * 1000], [x1 * 1000, y1 * 1000], [x0 * 1000, y1 * 1000]]
        return {"id": rid, "name": name, "category": classify(name), "poly": poly,
                "label_pt": [(x0 + x1) * 500, (y0 + y1) * 500], "conf": "High", "boundary": "drawn",
                "comms": "IDF" if classify(name) == "comms" else None}
    rooms = [room("R001", "CAR PARK", 0, 0, 80, 50), room("R002", "LIFT LOBBY", 80, 20, 90, 30),
             room("R003", "STAIR 01", 80, 30, 86, 36), room("R004", "FAHU ROOM", 80, 36, 90, 44),
             room("R005", "VRF ROOM", 80, 44, 90, 50), room("R006", "LV ROOM", 80, 10, 90, 20),
             room("R007", "IDF ROOM", 80, 0, 86, 10), room("R008", "RAMP", -12, 0, 0, 30)]
    dwg = {"id": "probe", "floor": "B1", "extraction": {"rooms": rooms, "doors": [], "furniture": [], "unit_m": 0.001,
                                                       "scale_conf": "High", "extents": [-12000, 0, 90000, 50000], "kind": "dxf"}}
    fl = build_floor(dwg, 0, {})
    devs = place_all([fl], {})
    cams = [d for d in devs if d["sys"] == "cctv"]
    by_room = {}
    for d in devs:
        by_room.setdefault(d["room"], {}).setdefault(d["item"], 0)
        by_room[d["room"]][d["item"]] += 1
    rid = {r.id: r for r in fl.rooms}
    cam_rows = []
    for d in cams:
        r = rid[d["room"]]
        cam_rows.append({"id": d["id"], "room": r.name, "x_m": round(d["x"] / 1000, 2), "y_m": round(d["y"] / 1000, 2),
                         "aim_deg": d["a"], "target": d["target"], "range_m": d["range_m"],
                         "aim_vs_bearing_to_centroid_deg": round(abs(((G.angle_deg((d["x"], d["y"]), r.centroid) - d["a"]) + 180) % 360 - 180), 1)})
    return {"inputs": {"rooms": [{"name": r["name"], "category": r["category"],
                                  "bbox_m": [r["poly"][0][0] / 1000, r["poly"][0][1] / 1000, r["poly"][2][0] / 1000, r["poly"][2][1] / 1000]} for r in rooms],
                       "params": "defaults"},
            "rooms_out": [{"id": r.id, "name": r.name, "category": r.category, "area_m2": round(r.area_m2, 1),
                           "doors": len(r.doors), "inferred_doors": sum(1 for d in r.doors if d.inferred),
                           "devices": by_room.get(r.id, {})} for r in fl.rooms],
            "cameras": cam_rows}


def probe_large_carpark() -> list[dict]:
    """extract_dxf on small generated DXFs (mm, A-AREA boundary + A-AREA-IDEN label) with car parks of
    increasing size, to see whether the boundary is kept (extract_dxf limits room polygons to 1..6000 m²)."""
    import tempfile

    import ezdxf

    from elv_engine.extract.dxf import extract_dxf
    rows = []
    tmp = Path(tempfile.mkdtemp(prefix="elv-probe-"))
    for w, h in ((50, 40), (75, 80), (80, 76), (120, 90)):
        doc = ezdxf.new("R2018")
        doc.header["$INSUNITS"] = 4
        msp = doc.modelspace()
        for lay in ("A-AREA", "A-AREA-IDEN"):
            doc.layers.add(lay)
        rects = [("CAR PARK", 0, 0, w, h), ("LIFT LOBBY", w, 0, w + 8, 8), ("FAHU ROOM", w, 8, w + 8, 16),
                 ("ELV ROOM", w, 16, w + 6, 22)]
        for name, x0, y0, x1, y1 in rects:
            msp.add_lwpolyline([(x0 * 1000, y0 * 1000), (x1 * 1000, y0 * 1000), (x1 * 1000, y1 * 1000), (x0 * 1000, y1 * 1000)],
                               close=True, dxfattribs={"layer": "A-AREA"})
            msp.add_text(name, height=300, dxfattribs={"layer": "A-AREA-IDEN"}).set_placement(((x0 + x1) * 500, (y0 + y1) * 500))
        f = tmp / f"carpark_{w}x{h}.dxf"
        doc.saveas(f)
        ex = extract_dxf(str(f))
        cp = [r for r in ex["rooms"] if r["name"] == "CAR PARK"]
        rows.append({"carpark_m": [w, h], "carpark_area_m2": w * h, "rooms": len(ex["rooms"]),
                     "carpark_room_area_m2": cp[0]["area_m2"] if cp else None,
                     "carpark_boundary": cp[0]["boundary"] if cp else None, "unit_m": ex["unit_m"]})
    return rows


def main(out_dir: str) -> None:
    out = Path(out_dir)
    (out / "json").mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(parents=True, exist_ok=True)
    data = {"classification": probe_classification(), "labels": probe_labels(), "units": probe_units(),
            "fov": probe_fov(), "floor_names": probe_floors(), "parking_floor": probe_parking(),
            "large_carpark": probe_large_carpark()}
    (out / "json" / "probes.json").write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    L = []
    L.append("== Classification of basement / parking label texts (classify + looks_like_room_name)")
    L.append(f"{'label':26s} {'room name?':10s} {'category':12s} {'CCTV':5s} {'WiFi AP':7s}")
    for r in data["classification"]:
        L.append(f"{r['label']:26s} {str(r['accepted_as_room_name']):10s} {r['category']:12s} "
                 f"{str(r['cctv_default']):5s} {str(r['wifi_ap_eligible(OCCUPIED)']):7s}")
    L.append("\n== Label -> room matching (assign_labels + finalise_rooms), mm units")
    for c in data["labels"]:
        L.append(f"-- {c['case']}\n   {c['note']}\n   rooms out: {len(c['rooms'])}")
        for r in c["rooms"]:
            L.append(f"   {r['id']} {r['name']!r:40s} {r['category']:10s} {r['area_m2']:>9} m2 {r['boundary']:9s} conf={r['conf']}")
    L.append("\n== Units inference (infer_units)")
    for r in data["units"]:
        L.append(f"   INSUNITS={r['insunits']} extent={r['extent']} -> unit_m={r['unit_m']} {r['confidence']}: "
                 f"{r['message']}   [{r['note']}]")
    L.append("\n== FOV radius and drawn wedge angle")
    L.append(f"   {data['fov']['formula']}  ppm={data['fov']['ppm']}  wedge half-angle={WEDGE_HALF_RAD} rad")
    for r in data["fov"]["rows"]:
        L.append(f"   {r['item']:18s} HFOV {r['hfov_deg_catalogue']:>4}°  drawn {r['wedge_full_angle_drawn_deg']}° "
                 f"(diff {r['wedge_vs_hfov_deg']:+}°)  Identify {r['range_m_Identify']} m  Recognise {r['range_m_Recognise']} m  "
                 f"Observe {r['range_m_Observe']} m")
    L.append("\n== Floor name from file name (guess_floor)")
    for r in data["floor_names"]:
        L.append(f"   {r['file']:28s} -> {r['floor']}")
    L.append("\n== Synthetic basement floor through build_floor + place_all (defaults)")
    for r in data["parking_floor"]["rooms_out"]:
        L.append(f"   {r['id']:12s} {r['name']:12s} {r['category']:10s} {r['area_m2']:>7} m2 doors={r['doors']} "
                 f"(inferred {r['inferred_doors']})  devices={r['devices']}")
    for c in data["parking_floor"]["cameras"]:
        L.append(f"   cam {c['id']:8s} {c['room']:10s} ({c['x_m']:>6}, {c['y_m']:>6}) m aim {c['aim_deg']:>6}° "
                 f"target {c['target']:9s} |aim-bearing to centroid| {c['aim_vs_bearing_to_centroid_deg']}°")
    L.append("\n== Car park boundary size through extract_dxf (generated DXF, mm)")
    for r in data["large_carpark"]:
        L.append(f"   car park {r['carpark_m'][0]}x{r['carpark_m'][1]} m = {r['carpark_area_m2']} m2 -> room area "
                 f"{r['carpark_room_area_m2']} m2, boundary={r['carpark_boundary']}, rooms={r['rooms']}")
    (out / "logs" / "probes.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
