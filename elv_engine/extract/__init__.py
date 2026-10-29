"""Drawing import: DWG (via LibreDWG) / DXF / PDF -> rooms, doors, work positions, grids, scale."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable

from .dwg import DwgError, dwg_to_dxf

Progress = Callable[[float, str], None]

_FLOOR_PATTERNS = [
    (re.compile(r"\b(B\d)\b", re.I), lambda m: m.group(1).upper()),
    (re.compile(r"\b(GF|G\.F|GROUND)\b", re.I), lambda m: "GF"),
    (re.compile(r"\b(MEZZ|MZ)\w*", re.I), lambda m: "MZ"),
    (re.compile(r"\b(RF|ROOF)\b", re.I), lambda m: "RF"),
    (re.compile(r"\b(\d{1,2})\s?(?:ST|ND|RD|TH)?\s?F(?:LOOR|L)?\b", re.I), lambda m: f"{int(m.group(1))}F"),
    (re.compile(r"\b(?:L|LEVEL|LVL)[-_ ]?(\d{1,2})\b", re.I), lambda m: f"{int(m.group(1))}F"),
    (re.compile(r"\b(FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH)\b", re.I),
     lambda m: {"FIRST": "1F", "SECOND": "2F", "THIRD": "3F", "FOURTH": "4F", "FIFTH": "5F", "SIXTH": "6F"}[m.group(1).upper()]),
]


def guess_floor(name: str, fallback: str) -> str:
    stem = Path(name).stem.replace("_", " ")
    for pat, fn in _FLOOR_PATTERNS:
        m = pat.search(stem)
        if m:
            return fn(m)
    return fallback


def kind_of(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {".dwg": "dwg", ".dxf": "dxf", ".pdf": "pdf"}.get(ext, "unknown")


def extract_drawing(path: str, cache_dir: str, drawing_id: str, page: int = 0,
                    progress: Progress | None = None) -> dict:
    """Run extraction for one drawing; writes background PNG and linework into cache_dir."""
    from . import dxf as dxf_mod
    from . import pdf as pdf_mod
    from .render import render_png, save_linework

    progress = progress or (lambda f, m: None)
    kind = kind_of(path)
    os.makedirs(cache_dir, exist_ok=True)
    if kind == "dwg":
        progress(0.02, "Converting DWG with LibreDWG")
        dxf_path = os.path.join(cache_dir, f"{drawing_id}.dxf")
        dwg_to_dxf(path, dxf_path)
        res = dxf_mod.extract_dxf(dxf_path, lambda f, m: progress(0.1 + f * 0.75, m))
        res["kind"] = "dwg"
    elif kind == "dxf":
        res = dxf_mod.extract_dxf(path, lambda f, m: progress(f * 0.85, m))
    elif kind == "pdf":
        res = pdf_mod.extract_pdf(path, page, lambda f, m: progress(f * 0.85, m))
    else:
        raise ValueError(f"Unsupported file type: {Path(path).suffix}")

    progress(0.9, "Rendering background")
    lw_path = os.path.join(cache_dir, f"{drawing_id}.lines.json.gz")
    save_linework(res.pop("linework", []), lw_path)
    png_path = os.path.join(cache_dir, f"{drawing_id}.png")
    try:
        if kind == "pdf":
            bg = pdf_mod.render_page_png(path, page, png_path)
        else:
            from .render import load_linework
            bg = render_png(load_linework(lw_path), res["extents"], png_path)
        res["background"] = {"png": os.path.basename(png_path), "width": bg["width"], "height": bg["height"],
                             "extents": bg["extents"]}
    except Exception as exc:  # background is optional
        res["background"] = None
        res["warnings"].append(f"Background could not be rendered ({exc}).")
    res["linework_file"] = os.path.basename(lw_path)
    progress(1.0, "Done")
    return res


__all__ = ["extract_drawing", "guess_floor", "kind_of", "DwgError"]
