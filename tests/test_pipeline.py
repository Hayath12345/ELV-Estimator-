"""End-to-end calculation tests on the synthetic two-floor project, including a golden
regression: any change to calculation results must be deliberate (regenerate with
`python -m tests.make_golden` and explain the change in the commit message).
"""
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from elv_engine import pipeline
from elv_engine.boq import all_lines
from elv_engine.money import ZERO

GOLDEN = Path(__file__).parent / "golden" / "sample_totals.json"


def run(project, lib):
    fx = pipeline.effective_fx(lib.fx(), project.get("fx_overrides"))
    return pipeline.compute(project, lib.as_map(), fx)


def summary(res) -> dict:
    t = res.boq["totals"]
    return {
        "devices": dict(sorted(Counter(d["sys"] for d in res.devices).items())),
        "shared": str(t["shared"]), "standalone": str(t["standalone"]), "combined": str(t["combined"]),
        "saving": str(t["saving"]), "network": str(t["network"]), "optional": str(t["optional"]),
        "systems": {k: {"standalone": str(v["standalone"]), "combined": str(v["combined"])}
                    for k, v in t["systems"].items()},
        "checks": f"{res.checks['passed']}/{res.checks['total']}",
    }


def test_all_checks_pass_and_totals_reconcile(sample_project, priced_library):
    res = run(sample_project, priced_library)
    failing = [(g["g"], r) for g in res.checks["groups"] for r in g["rows"] if not r["pass"]]
    assert not failing, failing
    t = res.boq["totals"]
    lines = all_lines(res.boq)
    base_lines = sum((l.total for l in lines if l.tab not in ("network", "optional")), ZERO)
    assert base_lines == t["base"] == t["combined"]
    assert t["saving"] == t["standalone"] - t["combined"] and t["saving"] > 0
    assert t["shared"] > 0 and t["network"] > 0
    for l in lines:
        assert l.total == l.total.quantize(Decimal("0.01"))
        if l.unit_qar is not None:
            assert l.unit_qar == l.unit_qar.quantize(Decimal("0.01"))


def test_golden_totals(sample_project, priced_library):
    got = summary(run(sample_project, priced_library))
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert got == want


def test_unpriced_items_block_issue(sample_project, library):
    res = run(sample_project, library)
    assert res.boq["totals"]["base"] == 0
    assert res.boq["unpriced"] > 0
    pricing = [g for g in res.checks["groups"] if g["g"] == "Pricing"][0]
    assert not pricing["rows"][0]["pass"]
    assert res.checks["blocking"] >= 1


def test_standalone_award(sample_project, priced_library):
    sample_project["systems"]["selected"] = ["cctv", "access"]
    sample_project["systems"]["combined"] = False
    res = run(sample_project, priced_library)
    t = res.boq["totals"]
    assert "shared" not in res.boq["tabs"] and "network" not in res.boq["tabs"]
    assert t["base"] == t["standalone"] == t["systems"]["cctv"]["standalone"] + t["systems"]["access"]["standalone"]
    assert t["saving"] == 0


def test_layout_edits_flow_into_boq(sample_project, priced_library):
    base = run(sample_project, priced_library)
    cams = [d for d in base.devices if d["sys"] == "cctv"]
    n0 = len(cams)
    edits = sample_project["layout_edits"]
    edits["deleted"].append(cams[0]["id"])
    edits["added"].append({"id": "C2-99", "sys": "cctv", "item": "cctv_bullet_8mp", "floor": "dw1",
                           "x": 10000, "y": 20000, "a": 0, "target": "Observe"})
    edits["added"].append({"id": "C2-98", "sys": "cctv", "item": "cctv_bullet_8mp", "floor": "dw1",
                           "x": 12000, "y": 20000, "a": 0, "target": "Observe"})
    edits["moved"][cams[1]["id"]] = [cams[1]["x"] + 5000, cams[1]["y"]]
    res = run(sample_project, priced_library)
    lines = {l.item: l for l in all_lines(res.boq) if l.tab == "cctv"}
    assert sum(1 for d in res.devices if d["sys"] == "cctv") == n0 + 1
    assert lines["cctv_bullet_8mp"].qty == 2
    assert lines["cctv_vms_cam"].qty == n0 + 1
    assert res.routes[cams[1]["id"]]["len_m"] != base.routes[cams[1]["id"]]["len_m"]


def test_quantity_override_is_reconciled(sample_project, priced_library):
    res = run(sample_project, priced_library)
    line = [l for l in all_lines(res.boq) if l.item == "cctv_dome_4mp"][0]
    sample_project["boq"]["overrides"][line.key] = {"qty": str(line.qty + 3)}
    res2 = run(sample_project, priced_library)
    assert res2.boq["totals"]["base"] > res.boq["totals"]["base"]
    counts = [g for g in res2.checks["groups"] if g["g"] == "Counts"][0]
    assert not counts["rows"][0]["pass"]  # layout vs BOQ mismatch is flagged


def test_fx_override_changes_imported_lines_only(sample_project, priced_library):
    res = run(sample_project, priced_library)
    sample_project["fx_overrides"] = {"USD": "3.70"}
    res2 = run(sample_project, priced_library)
    a = {l.key: l for l in all_lines(res.boq)}
    b = {l.key: l for l in all_lines(res2.boq)}
    for k, l in a.items():
        if l.currency == "USD" and l.list_price:
            assert b[k].unit_qar > l.unit_qar
        elif l.currency == "QAR":
            assert b[k].unit_qar == l.unit_qar
