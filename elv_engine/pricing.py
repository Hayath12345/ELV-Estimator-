"""Unit price build-up (all results in QAR, 2 decimals).

    Imported item (currency ≠ QAR):  list × FX × (1 − disc) × (1 + duty) × (1 + freight) × (1 + markup)
    Local item (QAR):                list × (1 − disc) × (1 + markup)
    Labour (rate per hour):          rate × FX × (1 + labour markup)

The unit price is rounded to 2 decimals, then line total = round(unit × qty, 2).
The same formula is written into the Excel workbook so both always agree.
"""
from __future__ import annotations

from decimal import Decimal

from .money import ONE, ZERO, dec, pct, r2


def factors(commercial: dict) -> dict[str, Decimal]:
    mk = pct(commercial.get("markup", 0))
    lm = commercial.get("labour_markup")
    return {
        "markup": mk,
        "labour_markup": pct(lm) if lm not in (None, "") else mk,
        "duty": pct(commercial.get("duty", 0)),
        "freight": pct(commercial.get("freight", 0)),
    }


def fx_rate(currency: str, fx: dict[str, Decimal]) -> Decimal | None:
    if not currency or currency == "QAR":
        return ONE
    r = fx.get(currency)
    return dec(r, None) if r is not None else None


def unit_cost(list_price, currency: str, discount, category: str, fx: dict, f: dict) -> Decimal | None:
    """Landed cost before markup (internal costing)."""
    lp = dec(list_price, None)
    if lp is None:
        return None
    rate = fx_rate(currency, fx)
    if rate is None:
        return None
    if category == "Labour":
        return lp * rate
    disc = ONE - pct(discount)
    if currency == "QAR":
        return lp * disc
    return lp * rate * disc * (ONE + f["duty"]) * (ONE + f["freight"])


def unit_sell(list_price, currency: str, discount, category: str, fx: dict, f: dict) -> Decimal | None:
    c = unit_cost(list_price, currency, discount, category, fx, f)
    if c is None:
        return None
    mk = f["labour_markup"] if category == "Labour" else f["markup"]
    return r2(c * (ONE + mk))


def line_total(unit: Decimal | None, qty) -> Decimal:
    if unit is None:
        return ZERO
    return r2(unit * (dec(qty) or ZERO))
