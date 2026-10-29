"""Test-only helper: draw per-floor diagnostic PNGs (150 dpi, metre scale bar on every image)
from the engine's own floor/device/route objects. Used by run_project_diagnostics.py.

Wedges are drawn exactly as the app draws them (ui/src/components/FloorPlan.tsx): half-angle
0.62 rad, radius = camera range for the device's target, not clipped. The "clipped" panel clips
each wedge to the camera's own room polygon (room boundaries treated as walls, doors ignored).
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from elv_engine.extract.render import load_linework
from elv_engine.systems import BY_KEY

DPI = 150
STD = [50, 100, 200, 250, 500, 1000, 2000]
WEDGE_HALF_RAD = 0.62
CAT_COLOR = {
    "corridor": "#C9D3E3", "lift_lobby": "#B7C7E6", "lift": "#9FB0CC", "stair": "#AFB8C6", "entrance": "#F2D49B",
    "reception": "#F2D49B", "comms": "#E8A0A0", "server": "#E8A0A0", "electrical": "#E9C3A0", "plant": "#D9C7B0",
    "parking": "#CFE3C8", "loading": "#CFE3C8", "other": "#E6E6E6", "toilet": "#D7E7EE", "prayer": "#E2DAF0",
}


def _font(size: int):
    for name in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _rgba(hexs: str, a: int = 255):
    h = hexs.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


class Canvas:
    """Paper canvas at 150 dpi. World coordinates are drawing units (y up)."""

    def __init__(self, floor, title: str, max_mm=(800, 540), scale: int | None = None):
        self.f = floor
        um = floor.unit_m
        xs = [p[0] for r in floor.rooms for p in r.poly] or [floor.extents[0], floor.extents[2]]
        ys = [p[1] for r in floor.rooms for p in r.poly] or [floor.extents[1], floor.extents[3]]
        self.x0, self.y0, self.x1, self.y1 = min(xs), min(ys), max(xs), max(ys)
        w_m, h_m = (self.x1 - self.x0) * um, (self.y1 - self.y0) * um
        if scale is None:
            scale = next((s for s in STD if w_m * 1000 / s <= max_mm[0] and h_m * 1000 / s <= max_mm[1]), STD[-1])
        self.scale = scale
        self.ppm = DPI / 25.4 * 1000 / scale  # pixels per metre
        self.mx, self.top, self.bottom = int(15 / 25.4 * DPI), int(28 / 25.4 * DPI), int(30 / 25.4 * DPI)
        W = int(w_m * self.ppm) + 2 * self.mx
        H = int(h_m * self.ppm) + self.top + self.bottom
        self.img = Image.new("RGB", (W, H), "white")
        self.d = ImageDraw.Draw(self.img, "RGBA")
        self.fs = max(10, int(self.ppm * 0.45))
        self.font = _font(self.fs)
        self.small = _font(max(9, int(self.fs * 0.75)))
        self.big = _font(max(16, int(DPI * 0.16)))
        self.d.text((self.mx, int(8 / 25.4 * DPI)), title, fill="#14254A", font=self.big)
        self.d.text((self.mx, int(8 / 25.4 * DPI) + int(self.big.size * 1.3)),
                    f"Scale 1:{scale} at {DPI} dpi · {self.ppm:.1f} px/m · floor {floor.name} ({floor.key}) · units {um} m/unit",
                    fill="#5E6A7D", font=self.small)

    def P(self, x, y):
        um = self.f.unit_m
        return (self.mx + (x - self.x0) * um * self.ppm, self.top + (self.y1 - y) * um * self.ppm)

    def m(self, metres: float) -> float:
        return metres * self.ppm

    def linework(self, path: Path | None):
        if not path or not path.exists():
            return
        for pl in load_linework(str(path)):
            pts = [self.P(pl[i], pl[i + 1]) for i in range(0, len(pl) - 1, 2)]
            if len(pts) >= 2:
                self.d.line(pts, fill=(150, 160, 175, 255), width=1)

    def rooms(self, fill=True, labels=True, detail=True):
        for r in self.f.rooms:
            pts = [self.P(*p) for p in r.poly]
            col = CAT_COLOR.get(r.category, "#EEF1F6")
            dash = r.boundary == "estimated"
            self.d.polygon(pts, fill=_rgba(col, 110 if fill else 0), outline=_rgba("#C0392B" if dash else "#1F3B70", 255),
                           width=2 if dash else 1)
            if labels:
                cx, cy = self.P(*r.label_pt)
                t = r.name if not detail else f"{r.name}\n{r.rid} · {r.category} · {r.area_m2:.0f} m²" + \
                    (" · EST." if dash else "") + (f" · {r.comms}" if r.comms else "")
                self.d.multiline_text((cx, cy), t, fill="#14254A", font=self.small, anchor="mm", align="center")

    def wedge(self, d, clip_room=None, color="#E07A1F", alpha=70, half=WEDGE_HALF_RAD):
        r_px = self.m(d["_range"])
        cx, cy = self.P(d["x"], d["y"])
        a = d.get("a", 0) or 0
        box = [cx - r_px, cy - r_px, cx + r_px, cy + r_px]
        start, end = -a - math.degrees(half), -a + math.degrees(half)
        if clip_room is None:
            self.d.pieslice(box, start, end, fill=_rgba(color, alpha), outline=_rgba(color, 200), width=1)
            return
        mask = Image.new("L", self.img.size, 0)
        md = ImageDraw.Draw(mask)
        md.pieslice(box, start, end, fill=255)
        rm = Image.new("L", self.img.size, 0)
        ImageDraw.Draw(rm).polygon([self.P(*p) for p in clip_room.poly], fill=255)
        from PIL import ImageChops
        m2 = ImageChops.multiply(mask, rm).point(lambda v: alpha if v else 0)
        layer = Image.new("RGB", self.img.size, color)
        self.img.paste(layer, (0, 0), m2)
        self.d = ImageDraw.Draw(self.img, "RGBA")

    def symbol(self, d, label=True):
        s = d["sys"]
        c = BY_KEY[s].color
        x, y = self.P(d["x"], d["y"])
        r = max(4, self.m(0.35))
        if s == "cctv":
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=c, outline="white")
            a = math.radians(d.get("a", 0) or 0)
            self.d.line([x, y, x + 2.2 * r * math.cos(a), y - 2.2 * r * math.sin(a)], fill=c, width=2)
        elif s == "access":
            self.d.rectangle([x - r, y - r, x + r, y + r], fill=c, outline="white")
        elif s == "iptv":
            self.d.rectangle([x - 1.4 * r, y - 0.6 * r, x + 1.4 * r, y + 0.6 * r], fill=c, outline="white")
        elif s == "cabling":
            if d.get("sub") == "ap":
                self.d.ellipse([x - r, y - r, x + r, y + r], outline=c, width=3)
            else:
                self.d.rectangle([x - 0.5 * r, y - 0.5 * r, x + 0.5 * r, y + 0.5 * r], fill=c)
        elif s == "intercom":
            self.d.polygon([(x, y - 1.2 * r), (x + 1.2 * r, y), (x, y + 1.2 * r), (x - 1.2 * r, y)], fill=c, outline="white")
        else:
            self.d.polygon([(x, y - r), (x + r, y + 0.8 * r), (x - r, y + 0.8 * r)], fill=c, outline="white")
        if label:
            self.d.text((x + r + 2, y - r - 2), d["id"], fill="#14254A", font=self.small)

    def route(self, d, rt, over_color="#D0021B"):
        pts = [self.P(*p) for p in rt["pts"]]
        if rt.get("over"):
            self.d.line(pts, fill=over_color, width=4)
            x, y = pts[0]
            self.d.text((x + 4, y + 4), f"{d['id']} {rt['len_m']} m", fill=over_color, font=self.small)
        else:
            self.d.line(pts, fill=_rgba(BY_KEY[d["sys"]].color, 110), width=1)

    def legend(self, lines: list[str]):
        y = self.img.height - self.bottom + int(19 / 25.4 * DPI)  # below the scale bar and its labels
        self.d.multiline_text((self.mx, y), "\n".join(lines), fill="#3D475A", font=self.small)

    def scale_bar(self):
        um_w = (self.x1 - self.x0) * self.f.unit_m
        nice = [1, 2, 5, 10, 20, 25, 50, 100, 200]
        L = next((n for n in nice if n * 5 >= um_w / 4), 200)
        total = L * 5 if L * 5 <= um_w else L * 2
        segs = 5 if total == L * 5 else 2
        x0 = self.mx
        y = self.img.height - self.bottom + int(10 / 25.4 * DPI)
        h = 10
        for i in range(segs):
            xa, xb = x0 + self.m(i * total / segs), x0 + self.m((i + 1) * total / segs)
            self.d.rectangle([xa, y, xb, y + h], fill="#14254A" if i % 2 == 0 else "white", outline="#14254A")
        for i in range(segs + 1):
            xa = x0 + self.m(i * total / segs)
            self.d.text((xa, y + h + 3), f"{total / segs * i:g}", fill="#14254A", font=self.small, anchor="ma")
        self.d.text((x0 + self.m(total) + 10, y - 2), "m", fill="#14254A", font=self.font)

    def save(self, path: Path):
        self.scale_bar()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.img.save(path, dpi=(DPI, DPI), optimize=True)
        return path


def render_floor(out_dir: Path, tag: str, fl, devices, routes, selected, linework_path: Path | None, ranges) -> list[str]:
    """ranges: device id -> radius (m) used in the app for its target."""
    files = []
    rooms_by = {r.id: r for r in fl.rooms}
    cams = [dict(d, _range=ranges[d["id"]]) for d in devices if d["sys"] == "cctv" and d["id"] in ranges]
    base = f"{tag}_{fl.name}"

    c = Canvas(fl, f"{tag} · {fl.name} · (i) plan with rooms and labels — {len(fl.rooms)} rooms "
                   f"({sum(1 for r in fl.rooms if r.boundary == 'estimated')} estimated, red outline)")
    c.linework(linework_path)
    c.rooms()
    c.legend(["Room fill = category; label = name / id / category / area; red outline = estimated 4 m room (no boundary)"])
    files.append(str(c.save(out_dir / f"{base}_i_plan_rooms.png")))

    c = Canvas(fl, f"{tag} · {fl.name} · (ii) CCTV wedges as drawn in the app — {len(cams)} cameras")
    c.linework(linework_path)
    c.rooms(labels=True, detail=False)
    for d in cams:
        c.wedge(d)
    for d in cams:
        c.symbol(d)
    c.legend(["Wedge: half-angle 0.62 rad (71° total) for every camera type, radius = range for target, no clipping",
              "(same geometry as ui/src/components/FloorPlan.tsx)"])
    files.append(str(c.save(out_dir / f"{base}_ii_cctv_wedges_app.png")))

    # (iii) side by side at half the scale
    s2 = Canvas(fl, "", scale=None).scale * 2
    left = Canvas(fl, f"{tag} · {fl.name} · (iii-a) unclipped (as app)", scale=s2)
    left.linework(linework_path)
    left.rooms(labels=False)
    for d in cams:
        left.wedge(d)
    for d in cams:
        left.symbol(d, label=False)
    left.scale_bar()
    right = Canvas(fl, f"{tag} · {fl.name} · (iii-b) clipped to the camera's own room", scale=s2)
    right.linework(linework_path)
    right.rooms(labels=False)
    for d in cams:
        right.wedge(d, clip_room=rooms_by.get(d.get("room")), alpha=90)
    for d in cams:
        right.symbol(d, label=False)
    right.scale_bar()
    W = left.img.width + right.img.width + 20
    H = max(left.img.height, right.img.height)
    both = Image.new("RGB", (W, H), "white")
    both.paste(left.img, (0, 0))
    both.paste(right.img, (left.img.width + 20, 0))
    p = out_dir / f"{base}_iii_cctv_clipped_vs_unclipped.png"
    both.save(p, dpi=(DPI, DPI), optimize=True)
    files.append(str(p))

    for s in ("access", "iptv", "cabling", "intercom", "intrusion"):
        ds = [d for d in devices if d["sys"] == s]
        c = Canvas(fl, f"{tag} · {fl.name} · (iv) {BY_KEY[s].name} — {len(ds)} devices"
                       + ("" if s in selected else " (system not selected)"))
        c.linework(linework_path)
        c.rooms(labels=True, detail=False)
        for d in ds:
            c.symbol(d, label=(s != "cabling"))
        if s == "cabling":
            c.legend(["filled square = data outlet, ring = Wi-Fi AP outlet; ids omitted for legibility"])
        files.append(str(c.save(out_dir / f"{base}_iv_{s}.png")))

    rts = [(d, routes[d["id"]]) for d in devices if d["id"] in routes and d["sys"] in selected]
    over = [x for x in rts if x[1].get("over")]
    c = Canvas(fl, f"{tag} · {fl.name} · (v) cable routes — {len(rts)} links, {len(over)} over 90 m (red)")
    c.linework(linework_path)
    c.rooms(labels=True, detail=False)
    for d, rt in rts:
        if not rt.get("over"):
            c.route(d, rt)
    for d, rt in over:
        c.route(d, rt)
    for r in fl.comms_rooms:
        x, y = c.P(*r.centroid)
        c.d.rectangle([x - 8, y - 8, x + 8, y + 8], fill="#14254A")
        c.d.text((x + 10, y - 10), f"{r.comms} {r.name}", fill="#14254A", font=c.font)
    c.legend(["Thin line = routed device link (system colour); red = permanent link over 90 m; navy square = comms room",
              "Routes as computed by elv_engine/layout/routing.py (riser links show only the on-floor part)"])
    files.append(str(c.save(out_dir / f"{base}_v_routes.png")))
    return files
