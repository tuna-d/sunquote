"""Interfaces to everything outside the domain. Adapters implement them; tests use fakes."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sunquote.domain.conversation import (
    ChatMessage,
    ModelReply,
    ReplyRejection,
    ToolDeclaration,
    ToolExchange,
)
from sunquote.domain.model import Coordinates, GeocodingResult
from sunquote.domain.money import Currency, ExchangeRate
from sunquote.domain.narrative import NarrativeContext, NarrativeDraft, Violation
from sunquote.domain.production import SpecificYield
from sunquote.domain.quote import Quote


class Geocoder(Protocol):
    async def geocode(self, address: str) -> GeocodingResult:
        """Resolve an Address, raising `AddressNotFoundError` or `UpstreamUnavailableError`."""
        ...


@dataclass(frozen=True, slots=True)
class SpecificYieldQuery:
    """What to estimate: where, and for which orientation. `azimuth_deg` is a compass bearing."""

    coordinates: Coordinates
    tilt_deg: Decimal
    azimuth_deg: Decimal
    system_loss_percent: Decimal


class SpecificYieldProvider(Protocol):
    async def fetch(self, query: SpecificYieldQuery) -> SpecificYield:
        """Raises `UpstreamUnavailableError` when the source cannot give an answer."""
        ...


class ExchangeRateProvider(Protocol):
    async def fetch(self, currency: Currency, quote_date: date) -> ExchangeRate:
        """The `currency`/TRY rate a Quote issued on `quote_date` is priced with.

        The adapter decides which published rate that is (TCMB: the forex selling rate of the
        last business day before `quote_date`). Raises `UpstreamUnavailableError` when the
        source cannot give an answer.
        """
        ...


class Clock(Protocol):
    def today(self) -> date:
        """The date a Quote is issued on."""
        ...

    def now(self) -> datetime:
        """The current moment, timezone-aware UTC."""
        ...


class CounterStore(Protocol):
    """Shared counters that expire, for limits that hold across serverless instances.

    The per-IP rate limits use it, and the daily Gemini budget will too. A counter is a named
    integer that starts at zero and disappears `ttl_seconds` after it was created.
    """

    async def increment(self, key: str, *, ttl_seconds: int) -> int:
        """Add one to the counter `key` and return its new value, so the first call returns 1.

        A counter that is missing or has expired starts again at 1 and lives `ttl_seconds`.
        Concurrent calls each get a distinct value.
        """
        ...


class NarrativeWriter(Protocol):
    """Writes the prose of a Quote (ADR 0001): text with placeholders, never a figure."""

    @property
    def model_name(self) -> str:
        """The name of the model that writes, recorded with the Quote."""
        ...

    async def write(
        self, context: NarrativeContext, *, previous_violations: Sequence[Violation] = ()
    ) -> NarrativeDraft:
        """A draft for the Quote `context` describes.

        On a retry, `previous_violations` are what was wrong with the previous attempt. Any
        failure is raised as `NarrativeUnavailableError`.
        """
        ...


class ConversationModel(Protocol):
    """The LLM behind the quote assistant: one step of a tool-calling conversation. Its
    instruction is the adapter's, like the Narrative writer's prompt."""

    @property
    def model_name(self) -> str:
        """The name of the model that answers."""
        ...

    async def respond(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDeclaration],
        exchanges: Sequence[ToolExchange] = (),
        rejected_reply: ReplyRejection | None = None,
    ) -> ModelReply:
        """The model's next move: text, or a call to one of `tools`.

        `messages` is the conversation so far, ending with the Sales Rep's message. `exchanges`
        are the tool calls made since then with their results, oldest first, and
        `rejected_reply` is a text answer the assistant refused and the reason, to be corrected.
        Any failure is raised as `ConversationUnavailableError`.
        """
        ...


@dataclass(frozen=True, slots=True)
class StoredQuote:
    """A Quote as the repository holds it: the immutable Quote plus its identity.

    `district` and `province` are optional listing columns supplied by geocoding.
    """

    id: UUID
    created_at: datetime
    quote: Quote
    district: str | None = None
    province: str | None = None


@dataclass(frozen=True, slots=True)
class QuotePage:
    """One page of stored Quotes, newest first, with the total number of stored Quotes."""

    items: tuple[StoredQuote, ...]
    total: int


class QuoteRepository(Protocol):
    """Stores Quotes and issues their numbers. A stored Quote can never be changed or deleted,
    so the port has no update or delete."""

    async def next_quote_number(self, year: int) -> str:
        """The next free Quote Number of `year` (`SQ-<year>-<6-digit sequence>`).

        Numbers are unique and consecutive, also under concurrent calls, and the sequence
        restarts each year.
        """
        ...

    async def save(
        self, quote: Quote, *, district: str | None = None, province: str | None = None
    ) -> StoredQuote:
        """Store `quote` under a new id and return it as stored."""
        ...

    async def get(self, quote_id: UUID) -> StoredQuote | None:
        """The stored Quote, or None when no Quote has that id."""
        ...

    async def list_newest_first(self, *, page: int, page_size: int) -> QuotePage:
        """One page (1-based) of stored Quotes, the most recently created first."""
        ...
