"""Annual Savings, the yearly cash flow and the Payback Period (spec #1, ticket #8).

Fixed tariff (tests/factories.py): threshold 3,000 kWh/year, low 3 and high 5 TRY/kWh, Export
Price 2 TRY/kWh, Self-Consumption Ratio 0.8. Annual consumption is 6,000 kWh unless a test says
otherwise, so the grid bill is 3,000 x 3 + 3,000 x 5 = 24,000 TRY. Expected values were worked
out by hand, year by year (the multi-year example), and not with the code under test.
"""

from decimal import Decimal

import pytest

from sunquote.domain.assumptions import FinancialAssumptions
from sunquote.domain.money import Currency, Money
from sunquote.domain.savings import SavingsAnalysis, analyze_savings
from tests.factories import make_financial_assumptions, make_tariff


def try_(amount: str) -> Money:
    return Money(Decimal(amount), Currency.TRY)


def analyze(
    *,
    production_kwh: str = "6000",
    consumption_kwh: str = "6000",
    degradation: str = "0",
    total_price: str = "1000000",
    inverter_price: str = "1000",
    financial: FinancialAssumptions | None = None,
) -> SavingsAnalysis:
    return analyze_savings(
        year1_production_kwh=Decimal(production_kwh),
        annual_consumption_kwh=Decimal(consumption_kwh),
        degradation_rate_per_year=Decimal(degradation),
        tariff=make_tariff(),
        financial=financial or make_financial_assumptions(),
        inverter_price_incl_vat=try_(inverter_price),
        total_price_incl_vat=try_(total_price),
    )


def test_worked_three_year_example_with_degradation_escalation_and_replacement() -> None:
    """Production 6,000 kWh, degradation 1%, tariff escalation 2%, equipment escalation 10%,
    a 1,000 TRY inverter replaced in year 2, a 3-year lifetime and a 40,000 TRY total price.

    Year 1: self-consumed 4,800 kWh, worth 24,000 - 3,600 = 20,400 (the grid bill drops from
      6,000 to 1,200 kWh); exported 1,200 kWh x 2 = 2,400 -> 22,800.
    Year 2: production 5,940, self-consumed 4,752 -> (24,000 - 3,744) x 1.02 = 20,661.12;
      exported 1,188 x 2 x 1.02 = 2,423.52 -> 23,084.64, less the replacement 1,000 x 1.1 =
      1,100 -> net 21,984.64, cumulative 44,784.64. Payback = 1 + (40,000 - 22,800) / 21,984.64.
    Year 3: production 5,880.6, self-consumed 4,704.48 -> net 23,373.293472.
    """
    financial = make_financial_assumptions(
        tariff_escalation="0.02",
        equipment_escalation="0.10",
        lifetime_years=3,
        replacement_year=2,
    )

    result = analyze(degradation="0.01", total_price="40000", financial=financial)

    first, second, third = result.cash_flow
    assert [row.year for row in result.cash_flow] == [1, 2, 3]
    assert first.production_kwh == Decimal("6000")
    assert first.self_consumed_kwh == Decimal("4800")
    assert first.exported_kwh == Decimal("1200")
    assert first.self_consumption_savings == try_("20400")
    assert first.export_income == try_("2400")
    assert first.annual_savings == try_("22800")
    assert first.inverter_replacement == try_("0")
    assert first.net_savings == try_("22800")
    assert first.cumulative_net_savings == try_("22800")

    assert second.production_kwh == Decimal("5940")
    assert second.self_consumed_kwh == Decimal("4752")
    assert second.exported_kwh == Decimal("1188")
    assert second.self_consumption_savings == try_("20661.12")
    assert second.export_income == try_("2423.52")
    assert second.annual_savings == try_("23084.64")
    assert second.inverter_replacement == try_("1100")
    assert second.net_savings == try_("21984.64")
    assert second.cumulative_net_savings == try_("44784.64")

    assert third.production_kwh == Decimal("5880.6")
    assert third.net_savings == try_("23373.293472")
    assert third.cumulative_net_savings == try_("68157.933472")

    assert result.first_year_annual_savings == try_("22800")
    assert result.lifetime_savings == try_("68157.933472")
    assert result.payback_years == pytest.approx(Decimal("1.7823644144"), abs=Decimal("1e-9"))
    assert result.payback_beyond_lifetime is False


def test_cash_flow_covers_the_configured_lifetime() -> None:
    result = analyze(financial=make_financial_assumptions(lifetime_years=25))

    assert [row.year for row in result.cash_flow] == list(range(1, 26))


@pytest.mark.parametrize(
    ("production_kwh", "self_consumed", "exported", "savings_try", "export_try"),
    [
        # 0.8 x 1,500 = 1,200 kWh stays in the high tier: 1,200 x 5.
        ("1500", "1200", "300", "6000", "600"),
        # 0.8 x 3,000 = 2,400 kWh still stays in the high tier (3,000 kWh of it): 2,400 x 5.
        ("3000", "2400", "600", "12000", "1200"),
        # 4,800 kWh crosses into the low tier: 3,000 high x 5 + 1,800 low x 3.
        ("6000", "4800", "1200", "20400", "2400"),
    ],
)
def test_self_consumed_energy_comes_off_the_high_tier_first(
    production_kwh: str, self_consumed: str, exported: str, savings_try: str, export_try: str
) -> None:
    year_one = analyze(production_kwh=production_kwh).cash_flow[0]

    assert year_one.self_consumed_kwh == Decimal(self_consumed)
    assert year_one.exported_kwh == Decimal(exported)
    assert year_one.self_consumption_savings == try_(savings_try)
    assert year_one.export_income == try_(export_try)


def test_self_consumption_is_capped_at_annual_consumption() -> None:
    """Production 10,000 x 0.8 = 8,000 kWh is more than the 6,000 kWh the Customer uses."""
    year_one = analyze(production_kwh="10000").cash_flow[0]

    assert year_one.self_consumed_kwh == Decimal("6000")
    assert year_one.exported_kwh == Decimal("4000")
    assert year_one.self_consumption_savings == try_("24000")  # the whole bill
    assert year_one.export_income == try_("8000")


@pytest.mark.parametrize(
    ("consumption_kwh", "self_consumed", "savings_try", "export_try"),
    [
        # Entirely below the threshold: only the low tier, 2,000 x 3; the other 4,000 kWh export.
        ("2000", "2000", "6000", "8000"),
        # Exactly at the threshold: 3,000 x 3; the other 3,000 kWh export.
        ("3000", "3000", "9000", "6000"),
        # Above it: 4,800 kWh self-consumed, worth 24,000 - 3,600.
        ("6000", "4800", "20400", "2400"),
    ],
)
def test_savings_for_consumption_below_at_and_above_the_threshold(
    consumption_kwh: str, self_consumed: str, savings_try: str, export_try: str
) -> None:
    year_one = analyze(production_kwh="6000", consumption_kwh=consumption_kwh).cash_flow[0]

    assert year_one.self_consumed_kwh == Decimal(self_consumed)
    assert year_one.self_consumption_savings == try_(savings_try)
    assert year_one.export_income == try_(export_try)


def test_nothing_is_replaced_when_the_replacement_year_is_beyond_the_lifetime() -> None:
    financial = make_financial_assumptions(lifetime_years=5, replacement_year=12)

    result = analyze(financial=financial)

    assert {row.inverter_replacement for row in result.cash_flow} == {try_("0")}


def test_replacement_in_the_last_year_of_the_lifetime_is_included() -> None:
    financial = make_financial_assumptions(lifetime_years=5, replacement_year=5)

    result = analyze(financial=financial)

    assert result.cash_flow[4].inverter_replacement == try_("1000")
    assert result.cash_flow[3].inverter_replacement == try_("0")


def test_the_replacement_can_make_a_years_net_savings_negative() -> None:
    result = analyze(
        inverter_price="100000", financial=make_financial_assumptions(replacement_year=3)
    )

    year_two, year_three = result.cash_flow[1], result.cash_flow[2]
    assert year_three.net_savings.amount < 0
    assert year_three.cumulative_net_savings.amount < year_two.cumulative_net_savings.amount


def test_payback_interpolates_within_the_year_it_is_reached() -> None:
    """22,800 a year with no degradation or escalation: 34,200 is reached half way into year 2."""
    financial = make_financial_assumptions(tariff_escalation="0")

    result = analyze(total_price="34200", financial=financial)

    assert result.payback_years == Decimal("1.5")
    assert result.payback_beyond_lifetime is False


def test_payback_is_exactly_the_year_when_the_total_is_reached_at_year_end() -> None:
    financial = make_financial_assumptions(tariff_escalation="0")

    result = analyze(total_price="22800", financial=financial)

    assert result.payback_years == Decimal("1")


def test_payback_within_the_first_year() -> None:
    result = analyze(total_price="11400")

    assert result.payback_years == Decimal("0.5")


def test_payback_beyond_the_lifetime_is_absent_and_flagged() -> None:
    result = analyze(
        total_price="10000000", financial=make_financial_assumptions(lifetime_years=25)
    )

    assert result.payback_years is None
    assert result.payback_beyond_lifetime is True


def test_lifetime_savings_is_the_sum_of_net_savings_after_the_replacement() -> None:
    financial = make_financial_assumptions(
        tariff_escalation="0", lifetime_years=4, replacement_year=2
    )

    result = analyze(financial=financial)

    # 4 x 22,800 - 1,000
    assert result.lifetime_savings == try_("90200")
