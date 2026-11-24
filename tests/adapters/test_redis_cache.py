"""Redis cache contracts. The real Redis tests use SUNQUOTE_TEST_REDIS_URL."""

import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError

from sunquote.adapters.redis_cache import (
    CachedExchangeRateProvider,
    CachedGeocoder,
    CachedSpecificYieldProvider,
)
from sunquote.domain.errors import AddressNotFoundError, UpstreamUnavailableError
from sunquote.domain.model import Coordinates
from sunquote.domain.money import Currency
from sunquote.domain.ports import SpecificYieldQuery
from tests.factories import make_exchange_rate
from tests.fakes import FakeExchangeRateProvider, FakeGeocoder, FakeSpecificYieldProvider

pytestmark = pytest.mark.anyio


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    url = os.environ.get("SUNQUOTE_TEST_REDIS_URL")
    required = os.environ.get("CI") == "true"
    if not url:
        if required:
            pytest.fail("SUNQUOTE_TEST_REDIS_URL is not set")
        pytest.skip("SUNQUOTE_TEST_REDIS_URL is not set")

    async with Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1) as client:
        try:
            await client.ping()
        except (OSError, RedisError) as error:
            if required:
                pytest.fail(f"the test Redis is unreachable: {error}")
            pytest.skip(f"the test Redis is unreachable: {error}")
        yield client


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
