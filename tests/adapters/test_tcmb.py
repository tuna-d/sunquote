"""The TCMB adapter against recorded responses (no network).

Recordings (real responses fetched 2026-11-24): the daily rate files for Friday 2026-11-20
(USD forex selling 50.4936) and Monday 2026-11-23 (USD 50.6026, EUR 55.5655), and the HTML
404 page TCMB serves for a day with no publication (2026-11-21 and 22 were a weekend).
The real call is in `test_tcmb_integration.py`.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from sunquote.adapters.tcmb import TcmbExchangeRateProvider
from sunquote.domain.errors import UpstreamUnavailableError
from sunquote.domain.money import Currency

pytestmark = pytest.mark.anyio

RECORDINGS = Path(__file__).parent / "recordings"
BASE_URL = "https://tcmb.example/kurlar"
FRIDAY = RECORDINGS / "tcmb_2026-11-20_friday.xml"
MONDAY = RECORDINGS / "tcmb_2026-11-23_monday.xml"
NOT_PUBLISHED = RECORDINGS / "tcmb_not_published.html"
MONDAY_PATH = "/kurlar/202611/23112026.xml"


def published(path: Path) -> httpx.Response:
    return httpx.Response(200, content=path.read_bytes(), headers={"content-type": "text/xml"})


def not_published() -> httpx.Response:
    return httpx.Response(404, content=NOT_PUBLISHED.read_bytes())


def usd_file(selling: str, unit: str = "1") -> str:
    return (
        '<Tarih_Date Tarih="23.11.2026"><Currency Kod="USD" CurrencyCode="USD">'
        f"<Unit>{unit}</Unit><ForexSelling>{selling}</ForexSelling></Currency></Tarih_Date>"
    )


class FakeTcmb:
    """Serves a response per request path (404 for the rest) and remembers the paths asked."""

    def __init__(self, responses: dict[str, httpx.Response] | None = None) -> None:
        self.responses = responses or {}
        self.paths: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        return self.responses.get(request.url.path, not_published())


def provider_with(handler: FakeTcmb | httpx.MockTransport) -> TcmbExchangeRateProvider:
    transport = (
        handler if isinstance(handler, httpx.MockTransport) else httpx.MockTransport(handler)
    )
    return TcmbExchangeRateProvider(
        client=httpx.AsyncClient(transport=transport), base_url=BASE_URL, timeout_seconds=5.0
    )


def recorded_week() -> FakeTcmb:
    return FakeTcmb(
        {
            "/kurlar/202611/20112026.xml": published(FRIDAY),
            MONDAY_PATH: published(MONDAY),
        }
    )


async def test_uses_the_usd_forex_selling_rate_of_the_day_before_the_quote_date() -> None:
    tcmb = recorded_week()

    rate = await provider_with(tcmb).fetch(Currency.USD, date(2026, 11, 24))

    assert tcmb.paths == [MONDAY_PATH]
    assert (rate.base, rate.quote) == (Currency.USD, Currency.TRY)
    assert rate.rate == Decimal("50.6026")  # ForexSelling, not ForexBuying or Banknote*
    assert rate.rate_date == date(2026, 11, 23)
    assert rate.overridden is False


async def test_the_quote_dates_own_rate_is_never_used() -> None:
    tcmb = recorded_week()

    rate = await provider_with(tcmb).fetch(Currency.USD, date(2026, 11, 23))

    assert rate.rate_date == date(2026, 11, 20)
    assert MONDAY_PATH not in tcmb.paths


async def test_walks_back_over_a_weekend_to_the_last_business_day() -> None:
    tcmb = recorded_week()

    rate = await provider_with(tcmb).fetch(Currency.USD, date(2026, 11, 23))  # a Monday

    assert tcmb.paths == [
        "/kurlar/202611/22112026.xml",  # Sunday: 404
        "/kurlar/202611/21112026.xml",  # Saturday: 404
        "/kurlar/202611/20112026.xml",  # Friday: published
    ]
    assert rate.rate == Decimal("50.4936")
    assert rate.rate_date == date(2026, 11, 20)


async def test_walks_back_across_a_month_boundary() -> None:
    tcmb = FakeTcmb({"/kurlar/202602/27022026.xml": published(FRIDAY)})

    rate = await provider_with(tcmb).fetch(Currency.USD, date(2026, 3, 2))

    assert tcmb.paths[-1] == "/kurlar/202602/27022026.xml"
    assert rate.rate_date == date(2026, 2, 27)


async def test_gives_the_eur_selling_rate_too() -> None:
    rate = await provider_with(recorded_week()).fetch(Currency.EUR, date(2026, 11, 24))

    assert (rate.base, rate.quote) == (Currency.EUR, Currency.TRY)
    assert rate.rate == Decimal("55.5655")


async def test_try_needs_no_rate() -> None:
    with pytest.raises(ValueError, match="TRY"):
        await provider_with(recorded_week()).fetch(Currency.TRY, date(2026, 11, 24))


async def test_a_rate_quoted_per_hundred_units_is_scaled_to_one_unit() -> None:
    tcmb = FakeTcmb({MONDAY_PATH: httpx.Response(200, text=usd_file("5060.26", unit="100"))})

    rate = await provider_with(tcmb).fetch(Currency.USD, date(2026, 11, 24))

    assert rate.rate == Decimal("50.6026")


async def test_gives_up_when_nothing_was_published_for_ten_days() -> None:
    tcmb = FakeTcmb()

    with pytest.raises(UpstreamUnavailableError, match="TCMB"):
        await provider_with(tcmb).fetch(Currency.USD, date(2026, 11, 24))

    assert len(tcmb.paths) == 10
    assert tcmb.paths[0] == MONDAY_PATH
    assert tcmb.paths[-1] == "/kurlar/202611/14112026.xml"


async def test_timeout_is_upstream_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(UpstreamUnavailableError) as raised:
        await provider_with(httpx.MockTransport(handler)).fetch(Currency.USD, date(2026, 11, 24))

    assert raised.value.service == "TCMB"


async def test_connection_failure_is_upstream_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(UpstreamUnavailableError):
        await provider_with(httpx.MockTransport(handler)).fetch(Currency.USD, date(2026, 11, 24))


@pytest.mark.parametrize("status", [403, 429, 500, 502, 503])
async def test_other_errors_are_upstream_unavailable_and_do_not_walk_back(status: int) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(status, text="busy")

    with pytest.raises(UpstreamUnavailableError, match=str(status)):
        await provider_with(httpx.MockTransport(handler)).fetch(Currency.USD, date(2026, 11, 24))

    assert len(seen) == 1


@pytest.mark.parametrize(
    "body",
    [
        "not xml",
        "<Tarih_Date/>",
        usd_file("55").replace("USD", "EUR"),  # no USD entry
        usd_file(""),
        usd_file("n/a"),
        usd_file("-5"),
        usd_file("5", unit="0"),
    ],
)
async def test_a_response_without_a_usable_rate_is_upstream_unavailable(body: str) -> None:
    tcmb = FakeTcmb({MONDAY_PATH: httpx.Response(200, text=body)})

    with pytest.raises(UpstreamUnavailableError, match="TCMB"):
        await provider_with(tcmb).fetch(Currency.USD, date(2026, 11, 24))
