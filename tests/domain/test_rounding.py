from decimal import Decimal

import pytest

from sunquote.domain import rounding


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("2.5", 3),
        ("2.4999", 2),
        ("1234.5", 1235),
        ("0.5", 1),
        ("100", 100),
        ("-2.5", -3),
    ],
)
def test_try_rounds_to_whole_lira_half_up(amount: str, expected: int) -> None:
    assert rounding.round_try(Decimal(amount)) == expected


@pytest.mark.parametrize(
    ("capacity", "expected"),
    [("8.804", "8.80"), ("8.805", "8.81"), ("8.8", "8.80"), ("0.125", "0.13")],
)
def test_capacity_kwp_rounds_to_two_decimals_half_up(capacity: str, expected: str) -> None:
    result = rounding.round_capacity_kwp(Decimal(capacity))

    assert result == Decimal(expected)
    assert result.as_tuple().exponent == -2


@pytest.mark.parametrize(
    ("energy", "expected"),
    [("12345.5", 12346), ("12345.49", 12345), ("0.4", 0)],
)
def test_kwh_rounds_to_whole_numbers_half_up(energy: str, expected: int) -> None:
    assert rounding.round_kwh(Decimal(energy)) == expected


@pytest.mark.parametrize(
    ("years", "expected"),
    [("6.25", "6.3"), ("6.24", "6.2"), ("6", "6.0")],
)
def test_payback_period_rounds_to_one_decimal_half_up(years: str, expected: str) -> None:
    result = rounding.round_payback_years(Decimal(years))

    assert result == Decimal(expected)
    assert result.as_tuple().exponent == -1
