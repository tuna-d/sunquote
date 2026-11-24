from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from sunquote.api.app import create_app
from sunquote.api.dependencies import AppDependencies
from sunquote.config import Settings
from sunquote.domain.service import QuoteService
from tests.factories import make_assumptions, make_catalog, make_pricing_assumptions
from tests.fakes import FakeExchangeRateProvider, FakeSpecificYieldProvider, FixedClock


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def specific_yield_provider() -> FakeSpecificYieldProvider:
    """The fake Specific Yield provider behind `client`; tests tweak it before the first call."""
    return FakeSpecificYieldProvider()


@pytest.fixture
def exchange_rate_provider() -> FakeExchangeRateProvider:
    """The fake TCMB behind `client` (40 TRY/USD); tests tweak it before the first call."""
    return FakeExchangeRateProvider()


@pytest.fixture
def client(
    specific_yield_provider: FakeSpecificYieldProvider,
    exchange_rate_provider: FakeExchangeRateProvider,
) -> Iterator[TestClient]:
    """An app built by the factory with explicit settings and fake collaborators."""
    service = QuoteService(
        specific_yield_provider=specific_yield_provider,
        exchange_rate_provider=exchange_rate_provider,
        clock=FixedClock(),
        catalog=make_catalog(),
        assumptions=make_assumptions(),
        pricing=make_pricing_assumptions(),
    )
    app = create_app(settings=Settings(), dependencies=AppDependencies(quote_service=service))
    with TestClient(app) as test_client:
        yield test_client
