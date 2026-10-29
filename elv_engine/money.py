"""Money and quantity helpers.

All money is held as ``Decimal`` and rounded half-up to 2 decimals (QAR, dirhams).
Unit prices are rounded to 2 decimals before being multiplied by quantity, and line
totals are rounded again, so the PDF, the Excel formulas and the UI all agree.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def dec(value: Any, default: Decimal | None = ZERO) -> Decimal | None:
    """Parse a user or JSON value into Decimal. Accepts '1,234.50', 12, 1.5, None."""
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    text = str(value).strip().replace(",", "").replace(" ", "")
    if text == "" or text == "—" or text == "-":
        return default
    try:
        return Decimal(text)
    except InvalidOperation:
        return default


def r2(value: Decimal | int | float | str | None) -> Decimal:
    """Round half-up to 2 decimals."""
    d = dec(value)
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def pct(value: Any) -> Decimal:
    """Percentage (e.g. 35) to fraction (0.35)."""
    return (dec(value) or ZERO) / HUNDRED


def fmt(value: Decimal | float | int | None, blank: str = "") -> str:
    """1234567.8 -> '1,234,567.80'."""
    if value is None:
        return blank
    d = r2(value)
    sign = "-" if d < 0 else ""
    whole, frac = f"{abs(d):.2f}".split(".")
    return f"{sign}{int(whole):,}.{frac}"


def fmt_qty(value: Decimal | float | int | None) -> str:
    """Quantities: integers without decimals, otherwise up to 2 decimals."""
    if value is None:
        return ""
    d = dec(value)
    if d == d.to_integral_value():
        return f"{int(d):,}"
    return f"{d.quantize(CENT, rounding=ROUND_HALF_UP):,}"


def fmt_price(value: Decimal | float | int | None) -> str:
    """List prices keep up to 4 significant decimals (e.g. cable 1.85/m, 0.125)."""
    if value is None:
        return ""
    d = dec(value)
    if d == d.quantize(CENT):
        return fmt(d)
    text = f"{d.normalize():f}"
    whole, _, frac = text.partition(".")
    return f"{int(whole):,}.{frac[:4]}"


def to_json(value: Decimal | None) -> str | None:
    """Exact decimal string for JSON transport."""
    if value is None:
        return None
    return format(value, "f")


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
         "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
         "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _words_below_1000(n: int) -> str:
    parts = []
    if n >= 100:
        parts.append(_ONES[n // 100] + " Hundred")
        n %= 100
    if n >= 20:
        parts.append(_TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else ""))
    elif n > 0:
        parts.append(_ONES[n])
    return " ".join(parts)


def int_to_words(n: int) -> str:
    if n == 0:
        return "Zero"
    scales = [(10**9, "Billion"), (10**6, "Million"), (10**3, "Thousand")]
    parts = []
    for size, name in scales:
        if n >= size:
            parts.append(_words_below_1000(n // size) + " " + name)
            n %= size
    if n:
        parts.append(_words_below_1000(n))
    return " ".join(parts)


def amount_in_words(value: Decimal, currency: str = "Qatari Riyals", minor: str = "Dirhams") -> str:
    """4010502.21 -> 'Qatari Riyals Four Million Ten Thousand Five Hundred Two and Dirhams Twenty-One Only'."""
    d = r2(value)
    whole = int(d)
    cents = int((d - whole) * 100)
    text = f"{currency} {int_to_words(whole)}"
    if cents:
        text += f" and {minor} {int_to_words(cents)}"
    return text + " Only"
