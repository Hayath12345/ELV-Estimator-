"""Test-only helper: copy the functions a reviewer needs verbatim (with line numbers) into
code_excerpts.md (section 12 of the test report).

Usage: python tests/diagnostics/code_excerpts.py OUT_FILE
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# (topic, file, [python function/class/assignment names]) — for .tsx use ("marker", start_text, end_text)
PY = [
    ("Read DWG/PDF text and decide room labels", "elv_engine/extract/dwg.py", ["dwg_to_dxf", "_looks_like_dxf"]),
    ("Read DWG/PDF text and decide room labels", "elv_engine/extract/dxf.py",
     ["RE_ROOM_LAYER", "RE_LABEL_LAYER", "RE_DOOR", "RE_DOOR_TAG", "_walk", "_text_of", "_clean", "extract_dxf", "_robust_extents",
      "_grids", "_is_grid_label", "_dim_ratio", "_viewport_scale", "_doors"]),
    ("Read DWG/PDF text and decide room labels", "elv_engine/extract/pdf.py", ["extract_pdf", "_merge_lines"]),
    ("Decide room labels / de-duplicate rooms (label -> boundary matching, orphan merge)", "elv_engine/extract/common.py",
     ["RE_AREA_TEXT", "_is_name", "assign_labels", "finalise_rooms"]),
    ("Classify rooms", "elv_engine/extract/classify.py",
     ["_RULES", "classify", "comms_role", "looks_like_room_name", "_ROOM_NO", "looks_like_room_number", "OCCUPIED", "PRIVATE"]),
    ("Units / scale", "elv_engine/extract/common.py", ["UNITS_TO_M", "STD_SCALES", "standard_scale", "_plausible", "infer_units"]),
    ("Units / scale (floor model, calibration fallback)", "elv_engine/layout/floor.py", ["build_floor", "_boundary_toward"]),
    ("Units / scale (two-point calibration API)", "app/backend.py", ["calibrate"]),
    ("Place cameras (all categories incl. PARKING), aim angle", "elv_engine/layout/place.py",
     ["_corner", "_wall_opposite", "_door_pt", "place_cctv", "camera_range"]),
    ("Place other systems (for overlap analysis)", "elv_engine/layout/place.py",
     ["_offset", "place_access", "place_cabling", "place_intercom", "place_intrusion", "place_all"]),
    ("Geometry helpers used by placement", "elv_engine/geometry.py", ["grid_points", "principal_axis", "along", "angle_deg", "inset_toward"]),
    ("FOV radius / HFOV inputs", "elv_engine/catalog.py", ["CAMERA_OPTICS", "CAMERA_BITRATE"]),
    ("FOV in the device panel (range per target)", "app/backend.py", ["get_layout"]),
    ("Draw wedges in layout PDFs (no clipping)", "elv_engine/outputs/pdf_layout.py", ["build"]),
    ("Route cables", "elv_engine/layout/routing.py", ["LIMITED", "Spine", "spines", "_len", "route_pts", "assign", "mdf_of", "backbone", "trunk_length_m"]),
    ("Placement rules / config", "elv_engine/params.py", ["ROOM_CATEGORY_LABELS", "SYSTEM_PARAMS", "COMMERCIAL_DEFAULTS", "COMMS_DEFAULTS"]),
]
TSX = [
    ("Draw wedges in the app (FloorPlan.tsx, no clipping)", "ui/src/components/FloorPlan.tsx", "{showFov && layers.cctv", "})}"),
    ("Live route preview in the app (FloorPlan.tsx)", "ui/src/components/FloorPlan.tsx", "const preview = (x: number, y: number)", "  }\n"),
]


def py_ranges(path: Path, names: list[str]) -> list[tuple[str, int, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in tree.body:
        nm = None
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            nm = node.name
        elif isinstance(node, ast.Assign) and node.targets and isinstance(node.targets[0], ast.Name):
            nm = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            nm = node.target.id
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name in names:
                    out.append((f"{node.name}.{sub.name}", sub.lineno, sub.end_lineno))
        if nm in names:
            start = node.lineno
            if getattr(node, "decorator_list", None):
                start = min(d.lineno for d in node.decorator_list)
            out.append((nm, start, node.end_lineno))
    found = {n for n, _, _ in out} | {n.split(".")[-1] for n, _, _ in out}
    missing = [n for n in names if n not in found]
    return out, missing


def main(out_file: str) -> None:
    parts = ["# Code excerpts (verbatim)", "",
             f"Repository commit: see environment.txt. Paths are relative to the repository root. "
             f"Line numbers are 1-based and refer to that commit.", ""]
    for topic, rel, names in PY:
        path = ROOT / rel
        lines = path.read_text(encoding="utf-8").splitlines()
        ranges, missing = py_ranges(path, names)
        parts.append(f"## {topic}\n\n`{rel}`" + (f" — not found: {missing}" if missing else ""))
        for nm, a, b in ranges:
            parts.append(f"\n### `{rel}:{a}-{b}` — `{nm}`\n")
            parts.append("```python")
            parts += [f"{i:4d}  {lines[i - 1]}" for i in range(a, b + 1)]
            parts.append("```")
        parts.append("")
    for topic, rel, start, end in TSX:
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        i0 = next((i for i, l in enumerate(lines) if start in l), None)
        if i0 is None:
            parts.append(f"## {topic}\n\n`{rel}` — marker not found: {start!r}\n")
            continue
        depth, i1 = 0, i0
        for i in range(i0, min(len(lines), i0 + 80)):
            depth += lines[i].count("(") + lines[i].count("{") - lines[i].count(")") - lines[i].count("}")
            i1 = i
            if i > i0 and depth <= 0:
                break
        parts.append(f"## {topic}\n\n### `{rel}:{i0 + 1}-{i1 + 1}`\n")
        parts.append("```tsx")
        parts += [f"{i + 1:4d}  {lines[i]}" for i in range(i0, i1 + 1)]
        parts.append("```\n")
    Path(out_file).write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"wrote {out_file} ({sum(1 for _ in parts)} blocks)")


if __name__ == "__main__":
    main(sys.argv[1])
