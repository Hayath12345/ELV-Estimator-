from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fixtures.sample_plans import make_set  # noqa: E402

# Deterministic test prices: (list price, currency, discount %, confidence). Labour in QAR/hr.
TEST_PRICES = {
    "Device": ("250", "USD", "15", "H"),
    "Software": ("1200", "EUR", "10", "M"),
    "Licence": ("180", "EUR", "10", "H"),
    "Accessory": ("22.5", "USD", "10", "H"),
    "Infrastructure": ("640", "USD", "18", "H"),
    "Cable": ("1.85", "USD", "12", "H"),
    "Service": ("15000", "QAR", "0", "O"),
    "Labour": ("95", "QAR", "0", "L"),
}


@pytest.fixture(scope="session")
def sample_dxfs(tmp_path_factory):
    d = tmp_path_factory.mktemp("drawings")
    return make_set(str(d))


@pytest.fixture()
def library(tmp_path):
    from elv_engine.pricelib import PriceLibrary
    lib = PriceLibrary(str(tmp_path / "prices.sqlite"))
    yield lib
    lib.close()


@pytest.fixture()
def priced_library(library):
    for r in library.rows():
        lp, cur, disc, conf = TEST_PRICES[r["category"]]
        library.update(r["key"], {"list_price": lp, "currency": cur, "discount": disc, "confidence": conf,
                                  "source": "Test price list", "date_checked": date.today().isoformat()})
    return library


@pytest.fixture(scope="session")
def extracted(sample_dxfs):
    from elv_engine.extract.dxf import extract_dxf
    out = []
    for f in sample_dxfs:
        ex = extract_dxf(f)
        ex.pop("linework", None)
        out.append(ex)
    return out


@pytest.fixture()
def sample_project(sample_dxfs, extracted):
    import copy
    from elv_engine.project import new_project
    p = new_project({"name": "Sample HQ Fit-Out", "client": "Sample Client", "ref": "QTN-TEST-ELV-ALL-001"})
    for i, (f, ex) in enumerate(zip(sample_dxfs, extracted)):
        p["drawings"].append({"id": f"dw{i + 1}", "file": Path(f).name, "kind": "dxf", "floor": ["2F", "3F"][i],
                              "order": i, "status": "Extracted", "extraction": copy.deepcopy(ex)})
    return p
