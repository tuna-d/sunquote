"""ReferenceData names the one foreign currency its prices are in, so the Quote knows which
Exchange Rate to fetch. The data files are the single source of that currency."""

from dataclasses import replace
from decimal import Decimal

import pytest

from sunquote.domain.catalog import Catalog
from sunquote.domain.money import Currency, Money
from sunquote.domain.reference_data import ReferenceData
from tests.factories import make_catalog, make_pricing_assumptions, make_reference_data


def in_currency(data: ReferenceData, currency: Currency) -> ReferenceData:
    """The same prices, with every foreign price declared in `currency`."""

    def convert(money: Money) -> Money:
        return money if money.currency is Currency.TRY else Money(money.amount, currency)

    catalog = data.catalog
    return replace(
        data,
        catalog=Catalog(
            panels=tuple(
                replace(panel, unit_price=convert(panel.unit_price)) for panel in catalog.panels
            ),
            default_panel_id=catalog.default_panel_id,
            inverters=tuple(
                replace(inverter, unit_price=convert(inverter.unit_price))
                for inverter in catalog.inverters
            ),
        ),
        pricing=replace(data.pricing, bos_price_per_kwp=convert(data.pricing.bos_price_per_kwp)),
    )


def test_the_exchange_rate_currency_is_the_one_foreign_currency_of_the_prices() -> None:
    assert make_reference_data().exchange_rate_currency is Currency.USD


def test_prices_all_in_euro_need_a_euro_rate() -> None:
    data = in_currency(make_reference_data(), Currency.EUR)

    assert data.exchange_rate_currency is Currency.EUR


def test_try_prices_alongside_one_foreign_currency_are_fine() -> None:
    # The default pricing already mixes USD (BOS) with TRY (labour, fixed cost).
    pricing = make_pricing_assumptions()
    assert {pricing.labour_price_per_kwp.currency, pricing.bos_price_per_kwp.currency} == {
        Currency.TRY,
        Currency.USD,
    }
    assert make_reference_data(pricing=pricing).exchange_rate_currency is Currency.USD


def test_prices_in_two_foreign_currencies_are_refused_with_a_clear_message() -> None:
    data = make_reference_data()
    mixed = replace(
        data.pricing, bos_price_per_kwp=Money(Decimal(100), Currency.EUR)
    )  # the catalog is in USD

    with pytest.raises(ValueError, match=r"EUR.*USD|USD.*EUR"):
        make_reference_data(pricing=mixed)


def test_a_foreign_labour_price_counts_towards_the_currency() -> None:
    data = make_reference_data(catalog=make_catalog())
    labour_in_euro = replace(data.pricing, labour_price_per_kwp=Money(Decimal(90), Currency.EUR))

    with pytest.raises(ValueError, match="EUR"):
        make_reference_data(pricing=labour_in_euro)


def test_prices_with_no_foreign_currency_are_refused() -> None:
    with pytest.raises(ValueError, match="foreign currency"):
        in_currency(make_reference_data(), Currency.TRY)
