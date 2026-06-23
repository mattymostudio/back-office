"""Money, quantity, and date helpers.

All currency math runs through Decimal with explicit ROUND_HALF_UP so totals
are reproducible and never carry float drift. Formatting is presentation-only;
keep it out of the template.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

CENTS = Decimal("0.01")


def to_money(value) -> Decimal:
    """Coerce int/float/str/Decimal to a 2-dp Decimal."""
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


# Common currency symbols. Anything else renders as a prefixed code ("CHF ").
_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CAD": "$", "AUD": "$"}


def fmt_money(value, currency: str = "USD") -> str:
    """Format a number as a currency string, e.g. $1,234.50 or €1.234,50.

    USD-style grouping is used for all currencies for simplicity; the symbol or
    code is driven by `currency`. JPY renders with no decimal places.
    """
    d = to_money(value)
    sign = "-" if d < 0 else ""
    d = abs(d)
    if currency.upper() == "JPY":
        whole = f"{int(d):,}"
        body = whole
    else:
        whole, _, frac = f"{d:.2f}".partition(".")
        body = f"{int(whole):,}.{frac}"
    sym = _SYMBOLS.get(currency.upper())
    if sym:
        return f"{sign}{sym}{body}"
    return f"{sign}{currency.upper()} {body}"


def fmt_qty(value) -> str:
    """Format a quantity — integer if whole, else up to 4 trimmed decimals."""
    d = Decimal(str(value))
    if d == d.to_integral():
        return str(int(d))
    return str(d.normalize())


def coerce_date(value):
    """Return a date from a date/datetime/'YYYY-MM-DD' str, or None."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def fmt_date(value) -> str:
    """Format a date as 'June 15, 2026'. Passes through unparseable values."""
    d = coerce_date(value)
    if d is None:
        return str(value)
    # %-d is non-portable (fails on Windows); strip the leading zero ourselves.
    return d.strftime("%B %d, %Y").replace(" 0", " ", 1)
