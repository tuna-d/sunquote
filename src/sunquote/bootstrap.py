"""Composition root: builds the real collaborators from settings.

This is the one place that knows which adapter implements which port.
"""

import httpx

from sunquote.adapters.clock import SystemClock
from sunquote.adapters.data_files import (
    default_data_dir,
    load_catalog,
    load_engineering_assumptions,
    load_pricing_assumptions,
)
from sunquote.adapters.pvgis import PvgisSpecificYieldProvider
from sunquote.adapters.tcmb import TcmbExchangeRateProvider
from sunquote.api.dependencies import AppDependencies
from sunquote.config import Settings
from sunquote.domain.service import QuoteService


def build_dependencies(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> AppDependencies:
    """Load the data files and wire the adapters. Makes no network call itself.

    `transport` replaces the HTTP transport, so tests can serve recorded responses.
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
    service = QuoteService(
        specific_yield_provider=provider,
        exchange_rate_provider=exchange_rate_provider,
        clock=SystemClock(),
        catalog=catalog,
        assumptions=assumptions,
        pricing=pricing,
    )
    return AppDependencies(quote_service=service, closers=(http_client.aclose,))
