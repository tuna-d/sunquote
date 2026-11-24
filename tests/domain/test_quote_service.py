from datetime import date
from decimal import Decimal

import pytest

from sunquote.domain.errors import UpstreamUnavailableError
from sunquote.domain.money import Currency, ExchangeRateOverride
from sunquote.domain.service import QuoteService
from tests.factories import (
    QUOTE_DATE,
    RATE_DATE,
    make_assumptions,
    make_catalog,
    make_exchange_rate,
    make_financial_assumptions,
    make_pricing_assumptions,
    make_request,
    make_specific_yield,
    make_tariff,
)
from tests.fakes import FakeExchangeRateProvider, FakeSpecificYieldProvider, FixedClock

pytestmark = pytest.mark.anyio


def make_service(
    provider: FakeSpecificYieldProvider,
    rates: FakeExchangeRateProvider | None = None,
) -> QuoteService:
    return QuoteService(
        specific_yield_provider=provider,
        exchange_rate_provider=rates or FakeExchangeRateProvider(),
        clock=FixedClock(),
        catalog=make_catalog(),
        assumptions=make_assumptions(system_loss_percent="12"),
        pricing=make_pricing_assumptions(),
        tariff=make_tariff(),
        financial=make_financial_assumptions(),
    )


async def test_service_fetches_the_yield_for_the_roof_and_builds_the_quote() -> None:
    provider = FakeSpecificYieldProvider(make_specific_yield(annual="1500"))

    quote = await make_service(provider).create_quote(
        make_request(azimuth_deg="225", tilt_deg="35")
    )

    [query] = provider.queries
    assert query.coordinates.latitude == Decimal("39.9334")
    assert query.coordinates.longitude == Decimal("32.8597")
    assert query.tilt_deg == Decimal("35")
    assert query.azimuth_deg == Decimal("225")
    assert query.system_loss_percent == Decimal("12")
    assert quote.quote_date == QUOTE_DATE
    assert quote.system_options[0].annual_production_kwh == Decimal("6000")


async def test_service_prices_with_the_usd_rate_for_the_quote_date() -> None:
    rates = FakeExchangeRateProvider(make_exchange_rate("40"))

    quote = await make_service(FakeSpecificYieldProvider(), rates).create_quote(make_request())

    assert rates.requests == [(Currency.USD, QUOTE_DATE)]
    assert quote.assumptions.exchange_rate == make_exchange_rate("40")
    assert quote.system_options[0].price.installation_cost.amount == Decimal("106000")


async def test_an_override_replaces_the_provider_and_is_recorded() -> None:
    rates = FakeExchangeRateProvider(make_exchange_rate("40"))
    override = ExchangeRateOverride(rate=Decimal("45"), rate_date=date(2026, 11, 1))

    quote = await make_service(FakeSpecificYieldProvider(), rates).create_quote(
        make_request(), exchange_rate_override=override
    )

    assert rates.requests == []
    recorded = quote.assumptions.exchange_rate
    assert (recorded.base, recorded.quote) == (Currency.USD, Currency.TRY)
    assert (recorded.rate, recorded.rate_date, recorded.overridden) == (
        Decimal("45"),
        date(2026, 11, 1),
        True,
    )
    # 1,850 USD x 45 = 83,250 + 12,000 labour + 20,000 fixed
    assert quote.system_options[0].price.installation_cost.amount == Decimal("115250")


async def test_the_provider_rate_is_not_marked_overridden() -> None:
    quote = await make_service(FakeSpecificYieldProvider()).create_quote(make_request())

    assert quote.assumptions.exchange_rate.overridden is False
    assert quote.assumptions.exchange_rate.rate_date == RATE_DATE


async def test_upstream_outage_propagates_and_builds_no_quote() -> None:
    provider = FakeSpecificYieldProvider(error=UpstreamUnavailableError("PVGIS", "timed out"))

    with pytest.raises(UpstreamUnavailableError):
        await make_service(provider).create_quote(make_request())


async def test_exchange_rate_outage_propagates_and_builds_no_quote() -> None:
    rates = FakeExchangeRateProvider(error=UpstreamUnavailableError("TCMB", "timed out"))

    with pytest.raises(UpstreamUnavailableError, match="TCMB"):
        await make_service(FakeSpecificYieldProvider(), rates).create_quote(make_request())


async def test_an_override_works_while_tcmb_is_down() -> None:
    rates = FakeExchangeRateProvider(error=UpstreamUnavailableError("TCMB", "timed out"))
    override = ExchangeRateOverride(rate=Decimal("45"), rate_date=date(2026, 11, 1))

    quote = await make_service(FakeSpecificYieldProvider(), rates).create_quote(
        make_request(), exchange_rate_override=override
    )

    assert quote.assumptions.exchange_rate.overridden is True


@pytest.mark.parametrize("rate", ["0", "-3"])
def test_an_override_rate_must_be_positive(rate: str) -> None:
    with pytest.raises(ValueError, match="rate"):
        ExchangeRateOverride(rate=Decimal(rate), rate_date=date(2026, 11, 1))
