"""Small, dependency-free 2D geometry helpers (drawing units)."""
from __future__ import annotations

import math
from typing import Iterable, Sequence

Pt = tuple[float, float]


def area(poly: Sequence[Pt]) -> float:
    """Absolute polygon area (shoelace)."""
    n = len(poly)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def centroid(poly: Sequence[Pt]) -> Pt:
    n = len(poly)
    if n == 0:
        return (0.0, 0.0)
    a = 0.0
    cx = cy = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(a) < 1e-12:
        return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
    a *= 0.5
    return (cx / (6 * a), cy / (6 * a))


def bbox(points: Iterable[Pt]) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for x, y in points:
        xs.append(x)
        ys.append(y)
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def contains(poly: Sequence[Pt], p: Pt) -> bool:
    """Ray-casting point-in-polygon."""
    x, y = p
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            xin = (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
            if x < xin:
                inside = not inside
        j = i
    return inside


def dist(a: Pt, b: Pt) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def seg_dist(p: Pt, a: Pt, b: Pt) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return dist(p, (ax + t * dx, ay + t * dy))


def poly_dist(poly: Sequence[Pt], p: Pt) -> float:
    """Distance from point to polygon boundary (0 is on the edge)."""
    n = len(poly)
    return min(seg_dist(p, poly[i], poly[(i + 1) % n]) for i in range(n)) if n else float("inf")


def nearest_vertex(poly: Sequence[Pt], p: Pt) -> Pt:
    return min(poly, key=lambda v: dist(v, p))


def inset_toward(p: Pt, target: Pt, d: float) -> Pt:
    """Move p toward target by d."""
    L = dist(p, target)
    if L < 1e-9:
        return p
    t = min(1.0, d / L)
    return (p[0] + (target[0] - p[0]) * t, p[1] + (target[1] - p[1]) * t)


def grid_points(poly: Sequence[Pt], n: int, margin: float = 0.0) -> list[Pt]:
    """Return n points spread evenly inside a polygon (grid over its bbox, kept if inside)."""
    if n <= 0:
        return []
    x0, y0, x1, y1 = bbox(poly)
    w, h = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    c = centroid(poly)
    if n == 1:
        return [c if contains(poly, c) else _interior_point(poly)]
    # columns/rows proportional to aspect ratio
    for extra in range(0, 6):
        cols = max(1, round(math.sqrt(n * w / h))) + extra
        rows = max(1, math.ceil(n / cols)) + extra
        pts = []
        for r in range(rows):
            for k in range(cols):
                px = x0 + margin + (w - 2 * margin) * (k + 0.5) / cols
                py = y0 + margin + (h - 2 * margin) * (r + 0.5) / rows
                if contains(poly, (px, py)):
                    pts.append((px, py))
        if len(pts) >= n:
            return spread(pts, n)
    pts = pts or [c]
    while len(pts) < n:
        pts.append(pts[len(pts) % max(1, len(pts))])
    return pts[:n]


def _interior_point(poly: Sequence[Pt]) -> Pt:
    x0, y0, x1, y1 = bbox(poly)
    for fy in (0.5, 0.35, 0.65, 0.2, 0.8):
        y = y0 + (y1 - y0) * fy
        xs = []
        n = len(poly)
        for i in range(n):
            (ax, ay), (bx, by) = poly[i], poly[(i + 1) % n]
            if (ay > y) != (by > y):
                xs.append(ax + (y - ay) * (bx - ax) / ((by - ay) or 1e-12))
        xs.sort()
        if len(xs) >= 2:
            return ((xs[0] + xs[1]) / 2, y)
    return centroid(poly)


def spread(items: list, n: int) -> list:
    """Pick n items evenly spaced from a list."""
    if n >= len(items):
        return list(items)
    return [items[int(i * len(items) / n)] for i in range(n)]


def principal_axis(poly: Sequence[Pt]) -> tuple[Pt, Pt, float, float]:
    """For elongated rooms (corridors): returns (start, end, length, width) of the bbox long axis."""
    x0, y0, x1, y1 = bbox(poly)
    w, h = x1 - x0, y1 - y0
    if w >= h:
        cy = (y0 + y1) / 2
        return (x0, cy), (x1, cy), w, h
    cx = (x0 + x1) / 2
    return (cx, y0), (cx, y1), h, w


def along(a: Pt, b: Pt, n: int) -> list[Pt]:
    """n points evenly along segment a-b (centred)."""
    return [(a[0] + (b[0] - a[0]) * (i + 0.5) / n, a[1] + (b[1] - a[1]) * (i + 0.5) / n) for i in range(n)]


def angle_deg(a: Pt, b: Pt) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
