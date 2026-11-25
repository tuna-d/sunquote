"""The domain entry point, tested through `build_quote` with fixed inputs.

Fixed inputs: panel 0.5 kWp / 2.0 m2, coverage ratio 0.80, annual specific yield 1,500
kWh/kWp (monthly values sum to 1,500).
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from sunquote.domain.errors import NoViableSystemError
from sunquote.domain.model import Consumption, RoofType
from sunquote.domain.money import Currency, Money
from sunquote.domain.quote import build_quote
from sunquote.domain.sizing import BindingLimit, SizingStrategy
from tests.factories import (
    DEFAULT_INVERTERS,
    QUOTE_DATE,
    QUOTE_NUMBER,
    make_assumptions,
    make_catalog,
    make_exchange_rate,
    make_financial_assumptions,
    make_inverter,
    make_pricing_assumptions,
    make_reference_data,
    make_request,
    make_specific_yield,
    make_tariff,
)


def build(
    *,
    usable_area_m2: str = "40",
    monthly_consumption_kwh: str = "500",
    annual_yield: str = "1500",
):
    return build_quote(
        request=make_request(
            usable_area_m2=usable_area_m2, monthly_consumption_kwh=monthly_consumption_kwh
        ),
        specific_yield=make_specific_yield(annual=annual_yield),
        reference_data=make_reference_data(),
        exchange_rate=make_exchange_rate(),
        quote_date=QUOTE_DATE,
        quote_number=QUOTE_NUMBER,
    )


@pytest.mark.parametrize(
    ("usable_area_m2", "monthly_kwh", "annual_yield", "panels", "limit"),
    [
        # target 6000/1500 = 4.0 kWp = 8 panels; roof fits 16 -> consumption target
        ("40", "500", "1500", 8, BindingLimit.CONSUMPTION_TARGET),
        # target 6000/1450 = 4.138 kWp = 8.28 panels -> rounds down to 8
        ("40", "500", "1450", 8, BindingLimit.CONSUMPTION_TARGET),
        # target 0.08 kWp = 0.16 panels -> at least one panel
        ("40", "10", "1500", 1, BindingLimit.CONSUMPTION_TARGET),
        # target 32 panels; roof fits floor(40*0.8/2) = 16 -> roof
        ("40", "2000", "1500", 16, BindingLimit.ROOF),
        # roof fits floor(41*0.8/2) = floor(16.4) = 16 -> roof rounds down
        ("41", "2000", "1500", 16, BindingLimit.ROOF),
        # tie: roof fits 8 and target is 8 panels -> the Roof counts as binding
        ("20", "500", "1500", 8, BindingLimit.ROOF),
        # one panel fits (2.5*0.8/2 = 1) and the target is also one -> Roof (tie)
        ("2.5", "10", "1500", 1, BindingLimit.ROOF),
    ],
)
def test_consumption_matched_sizing(
    usable_area_m2: str,
    monthly_kwh: str,
    annual_yield: str,
    panels: int,
    limit: BindingLimit,
) -> None:
    quote = build(
        usable_area_m2=usable_area_m2,
        monthly_consumption_kwh=monthly_kwh,
        annual_yield=annual_yield,
    )

    option = quote.system_options[0]
    assert option.strategy is SizingStrategy.CONSUMPTION_MATCHED
    assert option.panel_count == panels
    assert option.capacity_kwp == Decimal(panels) * Decimal("0.5")
    assert option.binding_limit is limit


@pytest.mark.parametrize("usable_area_m2", ["2", "2.4", "0.01"])
def test_roof_that_fits_no_panel_is_not_a_viable_system(usable_area_m2: str) -> None:
    with pytest.raises(NoViableSystemError):
        build(usable_area_m2=usable_area_m2)


def test_production_is_capacity_times_specific_yield() -> None:
    option = build().system_options[0]  # 8 panels = 4.0 kWp

    assert option.annual_production_kwh == Decimal("6000")
    assert option.monthly_production_kwh == tuple(
        Decimal(kwh) for kwh in (280, 360, 480, 560, 640, 700, 740, 680, 560, 440, 320, 240)
    )


def test_flat_roof_uses_its_coverage_ratio_and_the_installer_orientation() -> None:
    request = make_request(
        roof_type=RoofType.FLAT, monthly_consumption_kwh="2000", azimuth_deg="90", tilt_deg="30"
    )
    quote = build_quote(
        request=request,
        specific_yield=make_specific_yield(tilt_deg="18"),
        reference_data=make_reference_data(assumptions=make_assumptions(flat_roof_tilt_deg="18")),
        exchange_rate=make_exchange_rate(),
        quote_date=QUOTE_DATE,
        quote_number=QUOTE_NUMBER,
    )

    # The consumption target is 32 panels. A flat Roof fits 10, while a pitched one fits 16.
    [option] = quote.system_options
    assert option.panel_count == 10
    assert option.binding_limit is BindingLimit.ROOF
    recorded = quote.assumptions
    assert recorded.roof_type is RoofType.FLAT
    assert recorded.coverage_ratio == Decimal("0.50")
    assert recorded.effective_azimuth_deg == Decimal("180")
    assert recorded.effective_tilt_deg == Decimal("18")
    # The angles the Sales Rep gave stay in the submitted request, though they are not used.
    assert recorded.submitted_request.site.roof.azimuth_deg == Decimal("90")
    assert recorded.submitted_request.site.roof.tilt_deg == Decimal("30")
    assert recorded.submitted_request == request


def test_quote_carries_customer_date_and_the_assumptions_it_was_built_with() -> None:
    request = make_request()
    quote = build_quote(
        request=request,
        specific_yield=make_specific_yield(),
        reference_data=make_reference_data(
            assumptions=make_assumptions(pitched_coverage_ratio="0.75", system_loss_percent="12")
        ),
        exchange_rate=make_exchange_rate(),
        quote_date=QUOTE_DATE,
        quote_number=QUOTE_NUMBER,
    )

    assert quote.customer == request.customer
    assert quote.quote_date == QUOTE_DATE
    recorded = quote.assumptions
    assert recorded.submitted_request == request
    assert recorded.pvgis_inputs == make_specific_yield().inputs
    assert recorded.coverage_ratio == Decimal("0.75")
    assert recorded.default_panel == make_catalog().default_panel


def test_quote_carries_its_number_and_is_valid_for_the_validity_period() -> None:
    quote = build_quote(
        request=make_request(),
        specific_yield=make_specific_yield(),
        reference_data=make_reference_data(
            pricing=make_pricing_assumptions(validity_period_days=15)
        ),
        exchange_rate=make_exchange_rate(),
        quote_date=date(2026, 12, 20),
        quote_number="SQ-2026-000123",
    )

    assert quote.quote_number == "SQ-2026-000123"
    assert quote.valid_until == date(2027, 1, 4)  # 15 days after 2026-12-20, across the new year
    assert quote.assumptions.pricing.validity_period_days == 15


def test_same_inputs_give_an_identical_quote() -> None:
    assert build() == build()


# --- Savings and the tariff assumptions ----------------------------------------------------
#
# Default quote: 500 kWh/month (6,000 kWh/year), 8 panels = 4.0 kWp producing 6,000 kWh in year 1,
# the 3.5 kW inverter (USD 650 = 26,000 TRY, 31,200 with VAT), total price 159,000 TRY.
# Tariff and financial assumptions: see tests/factories.py (escalation 2%, replacement in year 12,
# lifetime 25 years, panel degradation 0.5%/year). Year-by-year figures worked out by hand.


def test_option_savings_follow_from_production_consumption_and_tariff() -> None:
    savings = build().system_options[0].savings

    assert savings.first_year_annual_savings == Money(Decimal("22960"), Currency.TRY)
    assert len(savings.cash_flow) == 25
    # The 31,200 TRY replacement (inverter incl. 20% VAT, equipment escalation 0) falls in year 12.
    year_twelve = savings.cash_flow[11]
    assert year_twelve.inverter_replacement == Money(Decimal("31200"), Currency.TRY)
    assert year_twelve.net_savings.amount < 0
    assert savings.payback_years == pytest.approx(Decimal("6.6132055794"), abs=Decimal("1e-9"))
    assert savings.payback_beyond_lifetime is False
    assert savings.lifetime_savings.amount == pytest.approx(
        Decimal("670530.38855"), abs=Decimal("1e-4")
    )


def test_savings_are_computed_for_each_option_from_its_own_price_and_production() -> None:
    small = build(monthly_consumption_kwh="313").system_options[0]  # 5 panels = 2.5 kWp
    large = build().system_options[0]  # 8 panels = 4.0 kWp

    assert small.savings.cash_flow[0].production_kwh == Decimal("3750")
    assert large.savings.cash_flow[0].production_kwh == Decimal("6000")
    assert small.savings != large.savings


def test_quote_records_the_consumption_tier_split_and_the_tariff_and_financial_assumptions() -> (
    None
):
    recorded = build().assumptions

    assert recorded.annual_consumption_kwh == Decimal("6000")
    assert recorded.low_tier_consumption_kwh == Decimal("2920")
    assert recorded.high_tier_consumption_kwh == Decimal("3080")
    assert recorded.tariff == make_tariff()
    assert recorded.financial == make_financial_assumptions()


def test_the_roof_max_option_gets_its_own_savings_from_its_own_price_and_production() -> None:
    matched, roof_max = build().system_options  # 4.0 kWp and 8.0 kWp

    # 12,000 kWh produced: the whole 6,000 kWh bill is saved (24,160), 6,000 kWh export at 2.
    assert roof_max.savings.first_year_annual_savings == Money(Decimal("36160"), Currency.TRY)
    assert matched.savings.first_year_annual_savings == Money(Decimal("22960"), Currency.TRY)
    # The replacement is the 8 kW inverter (USD 1,100 x 40 x 1.2 VAT), not the 3.5 kW one.
    assert roof_max.savings.cash_flow[11].inverter_replacement == Money(
        Decimal("52800"), Currency.TRY
    )


@pytest.mark.parametrize(
    ("bill_try", "annual_cost_try", "annual_kwh", "monthly_kwh"),
    [
        # With a 10 kWh/day allowance the monthly thresholds are February 280, April, June,
        # September and November 300, the other seven months 310 kWh, so the bill breakpoints
        # are 8,400 (3,360 kWh), 9,025 (3,600 kWh) and 9,387.50 TRY (3,720 kWh) a year.
        # At or below the first breakpoint everything is low tier: 8,400 / 2.50.
        ("700", "8400", "3360", "280"),
        # Between 3,360 and 3,600 kWh a kWh costs (11 x 2.50 + 3.75) / 12:
        # 3,360 + 600 / (31.25 / 12).
        ("750", "9000", "3590.4", "299.2"),
        # Above 3,720 kWh every kWh costs 3.75: 3,720 + (12,000 - 9,387.50) / 3.75.
        ("1000", "12000", "4416.67", "368.06"),
        ("2000", "24000", "7616.67", "634.72"),
    ],
)
def test_monthly_bill_converts_through_the_marginal_tariff_tiers(
    bill_try: str, annual_cost_try: str, annual_kwh: str, monthly_kwh: str
) -> None:
    tariff = make_tariff(daily_allowance_kwh="10", low_try_per_kwh="2.50", high_try_per_kwh="3.75")
    quote = build_quote(
        request=replace(
            make_request(), consumption=Consumption(monthly_bill_try=Decimal(bill_try))
        ),
        specific_yield=make_specific_yield(),
        reference_data=make_reference_data(
            catalog=make_catalog((*DEFAULT_INVERTERS, make_inverter("i2", "2", "375"))),
            tariff=tariff,
        ),
        exchange_rate=make_exchange_rate(),
        quote_date=QUOTE_DATE,
        quote_number=QUOTE_NUMBER,
    )

    recorded = quote.assumptions
    assert recorded.annual_consumption_kwh == pytest.approx(
        Decimal(annual_kwh), abs=Decimal("0.01")
    )
    assert tariff.annual_cost(recorded.annual_consumption_kwh).amount == pytest.approx(
        Decimal(annual_cost_try), abs=Decimal("1e-20")
    )
    assert recorded.consumption_derived_from_bill
    assert recorded.submitted_request.consumption.monthly_bill_try == Decimal(bill_try)
    assert recorded.derived_monthly_consumption_kwh is not None
    assert recorded.derived_monthly_consumption_kwh.quantize(Decimal("0.01")) == Decimal(
        monthly_kwh
    )
    assert 12 * recorded.derived_monthly_consumption_kwh == pytest.approx(
        recorded.annual_consumption_kwh, abs=Decimal("1e-20")
    )
