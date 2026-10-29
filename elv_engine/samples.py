"""Generate synthetic but realistic office floor plans as DXF (mm, INSUNITS=4).

Layers follow common AIA naming: A-WALL, A-AREA (room boundaries), A-AREA-IDEN (names),
A-DOOR (door blocks), A-DOOR-IDEN (door tags), I-FURN (desks/chairs/tables), S-GRID.
Used by the tests, the app self-test and "Open sample project" (`python -m elv_engine.samples OUTDIR`).
"""
from __future__ import annotations

import sys
from pathlib import Path

GRID_X = [i * 9000 for i in range(9)]  # 1..9
GRID_Y = [i * 10000 for i in range(5)]  # A..E


def _blocks(doc):
    if "DOOR_SGL" not in doc.blocks:
        b = doc.blocks.new("DOOR_SGL")
        b.add_line((0, 0), (1000, 0))
        b.add_line((0, 0), (0, 1000))
        b.add_arc((0, 0), 1000, 0, 90)
    if "DOOR_DBL" not in doc.blocks:
        b = doc.blocks.new("DOOR_DBL")
        b.add_line((0, 0), (1800, 0))
        b.add_line((0, 0), (0, 900))
        b.add_line((1800, 0), (1800, 900))
        b.add_arc((0, 0), 900, 0, 90)
        b.add_arc((1800, 0), 900, 90, 180)
    if "WS-DESK" not in doc.blocks:
        b = doc.blocks.new("WS-DESK")
        b.add_lwpolyline([(-800, -400), (800, -400), (800, 400), (-800, 400)], close=True)
    if "CHAIR-01" not in doc.blocks:
        b = doc.blocks.new("CHAIR-01")
        b.add_circle((0, 0), 250)
    if "TABLE-MTG" not in doc.blocks:
        b = doc.blocks.new("TABLE-MTG")
        b.add_lwpolyline([(-1500, -600), (1500, -600), (1500, 600), (-1500, 600)], close=True)


def make_floor(path: str, level: int, with_mdf: bool) -> dict:
    import ezdxf
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 4
    for name, color in (("A-WALL", 7), ("A-AREA", 8), ("A-AREA-IDEN", 2), ("A-DOOR", 3), ("A-DOOR-IDEN", 3),
                        ("I-FURN", 9), ("S-GRID", 1)):
        doc.layers.add(name, color=color)
    _blocks(doc)
    msp = doc.modelspace()
    L = str(level)
    rooms: list[tuple[str, tuple[float, float, float, float]]] = []
    doors: list[tuple[float, float, str, float]] = []  # x, y, block, rotation

    # top row of rooms y 32000-40000, 12 slots of 6 m
    for i in range(12):
        x0 = i * 6000
        if i == 0:
            name = f"IDF-{L}W"
        elif i == 1 and with_mdf:
            name = "Electrical Room"
        elif i == 11:
            name = "Server Room MDF" if with_mdf else f"IDF-{L}E"
        elif i == 5:
            name = "CEO Office" if with_mdf else "Director Office"
        elif i == 6:
            name = "Store"
        else:
            name = f"Office {L}.{i:02d}"
        rooms.append((name, (x0, 32000, x0 + 6000, 40000)))
        doors.append((x0 + 2500, 32000, "DOOR_SGL", 0))
    rooms.append(("Corridor North", (0, 30000, 72000, 32000)))
    # middle band
    rooms.append(("Open Office West", (0, 10000, 24000, 30000)))
    doors.append((11000, 30000, "DOOR_DBL", 0))
    for k in range(3):
        rooms.append(((f"Boardroom" if (with_mdf and k == 1) else f"Meeting Room {L}.M{k + 1}"),
                      (24000 + k * 8000, 24000, 32000 + k * 8000, 30000)))
        doors.append((27000 + k * 8000, 30000, "DOOR_DBL" if k == 1 else "DOOR_SGL", 0))
    rooms.append(("Stair 1", (24000, 19000, 30000, 24000)))
    rooms.append(("Toilet", (24000, 14000, 30000, 19000)))
    rooms.append(("Lift Lobby", (30000, 14000, 42000, 24000)))
    rooms.append(("Pantry", (42000, 19000, 48000, 24000)))
    rooms.append(("Prayer Room", (42000, 14000, 48000, 19000)))
    for k in range(3):
        rooms.append((f"Meeting Room {L}.M{k + 4}", (24000 + k * 8000, 10000, 32000 + k * 8000, 14000)))
        doors.append((27000 + k * 8000, 10000, "DOOR_SGL", 0))
    rooms.append(("Open Office East", (48000, 10000, 72000, 30000)))
    doors.append((59000, 30000, "DOOR_DBL", 0))
    rooms.append(("Corridor South", (0, 8000, 72000, 10000)))
    # bottom row
    for i in range(12):
        x0 = i * 6000
        if i in (5, 6):
            continue
        name = f"Office {L}.{i + 20:02d}"
        rooms.append((name, (x0, 0, x0 + 6000, 8000)))
        doors.append((x0 + 2500, 8000, "DOOR_SGL", 0))
    rooms.append(("Reception", (30000, 0, 36000, 8000)))
    rooms.append(("Entrance Lobby", (36000, 0, 42000, 8000)))
    doors.append((37500, 8000, "DOOR_DBL", 0))
    doors.append((38500, 0, "DOOR_DBL", 0))  # main entrance
    doors.append((32500, 8000, "DOOR_SGL", 0))

    for name, (x0, y0, x1, y1) in rooms:
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": "A-AREA"})
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": "A-WALL"})
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        msp.add_text(name, height=250, dxfattribs={"layer": "A-AREA-IDEN"}).set_placement(
            (cx, cy), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    for j, (x, y, blk, rot) in enumerate(doors, 1):
        msp.add_blockref(blk, (x, y), dxfattribs={"layer": "A-DOOR", "rotation": rot})
        msp.add_text(f"D-{L}{j:02d}", height=180, dxfattribs={"layer": "A-DOOR-IDEN"}).set_placement(
            (x + 300, y - 600), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    # desks: open offices 6 x 4, offices 1 desk + chair
    n_desks = 0
    for ox in (0, 48000):
        for r in range(4):
            for c in range(6):
                msp.add_blockref("WS-DESK", (ox + 2500 + c * 3800, 13000 + r * 4200), dxfattribs={"layer": "I-FURN"})
                msp.add_blockref("CHAIR-01", (ox + 2500 + c * 3800, 12300 + r * 4200), dxfattribs={"layer": "I-FURN"})
                n_desks += 1
    for name, (x0, y0, x1, y1) in rooms:
        if name.startswith("Office") or name.endswith("Office") and "Open" not in name:
            msp.add_blockref("WS-DESK", ((x0 + x1) / 2, (y0 + y1) / 2 + 1000), dxfattribs={"layer": "I-FURN"})
            n_desks += 1
        if name.startswith("Meeting") or name == "Boardroom":
            msp.add_blockref("TABLE-MTG", ((x0 + x1) / 2, (y0 + y1) / 2), dxfattribs={"layer": "I-FURN"})
    # grid
    labels_x = [str(i + 1) for i in range(len(GRID_X))]
    labels_y = list("ABCDE")
    for x, lab in zip(GRID_X, labels_x):
        msp.add_line((x, -3000), (x, 43000), dxfattribs={"layer": "S-GRID"})
        msp.add_circle((x, 43600), 600, dxfattribs={"layer": "S-GRID"})
        msp.add_text(lab, height=400, dxfattribs={"layer": "S-GRID"}).set_placement(
            (x, 43600), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    for y, lab in zip(GRID_Y, labels_y):
        msp.add_line((-3000, y), (75000, y), dxfattribs={"layer": "S-GRID"})
        msp.add_circle((-3600, y), 600, dxfattribs={"layer": "S-GRID"})
        msp.add_text(lab, height=400, dxfattribs={"layer": "S-GRID"}).set_placement(
            (-3600, y), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)
    return {"rooms": len(rooms), "doors": len(doors), "desks": n_desks, "grids": len(GRID_X) + len(GRID_Y)}


def make_set(outdir: str) -> list[str]:
    out = Path(outdir)
    a = str(out / "SAMPLE-HQ-AR-102 Second Floor 2F.dxf")
    b = str(out / "SAMPLE-HQ-AR-103 Third Floor 3F.dxf")
    make_floor(a, 2, with_mdf=False)
    make_floor(b, 3, with_mdf=True)
    return [a, b]


if __name__ == "__main__":
    print(make_set(sys.argv[1] if len(sys.argv) > 1 else "sample_drawings"))
