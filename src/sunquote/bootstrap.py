"""Composition root: builds the real collaborators from settings.

This is the one place that knows which adapter implements which port.
"""

from collections.abc import Awaitable, Callable
from functools import partial

import httpx
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from sunquote.adapters.clock import SystemClock
from sunquote.adapters.data_files import (
    default_data_dir,
    load_catalog,
    load_engineering_assumptions,
    load_financial_assumptions,
    load_pricing_assumptions,
    load_residential_tariff,
)
from sunquote.adapters.gemini import GeminiNarrativeWriter
from sunquote.adapters.nominatim import NominatimGeocoder
from sunquote.adapters.postgres.migrate import upgrade_to_head
from sunquote.adapters.postgres.quote_repository import PostgresQuoteRepository, create_engine
from sunquote.adapters.pvgis import PvgisSpecificYieldProvider
from sunquote.adapters.redis_cache import (
    CachedExchangeRateProvider,
    CachedGeocoder,
    CachedSpecificYieldProvider,
)
from sunquote.adapters.tcmb import TcmbExchangeRateProvider
from sunquote.api.dependencies import AppDependencies
from sunquote.config import Settings
from sunquote.domain.ports import (
    ExchangeRateProvider,
    Geocoder,
    NarrativeWriter,
    QuoteRepository,
    SpecificYieldProvider,
)
from sunquote.domain.reference_data import ReferenceData
from sunquote.domain.service import QuoteService


def build_dependencies(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    quote_repository: QuoteRepository | None = None,
    narrative_writer: NarrativeWriter | None = None,
) -> AppDependencies:
    """Load the data files and wire the adapters. Makes no network call itself.

    `transport` replaces the HTTP transport, so tests can serve recorded responses.
    `quote_repository` replaces the Postgres one (no database is touched then, and no
    migration runs). `narrative_writer` writes the Quotes' Narrative; with none, the Gemini
    writer is wired when `SUNQUOTE_GEMINI_API_KEY` is set, and otherwise every Quote records
    `fallback` and shows the fixed text.
    """
    data_dir = settings.data_dir or default_data_dir()
    reference_data = ReferenceData(
        catalog=load_catalog(data_dir / "catalog.toml"),
        engineering=load_engineering_assumptions(data_dir / "assumptions.toml"),
        pricing=load_pricing_assumptions(data_dir / "assumptions.toml"),
        tariff=load_residential_tariff(data_dir / "tariff.toml"),
        financial=load_financial_assumptions(data_dir / "assumptions.toml"),
    )

    http_client = httpx.AsyncClient(timeout=settings.pvgis_timeout_seconds, transport=transport)
    geocoder: Geocoder = NominatimGeocoder(
        client=http_client,
        base_url=settings.nominatim_base_url,
        timeout_seconds=settings.nominatim_timeout_seconds,
    )
    specific_yield_provider: SpecificYieldProvider = PvgisSpecificYieldProvider(
        client=http_client,
        base_url=settings.pvgis_base_url,
        timeout_seconds=settings.pvgis_timeout_seconds,
    )
    exchange_rate_provider: ExchangeRateProvider = TcmbExchangeRateProvider(
        client=http_client,
        base_url=settings.tcmb_base_url,
        timeout_seconds=settings.tcmb_timeout_seconds,
    )
    if narrative_writer is None and settings.gemini_api_key is not None:
        narrative_writer = GeminiNarrativeWriter(
            client=http_client,
            api_key=settings.gemini_api_key.get_secret_value(),
            model=settings.gemini_model,
            base_url=settings.gemini_base_url,
            timeout_seconds=settings.gemini_timeout_seconds,
        )
    startup: tuple[Callable[[], Awaitable[None]], ...] = ()
    closers: tuple[Callable[[], Awaitable[None]], ...] = (http_client.aclose,)
    if settings.redis_url:
        redis = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
            retry=Retry(NoBackoff(), 0),
        )
        geocoder = CachedGeocoder(geocoder, redis)
        specific_yield_provider = CachedSpecificYieldProvider(specific_yield_provider, redis)
        exchange_rate_provider = CachedExchangeRateProvider(exchange_rate_provider, redis)
        closers = (*closers, redis.aclose)

    if quote_repository is None:
        engine = create_engine(settings.database_url)
        quote_repository = PostgresQuoteRepository(engine)
        closers = (*closers, engine.dispose)
        if settings.migrate_on_startup:
            startup = (partial(upgrade_to_head, engine),)

    service = QuoteService(
        quote_repository=quote_repository,
        geocoder=geocoder,
        specific_yield_provider=specific_yield_provider,
        exchange_rate_provider=exchange_rate_provider,
        clock=SystemClock(),
        reference_data=reference_data,
        narrative_writer=narrative_writer,
        narrative_budget_seconds=settings.narrative_timeout_seconds,
    )
    return AppDependencies(
        quote_service=service,
        quote_repository=quote_repository,
        startup=startup,
        closers=closers,
    )
