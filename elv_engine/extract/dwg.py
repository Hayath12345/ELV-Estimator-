"""DWG reading through LibreDWG (GPLv3, bundled as a separate program under vendor/libredwg).

``dwgread`` converts the DWG to DXF in a cache folder; ``dxf.py`` then parses the DXF.
LibreDWG runs as a separate process, so the app never links GPL code.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


class DwgError(RuntimeError):
    pass


def _candidates() -> list[Path]:
    roots = []
    if getattr(sys, "frozen", False):
        roots.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)))
        roots.append(Path(sys.executable).parent)
    roots.append(Path(__file__).resolve().parents[2])
    env = os.environ.get("ELV_LIBREDWG_DIR")
    out = [Path(env)] if env else []
    for r in roots:
        out += [r / "vendor" / "libredwg" / "bin", r / "vendor" / "libredwg"]
    return out


def find_tool(name: str = "dwgread") -> str | None:
    exe = name + (".exe" if os.name == "nt" else "")
    for d in _candidates():
        p = d / exe
        if p.is_file():
            return str(p)
    return shutil.which(name)


def dwg_to_dxf(dwg_path: str, out_dxf: str, timeout: int = 300) -> str:
    """Convert DWG -> DXF. Raises DwgError with a user-facing message on failure."""
    tool = find_tool("dwgread")
    alt = find_tool("dwg2dxf")
    if not tool and not alt:
        raise DwgError("LibreDWG (dwgread) is not installed. Reinstall ELV Estimator or upload the DXF/PDF set instead.")
    Path(out_dxf).parent.mkdir(parents=True, exist_ok=True)
    if os.path.exists(out_dxf):
        os.remove(out_dxf)
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    attempts = []
    # dwg2dxf is LibreDWG's dedicated converter; dwgread -O DXF is the fallback.
    if alt:
        attempts.append([alt, "-y", "-o", out_dxf, dwg_path])
    if tool:
        attempts.append([tool, "-O", "DXF", "-o", out_dxf, dwg_path])
    last = ""
    for cmd in attempts:
        if os.path.exists(out_dxf):
            os.remove(out_dxf)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout, creationflags=flags,
                                  cwd=str(Path(cmd[0]).parent))
        except subprocess.TimeoutExpired:
            last = "conversion timed out"
            continue
        except OSError as exc:
            last = str(exc)
            continue
        if _looks_like_dxf(out_dxf):
            return out_dxf
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or [f"exit code {proc.returncode}"]
        last = f"{Path(cmd[0]).name}: {tail[0]}"
    raise DwgError("The file could not be read — it may be password-protected or saved in an unsupported "
                   f"format. Re-save as AutoCAD 2018 DWG, or upload the PDF set instead. ({last})")


def _looks_like_dxf(path: str) -> bool:
    """ASCII DXF (group code 0 + SECTION near the top) or binary DXF sentinel."""
    try:
        if not os.path.exists(path) or os.path.getsize(path) < 1000:
            return False
        with open(path, "rb") as fh:
            head = fh.read(4096)
        if head.startswith(b"AutoCAD Binary DXF"):
            return True
        return b"SECTION" in head and (b"HEADER" in head or b"CLASSES" in head or b"TABLES" in head or b"ENTITIES" in head)
    except OSError:
        return False


def libredwg_version() -> str | None:
    tool = find_tool("dwgread")
    if not tool:
        return None
    try:
        p = subprocess.run([tool, "--version"], capture_output=True, text=True, errors="replace", timeout=10,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        return (p.stdout or p.stderr).strip().splitlines()[0]
    except Exception:
        return None
