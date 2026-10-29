"""Popular quotation currencies with indicative exchange rates to QAR.

The rates below are indicative defaults only (QAR is pegged at 3.64 per USD; the USD,
EUR and GBP values follow the company rates in the design). Every rate is editable in
the app (Settings and BOQ commercial controls) and the "as of" date is recorded with
each change. Rates are never fetched from the internet unless the user asks for it.
"""
from __future__ import annotations

from decimal import Decimal

BASE = "QAR"

# code, name, symbol, indicative QAR per 1 unit
_RAW: list[tuple[str, str, str, str]] = [
    ("QAR", "Qatari Riyal", "QR", "1"),
    ("USD", "US Dollar", "$", "3.65"),
    ("EUR", "Euro", "€", "3.96"),
    ("GBP", "British Pound", "£", "4.62"),
    ("SAR", "Saudi Riyal", "SR", "0.9733"),
    ("AED", "UAE Dirham", "AED", "0.9939"),
    ("KWD", "Kuwaiti Dinar", "KD", "11.90"),
    ("BHD", "Bahraini Dinar", "BD", "9.708"),
    ("OMR", "Omani Rial", "RO", "9.493"),
    ("JOD", "Jordanian Dinar", "JD", "5.148"),
    ("EGP", "Egyptian Pound", "E£", "0.0755"),
    ("INR", "Indian Rupee", "₹", "0.0415"),
    ("PKR", "Pakistani Rupee", "Rs", "0.0129"),
    ("LKR", "Sri Lankan Rupee", "Rs", "0.0121"),
    ("BDT", "Bangladeshi Taka", "৳", "0.0300"),
    ("PHP", "Philippine Peso", "₱", "0.0630"),
    ("CNY", "Chinese Yuan", "¥", "0.5130"),
    ("JPY", "Japanese Yen", "¥", "0.02430"),
    ("KRW", "South Korean Won", "₩", "0.002630"),
    ("HKD", "Hong Kong Dollar", "HK$", "0.4685"),
    ("SGD", "Singapore Dollar", "S$", "2.810"),
    ("MYR", "Malaysian Ringgit", "RM", "0.8690"),
    ("THB", "Thai Baht", "฿", "0.1110"),
    ("IDR", "Indonesian Rupiah", "Rp", "0.000223"),
    ("TWD", "New Taiwan Dollar", "NT$", "0.1180"),
    ("AUD", "Australian Dollar", "A$", "2.390"),
    ("NZD", "New Zealand Dollar", "NZ$", "2.120"),
    ("CAD", "Canadian Dollar", "C$", "2.630"),
    ("CHF", "Swiss Franc", "CHF", "4.560"),
    ("SEK", "Swedish Krona", "kr", "0.3840"),
    ("NOK", "Norwegian Krone", "kr", "0.3580"),
    ("DKK", "Danish Krone", "kr", "0.5308"),
    ("PLN", "Polish Zloty", "zł", "0.9860"),
    ("CZK", "Czech Koruna", "Kč", "0.1580"),
    ("HUF", "Hungarian Forint", "Ft", "0.01000"),
    ("TRY", "Turkish Lira", "₺", "0.0890"),
    ("RUB", "Russian Ruble", "₽", "0.0450"),
    ("ZAR", "South African Rand", "R", "0.2090"),
    ("BRL", "Brazilian Real", "R$", "0.6760"),
    ("MXN", "Mexican Peso", "MX$", "0.1970"),
]

CURRENCIES: list[dict] = [
    {"code": c, "name": n, "symbol": s, "rate": Decimal(r)} for c, n, s, r in _RAW
]
CODES = [c["code"] for c in CURRENCIES]
DEFAULT_RATES: dict[str, Decimal] = {c["code"]: c["rate"] for c in CURRENCIES}
NAMES = {c["code"]: c["name"] for c in CURRENCIES}

# Shown in the top bar, like the design ("USD 3.65 · EUR 3.96 · GBP 4.62").
TICKER = ["USD", "EUR", "GBP"]
