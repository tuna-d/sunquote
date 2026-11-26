"""Annual Savings under Monthly Netting, the yearly cash flow and the Payback Period (spec #30,
ticket #33; ADR 0005).

Fixed tariff (tests/factories.py): daily allowance 8 kWh (monthly thresholds 224-248 kWh), low 3
and high 5 TRY/kWh, Export Price 2 TRY/kWh. Consumption is 500 kWh in each month unless a test
says otherwise. A month with threshold t then costs 3t + 5(500 - t) = 2,500 - 2t: 2,004 in the
31-day months, 2,020 in the 30-day ones and 2,052 in February, 24,160 TRY a year. Expected
values were worked out by hand, month by month, and not with the code under test.
"""

from decimal import Decimal

import pytest

from sunquote.domain.assumptions import FinancialAssumptions
from sunquote.domain.money import Currency, Money
from sunquote.domain.savings import SavingsAnalysis, analyze_savings
from tests.factories import make_financial_assumptions, make_tariff


def try_(amount: str) -> Money:
    return Money(Decimal(amount), Currency.TRY)


def flat(kwh_per_month: str) -> tuple[Decimal, ...]:
    return (Decimal(kwh_per_month),) * 12


# 300 kWh in January-June, 700 in July-December: 6,000 kWh a year with a surplus in the second
# half. Its first-year Annual Savings are 22,960 TRY (see the worked example below).
SUMMER_HEAVY = (Decimal(300),) * 6 + (Decimal(700),) * 6


def analyze(
    *,
    production: tuple[Decimal, ...] = SUMMER_HEAVY,
    monthly_consumption_kwh: str = "500",
    degradation: str = "0",
    total_price: str = "1000000",
    inverter_price: str = "1000",
    financial: FinancialAssumptions | None = None,
) -> SavingsAnalysis:
    return analyze_savings(
        year1_monthly_production_kwh=production,
        monthly_consumption_kwh=Decimal(monthly_consumption_kwh),
        degradation_rate_per_year=Decimal(degradation),
        tariff=make_tariff(),
        financial=financial or make_financial_assumptions(),
        inverter_price_incl_vat=try_(inverter_price),
        total_price_incl_vat=try_(total_price),
    )


def test_worked_three_year_example_with_degradation_escalation_and_replacement() -> None:
    """Summer-heavy production (300 kWh in January-June, 700 in July-December), degradation 1%,
    tariff escalation 2%, equipment escalation 10%, a 1,000 TRY inverter replaced in year 2, a
    3-year lifetime and a 40,000 TRY total price.

    Year 1: January-June nets everything (300 kWh each, remaining consumption 200 kWh, all low
      tier, so each month costs 600 against 2,004 / 2,052 / 2,004 / 2,020 / 2,004 / 2,020 =
      12,104, a drop of 12,104 - 3,600 = 8,504). July-December nets 500 kWh each and exports
      200 kWh each: the bill drops by the whole 12,056. Netted 6 x 300 + 6 x 500 = 4,800 kWh,
      exported 1,200 kWh x 2 = 2,400 -> 8,504 + 12,056 + 2,400 = 22,960.
    Year 2: production x 0.99 = 297 / 693 kWh. January-June remaining consumption is 203 kWh
      (609 a month, drop 12,104 - 3,654 = 8,450); July-December still nets 500 and exports 193.
      Bill drop (8,450 + 12,056) x 1.02 = 20,916.12; exported 6 x 193 = 1,158 kWh x 2 x 1.02 =
      2,362.32 -> 23,278.44, less the replacement 1,000 x 1.1 = 1,100 -> net 22,178.44,
      cumulative 45,138.44. Payback = 1 + (40,000 - 22,960) / 22,178.44.
    Year 3: production x 0.9801 = 294.03 / 686.07 kWh. January-June remaining 205.97 kWh
      (617.91 a month, drop 12,104 - 3,707.46 = 8,396.54); exports 6 x 186.07 = 1,116.42 kWh.
      (8,396.54 + 12,056) x 1.0404 = 21,278.822616; 1,116.42 x 2 x 1.0404 = 2,323.046736 ->
      23,601.869352.
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
    assert first.netted_kwh == Decimal("4800")
    assert first.exported_kwh == Decimal("1200")
    assert first.netting_savings == try_("20560")
    assert first.export_income == try_("2400")
    assert first.annual_savings == try_("22960")
    assert first.inverter_replacement == try_("0")
    assert first.net_savings == try_("22960")
    assert first.cumulative_net_savings == try_("22960")

    assert second.production_kwh == Decimal("5940")
    assert second.netted_kwh == Decimal("4782")
    assert second.exported_kwh == Decimal("1158")
    assert second.netting_savings == try_("20916.12")
    assert second.export_income == try_("2362.32")
    assert second.annual_savings == try_("23278.44")
    assert second.inverter_replacement == try_("1100")
    assert second.net_savings == try_("22178.44")
    assert second.cumulative_net_savings == try_("45138.44")

    assert third.production_kwh == Decimal("5880.6")
    assert third.exported_kwh == Decimal("1116.42")
    assert third.netting_savings == try_("21278.822616")
    assert third.export_income == try_("2323.046736")
    assert third.net_savings == try_("23601.869352")
    assert third.cumulative_net_savings == try_("68740.309352")

    assert result.first_year_annual_savings == try_("22960")
    assert result.lifetime_savings == try_("68740.309352")
    assert result.payback_years == pytest.approx(Decimal("1.768314"), abs=Decimal("1e-6"))
    assert result.payback_beyond_lifetime is False
    assert result.netted_share == Decimal("0.8")


def test_cash_flow_covers_the_configured_lifetime() -> None:
    result = analyze(financial=make_financial_assumptions(lifetime_years=25))

    assert [row.year for row in result.cash_flow] == list(range(1, 26))


def test_a_system_below_consumption_every_month_nets_everything() -> None:
    """100 kWh a month against 500: all 1,200 kWh come off the bill at the high tier, 5 each."""
    result = analyze(production=flat("100"))

    year_one = result.cash_flow[0]
    assert year_one.netted_kwh == Decimal("1200")
    assert year_one.exported_kwh == Decimal("0")
    assert year_one.netting_savings == try_("6000")
    assert year_one.export_income == try_("0")
    assert result.netted_share == Decimal("1")


def test_a_system_exactly_matching_consumption_every_month_exports_nothing() -> None:
    year_one = analyze(production=flat("500")).cash_flow[0]

    assert year_one.netted_kwh == Decimal("6000")
    assert year_one.exported_kwh == Decimal("0")
    assert year_one.netting_savings == try_("24160")  # the whole bill
    assert year_one.export_income == try_("0")


def test_a_roof_max_system_exports_exactly_the_excess_of_its_surplus_months() -> None:
    """625 kWh a month against 500: 125 kWh a month is exported, 1,500 kWh in all, at 2 TRY."""
    year_one = analyze(production=flat("625")).cash_flow[0]

    assert year_one.production_kwh == Decimal("7500")
    assert year_one.netted_kwh == Decimal("6000")
    assert year_one.exported_kwh == Decimal("1500")
    assert year_one.netting_savings == try_("24160")  # the whole bill, no more
    assert year_one.export_income == try_("3000")


@pytest.mark.parametrize(
    ("monthly_production", "netted_share"),
    [
        ("250", "1"),  # below consumption
        ("500", "1"),  # exactly consumption
        ("625", "0.8"),  # 500 / 625
        ("1000", "0.5"),  # 500 / 1,000
    ],
)
def test_the_netted_share_falls_as_the_system_grows(
    monthly_production: str, netted_share: str
) -> None:
    assert analyze(production=flat(monthly_production)).netted_share == Decimal(netted_share)


def test_surplus_in_one_month_does_not_cover_a_shortfall_in_another() -> None:
    """Production is netted month by month: 800 kWh in January and nothing afterwards nets only
    January's 500 kWh, and the other 300 kWh are exported."""
    production = (Decimal(800),) + (Decimal(0),) * 11

    result = analyze(production=production)

    year_one = result.cash_flow[0]
    assert year_one.netted_kwh == Decimal("500")
    assert year_one.exported_kwh == Decimal("300")
    assert year_one.netting_savings == try_("2004")  # January's whole bill
    assert year_one.export_income == try_("600")
    assert result.netted_share == Decimal("0.625")


@pytest.mark.parametrize(
    ("consumption_kwh", "savings_try"),
    [
        # 100 kWh a month: every month is below its threshold, only the low tier, 1,200 x 3.
        ("100", "3600"),
        # 224 kWh is exactly February's threshold and below every other month's: 2,688 x 3.
        ("224", "8064"),
        # 240 kWh: February (224) is 16 kWh above its threshold, 2,880 x 3 + 16 x 2 = 8,672.
        ("240", "8672"),
    ],
)
def test_netting_everything_is_worth_the_bill_with_that_months_tiers(
    consumption_kwh: str, savings_try: str
) -> None:
    """1,000 kWh a month covers the consumption in every month; the rest is exported."""
    year_one = analyze(production=flat("1000"), monthly_consumption_kwh=consumption_kwh).cash_flow[
        0
    ]

    annual_consumption = Decimal(consumption_kwh) * 12
    assert year_one.netted_kwh == annual_consumption
    assert year_one.netting_savings == try_(savings_try)
    assert year_one.exported_kwh == 12000 - annual_consumption
    assert year_one.export_income == try_(str((12000 - annual_consumption) * 2))


def test_netted_energy_comes_off_that_months_high_tier_first() -> None:
    """In January (threshold 248) 300 kWh netted from 500 leaves 200 kWh, all low tier: the
    drop is 2,004 - 600 = 1,404, not 300 x 3 = 900 (the low-tier price)."""
    production = (Decimal(300),) + (Decimal(0),) * 11

    year_one = analyze(production=production).cash_flow[0]

    assert year_one.netting_savings == try_("1404")


def test_year_one_production_is_the_sum_of_its_months() -> None:
    production = tuple(
        Decimal(kwh) for kwh in (70, 90, 120, 140, 160, 175, 185, 170, 140, 110, 80, 60)
    )

    assert analyze(production=production).cash_flow[0].production_kwh == Decimal("1500")


def test_twelve_monthly_values_are_required() -> None:
    with pytest.raises(ValueError, match="12"):
        analyze(production=flat("500")[:11])


def test_nothing_is_replaced_when_the_replacement_year_is_beyond_the_lifetime() -> None:
    financial = make_financial_assumptions(lifetime_years=5, replacement_year=12)

    result = analyze(financial=financial)

    assert {row.inverter_replacement for row in result.cash_flow} == {try_("0")}


@pytest.mark.parametrize(
    ("lifetime_years", "replacement_year", "replaced"),
    [(25, 12, True), (5, 5, True), (5, 6, False), (5, 12, False)],
)
def test_the_analysis_says_whether_the_inverter_is_replaced_within_the_lifetime(
    lifetime_years: int, replacement_year: int, replaced: bool
) -> None:
    financial = make_financial_assumptions(
        lifetime_years=lifetime_years, replacement_year=replacement_year
    )

    assert analyze(financial=financial).inverter_replaced_within_lifetime is replaced


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
    """22,960 a year with no degradation or escalation: 34,440 is reached half way into year 2."""
    financial = make_financial_assumptions(tariff_escalation="0")

    result = analyze(total_price="34440", financial=financial)

    assert result.payback_years == Decimal("1.5")
    assert result.payback_beyond_lifetime is False


def test_payback_is_exactly_the_year_when_the_total_is_reached_at_year_end() -> None:
    financial = make_financial_assumptions(tariff_escalation="0")

    result = analyze(total_price="22960", financial=financial)

    assert result.payback_years == Decimal("1")


def test_payback_within_the_first_year() -> None:
    result = analyze(total_price="11480")

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

    # 4 x 22,960 - 1,000
    assert result.lifetime_savings == try_("90840")


# --- NPV and IRR (spec #30, ticket #34; ADR 0006) -------------------------------------------
#
# Expected values below were computed with exact fractions in a separate script, not with the
# code under test. Both are at the real Discount Rate and in today's lira, unrounded.


def no_escalation(**overrides: object) -> FinancialAssumptions:
    """22,960 TRY a year with the summer-heavy production: no escalation, no replacement."""
    return make_financial_assumptions(
        tariff_escalation="0",
        replacement_year=99,
        **overrides,  # type: ignore[arg-type]
    )


def test_npv_discounts_each_years_net_savings_and_subtracts_the_total_price() -> None:
    """22,960 a year for 3 years at 10%, total price 50,000:
    NPV = -50,000 + 22,960 x (1/1.1 + 1/1.21 + 1/1.331) = 9,447,600 / 1,331 - 0 = 7,098.1217...
    """
    financial = no_escalation(lifetime_years=3, discount_rate="0.10")

    result = analyze(total_price="50000", financial=financial)

    assert result.npv.currency is Currency.TRY
    assert result.npv.amount == pytest.approx(Decimal("7098.1217129977"), abs=Decimal("1e-9"))


def test_npv_uses_the_net_savings_after_the_inverter_replacement_and_escalation() -> None:
    """The 3-year worked example above (net savings 22,960 / 22,178.44 / 23,601.869352, total
    40,000) at 5%: -40,000 + 22,960/1.05 + 22,178.44/1.05^2 + 23,601.869352/1.05^3 = 22,371.3477.
    """
    financial = make_financial_assumptions(
        tariff_escalation="0.02",
        equipment_escalation="0.10",
        lifetime_years=3,
        replacement_year=2,
        discount_rate="0.05",
    )

    result = analyze(degradation="0.01", total_price="40000", financial=financial)

    assert result.npv.amount == pytest.approx(Decimal("22371.3476747651"), abs=Decimal("1e-9"))


def test_npv_is_not_rounded() -> None:
    financial = no_escalation(lifetime_years=3, discount_rate="0.10")

    result = analyze(total_price="50000", financial=financial)

    assert result.npv.amount != result.npv.amount.to_integral_value()
    assert len(result.npv.amount.as_tuple().digits) > 10


def test_npv_at_a_zero_discount_rate_is_the_lifetime_savings_less_the_price() -> None:
    financial = no_escalation(lifetime_years=3, discount_rate="0")

    result = analyze(total_price="50000", financial=financial)

    assert result.npv == try_("18880")  # 3 x 22,960 - 50,000


def test_a_higher_discount_rate_lowers_the_npv() -> None:
    low = analyze(total_price="50000", financial=no_escalation(discount_rate="0.03"))
    high = analyze(total_price="50000", financial=no_escalation(discount_rate="0.12"))

    assert high.npv.amount < low.npv.amount


def test_irr_is_the_rate_at_which_the_npv_is_zero() -> None:
    """Two years of 22,960 for a total price of 165,312 / 5 = 33,062.4: the price equals
    22,960/1.25 + 22,960/1.25^2 = 18,368 + 14,694.4, so the IRR is exactly 25%."""
    financial = no_escalation(lifetime_years=2)

    result = analyze(total_price="33062.4", financial=financial)

    assert result.irr is not None
    assert result.irr == pytest.approx(Decimal("0.25"), abs=Decimal("0.0001"))


def test_irr_of_a_single_payment_is_the_simple_return() -> None:
    """One year of 22,960 for a price of 20,000: the IRR is 22,960/20,000 - 1 = 14.8%."""
    financial = no_escalation(lifetime_years=1)

    result = analyze(total_price="20000", financial=financial)

    assert result.irr is not None
    assert result.irr == pytest.approx(Decimal("0.148"), abs=Decimal("0.0001"))


def test_irr_does_not_depend_on_the_discount_rate() -> None:
    low = analyze(total_price="33062.4", financial=no_escalation(lifetime_years=2))
    high = analyze(
        total_price="33062.4", financial=no_escalation(lifetime_years=2, discount_rate="0.30")
    )

    assert low.irr == high.irr


def test_irr_above_the_discount_rate_goes_with_a_positive_npv() -> None:
    result = analyze(
        total_price="33062.4", financial=no_escalation(lifetime_years=2, discount_rate="0.05")
    )

    assert result.irr is not None
    assert result.irr > Decimal("0.05")
    assert result.npv.amount > 0


def test_irr_below_the_discount_rate_goes_with_a_negative_npv() -> None:
    result = analyze(
        total_price="33062.4", financial=no_escalation(lifetime_years=2, discount_rate="0.40")
    )

    assert result.irr is not None
    assert result.irr < Decimal("0.40")
    assert result.npv.amount < 0


def test_irr_is_zero_when_the_price_is_exactly_recovered() -> None:
    result = analyze(total_price="68880", financial=no_escalation(lifetime_years=3))

    assert result.irr == Decimal("0")
    assert result.payback_years == Decimal("3")


def test_irr_is_found_even_when_it_is_far_above_one_hundred_percent() -> None:
    """One year of 22,960 for a price of 1,000: the IRR is 21.96 (2,196%)."""
    result = analyze(total_price="1000", financial=no_escalation(lifetime_years=1))

    assert result.irr is not None
    assert result.irr == pytest.approx(Decimal("21.96"), abs=Decimal("0.0001"))


def test_irr_is_absent_when_the_price_is_never_recovered() -> None:
    result = analyze(total_price="10000000", financial=make_financial_assumptions())

    assert result.irr is None
    assert result.payback_beyond_lifetime is True
    assert result.npv.amount < 0  # still reported: the NPV exists, only the IRR does not


def test_irr_is_absent_exactly_when_the_payback_period_is_absent() -> None:
    financial = no_escalation(lifetime_years=3)  # lifetime savings 68,880

    recovered = analyze(total_price="68880", financial=financial)
    not_recovered = analyze(total_price="68880.01", financial=financial)

    assert (recovered.irr is None, recovered.payback_beyond_lifetime) == (False, False)
    assert (not_recovered.irr is None, not_recovered.payback_beyond_lifetime) == (True, True)
