"""The residential Tariff Tiers are marginal bands (ADR 0002).

Fixed tariff (tests/factories.py): threshold 3,000 kWh/year, low 3 TRY/kWh, high 5 TRY/kWh.
"""

from decimal import Decimal

import pytest

from sunquote.domain.money import Currency, Money
from tests.factories import make_tariff


@pytest.mark.parametrize(
    ("annual_kwh", "expected_try"),
    [
        ("0", "0"),
        # entirely below the threshold: all energy at the low price
        ("2000", "6000"),
        # exactly at the threshold: 3,000 x 3
        ("3000", "9000"),
        # above: 3,000 x 3 + 3,000 x 5
        ("6000", "24000"),
        # fractions of a kWh are priced too
        ("3000.5", "9002.5"),
    ],
)
def test_annual_grid_cost_prices_only_the_part_above_the_threshold_at_the_high_tier(
    annual_kwh: str, expected_try: str
) -> None:
    cost = make_tariff().annual_cost(Decimal(annual_kwh))

    assert cost == Money(Decimal(expected_try), Currency.TRY)


def test_annual_grid_cost_is_continuous_across_the_threshold() -> None:
    tariff = make_tariff()

    just_below = tariff.annual_cost(Decimal("2999.99"))
    just_above = tariff.annual_cost(Decimal("3000.01"))

    assert just_above.amount - just_below.amount == Decimal("0.08")


def test_consumption_splits_into_low_and_high_tier_energy() -> None:
    tariff = make_tariff()

    assert tariff.split_by_tier(Decimal("2000")) == (Decimal("2000"), Decimal("0"))
    assert tariff.split_by_tier(Decimal("3000")) == (Decimal("3000"), Decimal("0"))
    assert tariff.split_by_tier(Decimal("6000")) == (Decimal("3000"), Decimal("3000"))


def test_negative_consumption_is_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        make_tariff().annual_cost(Decimal("-1"))
