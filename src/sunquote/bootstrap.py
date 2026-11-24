"""Composition root: builds the real collaborators from settings.

This is the one place that knows which adapter implements which port.
"""

from collections.abc import Awaitable, Callable
from functools import partial

import httpx

from sunquote.adapters.clock import SystemClock
from sunquote.adapters.data_files import (
    default_data_dir,
    load_catalog,
    load_engineering_assumptions,
    load_pricing_assumptions,
)
from sunquote.adapters.postgres.migrate import upgrade_to_head
from sunquote.adapters.postgres.quote_repository import PostgresQuoteRepository, create_engine
from sunquote.adapters.pvgis import PvgisSpecificYieldProvider
from sunquote.adapters.tcmb import TcmbExchangeRateProvider
from sunquote.api.dependencies import AppDependencies
from sunquote.config import Settings
from sunquote.domain.ports import QuoteRepository
from sunquote.domain.service import QuoteService


def build_dependencies(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    quote_repository: QuoteRepository | None = None,
) -> AppDependencies:
    """Load the data files and wire the adapters. Makes no network call itself.

    `transport` replaces the HTTP transport, so tests can serve recorded responses.
    `quote_repository` replaces the Postgres one (no database is touched then, and no
    migration runs).
    """
    data_dir = settings.data_dir or default_data_dir()
    catalog = load_catalog(data_dir / "catalog.toml")
    assumptions = load_engineering_assumptions(data_dir / "assumptions.toml")
    pricing = load_pricing_assumptions(data_dir / "assumptions.toml")

    http_client = httpx.AsyncClient(timeout=settings.pvgis_timeout_seconds, transport=transport)
    provider = PvgisSpecificYieldProvider(
        client=http_client,
        base_url=settings.pvgis_base_url,
        timeout_seconds=settings.pvgis_timeout_seconds,
    )
    exchange_rate_provider = TcmbExchangeRateProvider(
        client=http_client,
        base_url=settings.tcmb_base_url,
        timeout_seconds=settings.tcmb_timeout_seconds,
    )
    startup: tuple[Callable[[], Awaitable[None]], ...] = ()
    closers: tuple[Callable[[], Awaitable[None]], ...] = (http_client.aclose,)
    if quote_repository is None:
        engine = create_engine(settings.database_url)
        quote_repository = PostgresQuoteRepository(engine)
        closers = (*closers, engine.dispose)
        if settings.migrate_on_startup:
            startup = (partial(upgrade_to_head, engine),)

    service = QuoteService(
        quote_repository=quote_repository,
        specific_yield_provider=provider,
        exchange_rate_provider=exchange_rate_provider,
        clock=SystemClock(),
        catalog=catalog,
        assumptions=assumptions,
        pricing=pricing,
    )
    return AppDependencies(
        quote_service=service,
        quote_repository=quote_repository,
        startup=startup,
        closers=closers,
    )
