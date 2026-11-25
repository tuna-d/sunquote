"""The residential Tariff Tiers are marginal bands applied month by month (ADR 0002, ADR 0005).

Fixed tariff (tests/factories.py): daily allowance 8 kWh, low 3 TRY/kWh, high 5 TRY/kWh. A
month's threshold is 8 x its days in a 365-day year: January, March, May, July, August, October
and December 248 kWh, April, June, September and November 240 kWh, February 224 kWh (the sum
is 2,920 kWh). Expected values were worked out by hand.
"""

from decimal import Decimal

import pytest

from sunquote.domain.money import Currency, Money
from sunquote.domain.tariff import MONTHS_PER_YEAR
from tests.factories import make_tariff

JANUARY, FEBRUARY, APRIL = 1, 2, 4


@pytest.mark.parametrize(
    ("month", "threshold_kwh"),
    [(1, "248"), (2, "224"), (3, "248"), (4, "240"), (6, "240"), (8, "248"), (12, "248")],
)
def test_a_months_threshold_is_the_daily_allowance_times_its_days(
    month: int, threshold_kwh: str
) -> None:
    assert make_tariff().monthly_threshold_kwh(month) == Decimal(threshold_kwh)


def test_the_twelve_thresholds_add_up_to_the_annual_allowance() -> None:
    thresholds = [make_tariff().monthly_threshold_kwh(m) for m in range(1, MONTHS_PER_YEAR + 1)]

    assert sum(thresholds) == Decimal("2920")


def test_the_thresholds_follow_the_daily_allowance() -> None:
    assert make_tariff(daily_allowance_kwh="10").monthly_threshold_kwh(FEBRUARY) == Decimal("280")


@pytest.mark.parametrize("month", [0, 13, -1])
def test_a_month_outside_one_to_twelve_is_rejected(month: int) -> None:
    with pytest.raises(ValueError, match="month"):
        make_tariff().monthly_threshold_kwh(month)


@pytest.mark.parametrize(
    ("month", "kwh", "expected_try"),
    [
        (JANUARY, "0", "0"),
        # below January's 248 kWh: all low tier
        (JANUARY, "200", "600"),
        # exactly at the threshold: 248 x 3
        (JANUARY, "248", "744"),
        # above: 248 x 3 + 52 x 5
        (JANUARY, "300", "1004"),
        # the same 240 kWh is above February's 224 kWh threshold: 224 x 3 + 16 x 5
        (FEBRUARY, "240", "752"),
        # and exactly at April's: 240 x 3
        (APRIL, "240", "720"),
        # fractions of a kWh are priced too
        (JANUARY, "248.5", "746.5"),
    ],
)
def test_a_months_cost_prices_only_the_part_above_that_months_threshold_at_the_high_tier(
    month: int, kwh: str, expected_try: str
) -> None:
    cost = make_tariff().monthly_cost(month, Decimal(kwh))

    assert cost == Money(Decimal(expected_try), Currency.TRY)


def test_a_months_cost_is_continuous_across_its_threshold() -> None:
    tariff = make_tariff()

    just_below = tariff.monthly_cost(FEBRUARY, Decimal("223.99"))
    just_above = tariff.monthly_cost(FEBRUARY, Decimal("224.01"))

    assert just_above.amount - just_below.amount == Decimal("0.08")


@pytest.mark.parametrize(
    ("annual_kwh", "expected_try"),
    [
        ("0", "0"),
        # 166.67 kWh a month is below every threshold: all low tier, 2,000 x 3
        ("2000", "6000"),
        # 224 kWh a month is exactly February's threshold: 2,688 x 3
        ("2688", "8064"),
        # 240 kWh a month: February is 16 kWh above its threshold: 2,880 x 3 + 16 x 2
        ("2880", "8672"),
        # 248 kWh a month: February 24 above, the four 240-kWh months 8 above each:
        # 2,976 x 3 + 56 x 2
        ("2976", "9040"),
        # 250 kWh a month is above every threshold: 12 x 1,250 - 2 x 2,920
        ("3000", "9160"),
        # 500 kWh a month: 12 x 2,500 - 2 x 2,920
        ("6000", "24160"),
    ],
)
def test_the_annual_cost_of_a_flat_consumption_is_the_sum_of_its_twelve_monthly_costs(
    annual_kwh: str, expected_try: str
) -> None:
    cost = make_tariff().annual_cost(Decimal(annual_kwh))

    assert cost == Money(Decimal(expected_try), Currency.TRY)


def test_the_annual_cost_equals_the_sum_of_the_monthly_costs() -> None:
    tariff = make_tariff()
    monthly_kwh = Decimal("233.5")

    summed = sum(
        (tariff.monthly_cost(m, monthly_kwh).amount for m in range(1, MONTHS_PER_YEAR + 1)),
        start=Decimal(0),
    )

    assert tariff.annual_cost(12 * monthly_kwh).amount == summed


def test_the_annual_cost_is_continuous_across_every_threshold() -> None:
    tariff = make_tariff()

    for annual_kwh in ("2688", "2880", "2976"):
        below = tariff.annual_cost(Decimal(annual_kwh) - Decimal("0.01"))
        above = tariff.annual_cost(Decimal(annual_kwh) + Decimal("0.01"))
        assert Decimal(0) < above.amount - below.amount < Decimal("0.2")


def test_consumption_splits_into_low_and_high_tier_energy_month_by_month() -> None:
    tariff = make_tariff()

    # below every threshold
    assert tariff.split_by_tier(Decimal("2000")) == (Decimal("2000"), Decimal("0"))
    # 240 kWh a month: only February (224) is exceeded, by 16 kWh
    assert tariff.split_by_tier(Decimal("2880")) == (Decimal("2864"), Decimal("16"))
    # 500 kWh a month: the low tier fills to the 2,920 kWh allowance
    assert tariff.split_by_tier(Decimal("6000")) == (Decimal("2920"), Decimal("3080"))


def test_the_tier_split_priced_at_the_tier_prices_is_the_annual_cost() -> None:
    tariff = make_tariff()
    low_kwh, high_kwh = tariff.split_by_tier(Decimal("2880"))

    assert tariff.annual_cost(Decimal("2880")).amount == low_kwh * 3 + high_kwh * 5


def test_negative_consumption_is_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        make_tariff().annual_cost(Decimal("-1"))
    with pytest.raises(ValueError, match="negative"):
        make_tariff().monthly_cost(JANUARY, Decimal("-1"))
    with pytest.raises(ValueError, match="negative"):
        make_tariff().split_by_tier(Decimal("-1"))


def try_(amount: str) -> Money:
    return Money(Decimal(amount), Currency.TRY)


@pytest.mark.parametrize(
    ("annual_cost_try", "annual_kwh"),
    [
        ("0", "0"),
        # below every threshold: everything at the low price
        ("6000", "2000"),
        ("8064", "2688"),
        # between the breakpoints 2,688 and 2,880 kWh the slope is (11 x 3 + 5) / 12 per kWh:
        # 8,064 + 304 = 8,368 TRY is 2,688 + 96 kWh
        ("8368", "2784"),
        ("8672", "2880"),
        # between 2,880 and 2,976 kWh the slope is (7 x 3 + 5 x 5) / 12 per kWh
        ("8856", "2928"),
        ("9040", "2976"),
        # above every threshold: everything at the high price
        ("9160", "3000"),
        ("24160", "6000"),
    ],
)
def test_a_bill_converts_to_kwh_across_the_twelve_monthly_breakpoints(
    annual_cost_try: str, annual_kwh: str
) -> None:
    kwh = make_tariff().annual_consumption_from_cost(try_(annual_cost_try))

    assert kwh == pytest.approx(Decimal(annual_kwh), abs=Decimal("1e-20"))


@pytest.mark.parametrize(
    "annual_kwh", ["1", "1500", "2687.5", "2700", "2850.25", "2900", "2975", "2977", "5000", "9999"]
)
def test_converting_the_annual_cost_back_returns_the_consumption(annual_kwh: str) -> None:
    tariff = make_tariff()

    kwh = tariff.annual_consumption_from_cost(tariff.annual_cost(Decimal(annual_kwh)))

    assert kwh == pytest.approx(Decimal(annual_kwh), abs=Decimal("1e-20"))


def test_a_higher_bill_never_gives_a_lower_consumption() -> None:
    tariff = make_tariff()

    kwh = [tariff.annual_consumption_from_cost(try_(str(cost))) for cost in range(0, 20000, 250)]

    assert kwh == sorted(kwh)
    assert len(set(kwh)) == len(kwh)


def test_a_bill_in_another_currency_is_rejected() -> None:
    from sunquote.domain.errors import CurrencyMismatchError

    with pytest.raises(CurrencyMismatchError):
        make_tariff().annual_consumption_from_cost(Money(Decimal("100"), Currency.USD))


def test_a_negative_bill_is_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        make_tariff().annual_consumption_from_cost(try_("-1"))


def test_the_daily_allowance_must_be_positive() -> None:
    with pytest.raises(ValueError, match="allowance"):
        make_tariff(daily_allowance_kwh="0")
