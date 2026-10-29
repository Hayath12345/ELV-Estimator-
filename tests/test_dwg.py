"""DWG path through LibreDWG (runs where the tools are installed — CI fetches them).

The sample plan is written as an R2000 DXF, converted to DWG with dxf2dwg, then read back
through the app's normal DWG route (dwgread -> DXF -> extraction)."""
import shutil
import subprocess

import pytest

from elv_engine.extract import extract_drawing
from elv_engine.extract.dwg import find_tool

pytestmark = pytest.mark.skipif(not find_tool("dwgread"), reason="LibreDWG not installed")


def test_dwg_round_trip(tmp_path):
    import ezdxf
    from elv_engine.samples import make_floor
    dxf = tmp_path / "plan 2F.dxf"
    make_floor(str(dxf), 2, with_mdf=False)
    doc = ezdxf.readfile(str(dxf))
    doc.dxfversion = "AC1015"  # R2000 — the DXF version LibreDWG converts most reliably
    r2000 = tmp_path / "plan2000.dxf"
    doc.saveas(str(r2000))
    tool = find_tool("dxf2dwg")
    if not tool:
        pytest.skip("dxf2dwg not available to create a test DWG")
    dwg = tmp_path / "plan 2F.dwg"
    p = subprocess.run([tool, "-y", "-o", str(dwg), str(r2000)], capture_output=True, text=True, timeout=180)
    if not dwg.exists() or dwg.stat().st_size < 1000:
        pytest.skip(f"dxf2dwg could not write a DWG: {p.stderr[-300:]}")
    res = extract_drawing(str(dwg), str(tmp_path / "cache"), "dw1")
    names = {r["name"] for r in res["rooms"]}
    assert res["kind"] == "dwg"
    assert len(res["rooms"]) >= 35, (len(res["rooms"]), sorted(names)[:10])
    assert "IDF-2W" in names
    assert len(res["doors"]) >= 30
    assert res["unit_m"] == pytest.approx(0.001)


def test_unreadable_dwg_reports_clear_error(tmp_path):
    from elv_engine.extract.dwg import DwgError
    bad = tmp_path / "broken.dwg"
    bad.write_bytes(b"AC1032" + b"\x00" * 4000)
    with pytest.raises(DwgError) as e:
        extract_drawing(str(bad), str(tmp_path / "cache"), "dwx")
    assert "could not be read" in str(e.value)
