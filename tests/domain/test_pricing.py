"""Inverter choice and pricing, through `build_quote`.

Worked example (tests/factories.py): 8 panels of 0.5 kWp = 4.0 kWp at USD 100 each, BOS USD
100/kWp, labour 3,000 TRY/kWp, fixed project cost 20,000 TRY, Margin 25%, VAT 20%, 40 TRY/USD.
"""

from decimal import Decimal

import pytest

from sunquote.domain.catalog import Inverter
from sunquote.domain.errors import CurrencyMismatchError, NoCompatibleInverterError
from sunquote.domain.money import Currency, ExchangeRate, Money
from sunquote.domain.quote import Quote, build_quote
from tests.factories import (
    DEFAULT_INVERTERS,
    QUOTE_DATE,
    QUOTE_NUMBER,
    RATE_DATE,
    make_assumptions,
    make_catalog,
    make_exchange_rate,
    make_inverter,
    make_pricing_assumptions,
    make_reference_data,
    make_request,
    make_specific_yield,
)


def build(
    *,
    inverters=DEFAULT_INVERTERS,
    exchange_rate: ExchangeRate | None = None,
    pricing=None,
    assumptions=None,
) -> Quote:
    return build_quote(
        # 500 kWh/month -> 4.0 kWp, 8 panels; the roof fits 8
        request=make_request(usable_area_m2="20"),
        specific_yield=make_specific_yield(),
        reference_data=make_reference_data(
            catalog=make_catalog(inverters),
            assumptions=assumptions or make_assumptions(),
            pricing=pricing or make_pricing_assumptions(),
        ),
        exchange_rate=exchange_rate or make_exchange_rate(),
        quote_date=QUOTE_DATE,
        quote_number=QUOTE_NUMBER,
    )


def try_amount(value: str) -> Money:
    return Money(Decimal(value), Currency.TRY)


# --- Inverter selection --------------------------------------------------------------------


def test_the_cheapest_inverter_within_the_dc_ac_range_is_chosen() -> None:
    option = build().system_options[0]

    # i3 (USD 500) is cheaper but 4.0 / 3 = 1.33 is above 1.30; i35 (USD 650) is 1.14.
    assert option.inverter.inverter_id == "i35"
    assert option.dc_ac_ratio == Decimal("4.0") / Decimal("3.5")


def test_the_range_limits_are_inclusive() -> None:
    at_minimum = (make_inverter("min", "4", "700"),)  # 4.0 / 4 = 1.00
    at_maximum = (make_inverter("max", "3.2", "600"),)  # 4.0 / 3.2 = 1.25

    assert build(inverters=at_minimum).system_options[0].inverter.inverter_id == "min"
    assert (
        build(inverters=at_maximum, assumptions=make_assumptions(dc_ac_ratio_max="1.25"))
        .system_options[0]
        .inverter.inverter_id
        == "max"
    )
    with pytest.raises(NoCompatibleInverterError):
        build(inverters=at_maximum, assumptions=make_assumptions(dc_ac_ratio_max="1.24"))


def test_equal_prices_tie_break_on_the_smaller_ac_power_then_the_id() -> None:
    inverters = (
        make_inverter("b", "4", "600"),
        make_inverter("c", "3.5", "600"),
        make_inverter("a", "3.5", "600"),
    )

    assert build(inverters=inverters).system_options[0].inverter.inverter_id == "a"


def test_inverters_are_compared_in_try_after_conversion() -> None:
    def priced(inverter_id: str, price: Money) -> Inverter:
        return Inverter(
            inverter_id=inverter_id,
            manufacturer="Test",
            model=inverter_id,
            ac_power_kw=Decimal("3.5"),
            unit_price=price,
        )

    usd_650 = priced("usd", Money(Decimal(650), Currency.USD))  # 26,000 TRY at 40

    cheaper_in_try = priced("try-cheap", try_amount("25000"))
    dearer_in_try = priced("try-dear", try_amount("27000"))
    assert build(inverters=(usd_650, cheaper_in_try)).system_options[0].inverter == cheaper_in_try
    assert build(inverters=(usd_650, dearer_in_try)).system_options[0].inverter == usd_650


def test_no_compatible_inverter_is_a_domain_error() -> None:
    too_big = (make_inverter("huge", "20", "2000"),)  # 4 / 20 = 0.2
    too_small = (make_inverter("tiny", "1", "200"),)  # 4 / 1 = 4

    for inverters in (too_big, too_small, ()):
        with pytest.raises(NoCompatibleInverterError):
            build(inverters=inverters)


# --- Pricing -------------------------------------------------------------------------------


def test_fully_worked_pricing_example() -> None:
    price = build().system_options[0].price

    # panels 8 x 100 + inverter 650 + BOS 100 x 4.0 = USD 1,850 -> 74,000 TRY at 40
    # + labour 3,000 x 4.0 = 12,000 + fixed 20,000
    assert price.installation_cost == try_amount("106000")
    assert price.sale_price == try_amount("132500")  # x 1.25
    assert price.vat == try_amount("26500")  # x 0.20
    assert price.total == try_amount("159000")


def test_pricing_keeps_full_precision() -> None:
    quote = build(exchange_rate=make_exchange_rate("41.2345"))

    price = quote.system_options[0].price
    # 1,850 x 41.2345 = 76,283.825 + 12,000 + 20,000
    assert price.installation_cost == try_amount("108283.825")
    assert price.sale_price == try_amount("135354.78125")
    assert price.vat == try_amount("27070.95625")
    assert price.total == try_amount("162425.7375")


def test_a_zero_margin_and_zero_vat_leave_the_cost_unchanged() -> None:
    pricing = make_pricing_assumptions(margin="0", vat_rate="0")

    price = build(pricing=pricing).system_options[0].price

    assert price.sale_price == price.installation_cost == try_amount("106000")
    assert price.total == price.sale_price


def test_a_price_in_a_currency_without_a_rate_is_refused() -> None:
    eur_inverter = Inverter(
        inverter_id="eur",
        manufacturer="Test",
        model="EUR",
        ac_power_kw=Decimal("3.5"),
        unit_price=Money(Decimal(500), Currency.EUR),
    )

    with pytest.raises(CurrencyMismatchError):
        build(inverters=(eur_inverter,))


# --- Assumptions ---------------------------------------------------------------------------


def test_the_quote_records_the_exchange_rate_and_the_prices_it_used() -> None:
    recorded = build(exchange_rate=make_exchange_rate("41.2345", overridden=True)).assumptions

    assert recorded.exchange_rate.rate == Decimal("41.2345")
    assert recorded.exchange_rate.rate_date == RATE_DATE
    assert recorded.exchange_rate.overridden is True
    assert recorded.pricing == make_pricing_assumptions()
    assert recorded.dc_ac_ratio_range == make_assumptions().dc_ac_ratio_range
    assert recorded.inverters == DEFAULT_INVERTERS
    assert recorded.default_panel.unit_price == Money(Decimal(100), Currency.USD)
