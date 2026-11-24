"""In-memory stand-ins shared by tests of the domain and API."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sunquote.domain.conversation import (
    ChatMessage,
    ModelReply,
    ReplyRejection,
    ToolDeclaration,
    ToolExchange,
)
from sunquote.domain.errors import (
    ConversationUnavailableError,
    DomainError,
    NarrativeUnavailableError,
    UpstreamUnavailableError,
)
from sunquote.domain.model import Coordinates, GeocodingResult
from sunquote.domain.money import Currency, ExchangeRate
from sunquote.domain.narrative import NarrativeContext, NarrativeDraft, Violation
from sunquote.domain.ports import QuotePage, SpecificYieldQuery, StoredQuote
from sunquote.domain.production import SpecificYield
from sunquote.domain.quote import Quote, format_quote_number
from tests.factories import QUOTE_DATE, make_exchange_rate, make_specific_yield

NARRATIVE_TIME = datetime(2026, 11, 24, 9, 30, tzinfo=UTC)


class FixedClock:
    def __init__(self, today: date = QUOTE_DATE, now: datetime = NARRATIVE_TIME) -> None:
        self._today = today
        self._now = now

    def today(self) -> date:
        return self._today

    def now(self) -> datetime:
        return self._now


class ScriptedNarrativeWriter:
    """A NarrativeWriter that answers each call with the next scripted item: a draft is
    returned, an exception is raised, a number of seconds sleeps first (to hit a timeout).

    Records every context it receives and the violations passed with each call.
    """

    def __init__(
        self,
        *script: NarrativeDraft | Exception | float,
        model_name: str = "fake-model-1",
    ) -> None:
        self.model_name = model_name
        self._script = list(script)
        self.contexts: list[NarrativeContext] = []
        self.violations: list[tuple[Violation, ...]] = []

    @property
    def calls(self) -> int:
        return len(self.contexts)

    async def write(
        self, context: NarrativeContext, *, previous_violations: Sequence[Violation] = ()
    ) -> NarrativeDraft:
        self.contexts.append(context)
        self.violations.append(tuple(previous_violations))
        item = self._script.pop(0)
        if isinstance(item, int | float):
            await asyncio.sleep(item)
            raise NarrativeUnavailableError("scripted sleep ended")
        if isinstance(item, Exception):
            raise item
        return item


@dataclass(frozen=True)
class ConversationCall:
    """What the assistant sent the model in one call."""

    system_instruction: str
    messages: tuple[ChatMessage, ...]
    tools: tuple[ToolDeclaration, ...]
    exchanges: tuple[ToolExchange, ...]
    rejected_reply: ReplyRejection | None


class ScriptedConversationModel:
    """A ConversationModel that answers each call with the next scripted item: a reply (text
    or tool call) is returned, an exception is raised, a number of seconds sleeps first (to hit
    a time budget).

    Records every call it receives.
    """

    def __init__(
        self,
        *script: ModelReply | Exception | float,
        model_name: str = "fake-chat-1",
    ) -> None:
        self.model_name = model_name
        self._script = list(script)
        self.calls: list[ConversationCall] = []

    async def respond(
        self,
        *,
        system_instruction: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDeclaration],
        exchanges: Sequence[ToolExchange] = (),
        rejected_reply: ReplyRejection | None = None,
    ) -> ModelReply:
        self.calls.append(
            ConversationCall(
                system_instruction,
                tuple(messages),
                tuple(tools),
                tuple(exchanges),
                rejected_reply,
            )
        )
        item = self._script.pop(0)
        if isinstance(item, int | float):
            await asyncio.sleep(item)
            raise ConversationUnavailableError("scripted sleep ended")
        if isinstance(item, Exception):
            raise item
        return item


class FakeGeocoder:
    def __init__(self) -> None:
        self.result = GeocodingResult(
            display_name="An\u0131tkabir, Çankaya, Ankara, Türkiye",
            coordinates=Coordinates(
                latitude=Decimal("39.9267385"), longitude=Decimal("32.8365635")
            ),
            district="Çankaya",
            province="Ankara",
        )
        self.error: DomainError | None = None
        self.addresses: list[str] = []

    async def geocode(self, address: str) -> GeocodingResult:
        self.addresses.append(address)
        if self.error is not None:
            raise self.error
        return self.result


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
