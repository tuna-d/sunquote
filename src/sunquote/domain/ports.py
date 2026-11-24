"""Interfaces to everything outside the domain. Adapters implement them; tests use fakes."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sunquote.domain.model import Coordinates, GeocodingResult
from sunquote.domain.money import Currency, ExchangeRate
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
