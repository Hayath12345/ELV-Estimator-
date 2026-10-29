"""Render extracted linework to a background PNG (and reuse it as vectors in layout PDFs)."""
from __future__ import annotations

import gzip
import json
from pathlib import Path


def save_linework(linework: list[list[float]], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(linework, fh, separators=(",", ":"))


def load_linework(path: str) -> list[list[float]]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def draw_linework(page, linework, extents, rect, color=(0.36, 0.41, 0.49), width=0.35):
    """Draw linework (drawing units, y up) into a PyMuPDF page rectangle, keeping aspect."""
    import fitz
    x0, y0, x1, y1 = extents
    sx = rect.width / max(x1 - x0, 1e-9)
    sy = rect.height / max(y1 - y0, 1e-9)
    s = min(sx, sy)
    ox = rect.x0 + (rect.width - (x1 - x0) * s) / 2
    oy = rect.y0 + (rect.height - (y1 - y0) * s) / 2

    def tx(x, y):
        return fitz.Point(ox + (x - x0) * s, oy + (y1 - y) * s)

    shape = page.new_shape()
    n = 0
    for pl in linework:
        pts = [tx(pl[i], pl[i + 1]) for i in range(0, len(pl) - 1, 2)]
        if len(pts) >= 2:
            shape.draw_polyline(pts)
            n += 1
            if n % 5000 == 0:  # commit in batches to bound memory
                shape.finish(color=color, width=width, closePath=False)
                shape.commit()
                shape = page.new_shape()
    shape.finish(color=color, width=width, closePath=False)
    shape.commit()
    return s, ox, oy


def render_png(linework, extents, out_png: str, max_px: int = 4096) -> dict:
    import fitz
    x0, y0, x1, y1 = extents
    w, h = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    if w >= h:
        pw, ph = 1600.0, 1600.0 * h / w
    else:
        pw, ph = 1600.0 * w / h, 1600.0
    doc = fitz.open()
    page = doc.new_page(width=pw, height=ph)
    draw_linework(page, linework, extents, page.rect, width=0.45)
    zoom = max_px / max(pw, ph)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    pix.save(out_png)
    doc.close()
    return {"png": out_png, "width": pix.width, "height": pix.height, "extents": list(extents)}
