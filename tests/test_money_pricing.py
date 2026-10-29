from decimal import Decimal

from elv_engine.money import amount_in_words, dec, fmt, fmt_price, r2
from elv_engine.pricing import factors, line_total, unit_cost, unit_sell

FX = {"USD": Decimal("3.65"), "EUR": Decimal("3.96"), "GBP": Decimal("4.62")}
COMM = {"markup": "35", "duty": "5", "freight": "3"}


def test_rounding_half_up_and_format():
    assert r2("2.675") == Decimal("2.68")
    assert r2("2.665") == Decimal("2.67")
    assert fmt(Decimal("4010502.21")) == "4,010,502.21"
    assert fmt(-1234.5) == "-1,234.50"
    assert fmt_price("1.85") == "1.85"
    assert fmt_price("0.125") == "0.125"
    assert dec("1,234.50") == Decimal("1234.50")
    assert dec("") is not None and dec("", None) is None


def test_amount_in_words():
    assert amount_in_words(Decimal("4010502.21")) == (
        "Qatari Riyals Four Million Ten Thousand Five Hundred Two and Dirhams Twenty-One Only")
    assert amount_in_words(Decimal("100")) == "Qatari Riyals One Hundred Only"


def test_imported_item_build_up():
    # Fixed dome 412 USD, 22% discount: 412 × 3.65 × 0.78 × 1.05 × 1.03 × 1.35 = 1712.5568 -> 1712.56
    f = factors(COMM)
    assert unit_sell("412", "USD", "22", "Device", FX, f) == Decimal("1712.56")
    assert line_total(Decimal("1712.56"), 38) == Decimal("65077.28")


def test_local_and_labour():
    f = factors(COMM)
    assert unit_sell("48", "QAR", "0", "Infrastructure", FX, f) == Decimal("64.80")  # no duty/freight on local
    assert unit_sell("145", "QAR", "0", "Labour", FX, f) == Decimal("195.75")  # labour: rate × markup only
    assert unit_sell("145", "QAR", "20", "Labour", FX, f) == Decimal("195.75")  # discount never applies to labour


def test_cost_vs_sell_and_missing():
    f = factors(COMM)
    c = unit_cost("100", "EUR", "10", "Software", FX, f)
    assert c == Decimal("100") * Decimal("3.96") * Decimal("0.9") * Decimal("1.05") * Decimal("1.03")
    assert unit_sell(None, "USD", "0", "Device", FX, f) is None
    assert unit_sell("10", "XYZ", "0", "Device", FX, f) is None  # unknown currency -> unpriced, never guessed


def test_labour_markup_override():
    f = factors({**COMM, "labour_markup": "20"})
    assert unit_sell("100", "QAR", "0", "Labour", FX, f) == Decimal("120.00")
