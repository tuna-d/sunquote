from collections.abc import Callable, Iterator
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from sunquote.api.app import create_app
from sunquote.api.dependencies import AppDependencies
from sunquote.config import Settings
from sunquote.domain.reference_data import ReferenceData
from sunquote.domain.service import QuoteService
from tests.factories import make_reference_data
from tests.fakes import (
    FakeExchangeRateProvider,
    FakeGeocoder,
    FakeQuoteRepository,
    FakeSpecificYieldProvider,
    FixedClock,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def geocoder() -> FakeGeocoder:
    return FakeGeocoder()


@pytest.fixture
def specific_yield_provider() -> FakeSpecificYieldProvider:
    """The fake Specific Yield provider behind `client`; tests tweak it before the first call."""
    return FakeSpecificYieldProvider()


@pytest.fixture
def exchange_rate_provider() -> FakeExchangeRateProvider:
    """The fake TCMB behind `client` (40 TRY/USD); tests tweak it before the first call."""
    return FakeExchangeRateProvider()


@pytest.fixture
def quote_repository() -> FakeQuoteRepository:
    """The in-memory repository behind `client`; tests inspect what was stored."""
    return FakeQuoteRepository()


ClientFactory = Callable[..., TestClient]


@pytest.fixture
def client_factory(
    geocoder: FakeGeocoder,
    specific_yield_provider: FakeSpecificYieldProvider,
    exchange_rate_provider: FakeExchangeRateProvider,
    quote_repository: FakeQuoteRepository,
) -> Iterator[ClientFactory]:
    """Builds clients on the fake collaborators; a test overrides only the clock or the
    reference data it is about."""
    with ExitStack() as stack:

        def make(
            *, clock: FixedClock | None = None, reference_data: ReferenceData | None = None
        ) -> TestClient:
            service = QuoteService(
                quote_repository=quote_repository,
                geocoder=geocoder,
                specific_yield_provider=specific_yield_provider,
                exchange_rate_provider=exchange_rate_provider,
                clock=clock or FixedClock(),
                reference_data=reference_data or make_reference_data(),
            )
            app = create_app(
                settings=Settings(),
                dependencies=AppDependencies(
                    quote_service=service, quote_repository=quote_repository
                ),
            )
            return stack.enter_context(TestClient(app))

        yield make


@pytest.fixture
def client(client_factory: ClientFactory) -> TestClient:
    """An app built by the factory with explicit settings and fake collaborators."""
    return client_factory()
