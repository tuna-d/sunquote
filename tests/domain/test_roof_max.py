"""Roof-Max, the Contracted Power cap and the Binding Limit, through `build_quote`.

Fixed inputs (tests/factories.py): panel 0.5 kWp / 2.0 m2, coverage ratio 0.80, specific yield
1,500 kWh/kWp, DC/AC range 1.00-1.30, default Contracted Power 10 kW. So the Contracted Power
cap is floor(Contracted Power x 1.30 / 0.5) = floor(2.6 x kW) panels, and a roof of A m2 fits
floor(A x 0.8 / 2) panels (40 m2 -> 16, 18 m2 -> 7). A consumption of C kWh/month targets
C x 12 / 1500 kWp, so 500 -> 8 panels and 437.5 -> 7 panels.
"""

from decimal import Decimal

import pytest

from sunquote.domain.catalog import Inverter
from sunquote.domain.errors import NoCompatibleInverterError, NoViableSystemError
from sunquote.domain.model import QuoteRequest
from sunquote.domain.quote import Quote, build_quote
from sunquote.domain.sizing import BindingLimit, SizingStrategy
from tests.factories import (
    DEFAULT_INVERTERS,
    QUOTE_DATE,
    make_assumptions,
    make_catalog,
    make_exchange_rate,
    make_financial_assumptions,
    make_inverter,
    make_pricing_assumptions,
    make_request,
    make_specific_yield,
    make_tariff,
)


def build(
    *,
    usable_area_m2: str = "40",
    monthly_consumption_kwh: str = "500",
    contracted_power_kw: str | None = None,
    inverters: tuple[Inverter, ...] = DEFAULT_INVERTERS,
    default_contracted_power_kw: str = "10",
    request: QuoteRequest | None = None,
) -> Quote:
    return build_quote(
        request=request
        or make_request(
            usable_area_m2=usable_area_m2,
            monthly_consumption_kwh=monthly_consumption_kwh,
            contracted_power_kw=contracted_power_kw,
        ),
        specific_yield=make_specific_yield(),
        catalog=make_catalog(inverters),
        assumptions=make_assumptions(default_contracted_power_kw=default_contracted_power_kw),
        pricing=make_pricing_assumptions(),
        exchange_rate=make_exchange_rate(),
        tariff=make_tariff(),
        financial=make_financial_assumptions(),
        quote_date=QUOTE_DATE,
    )


# --- One option or two ---------------------------------------------------------------------


def test_a_quote_holds_consumption_matched_then_roof_max_when_they_differ() -> None:
    quote = build()  # target 8 panels, roof fits 16, cap 26

    consumption_matched, roof_max = quote.system_options
    assert consumption_matched.strategy is SizingStrategy.CONSUMPTION_MATCHED
    assert consumption_matched.panel_count == 8
    assert consumption_matched.binding_limit is BindingLimit.CONSUMPTION_TARGET
    assert roof_max.strategy is SizingStrategy.ROOF_MAX
    assert roof_max.panel_count == 16
    assert roof_max.capacity_kwp == Decimal("8.0")
    assert roof_max.binding_limit is BindingLimit.ROOF


def test_every_option_is_fully_priced_and_produces_by_its_own_size() -> None:
    consumption_matched, roof_max = build().system_options

    assert roof_max.annual_production_kwh == Decimal("12000")  # 8.0 kWp x 1,500
    assert sum(roof_max.monthly_production_kwh) == Decimal("12000")
    assert roof_max.inverter.inverter_id == "i8"  # the only inverter with a ratio in 1.00-1.30
    assert roof_max.dc_ac_ratio == Decimal(1)
    # (16 x 100 panels + 1,100 inverter + 8 x 100 BOS) USD x 40 = 140,000 TRY
    # + 8 x 3,000 labour + 20,000 fixed = 184,000; x 1.25 = 230,000; x 1.20 = 276,000
    assert roof_max.price.installation_cost.amount == Decimal("184000")
    assert roof_max.price.sale_price.amount == Decimal("230000")
    assert roof_max.price.total.amount == Decimal("276000")
    assert consumption_matched.price.installation_cost.amount == Decimal("106000")


def test_one_option_when_both_strategies_give_the_same_panel_count() -> None:
    quote = build(monthly_consumption_kwh="2000")  # target 32 panels; the roof fits 16

    [option] = quote.system_options
    assert option.strategy is SizingStrategy.CONSUMPTION_MATCHED
    assert option.panel_count == 16
    assert option.binding_limit is BindingLimit.ROOF


def test_consumption_matched_comes_first() -> None:
    options = build().system_options

    assert [option.strategy for option in options] == [
        SizingStrategy.CONSUMPTION_MATCHED,
        SizingStrategy.ROOF_MAX,
    ]


# --- Contracted Power ----------------------------------------------------------------------


def test_the_cap_in_panels_is_the_floor_of_power_times_max_ratio_over_panel_kwp() -> None:
    # 6 kW x 1.30 / 0.5 = 15.6 -> 15 panels, not 16 (the roof fits 16)
    quote = build(monthly_consumption_kwh="2000", contracted_power_kw="6")

    [option] = quote.system_options
    assert option.panel_count == 15
    assert option.binding_limit is BindingLimit.CONTRACTED_POWER
    assert option.inverter.inverter_id == "i6"


def test_both_strategies_respect_the_cap() -> None:
    # CM target 8 panels (below the cap) stays; Roof-Max 16 is cut to the cap of 15.
    consumption_matched, roof_max = build(contracted_power_kw="6").system_options

    assert consumption_matched.panel_count == 8
    assert consumption_matched.binding_limit is BindingLimit.CONSUMPTION_TARGET
    assert roof_max.panel_count == 15
    assert roof_max.binding_limit is BindingLimit.CONTRACTED_POWER


def test_consumption_matched_is_capped_too_so_both_can_collapse_onto_the_cap() -> None:
    quote = build(monthly_consumption_kwh="2000", contracted_power_kw="3")  # cap 7, roof 16

    [option] = quote.system_options
    assert option.panel_count == 7
    assert option.binding_limit is BindingLimit.CONTRACTED_POWER


def test_one_option_is_consumption_target_limited_and_the_other_power_limited() -> None:
    # target 5 panels (350 kWh/month), roof 16, cap 7
    consumption_matched, roof_max = build(
        monthly_consumption_kwh="350", contracted_power_kw="3"
    ).system_options

    assert (consumption_matched.panel_count, consumption_matched.binding_limit) == (
        5,
        BindingLimit.CONSUMPTION_TARGET,
    )
    assert (roof_max.panel_count, roof_max.binding_limit) == (7, BindingLimit.CONTRACTED_POWER)


def test_the_given_contracted_power_is_recorded_as_given() -> None:
    recorded = build(contracted_power_kw="6").assumptions

    assert recorded.contracted_power.kw == Decimal(6)
    assert recorded.contracted_power.given is True
    assert recorded.submitted_request.contracted_power_kw == Decimal(6)


def test_an_absent_contracted_power_defaults_to_the_data_file_value_and_says_so() -> None:
    quote = build(default_contracted_power_kw="4")  # cap 10; roof 16

    recorded = quote.assumptions
    assert recorded.contracted_power.kw == Decimal(4)
    assert recorded.contracted_power.given is False
    assert recorded.submitted_request.contracted_power_kw is None
    assert quote.system_options[-1].panel_count == 10  # the default caps Roof-Max too


def test_a_contracted_power_too_small_for_one_panel_is_not_a_viable_system() -> None:
    with pytest.raises(NoViableSystemError):
        build(contracted_power_kw="0.3")  # floor(0.78) = 0 panels


# --- Binding Limit ties --------------------------------------------------------------------
# Contracted Power 3 kW caps at 7 panels, an 18 m2 roof fits 7 and 437.5 kWh/month targets 7.


@pytest.mark.parametrize(
    ("usable_area_m2", "monthly_kwh", "contracted_power_kw", "panels", "limit"),
    [
        # Roof is the only constraint: cap 26, target 32
        ("40", "2000", "10", 16, BindingLimit.ROOF),
        # consumption target is the only constraint: roof 16, cap 26
        ("40", "500", "10", 8, BindingLimit.CONSUMPTION_TARGET),
        # Contracted Power is the only constraint: roof 16, target 32, cap 7
        ("40", "2000", "3", 7, BindingLimit.CONTRACTED_POWER),
        # Contracted Power ties the Roof (target 16): Contracted Power
        ("18", "1000", "3", 7, BindingLimit.CONTRACTED_POWER),
        # Contracted Power ties the consumption target (roof 16): Contracted Power
        ("40", "437.5", "3", 7, BindingLimit.CONTRACTED_POWER),
        # Roof ties the consumption target (cap 26): Roof
        ("20", "500", "10", 8, BindingLimit.ROOF),
        # all three tie: Contracted Power, then Roof, then consumption target
        ("18", "437.5", "3", 7, BindingLimit.CONTRACTED_POWER),
    ],
)
def test_binding_limit_of_the_consumption_matched_option(
    usable_area_m2: str,
    monthly_kwh: str,
    contracted_power_kw: str,
    panels: int,
    limit: BindingLimit,
) -> None:
    option = build(
        usable_area_m2=usable_area_m2,
        monthly_consumption_kwh=monthly_kwh,
        contracted_power_kw=contracted_power_kw,
    ).system_options[0]

    assert option.strategy is SizingStrategy.CONSUMPTION_MATCHED
    assert (option.panel_count, option.binding_limit) == (panels, limit)


@pytest.mark.parametrize(
    ("usable_area_m2", "contracted_power_kw", "panels", "limit"),
    [
        ("40", "10", 16, BindingLimit.ROOF),
        ("40", "3", 7, BindingLimit.CONTRACTED_POWER),
        # the cap and the roof both give 7: Contracted Power wins the tie
        ("18", "3", 7, BindingLimit.CONTRACTED_POWER),
    ],
)
def test_binding_limit_of_the_roof_max_option(
    usable_area_m2: str, contracted_power_kw: str, panels: int, limit: BindingLimit
) -> None:
    roof_max = build(
        usable_area_m2=usable_area_m2,
        monthly_consumption_kwh="100",  # target 2 panels, so there are two options
        contracted_power_kw=contracted_power_kw,
    ).system_options[-1]

    assert roof_max.strategy is SizingStrategy.ROOF_MAX
    assert (roof_max.panel_count, roof_max.binding_limit) == (panels, limit)


# --- Inverter AC cap -----------------------------------------------------------------------


def test_the_inverter_ac_power_may_not_exceed_the_contracted_power() -> None:
    # Cap 7 panels = 3.5 kWp. Both inverters are within 1.00-1.30, "wide" is cheaper but its
    # 3.2 kW AC is above the 3 kW Contracted Power.
    narrow = make_inverter("narrow", "3.0", "800")
    wide = make_inverter("wide", "3.2", "500")

    option = build(
        monthly_consumption_kwh="2000", contracted_power_kw="3", inverters=(narrow, wide)
    ).system_options[0]

    assert option.inverter.inverter_id == "narrow"


def test_the_ac_cap_is_inclusive() -> None:
    exactly = make_inverter("exactly", "3.0", "800")

    option = build(
        monthly_consumption_kwh="2000", contracted_power_kw="3", inverters=(exactly,)
    ).system_options[0]

    assert option.inverter.inverter_id == "exactly"


def test_no_compatible_inverter_when_every_fitting_inverter_exceeds_the_contracted_power() -> None:
    only_wide = make_inverter("wide", "3.2", "500")  # ratio 1.09 for the 3.5 kWp cap system

    with pytest.raises(NoCompatibleInverterError):
        build(monthly_consumption_kwh="2000", contracted_power_kw="3", inverters=(only_wide,))


def test_roof_max_picks_its_own_inverter() -> None:
    consumption_matched, roof_max = build(contracted_power_kw="10").system_options

    assert consumption_matched.inverter.inverter_id == "i35"  # 4.0 kWp
    assert roof_max.inverter.inverter_id == "i8"  # 8.0 kWp


def test_same_inputs_give_an_identical_two_option_quote() -> None:
    assert build(contracted_power_kw="6") == build(contracted_power_kw="6")
