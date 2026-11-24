"""Turkish display formatting: "." for thousands, "," for decimals, amounts in TL.

Rounding is not decided here: callers pass values already rounded by `sunquote.domain.rounding`.
"""

from datetime import date
from decimal import Decimal

from sunquote.domain import rounding

MONTH_NAMES = (
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
)


def format_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def format_decimal(value: Decimal) -> str:
    """The digits of `value` as they are, with a decimal comma and dotted thousands."""
    whole, _, fraction = format(value, "f").partition(".")
    text = format_int(int(whole)) if whole not in ("-0", "") else whole
    return f"{text},{fraction}" if fraction else text


def format_try(amount_try: int) -> str:
    return f"{format_int(amount_try)} TL"


def format_try_per_kwh(price_try_per_kwh: Decimal) -> str:
    return f"{format_decimal(rounding.round_try_per_kwh(price_try_per_kwh))} TL/kWh"


def format_percent(share: Decimal) -> str:
    """A share (0.25) as `%25`; one decimal is kept only when it is not zero."""
    percent = rounding.round_percent(share)
    text = format_decimal(percent)
    return f"%{text.removesuffix(',0')}"


def format_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")
