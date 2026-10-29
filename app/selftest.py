"""Headless end-to-end check of the bundled application (used by CI on the built .exe).

Creates a throw-away data folder, generates the two sample floor plans, runs extraction,
prices every catalogue item with test prices, runs all checks and generates every output.
If LibreDWG is bundled it also converts a DWG round trip (DXF -> DWG -> DXF) when
dxf2dwg is available. Exit code 0 = OK.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

PRICES = {"Device": ("250", "USD", "15", "H"), "Software": ("1200", "EUR", "10", "M"), "Licence": ("180", "EUR", "10", "H"),
          "Accessory": ("22.5", "USD", "10", "H"), "Infrastructure": ("640", "USD", "18", "H"), "Cable": ("1.85", "USD", "12", "H"),
          "Service": ("15000", "QAR", "0", "O"), "Labour": ("95", "QAR", "0", "L")}


def run(out_dir: str | None = None) -> int:
    t0 = time.time()
    tmp = Path(out_dir or tempfile.mkdtemp(prefix="elv-selftest-"))
    os.environ["ELV_NO_OPEN"] = "1"
    log = []

    def ok(msg):
        log.append(f"OK   {msg}")
        print(f"OK   {msg}", flush=True)
    try:
        from .api import dispatch
        from .backend import Backend
        from elv_engine.extract.dwg import find_tool, libredwg_version
        from elv_engine.samples import make_set

        b = Backend(data_dir=tmp / "data", projects_dir=tmp / "projects")

        def call(m, a=None):
            r = dispatch(b, m, a or {})
            if not r["ok"]:
                raise RuntimeError(f"{m}: {r['error']}")
            return r["data"]

        def wait(job_id):
            end = time.time() + 300
            while time.time() < end:
                j = call("get_job", {"id": job_id})
                if j["done"]:
                    if j["error"]:
                        raise RuntimeError(j["error"])
                    return j
                time.sleep(0.1)
            raise RuntimeError("job timeout")

        tool = find_tool("dwgread")
        ok(f"LibreDWG: {libredwg_version() or 'not bundled'} ({tool or '-'})")
        ok(f"UI bundle: {(Path(__file__).resolve().parents[1] / 'ui' / 'dist' / 'index.html').exists() or 'frozen'}")
        call("create_project", {"name": "Self-test", "client": "Self-test client", "ref": "SELFTEST-001"})
        files = make_set(str(tmp / "drawings"))
        dxf2dwg = find_tool("dxf2dwg")
        if dxf2dwg:
            import subprocess
            dwg = tmp / "drawings" / "roundtrip 2F.dwg"
            subprocess.run([dxf2dwg, "-y", "-o", str(dwg), files[0]], capture_output=True, timeout=120)
            if dwg.exists() and dwg.stat().st_size > 1000:
                files = [str(dwg), files[1]]
                ok("DXF -> DWG conversion with LibreDWG (DWG used for 2F)")
        wait(call("import_drawings", {"paths": files})["job"]["id"])
        dr = call("get_drawings")
        rooms = dr["rows"][0]["vals"] if dr["rows"] else []
        ok(f"Extraction: state={dr['state']} rooms per floor={rooms}")
        if dr["state"] not in ("results", "warn"):
            raise RuntimeError(f"extraction failed: {dr['errors']}")
        for row in call("get_prices")["rows"]:
            lp, cur, disc, conf = PRICES[row["category"]]
            call("update_price", {"key": row["key"], "patch": {"list_price": lp, "currency": cur, "discount": disc, "confidence": conf}})
        ck = call("get_checks")
        ok(f"Checks: {ck['passed']}/{ck['total']} passed, {ck['blocking']} blocking")
        st = call("project_state")
        ok(f"Combined base QAR {st['header']['baseF']} · network {st['header']['networkF']} · saving {st['header']['savingF']}")
        if ck["blocking"]:
            call("set_override", {"reason": "Self-test: issuing with failing checks for verification"})
        call("set_export_options", {"selected": {"cost": True}})
        j = wait(call("generate", {"bump": True, "change_log": "Self-test"})["job"]["id"])
        res = j["result"]
        ok(f"Outputs: {len(res['files'])} files in {res['folder']}")
        for f in res["files"]:
            p = Path(res["folder"]) / f
            if not p.exists() or p.stat().st_size == 0:
                raise RuntimeError(f"missing output {f}")
        b.lib.close()
        ok(f"Self-test passed in {time.time() - t0:.1f} s")
        return 0
    except Exception:
        traceback.print_exc()
        print("FAIL self-test", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else None))
