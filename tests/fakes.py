"""In-memory stand-ins for the domain's ports. Later specs add the geocoder, exchange rate
provider and repository fakes here, so every test layer shares them."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sunquote.domain.errors import DomainError, UpstreamUnavailableError
from sunquote.domain.money import Currency, ExchangeRate
from sunquote.domain.ports import QuotePage, SpecificYieldQuery, StoredQuote
from sunquote.domain.production import SpecificYield
from sunquote.domain.quote import Quote, format_quote_number
from tests.factories import QUOTE_DATE, make_exchange_rate, make_specific_yield


class FixedClock:
    def __init__(self, today: date = QUOTE_DATE) -> None:
        self._today = today

    def today(self) -> date:
        return self._today


class FakeSpecificYieldProvider:
    """Returns a canned Specific Yield and records every query it receives.

    Pass `error` to simulate an outage.
    """

    def __init__(
        self,
        specific_yield: SpecificYield | None = None,
        error: DomainError | None = None,
    ) -> None:
        self.specific_yield = specific_yield or make_specific_yield()
        self.error = error
        self.queries: list[SpecificYieldQuery] = []

    async def fetch(self, query: SpecificYieldQuery) -> SpecificYield:
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.specific_yield


class FakeExchangeRateProvider:
    """Returns a canned Exchange Rate and records every (currency, quote date) it is asked for.

    Pass `error` to simulate an outage.
    """

    def __init__(
        self,
        rate: ExchangeRate | None = None,
        error: UpstreamUnavailableError | None = None,
    ) -> None:
        self.rate = rate or make_exchange_rate()
        self.error = error
        self.requests: list[tuple[Currency, date]] = []

    async def fetch(self, currency: Currency, quote_date: date) -> ExchangeRate:
        self.requests.append((currency, quote_date))
        if self.error is not None:
            raise self.error
        return self.rate


class FakeQuoteRepository:
    """Keeps Quotes in memory and numbers them per year, like the Postgres adapter.

    Each saved Quote is created one minute after the previous one, so "newest first" is
    deterministic. `issued_numbers` records every number handed out, saved or not.
    """

    def __init__(self) -> None:
        self.stored: list[StoredQuote] = []
        self.issued_numbers: list[str] = []
        self._last_sequence: dict[int, int] = {}
        self._clock = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)

    async def next_quote_number(self, year: int) -> str:
        sequence = self._last_sequence.get(year, 0) + 1
        self._last_sequence[year] = sequence
        number = format_quote_number(year, sequence)
        self.issued_numbers.append(number)
        return number

    async def save(
        self, quote: Quote, *, district: str | None = None, province: str | None = None
    ) -> StoredQuote:
        self._clock += timedelta(minutes=1)
        stored = StoredQuote(
            id=uuid4(),
            created_at=self._clock,
            quote=quote,
            district=district,
            province=province,
        )
        self.stored.append(stored)
        return stored

    async def get(self, quote_id: UUID) -> StoredQuote | None:
        return next((stored for stored in self.stored if stored.id == quote_id), None)

    async def list_newest_first(self, *, page: int, page_size: int) -> QuotePage:
        newest_first = sorted(self.stored, key=lambda stored: stored.created_at, reverse=True)
        start = (page - 1) * page_size
        return QuotePage(
            items=tuple(newest_first[start : start + page_size]), total=len(self.stored)
        )
