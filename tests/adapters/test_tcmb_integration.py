"""One real call to TCMB. Run by hand with `uv run pytest -m integration`."""

from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest

from sunquote.adapters.tcmb import DEFAULT_TCMB_BASE_URL, TcmbExchangeRateProvider
from sunquote.domain.money import Currency

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_real_tcmb_returns_the_latest_published_usd_selling_rate() -> None:
    today = date.today()
    async with httpx.AsyncClient() as client:
        provider = TcmbExchangeRateProvider(
            client=client, base_url=DEFAULT_TCMB_BASE_URL, timeout_seconds=30.0
        )
        rate = await provider.fetch(Currency.USD, today)

    assert (rate.base, rate.quote) == (Currency.USD, Currency.TRY)
    assert Decimal(20) < rate.rate < Decimal(500)  # a sanity band, not a market claim
    assert today - timedelta(days=10) <= rate.rate_date < today
