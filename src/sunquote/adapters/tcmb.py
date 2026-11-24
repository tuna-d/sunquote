"""TCMB adapter: the USD/TRY and EUR/TRY Exchange Rate from the central bank's daily rate files.

TCMB publishes one XML file per business day at `<base>/<YYYYMM>/<DDMMYYYY>.xml` (about 15:30
Turkish time). Weekends and public holidays have no file: the server answers 404. A Quote uses
the forex selling rate of the last day *before* the quote date that has a file, which keeps the
result the same all day: today's file may not exist yet.
"""

import xml.etree.ElementTree as ET
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import httpx

from sunquote.domain.errors import UpstreamUnavailableError
from sunquote.domain.money import Currency, ExchangeRate

DEFAULT_TCMB_BASE_URL = "https://www.tcmb.gov.tr/kurlar"
# The longest run of days without a file is a bayram holiday bridged to a weekend, about nine
# days. Ten days back therefore always reaches a business day, and caps the requests per Quote.
MAX_LOOKBACK_DAYS = 10
_SERVICE = "TCMB"


class TcmbExchangeRateProvider:
    """Looks the rate up on `<base_url>/<YYYYMM>/<DDMMYYYY>.xml`, walking back day by day.

    The HTTP client is injected so tests can swap the transport. Every call carries its own
    timeout, whatever the client's defaults are.
    """

    def __init__(self, *, client: httpx.AsyncClient, base_url: str, timeout_seconds: float) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def fetch(self, currency: Currency, quote_date: date) -> ExchangeRate:
        if currency is Currency.TRY:
            raise ValueError("TRY has no exchange rate to TRY")
        for days_back in range(1, MAX_LOOKBACK_DAYS + 1):
            published_on = quote_date - timedelta(days=days_back)
            body = await self._get_day(published_on)
            if body is not None:
                return ExchangeRate(
                    base=currency,
                    quote=Currency.TRY,
                    rate=_forex_selling(body, currency),
                    rate_date=published_on,
                )
        raise UpstreamUnavailableError(
            _SERVICE, f"no rates were published in the {MAX_LOOKBACK_DAYS} days before {quote_date}"
        )

    async def _get_day(self, day: date) -> bytes | None:
        """The day's file, or None when TCMB published nothing that day (weekend, holiday)."""
        url = f"{self._base_url}/{day:%Y%m}/{day:%d%m%Y}.xml"
        try:
            response = await self._client.get(url, timeout=self._timeout_seconds)
        except httpx.TimeoutException:
            raise UpstreamUnavailableError(_SERVICE, "the request timed out") from None
        except httpx.TransportError as error:
            raise UpstreamUnavailableError(
                _SERVICE, f"could not connect ({type(error).__name__})"
            ) from None
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise UpstreamUnavailableError(_SERVICE, f"HTTP {response.status_code}")
        return response.content


def _forex_selling(body: bytes, currency: Currency) -> Decimal:
    """The `ForexSelling` of `currency` per one unit (some currencies are quoted per 100)."""
    try:
        root = ET.fromstring(body)
        entry = next(
            node for node in root.iter("Currency") if node.get("CurrencyCode") == currency.value
        )
        selling = Decimal(_text(entry, "ForexSelling"))
        unit = Decimal(_text(entry, "Unit"))
        rate = selling / unit
    except (ET.ParseError, StopIteration, InvalidOperation, ZeroDivisionError, ValueError):
        raise UpstreamUnavailableError(_SERVICE, "the response could not be parsed") from None
    if rate <= 0:
        raise UpstreamUnavailableError(_SERVICE, f"the {currency} rate is not positive")
    return rate


def _text(entry: ET.Element, tag: str) -> str:
    node = entry.find(tag)
    if node is None or node.text is None or not node.text.strip():
        raise ValueError(f"{tag} is missing")
    return node.text.strip()
