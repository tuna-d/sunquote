"""Redis cache contracts. The real Redis tests use SUNQUOTE_TEST_REDIS_URL."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from redis.asyncio import Redis
from redis.exceptions import TimeoutError as RedisTimeoutError

from sunquote.adapters.pvgis import PvgisSpecificYieldProvider, pvgis_request
from sunquote.adapters.redis_cache import (
    CachedExchangeRateProvider,
    CachedGeocoder,
    CachedSpecificYieldProvider,
    specific_yield_cache_key,
)
from sunquote.domain.errors import AddressNotFoundError, UpstreamUnavailableError
from sunquote.domain.model import Coordinates
from sunquote.domain.money import Currency
from sunquote.domain.ports import SpecificYieldQuery
from tests.factories import make_exchange_rate
from tests.fakes import FakeExchangeRateProvider, FakeGeocoder, FakeSpecificYieldProvider

pytestmark = pytest.mark.anyio


async def test_geocoding_reuses_a_match_for_the_normalised_address(redis_client: Redis) -> None:
    suffix = uuid4().hex
    address = f"  İSTANBUL\t  IŞIK   {suffix}  "
    key = f"sunquote:v1:geocoding:istanbul ışık {suffix}"
    provider = FakeGeocoder()
    cache = CachedGeocoder(provider, redis_client)

    try:
        assert await cache.geocode(address) == provider.result
        assert provider.addresses == [address]

        provider.error = AddressNotFoundError()
        assert await cache.geocode(f"istanbul ışık {suffix}") == provider.result
        assert 2_591_995 <= await redis_client.ttl(key) <= 2_592_000
    finally:
        await redis_client.delete(key)


async def test_an_address_without_a_match_is_looked_up_again(redis_client: Redis) -> None:
    address = f"Ankara {uuid4().hex}"
    key = f"sunquote:v1:geocoding:{address.lower()}"
    provider = FakeGeocoder()
    provider.error = AddressNotFoundError()
    cache = CachedGeocoder(provider, redis_client)

    try:
        with pytest.raises(AddressNotFoundError):
            await cache.geocode(address)

        assert await redis_client.exists(key) == 0
        provider.error = None
        assert await cache.geocode(address) == provider.result
    finally:
        await redis_client.delete(key)


async def test_specific_yield_is_cached_for_rounded_coordinates_and_roof_inputs(
    redis_client: Redis,
) -> None:
    suffix = f"{uuid4().int % 10**18:018d}1"
    query = SpecificYieldQuery(
        coordinates=Coordinates(Decimal("39.9325"), Decimal("32.8595")),
        tilt_deg=Decimal(f"30.{suffix}"),
        azimuth_deg=Decimal("190.0"),
        system_loss_percent=Decimal("14.00"),
    )
    nearby = replace(
        query,
        coordinates=Coordinates(Decimal("39.9334"), Decimal("32.8604")),
        tilt_deg=Decimal(f"30.{suffix}0"),
        azimuth_deg=Decimal("190"),
        system_loss_percent=Decimal("14"),
    )
    key = f"sunquote:v1:specific-yield:39.933:32.860:30.{suffix}:10:14"
    provider = FakeSpecificYieldProvider()
    cache = CachedSpecificYieldProvider(provider, redis_client)

    try:
        assert await cache.fetch(query) == provider.specific_yield
        assert provider.queries == [query]

        provider.error = UpstreamUnavailableError("PVGIS", "offline")
        assert await cache.fetch(nearby) == provider.specific_yield
        assert 2_591_995 <= await redis_client.ttl(key) <= 2_592_000

        different_queries = (
            replace(query, coordinates=Coordinates(Decimal("39.9324"), Decimal("32.8595"))),
            replace(query, coordinates=Coordinates(Decimal("39.9325"), Decimal("32.8594"))),
            replace(query, tilt_deg=Decimal(f"31.{suffix}")),
            replace(query, azimuth_deg=Decimal("191")),
            replace(query, system_loss_percent=Decimal("15")),
        )
        for different in different_queries:
            with pytest.raises(UpstreamUnavailableError):
                await cache.fetch(different)
    finally:
        await redis_client.delete(key)


def make_query(
    *,
    latitude: str = "39.9334",
    longitude: str = "32.8597",
    tilt_deg: str = "30",
    azimuth_deg: str = "180",
    system_loss_percent: str = "14",
) -> SpecificYieldQuery:
    return SpecificYieldQuery(
        coordinates=Coordinates(Decimal(latitude), Decimal(longitude)),
        tilt_deg=Decimal(tilt_deg),
        azimuth_deg=Decimal(azimuth_deg),
        system_loss_percent=Decimal(system_loss_percent),
    )


QUERIES = [
    make_query(),
    make_query(latitude="39.9335"),  # rounds up to 39.934
    make_query(latitude="39.93349"),  # rounds to 39.933, as the default does
    make_query(longitude="32.85970"),
    make_query(longitude="32.8595"),  # half-up to 32.860
    make_query(longitude="32.8604"),
    make_query(tilt_deg="30.0"),
    make_query(tilt_deg="31"),
    make_query(azimuth_deg="180.0"),
    make_query(azimuth_deg="181"),
    make_query(azimuth_deg="0"),
    make_query(azimuth_deg="359.5"),
    make_query(system_loss_percent="14.00"),
    make_query(system_loss_percent="12"),
]


def test_two_queries_share_a_cache_key_exactly_when_pvgis_would_receive_the_same_values() -> None:
    for first in QUERIES:
        for second in QUERIES:
            same_key = specific_yield_cache_key(first) == specific_yield_cache_key(second)
            same_request = pvgis_request(first) == pvgis_request(second)
            assert same_key is same_request, (first, second)


@pytest.mark.parametrize("query", QUERIES)
async def test_the_cache_key_holds_the_values_pvgis_is_actually_asked_for(
    query: SpecificYieldQuery,
) -> None:
    seen: list[httpx.Request] = []
    body = (Path(__file__).parent / "recordings" / "pvgis_pvcalc_ankara.json").read_text(
        encoding="utf-8"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=body)

    provider = PvgisSpecificYieldProvider(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="https://pvgis.example/api/v5_3",
        timeout_seconds=5.0,
    )

    await provider.fetch(query)

    [request] = seen
    params = request.url.params
    latitude, longitude, tilt, aspect, loss = specific_yield_cache_key(query).split(":")[-5:]
    assert Decimal(latitude) == Decimal(params["lat"])
    assert Decimal(longitude) == Decimal(params["lon"])
    assert Decimal(tilt) == Decimal(params["angle"])
    assert Decimal(aspect) == Decimal(params["aspect"])
    assert Decimal(loss) == Decimal(params["loss"])


async def test_exchange_rates_are_cached_indefinitely_by_quote_date_and_currency(
    redis_client: Redis,
) -> None:
    quote_date = date(8000, 1, 1) + timedelta(days=uuid4().int % 365_000)
    key = f"sunquote:v1:exchange-rate:{quote_date}:USD"
    rate = make_exchange_rate("50.12345678901234567890123456")
    provider = FakeExchangeRateProvider(rate=rate)
    cache = CachedExchangeRateProvider(provider, redis_client)

    try:
        assert await cache.fetch(Currency.USD, quote_date) == rate
        assert provider.requests == [(Currency.USD, quote_date)]

        provider.error = UpstreamUnavailableError("TCMB", "offline")
        assert await cache.fetch(Currency.USD, quote_date) == rate
        assert await redis_client.ttl(key) == -1
        with pytest.raises(UpstreamUnavailableError):
            await cache.fetch(Currency.USD, quote_date + timedelta(days=1))
        with pytest.raises(UpstreamUnavailableError):
            await cache.fetch(Currency.EUR, quote_date)
    finally:
        await redis_client.delete(key)


async def test_a_redis_write_timeout_preserves_the_provider_result(
    caplog: pytest.LogCaptureFixture,
) -> None:
    redis = Mock(spec=Redis)
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(side_effect=RedisTimeoutError())
    provider = FakeGeocoder()

    assert await CachedGeocoder(provider, redis).geocode("Ankara") == provider.result
    assert "Redis cache write failed (TimeoutError)" in caplog.messages
