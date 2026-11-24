"""Turkish number and date formatting: "." for thousands, "," for decimals, amounts in TL."""

from datetime import date
from decimal import Decimal

import pytest

from sunquote.api import turkish


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (999, "999"),
        (1000, "1.000"),
        (159000, "159.000"),
        (1234567, "1.234.567"),
        (-12500, "-12.500"),
    ],
)
def test_integers_group_thousands_with_a_dot(value: int, expected: str) -> None:
    assert turkish.format_int(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("4.00", "4,00"), ("8.81", "8,81"), ("1234.5", "1.234,5"), ("0.4", "0,4"), ("12", "12")],
)
def test_decimals_use_a_comma_and_keep_their_digits(value: str, expected: str) -> None:
    assert turkish.format_decimal(Decimal(value)) == expected


def test_amounts_are_in_lira() -> None:
    assert turkish.format_try(159000) == "159.000 TL"
    assert turkish.format_try_per_kwh(Decimal("3.24")) == "3,24 TL/kWh"


def test_percentages_trim_a_trailing_zero_decimal() -> None:
    assert turkish.format_percent(Decimal("0.25")) == "%25"
    assert turkish.format_percent(Decimal("0.004")) == "%0,4"
    assert turkish.format_percent(Decimal("0.85")) == "%85"
    assert turkish.format_percent(Decimal("0")) == "%0"


def test_dates_are_day_month_year() -> None:
    assert turkish.format_date(date(2026, 12, 9)) == "09.12.2026"
