"""Regenerate tests/golden/sample_totals.json (only after a deliberate calculation change)."""
import json
from datetime import date
import tempfile
from pathlib import Path

import pytest  # noqa: F401  (fixtures are reused directly)

from tests.conftest import TEST_PRICES
from tests.fixtures.sample_plans import make_set
from tests.test_pipeline import GOLDEN, run, summary


def main():
    import copy

    from elv_engine.extract.dxf import extract_dxf
    from elv_engine.pricelib import PriceLibrary
    from elv_engine.project import new_project
    with tempfile.TemporaryDirectory() as d:
        files = make_set(d)
        p = new_project({"name": "Sample HQ Fit-Out", "client": "Sample Client", "ref": "QTN-TEST-ELV-ALL-001"})
        for i, f in enumerate(files):
            ex = extract_dxf(f)
            ex.pop("linework", None)
            p["drawings"].append({"id": f"dw{i + 1}", "file": Path(f).name, "kind": "dxf", "floor": ["2F", "3F"][i],
                                  "order": i, "status": "Extracted", "extraction": copy.deepcopy(ex)})
        lib = PriceLibrary(str(Path(d) / "p.sqlite"))
        for r in lib.rows():
            lp, cur, disc, conf = TEST_PRICES[r["category"]]
            lib.update(r["key"], {"list_price": lp, "currency": cur, "discount": disc, "confidence": conf,
                                  "source": "Test price list", "date_checked": date.today().isoformat()})
        s = summary(run(p, lib))
        lib.close()
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps(s, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
