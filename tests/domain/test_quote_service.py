from datetime import date
from decimal import Decimal

import pytest

from sunquote.domain.errors import NoViableSystemError, UpstreamUnavailableError
from sunquote.domain.money import Currency, ExchangeRate, ExchangeRateOverride
from sunquote.domain.reference_data import ReferenceData
from sunquote.domain.service import QuoteService
from tests.domain.test_reference_data import in_currency
from tests.factories import (
    QUOTE_DATE,
    RATE_DATE,
    make_assumptions,
    make_exchange_rate,
    make_reference_data,
    make_request,
    make_specific_yield,
)
from tests.fakes import (
    FakeExchangeRateProvider,
    FakeGeocoder,
    FakeQuoteRepository,
    FakeSpecificYieldProvider,
    FixedClock,
)

pytestmark = pytest.mark.anyio


def make_service(
    provider: FakeSpecificYieldProvider,
    rates: FakeExchangeRateProvider | None = None,
    repository: FakeQuoteRepository | None = None,
    clock: FixedClock | None = None,
    reference_data: ReferenceData | None = None,
) -> QuoteService:
    return QuoteService(
        quote_repository=repository or FakeQuoteRepository(),
        geocoder=FakeGeocoder(),
        specific_yield_provider=provider,
        exchange_rate_provider=rates or FakeExchangeRateProvider(),
        clock=clock or FixedClock(),
        reference_data=reference_data
        or make_reference_data(assumptions=make_assumptions(system_loss_percent="12")),
    )


async def test_service_fetches_the_yield_for_the_roof_and_builds_the_quote() -> None:
    provider = FakeSpecificYieldProvider(make_specific_yield(annual="1500"))

    stored = await make_service(provider).create_quote(
        make_request(azimuth_deg="225", tilt_deg="35")
    )
    quote = stored.quote

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

    stored = await make_service(FakeSpecificYieldProvider(), rates).create_quote(make_request())
    quote = stored.quote

    assert rates.requests == [(Currency.USD, QUOTE_DATE)]
    assert quote.assumptions.exchange_rate == make_exchange_rate("40")
    assert quote.system_options[0].price.installation_cost.amount == Decimal("106000")


async def test_an_override_replaces_the_provider_and_is_recorded() -> None:
    rates = FakeExchangeRateProvider(make_exchange_rate("40"))
    override = ExchangeRateOverride(rate=Decimal("45"), rate_date=date(2026, 11, 1))

    stored = await make_service(FakeSpecificYieldProvider(), rates).create_quote(
        make_request(), exchange_rate_override=override
    )
    quote = stored.quote

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


async def test_the_rate_is_fetched_for_the_currency_the_data_files_price_in() -> None:
    euro_data = in_currency(make_reference_data(), Currency.EUR)
    euro_rate = ExchangeRate(
        base=Currency.EUR, quote=Currency.TRY, rate=Decimal(45), rate_date=RATE_DATE
    )
    rates = FakeExchangeRateProvider(euro_rate)

    stored = await make_service(
        FakeSpecificYieldProvider(), rates, reference_data=euro_data
    ).create_quote(make_request())

    assert rates.requests == [(Currency.EUR, QUOTE_DATE)]
    assert stored.quote.assumptions.exchange_rate == euro_rate
    # 1,850 EUR x 45 = 83,250 + 12,000 labour + 20,000 fixed
    assert stored.quote.system_options[0].price.installation_cost.amount == Decimal("115250")


async def test_an_override_is_in_the_currency_the_data_files_price_in() -> None:
    euro_data = in_currency(make_reference_data(), Currency.EUR)
    override = ExchangeRateOverride(rate=Decimal("46"), rate_date=date(2026, 11, 1))

    stored = await make_service(FakeSpecificYieldProvider(), reference_data=euro_data).create_quote(
        make_request(), exchange_rate_override=override
    )

    recorded = stored.quote.assumptions.exchange_rate
    assert (recorded.base, recorded.quote, recorded.rate) == (
        Currency.EUR,
        Currency.TRY,
        Decimal("46"),
    )
    assert recorded.overridden is True


async def test_the_provider_rate_is_not_marked_overridden() -> None:
    stored = await make_service(FakeSpecificYieldProvider()).create_quote(make_request())
    quote = stored.quote

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

    stored = await make_service(FakeSpecificYieldProvider(), rates).create_quote(
        make_request(), exchange_rate_override=override
    )
    quote = stored.quote

    assert quote.assumptions.exchange_rate.overridden is True


@pytest.mark.parametrize("rate", ["0", "-3"])
def test_an_override_rate_must_be_positive(rate: str) -> None:
    with pytest.raises(ValueError, match="rate"):
        ExchangeRateOverride(rate=Decimal(rate), rate_date=date(2026, 11, 1))


async def test_the_quote_is_numbered_by_the_repository_for_the_quote_year_and_stored() -> None:
    repository = FakeQuoteRepository()
    service = make_service(FakeSpecificYieldProvider(), repository=repository)

    first = await service.create_quote(make_request())
    second = await service.create_quote(make_request())

    assert first.quote.quote_number == "SQ-2026-000001"
    assert second.quote.quote_number == "SQ-2026-000002"
    assert first.quote.valid_until == date(2026, 12, 9)  # 2026-11-24 + 15 days
    assert first.id != second.id
    assert repository.stored == [first, second]
    assert await repository.get(first.id) == first


async def test_the_sequence_restarts_in_a_new_year() -> None:
    repository = FakeQuoteRepository()
    old = make_service(
        FakeSpecificYieldProvider(), repository=repository, clock=FixedClock(date(2026, 12, 31))
    )
    new = make_service(
        FakeSpecificYieldProvider(), repository=repository, clock=FixedClock(date(2027, 1, 1))
    )

    numbers = [
        (await old.create_quote(make_request())).quote.quote_number,
        (await new.create_quote(make_request())).quote.quote_number,
    ]

    assert numbers == ["SQ-2026-000001", "SQ-2027-000001"]


async def test_nothing_is_stored_or_numbered_when_an_upstream_is_down() -> None:
    repository = FakeQuoteRepository()
    provider = FakeSpecificYieldProvider(error=UpstreamUnavailableError("PVGIS", "timed out"))
    rates = FakeExchangeRateProvider(error=UpstreamUnavailableError("TCMB", "timed out"))

    with pytest.raises(UpstreamUnavailableError):
        await make_service(provider, repository=repository).create_quote(make_request())
    with pytest.raises(UpstreamUnavailableError):
        await make_service(FakeSpecificYieldProvider(), rates, repository=repository).create_quote(
            make_request()
        )

    assert repository.stored == []
    assert repository.issued_numbers == []


async def test_nothing_is_stored_when_no_system_is_viable() -> None:
    repository = FakeQuoteRepository()

    with pytest.raises(NoViableSystemError):
        await make_service(FakeSpecificYieldProvider(), repository=repository).create_quote(
            make_request(usable_area_m2="1")
        )

    assert repository.stored == []
