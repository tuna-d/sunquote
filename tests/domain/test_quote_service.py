from decimal import Decimal

import pytest

from sunquote.domain.errors import UpstreamUnavailableError
from sunquote.domain.service import QuoteService
from tests.factories import (
    QUOTE_DATE,
    make_assumptions,
    make_catalog,
    make_request,
    make_specific_yield,
)
from tests.fakes import FakeSpecificYieldProvider, FixedClock

pytestmark = pytest.mark.anyio


def make_service(provider: FakeSpecificYieldProvider) -> QuoteService:
    return QuoteService(
        specific_yield_provider=provider,
        clock=FixedClock(),
        catalog=make_catalog(),
        assumptions=make_assumptions(system_loss_percent="12"),
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


async def test_upstream_outage_propagates_and_builds_no_quote() -> None:
    provider = FakeSpecificYieldProvider(error=UpstreamUnavailableError("PVGIS", "timed out"))

    with pytest.raises(UpstreamUnavailableError):
        await make_service(provider).create_quote(make_request())
